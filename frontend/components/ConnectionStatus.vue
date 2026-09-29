<template>
  <div class="connection-status" :class="statusClass">
    <!-- WebSocket indicator -->
    <div class="status-indicator" :title="wsTitle">
      <span class="status-dot" :class="dotClass"></span>
      <span class="status-text">{{ statusText }}</span>
    </div>

    <!-- Model / slot indicator from GET /status -->
    <div class="status-indicator model-indicator" :title="modelTitle">
      <span class="status-dot" :class="modelDotClass"></span>
      <span class="status-text">
        <template v-if="status">
          <span class="model-name">{{ status.model || 'model' }}</span>
          <span class="model-detail">
            <template v-if="status.turnRunning || status.slotBusy">busy</template>
            <template v-else>idle</template>
            <template v-if="status.queueDepth > 0"> · queued {{ status.queueDepth }}</template>
          </span>
        </template>
        <template v-else-if="statusError">backend status unavailable</template>
        <template v-else>checking model...</template>
      </span>
    </div>

    <div v-if="hasConnectionError" class="status-error">
      {{ connectionState.error }}
    </div>
    <button
      v-if="showReconnect"
      @click="$emit('reconnect')"
      class="reconnect-button"
    >
      Reconnect
    </button>
  </div>
</template>

<script setup lang="ts">
import type { ConnectionState } from '~/types/chat'
import { formatTokens } from '~/utils/formatters'

interface Props {
  connectionState: ConnectionState
}

interface Emits {
  (e: 'reconnect'): void
}

const props = defineProps<Props>()
defineEmits<Emits>()

const { status, statusError } = useServerStatus()

const statusClass = computed(() => ({
  'status-connected': props.connectionState.connected,
  'status-connecting': props.connectionState.connecting,
  'status-disconnected': !props.connectionState.connected && !props.connectionState.connecting,
  'status-error': props.connectionState.error !== null
}))

const dotClass = computed(() => ({
  'dot-connected': props.connectionState.connected,
  'dot-connecting': props.connectionState.connecting,
  'dot-disconnected': !props.connectionState.connected && !props.connectionState.connecting
}))

const statusText = computed(() => {
  if (props.connectionState.connected) return 'Connected'
  if (props.connectionState.connecting) {
    return `Connecting${props.connectionState.reconnectAttempts > 0
      ? ` (attempt ${props.connectionState.reconnectAttempts})`
      : ''}...`
  }
  if (props.connectionState.error) return 'Connection Error'
  return 'Disconnected'
})

const wsTitle = computed(() => 'WebSocket to the chat backend')

const modelDotClass = computed(() => {
  if (!status.value) return statusError.value ? 'dot-disconnected' : 'dot-connecting'
  if (status.value.slotBusy === false && !status.value.turnRunning) return 'dot-connected'
  if (status.value.turnRunning || status.value.slotBusy) return 'dot-busy'
  return 'dot-connected'
})

const modelTitle = computed(() => {
  if (!status.value) return statusError.value ?? 'Fetching /status'
  const s = status.value
  return [
    `Backend: ${s.backend}`,
    `Model: ${s.model}`,
    s.nCtx ? `Window: ${formatTokens(s.nCtx)} tokens` : '',
    s.compactionTriggerTokens ? `Compaction trigger: ${formatTokens(s.compactionTriggerTokens)}` : '',
    s.promptCacheTokens != null ? `Prompt cache: ${formatTokens(s.promptCacheTokens)} tokens` : '',
    `Single model slot: ${s.slotBusy ? 'busy' : 'free'}; ${s.queueDepth} waiting`
  ].filter(Boolean).join('\n')
})

const hasConnectionError = computed<boolean>(() =>
  props.connectionState.error !== null && !props.connectionState.connecting
)

const showReconnect = computed<boolean>(() =>
  !props.connectionState.connected &&
  !props.connectionState.connecting &&
  props.connectionState.reconnectAttempts >= 5
)
</script>

<style scoped>
.connection-status {
  @apply flex items-center gap-4 px-3 py-2 flex-wrap;
  @apply bg-white dark:bg-gray-800 rounded-lg;
  @apply transition-colors duration-200;
}

.status-indicator {
  @apply flex items-center gap-2;
}

.model-indicator {
  @apply pl-4 border-l border-gray-200 dark:border-gray-700;
}

.status-dot {
  @apply w-2 h-2 rounded-full transition-colors duration-200 flex-shrink-0;
}

.dot-connected {
  @apply bg-green-500;
}

.dot-connecting {
  @apply bg-yellow-500;
  animation: pulse 1s ease-in-out infinite;
}

.dot-busy {
  @apply bg-blue-500;
  animation: pulse 1s ease-in-out infinite;
}

.dot-disconnected {
  @apply bg-red-500;
}

.status-text {
  @apply text-sm font-medium text-gray-700 dark:text-gray-300 flex items-baseline gap-1;
}

.model-name {
  @apply font-mono text-xs text-gray-800 dark:text-gray-100 max-w-[220px] truncate;
}

.model-detail {
  @apply text-xs text-gray-500 dark:text-gray-400;
}

.status-error {
  @apply text-sm text-red-600 dark:text-red-400;
}

.reconnect-button {
  @apply px-3 py-1 text-sm font-medium;
  @apply bg-blue-600 hover:bg-blue-700 text-white rounded;
  @apply transition-colors duration-200;
  @apply focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2;
}

.status-connected {
  @apply bg-green-50 dark:bg-green-900/10;
}

.status-connecting {
  @apply bg-yellow-50 dark:bg-yellow-900/10;
}

.status-disconnected,
.status-error {
  @apply bg-red-50 dark:bg-red-900/10;
}

@keyframes pulse {
  0% { opacity: 1; }
  50% { opacity: 0.4; }
  100% { opacity: 1; }
}
</style>
