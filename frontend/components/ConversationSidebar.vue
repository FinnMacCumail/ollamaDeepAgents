<script setup lang="ts">
/**
 * Sidebar component displaying conversation history.
 * Allows creating, selecting, renaming, and deleting conversations.
 */
import { useConversations } from '~/composables/useConversations'

const props = defineProps<{
  isOpen?: boolean
}>()

const emit = defineEmits<{
  close: []
}>()

const {
  conversations,
  activeConversationId,
  activeConversation,
  startNewConversation,
  setActiveConversation,
  renameConversation,
  deleteConversation,
  clearAllConversations
} = useConversations()

const { isProcessing } = useChatSocket()
const { status } = useServerStatus()

const creating = ref(false)

const NEW_CHAT_TOOLTIP =
  'Starts a clean thread - use this when an answer seems to reuse data from an earlier question. ' +
  'The model forgets everything in the current conversation.'

/**
 * Handle new conversation button click.
 * Asks the backend for a fresh thread id (new_conversation -> reset_complete).
 */
const handleNewChat = async () => {
  if (creating.value || isProcessing.value) return
  creating.value = true
  try {
    await startNewConversation()
  } finally {
    creating.value = false
  }
  emit('close')
}

/**
 * Handle conversation selection. Blocked while a turn is running so streamed
 * chunks cannot land in a different transcript.
 */
const handleSelectConversation = (conversationId: string) => {
  if (isProcessing.value) return
  setActiveConversation(conversationId)
  emit('close')
}

/**
 * Handle conversation rename.
 */
const handleRenameConversation = (conversationId: string, newTitle: string) => {
  renameConversation(conversationId, newTitle)
}

/**
 * Handle conversation deletion.
 */
const handleDeleteConversation = (conversationId: string) => {
  deleteConversation(conversationId)
}

/**
 * Handle clear all conversations.
 */
const handleClearAll = () => {
  if (confirm('Delete all conversations? This cannot be undone.')) {
    clearAllConversations()
  }
}
</script>

<template>
  <aside
    class="conversation-sidebar"
    :class="{ open: isOpen }"
  >
    <!-- Sidebar header -->
    <div class="sidebar-header">
      <h2 class="sidebar-title">Conversations</h2>

      <!-- Mobile close button -->
      <button
        class="mobile-close-button md:hidden"
        @click="emit('close')"
        title="Close sidebar"
      >
        <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
          <path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd" />
        </svg>
      </button>
    </div>

    <!-- New conversation button -->
    <button
      class="new-chat-button"
      :class="{ 'new-chat-disabled': creating || isProcessing }"
      :disabled="creating || isProcessing"
      :title="isProcessing ? 'Wait for the running turn to finish (or press Stop)' : NEW_CHAT_TOOLTIP"
      @click="handleNewChat"
    >
      <svg xmlns="http://www.w3.org/2000/svg" class="button-icon" viewBox="0 0 20 20" fill="currentColor">
        <path fill-rule="evenodd" d="M10 3a1 1 0 011 1v5h5a1 1 0 110 2h-5v5a1 1 0 11-2 0v-5H4a1 1 0 110-2h5V4a1 1 0 011-1z" clip-rule="evenodd" />
      </svg>
      {{ creating ? 'Creating...' : 'New conversation' }}
    </button>
    <p class="new-chat-hint">Switching conversations makes the next turn pay a cold prompt prefill.</p>

    <!-- Conversation list -->
    <div class="conversation-list" :class="{ 'list-locked': isProcessing }">
      <div v-if="conversations.length === 0" class="empty-state">
        <p class="empty-text">No conversations yet</p>
        <p class="empty-subtext">Start a new conversation to begin</p>
      </div>

      <ConversationItem
        v-for="conversation in conversations"
        :key="conversation.id"
        :conversation="conversation"
        :is-active="conversation.id === activeConversationId"
        @select="handleSelectConversation"
        @rename="handleRenameConversation"
        @delete="handleDeleteConversation"
      />
    </div>

    <!-- Per-conversation token ledger -->
    <TokenLedger
      v-if="activeConversation"
      :usage="activeConversation.usage"
      :messages="activeConversation.messages"
      :n-ctx="status?.nCtx ?? null"
    />

    <!-- Sidebar footer -->
    <div v-if="conversations.length > 0" class="sidebar-footer">
      <button
        class="clear-all-button"
        @click="handleClearAll"
        title="Delete all conversations"
      >
        <svg xmlns="http://www.w3.org/2000/svg" class="button-icon" viewBox="0 0 20 20" fill="currentColor">
          <path fill-rule="evenodd" d="M9 2a1 1 0 00-.894.553L7.382 4H4a1 1 0 000 2v10a2 2 0 002 2h8a2 2 0 002-2V6a1 1 0 100-2h-3.382l-.724-1.447A1 1 0 0011 2H9zM7 8a1 1 0 012 0v6a1 1 0 11-2 0V8zm5-1a1 1 0 00-1 1v6a1 1 0 102 0V8a1 1 0 00-1-1z" clip-rule="evenodd" />
        </svg>
        Clear All
      </button>
    </div>

    <!-- Mobile overlay -->
    <div
      v-if="isOpen"
      class="mobile-overlay md:hidden"
      @click="emit('close')"
    />
  </aside>
</template>

<style scoped>
.conversation-sidebar {
  @apply flex flex-col h-full;
  @apply bg-white dark:bg-gray-900;
  @apply border-r border-gray-200 dark:border-gray-700;
  @apply w-72 flex-shrink-0;
  @apply transition-transform duration-300;
}

/* Mobile: sidebar slides in from left */
@media (max-width: 768px) {
  .conversation-sidebar {
    @apply fixed inset-y-0 left-0 z-40;
    @apply -translate-x-full;
  }

  .conversation-sidebar.open {
    @apply translate-x-0;
  }
}

.sidebar-header {
  /* Same height as .chat-header (see assets/css/main.css --app-header-h). */
  @apply flex items-center justify-between flex-shrink-0;
  @apply px-4 py-0;
  min-height: var(--app-header-h);
  @apply border-b border-gray-200 dark:border-gray-700;
}

.sidebar-title {
  @apply text-lg font-semibold;
  @apply text-gray-900 dark:text-gray-100;
}

.mobile-close-button {
  @apply p-1 rounded-lg;
  @apply text-gray-500 hover:text-gray-700;
  @apply dark:text-gray-400 dark:hover:text-gray-200;
  @apply hover:bg-gray-100 dark:hover:bg-gray-800;
  @apply transition-colors;
}

.new-chat-button {
  @apply flex items-center justify-center gap-2;
  @apply mx-4 mt-4 px-4 py-2.5;
  @apply bg-blue-600 hover:bg-blue-700;
  @apply text-white font-medium text-sm;
  @apply rounded-lg shadow-sm;
  @apply transition-colors duration-150;
}

.new-chat-button:active {
  @apply bg-blue-800;
}

.new-chat-disabled {
  @apply bg-gray-400 dark:bg-gray-600 cursor-not-allowed hover:bg-gray-400 dark:hover:bg-gray-600;
}

.new-chat-hint {
  @apply mx-4 mt-1 text-[11px] text-gray-400 dark:text-gray-500;
}

.list-locked {
  @apply opacity-60 pointer-events-none;
}

.button-icon {
  @apply w-5 h-5;
}

.conversation-list {
  @apply flex-1 overflow-y-auto;
  @apply px-2 py-4;
  @apply space-y-1;
}

/* Custom scrollbar for conversation list */
.conversation-list::-webkit-scrollbar {
  @apply w-2;
}

.conversation-list::-webkit-scrollbar-track {
  @apply bg-transparent;
}

.conversation-list::-webkit-scrollbar-thumb {
  @apply bg-gray-300 dark:bg-gray-700 rounded-full;
}

.conversation-list::-webkit-scrollbar-thumb:hover {
  @apply bg-gray-400 dark:bg-gray-600;
}

.empty-state {
  @apply flex flex-col items-center justify-center;
  @apply py-12 px-4 text-center;
}

.empty-text {
  @apply text-gray-600 dark:text-gray-400;
  @apply font-medium;
}

.empty-subtext {
  @apply text-sm text-gray-500 dark:text-gray-500;
  @apply mt-1;
}

.sidebar-footer {
  @apply px-4 py-3;
  @apply border-t border-gray-200 dark:border-gray-700;
}

.clear-all-button {
  @apply flex items-center justify-center gap-2;
  @apply w-full px-3 py-2;
  @apply text-sm text-gray-600 dark:text-gray-400;
  @apply hover:text-red-600 dark:hover:text-red-400;
  @apply hover:bg-gray-100 dark:hover:bg-gray-800;
  @apply rounded-lg;
  @apply transition-colors;
}

.mobile-overlay {
  @apply fixed inset-0 bg-black bg-opacity-50 z-30;
}
</style>
