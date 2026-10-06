/**
 * Composable for managing chat conversations with localStorage persistence.
 *
 * Shared state (singleton pattern): all components that call useConversations()
 * share the same refs. A conversation's id IS the server-side LangGraph thread_id:
 * createConversation() asks the backend for one (new_conversation -> reset_complete)
 * and falls back to a client-generated hex id when the socket is down (the backend
 * accepts any string as a thread id).
 */
import type { ChatMessage, ConversationUsage, ConversationUsageWire, TraceRefWire } from '~/types/chat'

export interface Conversation {
  id: string
  title: string
  messages: ChatMessage[]
  createdAt: string
  updatedAt: string
  usage: ConversationUsage
}

const STORAGE_KEY = 'netbox-web-chat-conversations'
const MAX_TITLE_LENGTH = 60

const emptyUsage = (): ConversationUsage => ({
  promptTokensTotal: 0,
  cacheReadTotal: 0,
  completionTokensTotal: 0,
  modelCallsTotal: 0,
  elapsedSTotal: 0,
  contextEnd: null,
  turns: 0
})

/** Recompute cumulative usage from the messages' TurnMeta (single source of truth). */
export const usageFromMessages = (messages: ChatMessage[]): ConversationUsage => {
  const u = emptyUsage()
  for (const msg of messages) {
    const tu = msg.meta?.usage
    if (!tu || msg.kind) continue
    u.turns += 1
    u.promptTokensTotal += tu.promptTokensTotal
    u.cacheReadTotal += tu.cacheReadTotal
    u.completionTokensTotal += tu.completionTokensTotal
    u.modelCallsTotal += tu.modelCalls
    u.elapsedSTotal += tu.elapsedS
    if (tu.contextEnd != null) u.contextEnd = tu.contextEnd
  }
  return u
}

const generateTitle = (messages: ChatMessage[]): string => {
  const firstUserMessage = messages.find(m => m.role === 'user' && !m.kind)
  if (!firstUserMessage) return 'New Conversation'
  const content = firstUserMessage.content.trim()
  if (content.length <= MAX_TITLE_LENGTH) return content
  return content.substring(0, MAX_TITLE_LENGTH - 3) + '...'
}

/** Client-side fallback thread id: 32 hex chars, same shape as uuid4().hex on the server. */
const generateClientId = (): string => {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID().replace(/-/g, '')
  }
  return `${Date.now().toString(16)}${Math.random().toString(16).slice(2)}`.padEnd(32, '0').slice(0, 32)
}

// SHARED STATE - created once at module level
const conversations = ref<Conversation[]>([])
const activeConversationId = ref<string | null>(null)
let isInitialized = false

export const useConversations = () => {
  const loadConversations = () => {
    const stored = getItem<Conversation[]>(STORAGE_KEY, [])
    conversations.value = stored.map(c => ({
      ...c,
      messages: c.messages ?? [],
      usage: c.usage ?? usageFromMessages(c.messages ?? [])
    }))
    conversations.value.sort((a, b) =>
      new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime()
    )
  }

  const saveConversations = () => {
    setItem(STORAGE_KEY, conversations.value)
  }

  const activeConversation = computed(() => {
    if (!activeConversationId.value) return null
    return conversations.value.find(c => c.id === activeConversationId.value) || null
  })

  /** Insert a conversation with a known id (used by both create paths). */
  const addConversation = (id: string): Conversation => {
    const now = new Date().toISOString()
    const conversation: Conversation = {
      id,
      title: 'New Conversation',
      messages: [],
      createdAt: now,
      updatedAt: now,
      usage: emptyUsage()
    }
    conversations.value.unshift(conversation)
    activeConversationId.value = conversation.id
    saveConversations()
    return conversation
  }

  /**
   * Create a new conversation. Asks the server for the thread id when the
   * socket is connected; otherwise generates one locally.
   */
  const createConversation = async (): Promise<Conversation> => {
    const { connectionState, newConversation } = useChatSocket()
    let id: string
    if (connectionState.value.connected) {
      try {
        id = await newConversation()
      } catch (error) {
        console.warn('newConversation failed, using client id:', error)
        id = generateClientId()
      }
    } else {
      id = generateClientId()
    }
    if (!id) id = generateClientId()
    return addConversation(id)
  }

  /** Synchronous variant for first-mount bootstrap (no socket yet). */
  const createConversationLocal = (): Conversation => addConversation(generateClientId())

  const updateConversation = (conversationId: string, messages: ChatMessage[]) => {
    const conversation = conversations.value.find(c => c.id === conversationId)
    if (!conversation) {
      console.warn('updateConversation: conversation not found:', conversationId)
      return
    }
    conversation.messages = messages
    conversation.updatedAt = new Date().toISOString()
    conversation.usage = usageFromMessages(messages)

    if (conversation.title === 'New Conversation' && messages.length > 0) {
      conversation.title = generateTitle(messages)
    }

    const index = conversations.value.findIndex(c => c.id === conversationId)
    if (index > 0) {
      conversations.value.splice(index, 1)
      conversations.value.unshift(conversation)
    }
    saveConversations()
  }

  /** Prefer the server ledger when it knows more turns than we do. */
  const applyServerUsage = (conversationId: string, wire: ConversationUsageWire) => {
    const conversation = conversations.value.find(c => c.id === conversationId)
    if (!conversation) return
    if ((wire.turns?.length ?? 0) > conversation.usage.turns) {
      conversation.usage = {
        promptTokensTotal: wire.prompt_tokens_total,
        cacheReadTotal: wire.cache_read_total,
        completionTokensTotal: wire.completion_tokens_total,
        modelCallsTotal: wire.model_calls_total,
        elapsedSTotal: wire.elapsed_s_total,
        contextEnd: wire.context_end,
        turns: wire.turns.length
      }
      saveConversations()
    }
  }

  /** Fetch the server ledger for a thread the server says it knows. */
  const syncServerUsage = async (conversationId: string) => {
    const config = useRuntimeConfig()
    try {
      const wire = await $fetch<ConversationUsageWire>(
        `${config.public.apiUrl}/conversations/${conversationId}/usage`
      )
      applyServerUsage(conversationId, wire)
    } catch (error) {
      console.warn('Could not fetch server usage:', error)
    }
  }

  /**
   * Backfill LangSmith trace links on turns that have none (they predate minted run ids,
   * or ran in another client). The server lists the thread's root runs; each assistant
   * turn is matched to the run whose end time is closest to the turn's finish timestamp.
   * Returns true when any message was updated.
   */
  const syncServerTraces = async (conversationId: string): Promise<boolean> => {
    const conversation = conversations.value.find(c => c.id === conversationId)
    if (!conversation) return false
    const pending = conversation.messages.filter(
      m => m.role === 'assistant' && !m.kind && m.meta && !m.meta.traceUrl
    )
    if (pending.length === 0) return false

    const config = useRuntimeConfig()
    let runs: TraceRefWire[] = []
    try {
      runs = await $fetch<TraceRefWire[]>(
        `${config.public.apiUrl}/conversations/${conversationId}/traces`
      )
    } catch (error) {
      console.warn('Could not fetch traces:', error)
      return false
    }
    if (runs.length === 0) return false

    const MAX_SKEW_MS = 5 * 60 * 1000
    const taken = new Set<string>()
    let changed = false
    for (const msg of pending) {
      const t = Date.parse(msg.timestamp)
      if (Number.isNaN(t)) continue
      let best: TraceRefWire | null = null
      let bestDiff = Infinity
      for (const run of runs) {
        if (taken.has(run.run_id) || !run.end_time) continue
        const diff = Math.abs(Date.parse(run.end_time) - t)
        if (diff < bestDiff) { best = run; bestDiff = diff }
      }
      if (best && bestDiff <= MAX_SKEW_MS && msg.meta) {
        msg.meta.traceUrl = best.trace_url
        msg.meta.runId = best.run_id
        taken.add(best.run_id)
        changed = true
      }
    }
    if (changed) saveConversations()
    return changed
  }

  const renameConversation = (conversationId: string, newTitle: string) => {
    const conversation = conversations.value.find(c => c.id === conversationId)
    if (!conversation) return false
    conversation.title = newTitle.trim() || 'Untitled Conversation'
    conversation.updatedAt = new Date().toISOString()
    saveConversations()
    return true
  }

  const deleteConversation = (conversationId: string): boolean => {
    // Also drop the server-side thread (checkpoints + ledger). Fire-and-forget: the local
    // delete must succeed even when the backend is down.
    try {
      const config = useRuntimeConfig()
      void $fetch(`${config.public.apiUrl}/conversations/${conversationId}`, { method: 'DELETE' })
        .catch((error: unknown) => console.warn('Server-side delete failed:', error))
    } catch (error) {
      console.warn('Server-side delete not attempted:', error)
    }
    const index = conversations.value.findIndex(c => c.id === conversationId)
    if (index === -1) return false
    conversations.value.splice(index, 1)
    if (activeConversationId.value === conversationId) {
      activeConversationId.value = conversations.value.length > 0
        ? conversations.value[0].id
        : null
    }
    saveConversations()
    return true
  }

  const setActiveConversation = (conversationId: string | null) => {
    if (conversationId && !conversations.value.find(c => c.id === conversationId)) {
      console.warn(`Conversation ${conversationId} not found in shared state`)
      return false
    }
    activeConversationId.value = conversationId
    return true
  }

  const startNewConversation = () => createConversation()

  const clearAllConversations = () => {
    conversations.value = []
    activeConversationId.value = null
    saveConversations()
  }

  const getConversation = (conversationId: string): Conversation | null => {
    return conversations.value.find(c => c.id === conversationId) || null
  }

  onMounted(() => {
    if (!isInitialized) {
      isInitialized = true
      loadConversations()
      if (conversations.value.length === 0) {
        createConversationLocal()
      } else {
        activeConversationId.value = conversations.value[0].id
      }
    }
  })

  return {
    conversations,
    activeConversationId,
    activeConversation,
    createConversation,
    updateConversation,
    applyServerUsage,
    syncServerUsage,
    syncServerTraces,
    renameConversation,
    deleteConversation,
    setActiveConversation,
    startNewConversation,
    clearAllConversations,
    getConversation
  }
}
