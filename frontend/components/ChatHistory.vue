<template>
  <div class="chat-history" ref="historyContainer">
    <!-- Empty state -->
    <div v-if="messages.length === 0 && !isProcessing" class="empty-state">
      <div class="empty-icon">💬</div>
      <h3 class="empty-title">Start a conversation</h3>
      <p class="empty-description">
        Ask questions about your Netbox infrastructure using natural language.
      </p>
      <div class="example-questions">
        <p class="example-label">Try asking:</p>
        <ul class="example-list">
          <li>"What sites do I have?"</li>
          <li>"Show devices at site DM-Akron"</li>
          <li>"List the sites for tenant Dunder-Mifflin with their status"</li>
          <li>"Which VLANs exist at DM-Nashua?"</li>
        </ul>
      </div>
    </div>

    <!-- Messages -->
    <div v-else class="messages-container">
      <template v-for="(message, index) in messages" :key="`message-${index}`">
        <CompactionDivider
          v-if="message.kind === 'compaction'"
          :before-tokens="message.compaction?.beforeTokens ?? 0"
          :after-tokens="message.compaction?.afterTokens ?? 0"
        />
        <ChatMessage
          v-else
          :message="message"
          :is-streaming="isProcessing && index === messages.length - 1 && message.role === 'assistant' && !message.meta?.finishReason && hasPartial"
          :n-ctx="nCtx"
        />
      </template>

      <!-- Waiting indicator: queued or running, nothing streamed yet -->
      <div v-if="isProcessing && !hasPartial" class="loading-indicator">
        <LoadingSpinner size="md" aria-label="Assistant is processing" />
        <span class="loading-text">
          <template v-if="phase === 'queued' && queuePosition">
            Queued behind {{ queuePosition }} other turn{{ queuePosition === 1 ? '' : 's' }} (single model slot)...
          </template>
          <template v-else-if="phase === 'queued'">Waiting for the model slot...</template>
          <template v-else>NetBox Assistant is thinking{{ elapsedS ? ` (${Math.round(elapsedS)} s)` : '' }}...</template>
        </span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { ChatMessage } from '~/types/chat'

interface Props {
  messages: ChatMessage[]
  isProcessing?: boolean
  /** True once the in-flight bubble exists (text or tool activity). */
  hasPartial?: boolean
  partialMessage?: string
  phase?: 'idle' | 'queued' | 'running'
  queuePosition?: number | null
  elapsedS?: number
  nCtx?: number | null
}

const props = withDefaults(defineProps<Props>(), {
  isProcessing: false,
  hasPartial: false,
  partialMessage: '',
  phase: 'idle',
  queuePosition: null,
  elapsedS: 0,
  nCtx: null
})

const historyContainer = ref<HTMLElement>()

// Auto-scroll to bottom when new messages arrive
const scrollToBottom = () => {
  nextTick(() => {
    if (historyContainer.value) {
      historyContainer.value.scrollTop = historyContainer.value.scrollHeight
    }
  })
}

// Watch for new messages and scroll
watch(
  () => props.messages.length,
  () => {
    scrollToBottom()
  }
)

// Also scroll when partial message updates
watch(
  () => props.partialMessage,
  () => {
    if (props.partialMessage) {
      scrollToBottom()
    }
  }
)

// And when tool activity changes on the in-flight bubble
watch(
  () => props.messages[props.messages.length - 1]?.toolCalls?.length,
  () => {
    if (props.isProcessing) scrollToBottom()
  }
)

// Scroll on mount
onMounted(() => {
  scrollToBottom()
})
</script>

<style scoped>
.chat-history {
  @apply flex-1 overflow-y-auto p-4 bg-gray-50 dark:bg-gray-900;
  @apply min-h-0; /* Important for flexbox overflow */
}

/* Empty state */
.empty-state {
  @apply flex flex-col items-center justify-center h-full text-center py-12;
}

.empty-icon {
  @apply text-6xl mb-4;
}

.empty-title {
  @apply text-2xl font-semibold text-gray-900 dark:text-gray-100 mb-2;
}

.empty-description {
  @apply text-gray-600 dark:text-gray-400 mb-6;
}

.example-questions {
  @apply bg-white dark:bg-gray-800 rounded-lg p-6 max-w-md mx-auto;
  @apply border border-gray-200 dark:border-gray-700;
}

.example-label {
  @apply text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3;
}

.example-list {
  @apply space-y-2 text-left;
}

.example-list li {
  @apply text-sm text-gray-600 dark:text-gray-400;
  @apply bg-gray-50 dark:bg-gray-700/50 px-3 py-2 rounded;
  @apply font-mono;
}

/* Messages container */
.messages-container {
  @apply space-y-2;
}

/* Loading indicator */
.loading-indicator {
  @apply flex items-center gap-3 p-4 bg-gray-100 dark:bg-gray-800 rounded-lg mr-8;
}

.loading-text {
  @apply text-sm text-gray-600 dark:text-gray-400 font-medium;
}

/* Custom scrollbar */
.chat-history::-webkit-scrollbar {
  @apply w-2;
}

.chat-history::-webkit-scrollbar-track {
  @apply bg-gray-100 dark:bg-gray-800;
}

.chat-history::-webkit-scrollbar-thumb {
  @apply bg-gray-400 dark:bg-gray-600 rounded-full;
}

.chat-history::-webkit-scrollbar-thumb:hover {
  @apply bg-gray-500 dark:bg-gray-500;
}
</style>