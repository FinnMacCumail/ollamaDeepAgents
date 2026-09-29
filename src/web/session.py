"""TurnRunner: serialises turns through the single llama-server slot, tracks the queue,
supports cancellation and keeps a per-conversation usage ledger."""

import asyncio
import time
import uuid
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Any

from ..utils.logging import get_logger
from .events import TurnStats, finish, translate
from .models import ConversationUsage, StreamChunk, TurnUsage

logger = get_logger(__name__)

Sender = Callable[[StreamChunk], Awaitable[None]]

LEDGER_MAX_TURNS = 200


def sanitise_error(text: str) -> str:
    """Keep error text user-safe: no absolute paths or token-looking strings."""
    out = []
    for word in text.split():
        if word.startswith("/") or (len(word) >= 32 and word.isalnum()):
            out.append("[redacted]")
        else:
            out.append(word)
    return " ".join(out)[:500]


class TurnRunner:
    def __init__(self, agent: Any, config: Any, trace_linker: Any = None):
        self.agent = agent
        self.config = config
        self.trace_linker = trace_linker  # TraceLinker | None; url_for(run_id)
        self._lock = asyncio.Lock()
        self._waiting = 0
        self._current: asyncio.Task[None] | None = None
        self._current_owner: str | None = None
        self._user_cancel = False
        self._ledger: dict[str, list[TurnUsage]] = defaultdict(list)

    # ------------------------------------------------------------------ state
    @property
    def running(self) -> bool:
        return self._current is not None

    @property
    def queue_depth(self) -> int:
        return self._waiting

    def owns_turn(self, ws_id: str) -> bool:
        return self._current is not None and self._current_owner == ws_id

    # ------------------------------------------------------------------ ledger
    def record(self, conversation_id: str, usage: TurnUsage) -> None:
        turns = self._ledger[conversation_id]
        turns.append(usage)
        if len(turns) > LEDGER_MAX_TURNS:
            del turns[: len(turns) - LEDGER_MAX_TURNS]

    def conversation_usage(self, conversation_id: str) -> ConversationUsage:
        turns = list(self._ledger.get(conversation_id, []))
        return ConversationUsage(
            thread_id=conversation_id,
            turns=turns,
            prompt_tokens_total=sum(t.prompt_tokens_total for t in turns),
            cache_read_total=sum(t.cache_read_total for t in turns),
            completion_tokens_total=sum(t.completion_tokens_total for t in turns),
            model_calls_total=sum(t.model_calls for t in turns),
            elapsed_s_total=round(sum(t.elapsed_s for t in turns), 3),
            context_end=next((t.context_end for t in reversed(turns) if t.context_end), None),
            n_ctx=self.config.n_ctx,
        )

    # ------------------------------------------------------------------ cancel
    def cancel(self, ws_id: str) -> bool:
        """Cancel the running turn if `ws_id` owns it. Returns True when a cancel was issued."""
        if self._current is None or self._current_owner != ws_id or self._current.done():
            return False
        self._user_cancel = True
        self._current.cancel()
        return True

    # ------------------------------------------------------------------ run
    async def run(self, send: Sender, ws_id: str, conversation_id: str, text: str) -> None:
        if self._waiting >= self.config.max_queue:
            await send(
                StreamChunk(
                    type="error",
                    completed=True,
                    content="Server queue is full; try again shortly.",
                    metadata={"kind": "queue"},  # terminal for the turn, unlike "protocol"
                )
            )
            return

        # position = turns AHEAD of this one (0 = starts immediately): the running turn,
        # if any, plus everyone already waiting. Not "your slot number in the list".
        ahead = self._waiting + (1 if self._current is not None else 0)
        self._waiting += 1
        await send(StreamChunk(type="queued", metadata={"position": ahead}))
        started = time.monotonic()
        phase = {"value": "queued"}
        heartbeat = asyncio.create_task(self._heartbeat(send, started, phase))

        # Acquire explicitly so a client that disconnects while QUEUED leaves the counter
        # consistent and never goes on to occupy the slot for a dead socket.
        try:
            await self._lock.acquire()
        except asyncio.CancelledError:
            self._waiting -= 1
            heartbeat.cancel()
            raise
        self._waiting -= 1

        phase["value"] = "running"
        self._current = asyncio.current_task()
        self._current_owner = ws_id
        self._user_cancel = False
        stats = TurnStats(n_ctx=self.config.n_ctx)
        # One LangGraph root run per turn, minted here so the trace link exists up front.
        run_id = str(uuid.uuid4())
        stats.usage.run_id = run_id
        if self.trace_linker is not None:
            stats.usage.trace_url = self.trace_linker.url_for(run_id)
        turn_start = time.monotonic()
        try:
            async for mode, payload in self.agent.stream_events(
                text, conversation_id, run_id=run_id
            ):
                for chunk in translate(mode, payload, stats, self.config.tool_result_preview_chars):
                    await send(chunk)
            await send(finish(stats, time.monotonic() - turn_start, conversation_id))
        except asyncio.CancelledError:
            stats.usage.elapsed_s = round(time.monotonic() - turn_start, 3)
            if not self._user_cancel:
                raise  # shutdown: propagate
            await send(
                StreamChunk(
                    type="cancelled",
                    completed=True,
                    content="Cancelled. The model will not remember this partial answer.",
                    metadata=self._terminal_meta(stats, conversation_id),
                )
            )
        except Exception as e:  # noqa: BLE001 - surface any agent failure to the client
            logger.error("Turn failed", error=str(e), conversation_id=conversation_id[:8])
            stats.usage.elapsed_s = round(time.monotonic() - turn_start, 3)
            await send(
                StreamChunk(
                    type="error",
                    completed=True,
                    content=sanitise_error(str(e)),
                    metadata={"kind": "agent", **self._terminal_meta(stats, conversation_id)},
                )
            )
        finally:
            self.record(conversation_id, stats.usage)
            self._current = None
            self._current_owner = None
            self._lock.release()
            heartbeat.cancel()

    @staticmethod
    def _terminal_meta(stats: TurnStats, conversation_id: str) -> dict[str, Any]:
        """Same metadata keys as a `done` chunk, so the UI footer renders all terminal types."""
        return {
            "elapsed_s": stats.usage.elapsed_s,
            "tool_calls": stats.tool_calls,
            "model_calls": stats.usage.model_calls,
            "finish_reason": stats.finish_reason,
            "thread_id": conversation_id,
            "chars": stats.text_chars,
            "run_id": stats.usage.run_id,
            "trace_url": stats.usage.trace_url,
            "usage": stats.usage.model_dump(),
        }

    async def _heartbeat(self, send: Sender, started: float, phase: dict[str, str]) -> None:
        try:
            while True:
                await asyncio.sleep(self.config.heartbeat_s)
                await send(
                    StreamChunk(
                        type="status",
                        metadata={
                            "elapsed_s": round(time.monotonic() - started, 1),
                            "phase": phase["value"],
                        },
                    )
                )
        except asyncio.CancelledError:
            pass
        except Exception:  # noqa: BLE001 - a dead socket must not kill the turn
            pass
