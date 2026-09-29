"""Pydantic models for the web chat wire protocol.

StreamChunk keeps the {type, content, completed, metadata} shape of the claude-agentic-sdk
chatbox so its frontend composable ports with minimal edits.
"""

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

ChunkType = Literal[
    "connected",
    "resumed",
    "queued",
    "status",
    "text",
    "tool_use",
    "tool_result",
    "usage",
    "context_compacted",
    "done",
    "error",
    "cancelled",
    "reset_complete",
]


class StreamChunk(BaseModel):
    """Server -> client message."""

    type: ChunkType
    content: str = ""
    completed: bool = False
    metadata: dict[str, Any] | None = None


class ClientMessage(BaseModel):
    """Client -> server message. `message` is kept for wire-compat with the claude CLI."""

    type: Literal["message", "cancel", "new_conversation", "resume"] = "message"
    message: str | None = None
    conversation_id: str | None = None

    @field_validator("message")
    @classmethod
    def strip_message(cls, v: str | None) -> str | None:
        return v.strip() if v is not None else v

    @field_validator("conversation_id")
    @classmethod
    def validate_conversation_id(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if not v or len(v) > 128 or not all(c.isalnum() or c in "-_" for c in v):
            raise ValueError("conversation_id must be 1-128 chars of [A-Za-z0-9_-]")
        return v


class HistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class HealthResponse(BaseModel):
    status: Literal["healthy", "degraded", "unhealthy"]
    service: str = "netbox-web-chat"
    agent_ready: bool
    llama_ok: bool | None


class StatusResponse(BaseModel):
    model: str
    backend: str
    n_ctx: int | None
    compaction_trigger_tokens: int | None
    slot_busy: bool | None
    prompt_cache_tokens: int | None
    turn_running: bool
    queue_depth: int
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ModelInfo(BaseModel):
    id: str
    provider: str
    available: bool = True


class CallUsage(BaseModel):
    """One model call, from AIMessageChunk.usage_metadata plus llama.cpp timings when present."""

    call_index: int
    input_tokens: int
    output_tokens: int
    cache_read: int = 0
    prefill_tps: float | None = None
    decode_tps: float | None = None
    prompt_ms: float | None = None
    predicted_ms: float | None = None


class TurnUsage(BaseModel):
    """Per-turn roll-up; sent in `done` and kept in the per-thread ledger."""

    calls: list[CallUsage] = Field(default_factory=list)
    model_calls: int = 0
    prompt_tokens_total: int = 0
    cache_read_total: int = 0
    completion_tokens_total: int = 0
    context_start: int | None = None
    context_end: int | None = None
    context_peak: int = 0
    compacted: bool = False
    elapsed_s: float = 0.0
    run_id: str | None = None  # LangGraph root run id for this turn
    trace_url: str | None = None  # LangSmith link, when tracing is on

    def add_call(self, call: CallUsage) -> None:
        self.calls.append(call)
        self.model_calls += 1
        self.prompt_tokens_total += call.input_tokens
        self.cache_read_total += call.cache_read
        self.completion_tokens_total += call.output_tokens
        if self.context_start is None:
            self.context_start = call.input_tokens
        self.context_end = call.input_tokens
        self.context_peak = max(self.context_peak, call.input_tokens)


class TraceRef(BaseModel):
    """One LangSmith root run of a thread (GET /conversations/{id}/traces)."""

    run_id: str
    start_time: str
    end_time: str | None
    status: str | None
    trace_url: str


class ConversationUsage(BaseModel):
    """GET /conversations/{id}/usage - cumulative over a thread's turns (process lifetime)."""

    thread_id: str
    turns: list[TurnUsage] = Field(default_factory=list)
    prompt_tokens_total: int = 0
    cache_read_total: int = 0
    completion_tokens_total: int = 0
    model_calls_total: int = 0
    elapsed_s_total: float = 0.0
    context_end: int | None = None
    n_ctx: int | None = None
