<script setup lang="ts">
/**
 * Individual conversation item in the sidebar.
 * Displays conversation title with hover actions (rename, delete).
 */
import type { Conversation } from '~/composables/useConversations'
import { formatTokens } from '~/utils/formatters'

const props = defineProps<{
  conversation: Conversation
  isActive: boolean
}>()

const emit = defineEmits<{
  select: [conversationId: string]
  rename: [conversationId: string, newTitle: string]
  delete: [conversationId: string]
}>()

const isEditing = ref(false)
const editTitle = ref('')
const titleInput = ref<HTMLInputElement | null>(null)

/**
 * Format relative time for conversation timestamp.
 */
const relativeTime = computed(() => {
  const date = new Date(props.conversation.updatedAt)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffMins = Math.floor(diffMs / 60000)
  const diffHours = Math.floor(diffMs / 3600000)
  const diffDays = Math.floor(diffMs / 86400000)

  if (diffMins < 1) return 'Just now'
  if (diffMins < 60) return `${diffMins}m ago`
  if (diffHours < 24) return `${diffHours}h ago`
  if (diffDays < 7) return `${diffDays}d ago`

  return date.toLocaleDateString()
})

/**
 * Start editing the conversation title.
 */
const startEditing = () => {
  editTitle.value = props.conversation.title
  isEditing.value = true

  nextTick(() => {
    titleInput.value?.focus()
    titleInput.value?.select()
  })
}

/**
 * Save the edited title.
 */
const saveEdit = () => {
  const newTitle = editTitle.value.trim()
  if (newTitle && newTitle !== props.conversation.title) {
    emit('rename', props.conversation.id, newTitle)
  }
  isEditing.value = false
}

/**
 * Cancel editing.
 */
const cancelEdit = () => {
  isEditing.value = false
  editTitle.value = ''
}

/**
 * Handle key events in edit mode.
 */
const handleKeyDown = (event: KeyboardEvent) => {
  if (event.key === 'Enter') {
    event.preventDefault()
    saveEdit()
  } else if (event.key === 'Escape') {
    event.preventDefault()
    cancelEdit()
  }
}

/**
 * Handle conversation selection.
 */
const handleSelect = () => {
  if (!isEditing.value) {
    emit('select', props.conversation.id)
  }
}

/**
 * Handle delete confirmation.
 */
const handleDelete = (event: Event) => {
  event.stopPropagation()

  if (confirm(`Delete "${props.conversation.title}"?`)) {
    emit('delete', props.conversation.id)
  }
}
</script>

<template>
  <div
    class="conversation-item group"
    :class="{ active: isActive }"
    @click="handleSelect"
  >
    <!-- Title (normal or edit mode) -->
    <div v-if="!isEditing" class="conversation-title">
      <span class="title-text">{{ conversation.title }}</span>
      <span class="conversation-meta">
        <span v-if="conversation.usage?.turns" class="conversation-ctx" title="Resident context after the last turn">
          {{ formatTokens(conversation.usage.contextEnd) }} ctx
        </span>
        <span class="conversation-time">{{ relativeTime }}</span>
      </span>
    </div>

    <input
      v-else
      ref="titleInput"
      v-model="editTitle"
      type="text"
      class="conversation-title-input"
      @keydown="handleKeyDown"
      @blur="saveEdit"
      @click.stop
    />

    <!-- Hover actions -->
    <div v-if="!isEditing" class="conversation-actions">
      <button
        class="action-button"
        title="Rename"
        @click.stop="startEditing"
      >
        <svg xmlns="http://www.w3.org/2000/svg" class="icon" viewBox="0 0 20 20" fill="currentColor">
          <path d="M13.586 3.586a2 2 0 112.828 2.828l-.793.793-2.828-2.828.793-.793zM11.379 5.793L3 14.172V17h2.828l8.38-8.379-2.83-2.828z" />
        </svg>
      </button>

      <button
        class="action-button delete"
        title="Delete"
        @click="handleDelete"
      >
        <svg xmlns="http://www.w3.org/2000/svg" class="icon" viewBox="0 0 20 20" fill="currentColor">
          <path fill-rule="evenodd" d="M9 2a1 1 0 00-.894.553L7.382 4H4a1 1 0 000 2v10a2 2 0 002 2h8a2 2 0 002-2V6a1 1 0 100-2h-3.382l-.724-1.447A1 1 0 0011 2H9zM7 8a1 1 0 012 0v6a1 1 0 11-2 0V8zm5-1a1 1 0 00-1 1v6a1 1 0 102 0V8a1 1 0 00-1-1z" clip-rule="evenodd" />
        </svg>
      </button>
    </div>
  </div>
</template>

<style scoped>
.conversation-item {
  @apply relative flex items-center justify-between;
  @apply px-3 py-2.5 rounded-lg cursor-pointer;
  @apply text-gray-700 dark:text-gray-300;
  @apply hover:bg-gray-100 dark:hover:bg-gray-800;
  @apply transition-colors duration-150;
}

.conversation-item.active {
  @apply bg-blue-50 dark:bg-blue-900/20;
  @apply text-blue-900 dark:text-blue-100;
  @apply font-medium;
}

.conversation-title {
  @apply flex-1 flex items-center justify-between gap-2;
  @apply overflow-hidden;
}

.title-text {
  @apply flex-1 truncate text-sm;
}

.conversation-meta {
  @apply flex items-center gap-2;
}

.conversation-ctx {
  @apply text-[10px] font-mono text-gray-400 dark:text-gray-500 whitespace-nowrap;
}

.conversation-time {
  @apply text-xs text-gray-500 dark:text-gray-500;
  @apply whitespace-nowrap;
}

.conversation-title-input {
  @apply w-full px-2 py-1 text-sm;
  @apply bg-white dark:bg-gray-700;
  @apply border border-blue-500 rounded;
  @apply focus:outline-none focus:ring-2 focus:ring-blue-500;
}

.conversation-actions {
  @apply hidden group-hover:flex items-center gap-1;
  @apply ml-2;
}

.action-button {
  @apply p-1 rounded;
  @apply text-gray-500 hover:text-gray-700;
  @apply dark:text-gray-400 dark:hover:text-gray-200;
  @apply hover:bg-gray-200 dark:hover:bg-gray-700;
  @apply transition-colors;
}

.action-button.delete:hover {
  @apply text-red-600 dark:text-red-400;
}

.icon {
  @apply w-4 h-4;
}
</style>
