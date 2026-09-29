"""Translate LangGraph stream events into wire chunks.

Pure functions, no I/O: fed by NetBoxDeepAgent.stream_events() which yields
(mode, payload) tuples from agent.astream(stream_mode=["messages", "updates"]).

- "messages": payload is (message_chunk, metadata). AIMessageChunk carries token deltas,
  finish_reason (on the last content chunk) and usage_metadata (on a trailing empty chunk).
- "updates":  payload is {node_name: state_delta}. The "model" node emits AIMessages with
  tool_calls; the "tools" node emits ToolMessages. Middleware hook nodes are dotted
  ("<Name>.before_model") and are ignored except for the summarizer, which flags compaction.
"""

from dataclasses import dataclass, field
from typing import Any

from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage

from .models import CallUsage, StreamChunk, TurnUsage

VALIDATION_PREFIX = "TOOL_VALIDATION_ERROR:"
API_ERROR_PREFIX = "TOOL_API_ERROR:"
# A drop of more than 20% in resident context between consecutive calls = compaction.
COMPACTION_DROP_RATIO = 0.8
LENGTH_ERROR_TEXT = (
    "The model used its whole output budget on reasoning and produced no answer. "
    "Try again, or start a new conversation. "
    "(LLAMACPP_REASONING_EFFORT / LLAMACPP_MAX_TOKENS)"
)


@dataclass
class TurnStats:
    text_chars: int = 0
    tool_calls: int = 0
    finish_reason: str | None = None
    usage: TurnUsage = field(default_factory=TurnUsage)
    n_ctx: int = 131072
    compaction_emitted: bool = False
    compaction_pending: bool = False


def content_text(content: Any) -> str:
    """Flatten str-or-blocks message content to text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
        return "".join(parts)
    return str(content) if content else ""


def _tool_status(text: str) -> str:
    if text.startswith(VALIDATION_PREFIX):
        return "validation_error"
    if text.startswith(API_ERROR_PREFIX):
        return "api_error"
    return "ok"


def _usage_chunks(msg: AIMessageChunk, stats: TurnStats) -> list[StreamChunk]:
    um = msg.usage_metadata
    if not um:
        return []
    timings = (msg.response_metadata or {}).get("timings") or {}
    details = um.get("input_token_details") or {}
    call = CallUsage(
        call_index=len(stats.usage.calls) + 1,
        input_tokens=int(um.get("input_tokens", 0)),
        output_tokens=int(um.get("output_tokens", 0)),
        cache_read=int(details.get("cache_read", 0) or 0),
        prefill_tps=timings.get("prompt_per_second"),
        decode_tps=timings.get("predicted_per_second"),
        prompt_ms=timings.get("prompt_ms"),
        predicted_ms=timings.get("predicted_ms"),
    )
    prev = stats.usage.calls[-1].input_tokens if stats.usage.calls else None
    stats.usage.add_call(call)

    chunks: list[StreamChunk] = []
    dropped = prev is not None and call.input_tokens < COMPACTION_DROP_RATIO * prev
    if dropped and not stats.compaction_emitted:
        stats.compaction_emitted = True
        stats.usage.compacted = True
        chunks.append(
            StreamChunk(
                type="context_compacted",
                content=f"Context compacted: {prev:,} -> {call.input_tokens:,} tokens",
                metadata={"before_tokens": prev, "after_tokens": call.input_tokens},
            )
        )
    stats.compaction_pending = False

    pct = round(100.0 * call.input_tokens / stats.n_ctx, 1) if stats.n_ctx else None
    meta = call.model_dump()
    meta.update({"n_ctx": stats.n_ctx, "context_pct": pct})
    chunks.append(StreamChunk(type="usage", metadata=meta))
    return chunks


def translate(mode: str, payload: Any, stats: TurnStats, preview_chars: int) -> list[StreamChunk]:
    """Map one LangGraph stream item to zero or more wire chunks, updating stats."""
    chunks: list[StreamChunk] = []

    if mode == "messages":
        if not isinstance(payload, tuple) or len(payload) != 2:
            return chunks
        msg, _meta = payload
        if isinstance(msg, AIMessageChunk):
            delta = content_text(msg.content)
            if delta:
                stats.text_chars += len(delta)
                chunks.append(StreamChunk(type="text", content=delta))
            fr = (msg.response_metadata or {}).get("finish_reason")
            if fr:
                stats.finish_reason = fr
            chunks.extend(_usage_chunks(msg, stats))
        # ToolMessages also arrive here; handled once via "updates" to avoid duplicates.
        return chunks

    if mode == "updates" and isinstance(payload, dict):
        for node, delta in payload.items():
            if not isinstance(node, str) or not isinstance(delta, dict):
                continue
            if node.startswith("SummarizationMiddleware"):
                stats.compaction_pending = True
                continue
            if "." in node:
                continue
            for m in delta.get("messages", []) or []:
                if isinstance(m, AIMessage) and not isinstance(m, AIMessageChunk) and m.tool_calls:
                    for tc in m.tool_calls:
                        stats.tool_calls += 1
                        chunks.append(
                            StreamChunk(
                                type="tool_use",
                                content=tc.get("name", ""),
                                metadata={
                                    "call_id": tc.get("id"),
                                    "name": tc.get("name"),
                                    "args": tc.get("args") or {},
                                },
                            )
                        )
                elif isinstance(m, ToolMessage):
                    text = content_text(m.content)
                    chunks.append(
                        StreamChunk(
                            type="tool_result",
                            content=text[:preview_chars],
                            metadata={
                                "call_id": m.tool_call_id,
                                "name": m.name,
                                "status": _tool_status(text),
                                "truncated": len(text) > preview_chars,
                            },
                        )
                    )
    return chunks


def finish(stats: TurnStats, elapsed_s: float, thread_id: str) -> StreamChunk:
    """Terminal chunk for a turn: `done`, or `error` when the model produced nothing."""
    stats.usage.elapsed_s = round(elapsed_s, 3)
    base_meta: dict[str, Any] = {
        "elapsed_s": round(elapsed_s, 3),
        "tool_calls": stats.tool_calls,
        "model_calls": stats.usage.model_calls,
        "finish_reason": stats.finish_reason,
        "thread_id": thread_id,
        "chars": stats.text_chars,
        "run_id": stats.usage.run_id,
        "trace_url": stats.usage.trace_url,
        "usage": stats.usage.model_dump(),
    }
    if stats.finish_reason == "length" and stats.text_chars == 0:
        base_meta["kind"] = "length"
        return StreamChunk(
            type="error", content=LENGTH_ERROR_TEXT, completed=True, metadata=base_meta
        )
    return StreamChunk(type="done", completed=True, metadata=base_meta)
