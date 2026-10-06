<template>
  <div class="app-container">
    <!-- Conversation Sidebar -->
    <ConversationSidebar
      :is-open="sidebarOpen"
      @close="sidebarOpen = false"
    />

    <!-- Main Content Area -->
    <div class="main-content">
      <!-- Header -->
      <header class="chat-header">
        <div class="flex justify-between items-center gap-4 flex-wrap md:flex-nowrap w-full">
          <div class="flex items-center gap-3 min-w-0 flex-1">
            <!-- Mobile menu button -->
            <button
              class="mobile-menu-button md:hidden"
              @click="sidebarOpen = !sidebarOpen"
              title="Toggle sidebar"
            >
              <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            </button>

            <!-- Brand -->
            <BrandLogo />
            <span class="header-divider" aria-hidden="true"></span>

            <div class="min-w-0">
              <h1 class="chat-title">{{ activeConversation?.title || 'NetBox Web Chat' }}</h1>
              <p class="chat-subtitle">
                Local model
                <span v-if="serverModel" class="font-mono">{{ serverModel }}</span>
                over read-only NetBox tools
              </p>
            </div>
          </div>

          <div class="flex items-center gap-4 flex-wrap md:flex-nowrap flex-shrink-0">
            <ContextGauge
              :context-tokens="gaugeTokens"
              :n-ctx="status?.nCtx ?? null"
              :compaction-trigger-tokens="status?.compactionTriggerTokens ?? null"
              :live="isProcessing"
            />
            <ConnectionStatus
              :connection-state="connectionState"
              @reconnect="handleReconnect"
            />
          </div>
        </div>
      </header>

      <!-- Server memory lost banner -->
      <div v-if="showMemoryLostBanner" class="memory-banner">
        <span>
          The backend has no memory of this conversation (it predates persistent storage, or its
          checkpoint database was removed). The transcript below is only in your browser; the model
          will not recall it. Continue as a new conversation.
        </span>
        <button class="banner-button" @click="handleNewConversation">New conversation</button>
        <button class="banner-dismiss" title="Dismiss" @click="bannerDismissed = true">×</button>
      </div>

      <!-- Main chat area -->
      <main class="chat-main">
        <ChatHistory
          :messages="displayMessages"
          :is-processing="isProcessing"
          :has-partial="partialEntry !== null"
          :partial-message="partialMessage"
          :phase="phase"
          :queue-position="queuePosition"
          :elapsed-s="elapsedS"
          :n-ctx="status?.nCtx ?? null"
        />

        <ChatInput
          :disabled="!connectionState.connected || !activeConversationId"
          :is-processing="isProcessing"
          @send="handleSendMessage"
          @stop="handleStop"
        />
      </main>
    </div>
  </div>
</template>

<script setup lang="ts">
// Load debug utilities (makes window.dumpConversations() available)
if (import.meta.client) {
  import('~/utils/debug')
}

const {
  messages,
  allMessages,
  partialMessage,
  partialEntry,
  connectionState,
  isProcessing,
  liveContextTokens,
  queuePosition,
  phase,
  elapsedS,
  serverKnowsThread,
  serverModel,
  reconnect,
  sendMessage,
  cancel,
  setActiveThread,
  loadMessages,
  clearMessages
} = useChatSocket()

const {
  activeConversationId,
  activeConversation,
  createConversation,
  updateConversation,
  startNewConversation,
  syncServerUsage,
  syncServerTraces,
  clearAllConversations
} = useConversations()

const { status } = useServerStatus()

const sidebarOpen = ref(false)
const isLoadingMessages = ref(false)
const bannerDismissed = ref(false)

useHead({
  title: 'RTF research — NetBox Web Chat',
  meta: [
    { name: 'description', content: 'RTF research: query NetBox in natural language with a local LLM' }
  ]
})

const displayMessages = computed(() => allMessages.value)

/** Gauge value: live during a turn, else the conversation's last known context. */
const gaugeTokens = computed<number | null>(() => {
  if (liveContextTokens.value != null) return liveContextTokens.value
  return activeConversation.value?.usage.contextEnd ?? null
})

const showMemoryLostBanner = computed(() =>
  !bannerDismissed.value &&
  serverKnowsThread.value === false &&
  (activeConversation.value?.messages.length ?? 0) > 0 &&
  !isProcessing.value
)

/**
 * Persist finalised messages into the active conversation.
 * Watches `messages` (not `allMessages`) so the streaming partial is not written
 * to localStorage on every token.
 */
watch(
  () => messages.value,
  (newMessages) => {
    if (isLoadingMessages.value) return
    if (activeConversationId.value && newMessages.length > 0) {
      updateConversation(activeConversationId.value, [...newMessages])
    }
  },
  { deep: true }
)

/**
 * Switch the view when the active conversation changes: load its transcript and
 * tell the server which thread we are on (it answers with `resumed`).
 */
watch(
  () => activeConversationId.value,
  async (newId, oldId) => {
    if (newId === oldId || !newId) return
    const conv = activeConversation.value
    if (!conv) return

    bannerDismissed.value = false
    isLoadingMessages.value = true
    if (conv.messages.length > 0) {
      loadMessages(conv.messages)
    } else {
      clearMessages()
    }
    setActiveThread(newId)
    await nextTick()
    isLoadingMessages.value = false
    void backfillTraceLinks(newId)
  }
)

/**
 * Older turns have no trace link (their run id was not minted by this backend).
 * Ask the server for the thread's LangSmith runs and reload the transcript if any matched.
 */
const backfillTraceLinks = async (conversationId: string) => {
  const changed = await syncServerTraces(conversationId)
  if (changed && activeConversationId.value === conversationId && !isProcessing.value) {
    const conv = activeConversation.value
    if (conv) {
      isLoadingMessages.value = true
      loadMessages(conv.messages)
      await nextTick()
      isLoadingMessages.value = false
    }
  }
}

/** When the server confirms it knows the thread, prefer its ledger if it has more turns. */
watch(serverKnowsThread, (known) => {
  if (known === true && activeConversationId.value) {
    syncServerUsage(activeConversationId.value)
  }
})

const handleSendMessage = async (message: string) => {
  if (!activeConversationId.value) {
    await createConversation()
  }
  const cid = activeConversationId.value
  if (!cid) return
  bannerDismissed.value = true
  if (!sendMessage(message, cid)) {
    console.error('Failed to send message')
  }
  sidebarOpen.value = false
}

const handleStop = () => {
  cancel()
}

const handleReconnect = () => {
  reconnect()
}

const handleNewConversation = async () => {
  if (isProcessing.value) return
  await startNewConversation()
}

const handleResetStorage = () => {
  if (confirm('Clear all conversation history from localStorage?\n\nThis cannot be undone.')) {
    clearAllConversations()
    clearMessages()
    location.reload()
  }
}

const handleKeyboardShortcuts = (event: KeyboardEvent) => {
  if ((event.ctrlKey || event.metaKey) && event.key === 'b') {
    event.preventDefault()
    sidebarOpen.value = !sidebarOpen.value
  }
  if ((event.ctrlKey || event.metaKey) && event.key === 'n') {
    event.preventDefault()
    handleNewConversation()
  }
  if (event.key === 'Escape' && isProcessing.value) {
    handleStop()
  }
  if ((event.ctrlKey || event.metaKey) && event.shiftKey && event.key === 'Delete') {
    event.preventDefault()
    handleResetStorage()
  }
}

onMounted(async () => {
  window.addEventListener('keydown', handleKeyboardShortcuts)

  // useConversations sets the active id on its own mount; load it after a tick.
  await nextTick()
  if (activeConversationId.value && activeConversation.value) {
    isLoadingMessages.value = true
    if (activeConversation.value.messages.length > 0) {
      loadMessages(activeConversation.value.messages)
    }
    setActiveThread(activeConversationId.value)
    await nextTick()
    isLoadingMessages.value = false
    void backfillTraceLinks(activeConversationId.value)
  }
})

onUnmounted(() => {
  window.removeEventListener('keydown', handleKeyboardShortcuts)
})
</script>

<style scoped>
.app-container {
  @apply h-screen flex bg-white dark:bg-gray-900;
  @apply overflow-hidden;
}

.main-content {
  @apply flex-1 flex flex-col min-w-0;
}

.chat-header {
  /* Same height as .sidebar-header (see assets/css/main.css --app-header-h). */
  @apply flex items-center;
  @apply px-4 md:px-6 py-2;
  min-height: var(--app-header-h);
  @apply bg-white dark:bg-gray-800;
  @apply border-b border-gray-200 dark:border-gray-700;
  @apply shadow-sm;
}

.mobile-menu-button {
  @apply p-2 rounded-lg;
  @apply text-gray-600 dark:text-gray-400;
  @apply hover:bg-gray-100 dark:hover:bg-gray-700;
  @apply transition-colors;
}

.header-divider {
  @apply hidden md:block w-px h-8 flex-shrink-0;
  @apply bg-gray-200 dark:bg-gray-700;
}
.chat-title {
  @apply text-lg md:text-xl font-semibold;
  @apply text-gray-900 dark:text-gray-100;
  @apply truncate;
}

.chat-subtitle {
  @apply text-xs md:text-sm text-gray-600 dark:text-gray-400 truncate;
}

.memory-banner {
  @apply flex items-center gap-3 px-4 py-2 text-sm;
  @apply bg-amber-50 dark:bg-amber-900/20 text-amber-900 dark:text-amber-200;
  @apply border-b border-amber-200 dark:border-amber-800;
}

.banner-button {
  @apply ml-auto px-3 py-1 rounded bg-amber-600 text-white text-xs font-medium hover:bg-amber-700 whitespace-nowrap;
}

.banner-dismiss {
  @apply px-2 text-lg leading-none text-amber-700 dark:text-amber-300 hover:text-amber-900;
}

.chat-main {
  @apply flex-1 flex flex-col min-h-0;
}
</style>
