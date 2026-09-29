"""FastAPI app: one long-lived NetBoxDeepAgent, a WebSocket chat endpoint, status routes.

Structure mirrors claude-agentic-sdk/backend/api.py (lifespan, CORS, /health, /ws/chat).
"""

import asyncio
import contextlib
import os
import uuid
from collections.abc import AsyncIterator
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError

from ..utils.logging import get_logger, setup_logging
from .config import WebConfig, load_web_config
from .llama_status import probe
from .models import (
    ClientMessage,
    ConversationUsage,
    HealthResponse,
    HistoryMessage,
    ModelInfo,
    StatusResponse,
    StreamChunk,
    TraceRef,
)
from .session import TurnRunner
from .tracing import list_thread_runs, resolve_trace_linker

logger = get_logger(__name__)

COMPACTION_FRACTION = 0.85  # DeepAgents compute_summarization_defaults() fraction trigger


async def _build_agent(web_config: WebConfig, netbox_config: Any) -> Any:
    """Create the agent. Split out so tests can patch it."""
    from ..agents.netbox_agent import create_netbox_agent

    return await create_netbox_agent(
        netbox_config=netbox_config,
        model_name=web_config.model_name,
        backend=web_config.backend,
    )


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    setup_logging(os.getenv("LOG_LEVEL", "INFO"))
    web_config, netbox_config = load_web_config()
    app.state.web_config = web_config

    # The server's real window wins over the env default when reachable.
    if web_config.backend == "llamacpp":
        status = await probe(web_config.llama_base_url)
        if status.get("n_ctx"):
            web_config.n_ctx = int(status["n_ctx"])

    logger.info(
        "Starting web chat",
        backend=web_config.backend,
        model=web_config.model_name,
        port=web_config.port,
    )
    agent = await _build_agent(web_config, netbox_config)
    app.state.agent = agent
    # LangSmith trace links (optional): resolve ids off the event loop; None when tracing is off.
    trace_linker = await asyncio.to_thread(resolve_trace_linker)
    app.state.runner = TurnRunner(agent, web_config, trace_linker=trace_linker)
    try:
        yield
    finally:
        await agent.cleanup()
        logger.info("Web chat stopped")


def create_app() -> FastAPI:
    app = FastAPI(title="NetBox Web Chat", version="0.1.0", lifespan=lifespan)

    # CORS comes from config (the claude app parsed CORS_ORIGINS but hardcoded the list).
    origins = [
        o.strip()
        for o in os.getenv("WEB_CORS_ORIGINS", "http://localhost:3010,http://127.0.0.1:3010").split(
            ","
        )
        if o.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        cfg: WebConfig = app.state.web_config
        agent_ready = getattr(app.state, "agent", None) is not None and (
            getattr(app.state.agent, "agent", None) is not None
        )
        llama_ok: bool | None = None
        if cfg.backend == "llamacpp":
            llama_ok = bool((await probe(cfg.llama_base_url)).get("ok"))
        if not agent_ready:
            status = "unhealthy"
        elif llama_ok is False:
            status = "degraded"
        else:
            status = "healthy"
        return HealthResponse(status=status, agent_ready=agent_ready, llama_ok=llama_ok)  # type: ignore[arg-type]

    @app.get("/status", response_model=StatusResponse)
    async def status() -> StatusResponse:
        cfg: WebConfig = app.state.web_config
        runner: TurnRunner = app.state.runner
        n_ctx: int | None = cfg.n_ctx
        slot_busy = None
        cache_tokens = None
        if cfg.backend == "llamacpp":
            p = await probe(cfg.llama_base_url)
            if p.get("n_ctx"):
                n_ctx = int(p["n_ctx"])
            slot_busy = p.get("slot_busy")
            cache_tokens = p.get("prompt_cache_tokens")
        return StatusResponse(
            model=cfg.model_name,
            backend=cfg.backend,
            n_ctx=n_ctx,
            compaction_trigger_tokens=int(COMPACTION_FRACTION * n_ctx) if n_ctx else None,
            slot_busy=slot_busy,
            prompt_cache_tokens=cache_tokens,
            turn_running=runner.running,
            queue_depth=runner.queue_depth,
        )

    @app.get("/models", response_model=list[ModelInfo])
    async def models() -> list[ModelInfo]:
        cfg: WebConfig = app.state.web_config
        return [ModelInfo(id=cfg.model_name, provider=cfg.backend, available=True)]

    @app.get("/conversations/{conversation_id}/messages", response_model=list[HistoryMessage])
    async def conversation_messages(conversation_id: str) -> list[HistoryMessage]:
        history = await app.state.agent.get_history(conversation_id)
        if not history:
            raise HTTPException(status_code=404, detail="Unknown or empty conversation")
        return [HistoryMessage(**m) for m in history]

    @app.get("/conversations/{conversation_id}/usage", response_model=ConversationUsage)
    async def conversation_usage(conversation_id: str) -> ConversationUsage:
        runner: TurnRunner = app.state.runner
        return runner.conversation_usage(conversation_id)

    @app.get("/conversations/{conversation_id}/traces", response_model=list[TraceRef])
    async def conversation_traces(conversation_id: str) -> list[TraceRef]:
        """LangSmith root runs of this thread, oldest first; [] when tracing is off.

        Lets the UI backfill trace links on turns that predate minted run ids. Served
        from LangSmith, so it also works for threads the backend no longer remembers.
        """
        runner: TurnRunner = app.state.runner
        if runner.trace_linker is None:
            return []
        try:
            ClientMessage.validate_conversation_id(conversation_id)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e)) from e
        try:
            rows = await asyncio.to_thread(list_thread_runs, runner.trace_linker, conversation_id)
        except Exception as e:  # noqa: BLE001 - LangSmith is optional; never break the UI
            logger.warning("Trace lookup failed", error=str(e))
            raise HTTPException(status_code=502, detail="LangSmith lookup failed") from e
        return [TraceRef(**r) for r in rows]

    @app.websocket("/ws/chat")
    async def ws_chat(ws: WebSocket) -> None:
        await ws.accept()
        cfg: WebConfig = app.state.web_config
        runner: TurnRunner = app.state.runner
        agent = app.state.agent
        ws_id = uuid.uuid4().hex
        turn: asyncio.Task[None] | None = None
        closed = False

        async def send(chunk: StreamChunk) -> None:
            nonlocal closed
            if closed:
                return
            try:
                await ws.send_json(chunk.model_dump(mode="json"))
            except (WebSocketDisconnect, RuntimeError):
                closed = True

        await send(
            StreamChunk(
                type="connected",
                content="Connected to NetBox web chat",
                metadata={"model": cfg.model_name, "backend": cfg.backend, "n_ctx": cfg.n_ctx},
            )
        )

        async def protocol_error(text: str) -> None:
            await send(
                StreamChunk(
                    type="error", completed=True, content=text, metadata={"kind": "protocol"}
                )
            )

        try:
            while True:
                raw = await ws.receive_text()
                try:
                    msg = ClientMessage.model_validate_json(raw)
                except ValidationError:
                    await protocol_error("Invalid message")
                    continue

                if msg.type == "resume":
                    turns = 0
                    if msg.conversation_id:
                        turns = sum(
                            1
                            for m in await agent.get_history(msg.conversation_id)
                            if m["role"] == "user"
                        )
                    await send(
                        StreamChunk(
                            type="resumed",
                            metadata={"known": turns > 0, "turns": turns},
                        )
                    )
                elif msg.type == "new_conversation":
                    await send(
                        StreamChunk(type="reset_complete", metadata={"thread_id": uuid.uuid4().hex})
                    )
                elif msg.type == "cancel":
                    if not runner.cancel(ws_id):
                        await protocol_error("Nothing to cancel")
                else:
                    if turn is not None and not turn.done():
                        await protocol_error("A turn is already running on this connection")
                        continue
                    if not msg.message or not msg.conversation_id:
                        await protocol_error("message and conversation_id are required")
                        continue
                    turn = asyncio.create_task(
                        runner.run(send, ws_id, msg.conversation_id, msg.message)
                    )
        except WebSocketDisconnect:
            closed = True
            logger.info("WebSocket disconnected", ws_id=ws_id[:8])
        finally:
            closed = True
            if turn is not None and not turn.done():
                # Owner of the running turn: user-style cancel frees the slot and records usage.
                # Still queued: plain task cancel so it never runs for a dead socket.
                if not runner.cancel(ws_id):
                    turn.cancel()
            if turn is not None:
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await turn

    return app


app = create_app()
