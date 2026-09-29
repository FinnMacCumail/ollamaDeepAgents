<template>
  <div class="chat-message group" :class="messageClass">
    <div class="message-header">
      <span class="message-role">{{ roleLabel }}</span>
      <div class="header-right">
        <!-- Message actions (visible on hover), inline so they never cover the time -->
        <div class="message-actions">
          <button
            class="action-button"
            :class="{ copied: copySuccess }"
            :title="copySuccess ? 'Copied!' : 'Copy message'"
            @click="handleCopy"
          >
            <svg v-if="!copySuccess" xmlns="http://www.w3.org/2000/svg" class="icon" viewBox="0 0 20 20" fill="currentColor">
              <path d="M8 3a1 1 0 011-1h2a1 1 0 110 2H9a1 1 0 01-1-1z" />
              <path d="M6 3a2 2 0 00-2 2v11a2 2 0 002 2h8a2 2 0 002-2V5a2 2 0 00-2-2 3 3 0 01-3 3H9a3 3 0 01-3-3z" />
            </svg>
            <svg v-else xmlns="http://www.w3.org/2000/svg" class="icon" viewBox="0 0 20 20" fill="currentColor">
              <path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd" />
            </svg>
          </button>
        </div>
        <span class="message-time">{{ formattedTime }}</span>
      </div>
    </div>
    <div v-if="message.content" class="message-content" v-html="formattedContent"></div>
    <div v-else-if="isStreaming" class="message-content streaming-placeholder">
      Working on it{{ message.toolCalls?.length ? ' (calling NetBox tools)' : '' }}...
    </div>

    <!-- Tool activity + per-turn footer (assistant messages only) -->
    <ToolActivity
      v-if="message.role === 'assistant' && message.toolCalls?.length"
      :tool-calls="message.toolCalls"
      :default-open="isStreaming"
    />
    <TurnFooter
      v-if="message.role === 'assistant' && message.meta && !message.kind"
      :meta="message.meta"
      :n-ctx="nCtx"
    />
  </div>
</template>

<script setup lang="ts">
import type { ChatMessage } from '~/types/chat'
import { formatTime, formatMarkdown } from '~/utils/formatters'
import 'highlight.js/styles/github-dark.css'

interface Props {
  message: ChatMessage
  /** True for the in-flight assistant bubble. */
  isStreaming?: boolean
  /** Server context window, for the footer's ctx percentage. */
  nCtx?: number | null
}

const props = withDefaults(defineProps<Props>(), { isStreaming: false, nCtx: null })

const copySuccess = ref(false)

const messageClass = computed(() => ({
  'user-message': props.message.role === 'user',
  'assistant-message': props.message.role === 'assistant' && !props.message.kind,
  'notice-message': props.message.kind === 'notice',
  'streaming': props.isStreaming
}))

const roleLabel = computed(() => {
  if (props.message.kind === 'notice') return 'System'
  return props.message.role === 'user' ? 'You' : 'NetBox Assistant'
})

const formattedTime = computed(() =>
  formatTime(props.message.timestamp)
)

const formattedContent = computed(() => {
  if (props.message.role === 'assistant') {
    // Format markdown for assistant messages
    return formatMarkdown(props.message.content)
  }
  // Escape HTML for user messages
  return props.message.content.replace(/</g, '&lt;').replace(/>/g, '&gt;')
})

/**
 * Copy message content to clipboard.
 */
const handleCopy = async () => {
  try {
    await navigator.clipboard.writeText(props.message.content)
    copySuccess.value = true

    setTimeout(() => {
      copySuccess.value = false
    }, 2000)
  } catch (error) {
    console.error('Failed to copy message:', error)
  }
}

</script>

<style scoped>
.chat-message {
  @apply mb-4 p-4 rounded-lg relative;
}

.user-message {
  @apply bg-blue-50 dark:bg-blue-900/20 ml-8;
}

.assistant-message {
  @apply bg-gray-50 dark:bg-gray-800/50 mr-8;
}

.notice-message {
  @apply bg-yellow-50 dark:bg-yellow-900/20 mr-8 text-sm;
}

.streaming {
  @apply border border-dashed border-blue-300 dark:border-blue-700;
}

.streaming-placeholder {
  @apply text-gray-500 dark:text-gray-400 italic text-sm;
}

.message-header {
  @apply flex justify-between items-center mb-2 text-sm;
}

.message-role {
  @apply font-semibold text-gray-700 dark:text-gray-300;
}

.message-time {
  @apply text-gray-500 dark:text-gray-400;
  @apply transition-opacity duration-200;
}

/* Highlight timestamp on message hover */
.chat-message:hover .message-time {
  @apply text-gray-700 dark:text-gray-300;
}

/* Right side of the header: actions (hover-revealed) then the timestamp, never overlapping */
.header-right {
  @apply flex items-center gap-2;
}

.message-actions {
  @apply flex items-center gap-1;
  @apply opacity-0 group-hover:opacity-100 focus-within:opacity-100;
  @apply transition-opacity duration-200;
}

.action-button {
  @apply p-1.5 rounded-md;
  @apply bg-white dark:bg-gray-800;
  @apply border border-gray-200 dark:border-gray-700;
  @apply text-gray-600 dark:text-gray-400;
  @apply hover:text-gray-900 dark:hover:text-gray-100;
  @apply hover:bg-gray-50 dark:hover:bg-gray-700;
  @apply transition-colors duration-150;
  @apply shadow-sm;
}

.action-button.copied {
  @apply text-green-600 dark:text-green-400;
}

.icon {
  @apply w-4 h-4;
}

.message-content {
  @apply text-gray-800 dark:text-gray-200;
}

/* Style markdown content */
.message-content :deep(h1) {
  @apply text-xl font-bold mt-4 mb-2;
}

.message-content :deep(h2) {
  @apply text-lg font-semibold mt-3 mb-2;
}

.message-content :deep(h3) {
  @apply text-base font-semibold mt-2 mb-1;
}

.message-content :deep(p) {
  @apply mb-2;
}

.message-content :deep(ul) {
  @apply list-disc list-inside mb-2 ml-4;
}

.message-content :deep(ol) {
  @apply list-decimal list-inside mb-2 ml-4;
}

.message-content :deep(code) {
  @apply bg-gray-100 dark:bg-gray-800 px-1 py-0.5 rounded text-sm;
}

.message-content :deep(pre) {
  @apply bg-gray-100 dark:bg-gray-800 p-3 rounded-md overflow-x-auto mb-2;
}

.message-content :deep(pre code) {
  @apply bg-transparent p-0;
}

.message-content :deep(blockquote) {
  @apply border-l-4 border-gray-300 dark:border-gray-600 pl-4 italic my-2;
}

.message-content :deep(a) {
  @apply text-blue-600 dark:text-blue-400 underline hover:text-blue-800 dark:hover:text-blue-300;
}

/* Table wrapper for horizontal scroll */
.message-content :deep(.table-wrapper) {
  @apply overflow-x-auto my-4 rounded-lg shadow-sm;
  @apply border border-gray-200 dark:border-gray-700;
}

/* Enhanced table styling */
.message-content :deep(table.markdown-table) {
  @apply w-full border-collapse text-sm;
  @apply bg-white dark:bg-gray-800;
  min-width: 600px; /* Ensure table has minimum width for readability */
}

.message-content :deep(table.markdown-table thead) {
  @apply bg-blue-50 dark:bg-blue-900/30;
  @apply sticky top-0 z-10;
}

.message-content :deep(table.markdown-table th) {
  @apply font-semibold text-left;
  @apply px-4 py-3;
  @apply border-b-2 border-blue-200 dark:border-blue-700;
  @apply text-gray-900 dark:text-gray-100;
  @apply whitespace-nowrap;
}

.message-content :deep(table.markdown-table tbody tr) {
  @apply transition-colors duration-150;
  @apply border-b border-gray-200 dark:border-gray-700;
}

.message-content :deep(table.markdown-table tbody tr:nth-child(even)) {
  @apply bg-gray-50/50 dark:bg-gray-700/30;
}

.message-content :deep(table.markdown-table tbody tr:hover) {
  @apply bg-blue-50/50 dark:bg-blue-900/20;
}

.message-content :deep(table.markdown-table td) {
  @apply px-4 py-3;
  @apply text-gray-700 dark:text-gray-300;
}

.message-content :deep(table.markdown-table tbody tr:last-child) {
  @apply border-b-0;
}

/* Code block styling (syntax highlighted) */
.message-content :deep(pre) {
  @apply bg-gray-900 dark:bg-black p-4 rounded-lg overflow-x-auto mb-4;
  @apply border border-gray-700;
}

.message-content :deep(pre code.hljs) {
  @apply bg-transparent p-0 text-sm;
  @apply font-mono;
}

/* Inline code styling */
.message-content :deep(code:not(.hljs)) {
  @apply bg-gray-100 dark:bg-gray-800 px-2 py-0.5 rounded text-sm;
  @apply font-mono text-pink-600 dark:text-pink-400;
}

/* Improve spacing for better readability */
.message-content :deep(p + .table-wrapper) {
  @apply mt-3;
}

.message-content :deep(.table-wrapper + p) {
  @apply mt-3;
}
</style>