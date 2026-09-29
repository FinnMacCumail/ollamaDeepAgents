/**
 * TypeScript type definitions for the NetBox web chat frontend.
 * Wire shapes mirror src/web/models.py (snake_case on the wire, camelCase in app state).
 */

/** Result status of one NetBox tool call, derived from the ToolMessage prefix on the server. */
export type ToolCallStatus = 'pending' | 'ok' | 'validation_error' | 'api_error'

/** One tool call issued by the model during a turn. */
export interface ToolCall {
  callId: string
  name: string
  args: Record<string, unknown>
  status: ToolCallStatus
  preview?: string
  truncated?: boolean
}

/** Server-reported usage for one model call (llama.cpp usage + timings). */
export interface CallUsage {
  callIndex: number
  inputTokens: number
  outputTokens: number
  cacheRead: number
  prefillTps?: number | null
  decodeTps?: number | null
  promptMs?: number | null
  predictedMs?: number | null
}

/** Per-turn roll-up (Python TurnUsage). */
export interface TurnUsage {
  calls: CallUsage[]
  modelCalls: number
  promptTokensTotal: number
  cacheReadTotal: number
  completionTokensTotal: number
  contextStart?: number | null
  contextEnd?: number | null
  contextPeak: number
  compacted: boolean
  elapsedS: number
  runId?: string | null
  traceUrl?: string | null
}

/** Metadata attached to a finished assistant message. */
export interface TurnMeta {
  elapsedS: number
  toolCalls: number
  modelCalls: number
  finishReason?: string | null
  chars: number
  usage: TurnUsage
  cancelled?: boolean
  /** LangGraph root run id of this turn (server-minted). */
  runId?: string | null
  /** LangSmith trace link for this turn; null when tracing is off. */
  traceUrl?: string | null
}

/**
 * A transcript entry. `kind` is undefined for ordinary messages,
 * 'compaction' for a context-compacted divider, 'notice' for system notices.
 */
export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  timestamp: string
  kind?: 'compaction' | 'notice'
  toolCalls?: ToolCall[]
  meta?: TurnMeta
  compaction?: { beforeTokens: number; afterTokens: number }
}

/** Every chunk type the backend can send (src/web/models.py ChunkType). */
export type ChunkType =
  | 'connected'
  | 'resumed'
  | 'queued'
  | 'status'
  | 'text'
  | 'tool_use'
  | 'tool_result'
  | 'usage'
  | 'context_compacted'
  | 'done'
  | 'error'
  | 'cancelled'
  | 'reset_complete'

/** Server -> client chunk. metadata keys are snake_case exactly as sent. */
export interface StreamChunk {
  type: ChunkType
  content: string
  completed: boolean
  metadata?: Record<string, any> | null
}

/** Client -> server message. */
export interface WebSocketMessage {
  type: 'message' | 'cancel' | 'new_conversation' | 'resume'
  message?: string
  conversation_id?: string
}

/** WebSocket connection state. */
export interface ConnectionState {
  connected: boolean
  connecting: boolean
  error: string | null
  reconnectAttempts: number
}

/** GET /status response (snake_case on the wire). */
export interface ServerStatusWire {
  model: string
  backend: string
  n_ctx: number | null
  compaction_trigger_tokens: number | null
  slot_busy: boolean | null
  prompt_cache_tokens: number | null
  turn_running: boolean
  queue_depth: number
  generated_at: string
}

/** GET /status mapped to app state. */
export interface ServerStatus {
  model: string
  backend: string
  nCtx: number | null
  compactionTriggerTokens: number | null
  slotBusy: boolean | null
  promptCacheTokens: number | null
  turnRunning: boolean
  queueDepth: number
  generatedAt: string
}

/** GET /health response. */
export interface HealthResponse {
  status: 'healthy' | 'degraded' | 'unhealthy'
  service: string
  agent_ready: boolean
  llama_ok: boolean
}

/** Python TurnUsage.model_dump() as it appears on the wire. */
/** One LangSmith root run of a thread (GET /conversations/{id}/traces). */
export interface TraceRefWire {
  run_id: string
  start_time: string
  end_time: string | null
  status: string | null
  trace_url: string
}

export interface TurnUsageWire {
  calls: Array<{
    call_index: number
    input_tokens: number
    output_tokens: number
    cache_read: number
    prefill_tps?: number | null
    decode_tps?: number | null
    prompt_ms?: number | null
    predicted_ms?: number | null
  }>
  model_calls: number
  prompt_tokens_total: number
  cache_read_total: number
  completion_tokens_total: number
  run_id?: string | null
  trace_url?: string | null
  context_start?: number | null
  context_end?: number | null
  context_peak: number
  compacted: boolean
  elapsed_s: number
}

/** GET /conversations/{id}/usage response. */
export interface ConversationUsageWire {
  thread_id: string
  turns: TurnUsageWire[]
  prompt_tokens_total: number
  cache_read_total: number
  completion_tokens_total: number
  model_calls_total: number
  elapsed_s_total: number
  context_end: number | null
  n_ctx: number | null
}

/** Cumulative usage for one conversation in app state. */
export interface ConversationUsage {
  promptTokensTotal: number
  cacheReadTotal: number
  completionTokensTotal: number
  modelCallsTotal: number
  elapsedSTotal: number
  contextEnd: number | null
  turns: number
}

/** Convert a wire TurnUsage to app state. */
export const turnUsageFromWire = (w: TurnUsageWire | null | undefined): TurnUsage => ({
  calls: (w?.calls ?? []).map(c => ({
    callIndex: c.call_index,
    inputTokens: c.input_tokens,
    outputTokens: c.output_tokens,
    cacheRead: c.cache_read ?? 0,
    prefillTps: c.prefill_tps ?? null,
    decodeTps: c.decode_tps ?? null,
    promptMs: c.prompt_ms ?? null,
    predictedMs: c.predicted_ms ?? null
  })),
  modelCalls: w?.model_calls ?? 0,
  promptTokensTotal: w?.prompt_tokens_total ?? 0,
  cacheReadTotal: w?.cache_read_total ?? 0,
  completionTokensTotal: w?.completion_tokens_total ?? 0,
  contextStart: w?.context_start ?? null,
  contextEnd: w?.context_end ?? null,
  runId: w?.run_id ?? null,
  traceUrl: w?.trace_url ?? null,
  contextPeak: w?.context_peak ?? 0,
  compacted: w?.compacted ?? false,
  elapsedS: w?.elapsed_s ?? 0
})

/** Empty TurnUsage for the in-flight turn. */
export const emptyTurnUsage = (): TurnUsage => ({
  calls: [],
  modelCalls: 0,
  promptTokensTotal: 0,
  cacheReadTotal: 0,
  completionTokensTotal: 0,
  contextStart: null,
  contextEnd: null,
  contextPeak: 0,
  compacted: false,
  elapsedS: 0,
  runId: null,
  traceUrl: null
})
