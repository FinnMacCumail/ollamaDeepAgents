/**
 * WebSocket composable for the NetBox web chat.
 *
 * MODULE-LEVEL SINGLETON: every caller shares one socket and one set of refs
 * (the claude-agentic-sdk version created a socket per caller, which opened a
 * second connection from the sidebar). Handles connection lifecycle, the
 * StreamChunk protocol from src/web/api.py, delta accumulation, tool activity,
 * per-call usage, cancellation and conversation resume.
 */

import type {
  CallUsage,
  ChatMessage,
  ConnectionState,
  StreamChunk,
  ToolCall,
  TurnMeta,
  TurnUsage,
  WebSocketMessage
} from '~/types/chat'
import { emptyTurnUsage, turnUsageFromWire } from '~/types/chat'
import { getCurrentInstance } from 'vue'

// ---- shared state (created once) -------------------------------------------

const socket = ref<WebSocket | null>(null)
const messages = ref<ChatMessage[]>([])
const connectionState = ref<ConnectionState>({
  connected: false,
  connecting: false,
  error: null,
  reconnectAttempts: 0
})

const currentAssistantMessage = ref<string>('')
const currentToolCalls = ref<ToolCall[]>([])
const currentUsage = ref<TurnUsage>(emptyTurnUsage())
const liveContextTokens = ref<number | null>(null)
const liveContextPct = ref<number | null>(null)
const isProcessing = ref(false)
const queuePosition = ref<number | null>(null)
const phase = ref<'idle' | 'queued' | 'running'>('idle')
const elapsedS = ref(0)
const serverKnowsThread = ref<boolean | null>(null)
const serverTurns = ref(0)
const serverModel = ref<string>('')
const serverBackend = ref<string>('')
const lastError = ref<string | null>(null)

/** Thread the UI is currently looking at; resumed on (re)connect. */
const activeThreadId = ref<string | null>(null)
/** Thread of the in-flight turn (may differ from activeThreadId if the user switches). */
let inFlightThreadId: string | null = null

let turnStartedAt: number | null = null
let elapsedTimer: ReturnType<typeof setInterval> | null = null
let mountedCount = 0
let manualClose = false

const MAX_RECONNECT_ATTEMPTS = 5
const RECONNECT_DELAY_MS = 2000

/** Pending newConversation() promises, resolved on reset_complete in FIFO order. */
const pendingNewConversation: Array<{ resolve: (id: string) => void; reject: (e: Error) => void }> = []

// ---- helpers ----------------------------------------------------------------

const nowIso = () => new Date().toISOString()

const startElapsedTimer = () => {
  turnStartedAt = Date.now()
  elapsedS.value = 0
  if (elapsedTimer) clearInterval(elapsedTimer)
  elapsedTimer = setInterval(() => {
    if (turnStartedAt !== null) {
      elapsedS.value = Math.round((Date.now() - turnStartedAt) / 10) / 100
    }
  }, 1000)
}

const stopElapsedTimer = () => {
  if (elapsedTimer) {
    clearInterval(elapsedTimer)
    elapsedTimer = null
  }
  turnStartedAt = null
}

const resetTurnState = () => {
  currentAssistantMessage.value = ''
  currentToolCalls.value = []
  currentUsage.value = emptyTurnUsage()
  isProcessing.value = false
  queuePosition.value = null
  phase.value = 'idle'
  inFlightThreadId = null
  stopElapsedTimer()
}

const sendRaw = (msg: WebSocketMessage): boolean => {
  if (!socket.value || socket.value.readyState !== WebSocket.OPEN) {
    connectionState.value.error = 'Not connected to server'
    return false
  }
  try {
    socket.value.send(JSON.stringify(msg))
    return true
  } catch (error) {
    console.error('Failed to send WebSocket message:', error)
    connectionState.value.error = 'Failed to send message'
    return false
  }
}

/**
 * Turn the in-flight state into a finished assistant message.
 * `overrideContent` replaces the streamed text (length error, cancelled);
 * `extraMeta` merges into the TurnMeta.
 */
/**
 * Every terminal chunk (done / error / cancelled) carries the same server-side keys;
 * prefer them over client-side counters so cancelled and failed turns are costed too.
 */
const terminalMetaFromWire = (m: Record<string, any>): Partial<TurnMeta> => ({
  elapsedS: Number(m.elapsed_s ?? m.usage?.elapsed_s ?? elapsedS.value),
  toolCalls: Number(m.tool_calls ?? currentToolCalls.value.length),
  modelCalls: Number(m.model_calls ?? currentUsage.value.modelCalls),
  finishReason: m.finish_reason ?? null,
  chars: Number(m.chars ?? currentAssistantMessage.value.length),
  usage: m.usage ? turnUsageFromWire(m.usage) : currentUsage.value,
  runId: m.run_id ?? null,
  traceUrl: m.trace_url ?? null
})

const finaliseAssistant = (meta?: Partial<TurnMeta>, overrideContent?: string) => {
  const usage: TurnUsage = meta?.usage ?? currentUsage.value
  const content = overrideContent !== undefined
    ? (currentAssistantMessage.value ? `${currentAssistantMessage.value}\n\n${overrideContent}` : overrideContent)
    : currentAssistantMessage.value

  const turnMeta: TurnMeta = {
    elapsedS: meta?.elapsedS ?? usage.elapsedS ?? elapsedS.value,
    toolCalls: meta?.toolCalls ?? currentToolCalls.value.length,
    modelCalls: meta?.modelCalls ?? usage.modelCalls,
    finishReason: meta?.finishReason ?? null,
    chars: meta?.chars ?? currentAssistantMessage.value.length,
    usage,
    cancelled: meta?.cancelled ?? false,
    runId: meta?.runId ?? usage.runId ?? null,
    traceUrl: meta?.traceUrl ?? usage.traceUrl ?? null
  }

  if (content.trim() || currentToolCalls.value.length > 0) {
    messages.value.push({
      role: 'assistant',
      content: content || '(no visible answer)',
      timestamp: nowIso(),
      toolCalls: [...currentToolCalls.value],
      meta: turnMeta
    })
  }
  if (usage.contextEnd != null) {
    liveContextTokens.value = usage.contextEnd
  }
  resetTurnState()
}

const pushNotice = (content: string) => {
  messages.value.push({ role: 'assistant', content, timestamp: nowIso(), kind: 'notice' })
}

// ---- chunk handling ---------------------------------------------------------

const handleStreamChunk = (chunk: StreamChunk) => {
  const m = chunk.metadata ?? {}

  switch (chunk.type) {
    case 'connected':
      serverModel.value = m.model ?? ''
      serverBackend.value = m.backend ?? ''
      break

    case 'resumed': {
      // A slow reply for a previously selected thread must not label the current one.
      const forThread = m.conversation_id ? String(m.conversation_id) : null
      if (forThread && activeThreadId.value && forThread !== activeThreadId.value) break
      serverKnowsThread.value = Boolean(m.known)
      serverTurns.value = Number(m.turns ?? 0)
      break
    }

    case 'queued':
      phase.value = 'queued'
      queuePosition.value = Number(m.position ?? 0)
      break

    case 'status':
      phase.value = m.phase === 'queued' ? 'queued' : 'running'
      if (typeof m.elapsed_s === 'number') elapsedS.value = m.elapsed_s
      if (m.phase === 'running') queuePosition.value = null
      break

    case 'text':
      // Deltas, never cumulative.
      phase.value = 'running'
      queuePosition.value = null
      currentAssistantMessage.value += chunk.content
      break

    case 'tool_use':
      phase.value = 'running'
      queuePosition.value = null
      currentToolCalls.value.push({
        callId: String(m.call_id ?? `call-${currentToolCalls.value.length + 1}`),
        name: String(m.name ?? chunk.content),
        args: (m.args ?? {}) as Record<string, unknown>,
        status: 'pending'
      })
      break

    case 'tool_result': {
      const tc = currentToolCalls.value.find(t => t.callId === m.call_id)
      if (tc) {
        tc.status = (m.status ?? 'ok') as ToolCall['status']
        tc.preview = chunk.content
        tc.truncated = Boolean(m.truncated)
      } else {
        currentToolCalls.value.push({
          callId: String(m.call_id ?? `result-${currentToolCalls.value.length + 1}`),
          name: String(m.name ?? 'tool'),
          args: {},
          status: (m.status ?? 'ok') as ToolCall['status'],
          preview: chunk.content,
          truncated: Boolean(m.truncated)
        })
      }
      break
    }

    case 'usage': {
      const cu: CallUsage = {
        callIndex: Number(m.call_index ?? currentUsage.value.calls.length + 1),
        inputTokens: Number(m.input_tokens ?? 0),
        outputTokens: Number(m.output_tokens ?? 0),
        cacheRead: Number(m.cache_read ?? 0),
        prefillTps: m.prefill_tps ?? null,
        decodeTps: m.decode_tps ?? null,
        promptMs: m.prompt_ms ?? null,
        predictedMs: m.predicted_ms ?? null
      }
      const u = currentUsage.value
      u.calls.push(cu)
      u.modelCalls = u.calls.length
      u.promptTokensTotal += cu.inputTokens
      u.cacheReadTotal += cu.cacheRead
      u.completionTokensTotal += cu.outputTokens
      if (u.contextStart == null) u.contextStart = cu.inputTokens
      u.contextEnd = cu.inputTokens
      u.contextPeak = Math.max(u.contextPeak, cu.inputTokens)
      liveContextTokens.value = cu.inputTokens
      liveContextPct.value = typeof m.context_pct === 'number' ? m.context_pct : null
      break
    }

    case 'context_compacted':
      currentUsage.value.compacted = true
      messages.value.push({
        role: 'assistant',
        content: chunk.content || 'Context compacted',
        timestamp: nowIso(),
        kind: 'compaction',
        compaction: {
          beforeTokens: Number(m.before_tokens ?? 0),
          afterTokens: Number(m.after_tokens ?? 0)
        }
      })
      break

    case 'done':
      finaliseAssistant(terminalMetaFromWire(m))
      break

    case 'error':
      lastError.value = chunk.content
      if (m.kind === 'length') {
        finaliseAssistant(
          { ...terminalMetaFromWire(m), finishReason: 'length' },
          `⚠️ ${chunk.content}`
        )
      } else if (m.kind === 'protocol') {
        // Protocol errors do not end a running turn (e.g. "nothing to cancel").
        pushNotice(`⚠️ ${chunk.content}`)
        // Reject a pending newConversation if the server refused it.
        if (/conversation/i.test(chunk.content) && pendingNewConversation.length) {
          pendingNewConversation.shift()?.reject(new Error(chunk.content))
        }
      } else {
        finaliseAssistant(
          { ...terminalMetaFromWire(m), finishReason: 'error' },
          `❌ Error: ${chunk.content}`
        )
      }
      break

    case 'cancelled':
      finaliseAssistant(
        { ...terminalMetaFromWire(m), cancelled: true, finishReason: 'cancelled' },
        '(cancelled — rolled back; the model will not remember this question)'
      )
      break

    case 'reset_complete': {
      const id = String(m.thread_id ?? '')
      const waiter = pendingNewConversation.shift()
      if (waiter) {
        waiter.resolve(id)
      }
      break
    }
  }
}

// ---- connection -------------------------------------------------------------

const connect = () => {
  if (connectionState.value.connecting || connectionState.value.connected) return
  const config = useRuntimeConfig()
  manualClose = false
  connectionState.value.connecting = true
  connectionState.value.error = null

  try {
    const ws = new WebSocket(config.public.wsUrl as string)
    socket.value = ws

    ws.onopen = () => {
      connectionState.value.connected = true
      connectionState.value.connecting = false
      connectionState.value.reconnectAttempts = 0
      connectionState.value.error = null
      // A reconnect mid-turn loses the stream; do not pretend it is still running.
      if (isProcessing.value) {
        finaliseAssistant({ finishReason: 'disconnected' }, '(connection lost during this turn)')
      }
      if (activeThreadId.value) {
        resume(activeThreadId.value)
      }
    }

    ws.onmessage = (event) => {
      try {
        const chunk: StreamChunk = JSON.parse(event.data)
        handleStreamChunk(chunk)
      } catch (error) {
        console.error('Failed to parse WebSocket message:', error)
        connectionState.value.error = 'Failed to parse server message'
      }
    }

    ws.onerror = (error) => {
      console.error('WebSocket error:', error)
      connectionState.value.error = 'Connection error occurred'
    }

    ws.onclose = () => {
      connectionState.value.connected = false
      connectionState.value.connecting = false
      while (pendingNewConversation.length) {
        pendingNewConversation.shift()?.reject(new Error('Disconnected'))
      }
      if (manualClose) return
      if (connectionState.value.reconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
        connectionState.value.reconnectAttempts++
        setTimeout(connect, RECONNECT_DELAY_MS)
      } else {
        connectionState.value.error = 'Maximum reconnection attempts reached'
      }
    }
  } catch (error) {
    console.error('Failed to create WebSocket:', error)
    connectionState.value.connecting = false
    connectionState.value.error = 'Failed to establish connection'
  }
}

const disconnect = () => {
  manualClose = true
  if (socket.value) {
    socket.value.close()
    socket.value = null
  }
  connectionState.value.connected = false
  connectionState.value.connecting = false
  connectionState.value.reconnectAttempts = 0
}

/** Manual reconnect from the UI: resets the attempt counter. */
const reconnect = () => {
  connectionState.value.reconnectAttempts = 0
  connectionState.value.error = null
  connect()
}

// ---- actions ----------------------------------------------------------------

/** Send a user message on a conversation (thread). */
const sendMessage = (text: string, conversationId: string): boolean => {
  const trimmed = text.trim()
  if (!trimmed || !conversationId) return false
  if (isProcessing.value) {
    connectionState.value.error = 'A turn is already running'
    return false
  }
  messages.value.push({ role: 'user', content: trimmed, timestamp: nowIso() })
  if (!sendRaw({ type: 'message', message: trimmed, conversation_id: conversationId })) {
    messages.value.pop()
    return false
  }
  lastError.value = null
  isProcessing.value = true
  phase.value = 'queued'
  inFlightThreadId = conversationId
  currentAssistantMessage.value = ''
  currentToolCalls.value = []
  currentUsage.value = emptyTurnUsage()
  startElapsedTimer()
  return true
}

/** Cancel the running turn on this connection. */
const cancel = (): boolean => {
  if (!isProcessing.value) return false
  return sendRaw({ type: 'cancel' })
}

/** Ask the server for a fresh thread id. Resolves on reset_complete. */
const newConversation = (timeoutMs = 5000): Promise<string> => {
  return new Promise<string>((resolve, reject) => {
    if (!sendRaw({ type: 'new_conversation' })) {
      reject(new Error('Not connected'))
      return
    }
    const entry = { resolve, reject }
    pendingNewConversation.push(entry)
    setTimeout(() => {
      const idx = pendingNewConversation.indexOf(entry)
      if (idx !== -1) {
        pendingNewConversation.splice(idx, 1)
        reject(new Error('Timed out waiting for reset_complete'))
      }
    }, timeoutMs)
  })
}

/** Tell the server which thread we are looking at; it answers with `resumed`. */
const resume = (conversationId: string): boolean => {
  serverKnowsThread.value = null
  return sendRaw({ type: 'resume', conversation_id: conversationId })
}

/** Set the thread the UI is viewing (resumed on reconnect) and resume it now if connected. */
const setActiveThread = (conversationId: string | null) => {
  activeThreadId.value = conversationId
  serverKnowsThread.value = null
  serverTurns.value = 0
  if (conversationId && connectionState.value.connected) {
    resume(conversationId)
  }
}

const clearMessages = () => {
  messages.value = []
  liveContextTokens.value = null
  liveContextPct.value = null
  if (!isProcessing.value) resetTurnState()
}

/** Load a stored transcript (switching conversations). */
const loadMessages = (conversationMessages: ChatMessage[]) => {
  messages.value = conversationMessages.map(msg => ({ ...msg }))
  const last = [...messages.value].reverse().find(msg => msg.meta?.usage?.contextEnd != null)
  liveContextTokens.value = last?.meta?.usage?.contextEnd ?? null
  liveContextPct.value = null
  if (!isProcessing.value) resetTurnState()
}

// ---- derived ----------------------------------------------------------------

const partialMessage = computed(() => currentAssistantMessage.value)

/** In-flight assistant bubble, present once there is any text or tool activity. */
const partialEntry = computed<ChatMessage | null>(() => {
  if (!isProcessing.value) return null
  if (!currentAssistantMessage.value && currentToolCalls.value.length === 0) return null
  return {
    role: 'assistant',
    content: currentAssistantMessage.value,
    timestamp: nowIso(),
    toolCalls: currentToolCalls.value,
    meta: {
      elapsedS: elapsedS.value,
      toolCalls: currentToolCalls.value.length,
      modelCalls: currentUsage.value.modelCalls,
      finishReason: null,
      chars: currentAssistantMessage.value.length,
      usage: currentUsage.value
    }
  }
})

const allMessages = computed<ChatMessage[]>(() => {
  const all = [...messages.value]
  if (partialEntry.value) all.push(partialEntry.value)
  return all
})

// ---- composable -------------------------------------------------------------

export const useChatSocket = () => {
  // Lifecycle hooks only make sense inside a component's setup(). The composable is also
  // called from plain functions (e.g. useConversations.createConversation) to reach the
  // shared singleton state; registering hooks there would warn and do nothing useful.
  if (getCurrentInstance()) {
    onMounted(() => {
      mountedCount++
      connect()
    })

    onUnmounted(() => {
      mountedCount--
      if (mountedCount <= 0) {
        mountedCount = 0
        disconnect()
      }
    })
  }

  return {
    // state
    messages,
    allMessages,
    partialMessage,
    partialEntry,
    connectionState,
    isProcessing,
    currentAssistantMessage,
    currentToolCalls,
    currentUsage,
    liveContextTokens,
    liveContextPct,
    queuePosition,
    phase,
    elapsedS,
    serverKnowsThread,
    serverTurns,
    serverModel,
    serverBackend,
    lastError,
    activeThreadId,
    inFlightThreadId: () => inFlightThreadId,

    // actions
    connect,
    reconnect,
    disconnect,
    sendMessage,
    cancel,
    newConversation,
    resume,
    setActiveThread,
    loadMessages,
    clearMessages
  }
}
