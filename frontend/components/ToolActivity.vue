<template>
  <div v-if="toolCalls.length" class="tool-activity">
    <button class="tool-toggle" type="button" @click="open = !open">
      <span class="tool-toggle-icon">{{ open ? '▾' : '▸' }}</span>
      <span>{{ toolCalls.length }} NetBox tool call{{ toolCalls.length === 1 ? '' : 's' }}</span>
      <span v-if="errorCount" class="tool-error-count">{{ errorCount }} error{{ errorCount === 1 ? '' : 's' }}</span>
      <span v-if="pendingCount" class="tool-pending-count">{{ pendingCount }} running</span>
    </button>

    <ul v-if="open" class="tool-list">
      <li v-for="tc in toolCalls" :key="tc.callId" class="tool-row">
        <div class="tool-row-head" @click="toggleExpanded(tc.callId)">
          <span class="status-pill" :class="`status-${tc.status}`">{{ statusLabel(tc.status) }}</span>
          <code class="tool-name">{{ tc.name }}</code>
          <code class="tool-args" :title="fullArgs(tc)">{{ shortArgs(tc) }}</code>
          <span v-if="tc.preview" class="expand-hint">{{ expanded.has(tc.callId) ? 'hide' : 'result' }}</span>
        </div>
        <pre v-if="expanded.has(tc.callId) && tc.preview" class="tool-preview">{{ tc.preview }}<span v-if="tc.truncated" class="truncated-note">
... (truncated; the model received the full result)</span></pre>
      </li>
    </ul>
  </div>
</template>

<script setup lang="ts">
import type { ToolCall, ToolCallStatus } from '~/types/chat'

interface Props {
  toolCalls: ToolCall[]
  /** Start expanded (used for the in-flight message). */
  defaultOpen?: boolean
}

const props = withDefaults(defineProps<Props>(), { defaultOpen: false })

const open = ref(props.defaultOpen)
const expanded = ref(new Set<string>())

const errorCount = computed(() =>
  props.toolCalls.filter(t => t.status === 'validation_error' || t.status === 'api_error').length
)
const pendingCount = computed(() => props.toolCalls.filter(t => t.status === 'pending').length)

const statusLabel = (s: ToolCallStatus) => {
  switch (s) {
    case 'ok': return 'ok'
    case 'validation_error': return 'validation error'
    case 'api_error': return 'API error'
    default: return 'running'
  }
}

const fullArgs = (tc: ToolCall) => {
  try { return JSON.stringify(tc.args) } catch { return '' }
}

const shortArgs = (tc: ToolCall) => {
  const s = fullArgs(tc)
  return s.length > 90 ? s.slice(0, 87) + '...' : s
}

const toggleExpanded = (id: string) => {
  const next = new Set(expanded.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  expanded.value = next
}
</script>

<style scoped>
.tool-activity {
  @apply mt-3 border border-gray-200 dark:border-gray-700 rounded-md;
  @apply bg-white/60 dark:bg-gray-900/40 text-xs;
}

.tool-toggle {
  @apply w-full flex items-center gap-2 px-3 py-2;
  @apply text-gray-600 dark:text-gray-300 font-medium;
  @apply hover:bg-gray-50 dark:hover:bg-gray-800 rounded-md;
}

.tool-toggle-icon {
  @apply w-3 inline-block;
}

.tool-error-count {
  @apply ml-auto px-2 py-0.5 rounded-full bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300;
}

.tool-pending-count {
  @apply px-2 py-0.5 rounded-full bg-yellow-100 text-yellow-800 dark:bg-yellow-900/40 dark:text-yellow-200;
}

.tool-list {
  @apply border-t border-gray-200 dark:border-gray-700 divide-y divide-gray-100 dark:divide-gray-800;
}

.tool-row-head {
  @apply flex items-center gap-2 px-3 py-1.5 cursor-pointer;
  @apply hover:bg-gray-50 dark:hover:bg-gray-800;
}

.status-pill {
  @apply px-1.5 py-0.5 rounded text-[10px] uppercase tracking-wide font-semibold whitespace-nowrap;
}

.status-ok {
  @apply bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300;
}

.status-pending {
  @apply bg-yellow-100 text-yellow-800 dark:bg-yellow-900/40 dark:text-yellow-200;
  animation: pulse 1.2s ease-in-out infinite;
}

.status-validation_error {
  @apply bg-orange-100 text-orange-800 dark:bg-orange-900/40 dark:text-orange-200;
}

.status-api_error {
  @apply bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300;
}

.tool-name {
  @apply font-mono text-gray-800 dark:text-gray-100 whitespace-nowrap;
}

.tool-args {
  @apply font-mono text-gray-500 dark:text-gray-400 truncate flex-1;
}

.expand-hint {
  @apply text-blue-600 dark:text-blue-400 whitespace-nowrap;
}

.tool-preview {
  @apply mx-3 mb-2 p-2 rounded bg-gray-900 text-gray-100 font-mono text-[11px];
  @apply overflow-x-auto whitespace-pre-wrap break-words max-h-64 overflow-y-auto;
}

.truncated-note {
  @apply text-gray-400 italic;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}
</style>
