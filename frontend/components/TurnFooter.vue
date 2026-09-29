<template>
  <div class="turn-footer" :class="{ 'turn-footer-warning': isLength }">
    <div class="turn-line" @click="open = !open" :title="open ? 'Hide per-call detail' : 'Show per-call detail'">
      <span>{{ formatSeconds(meta.elapsedS) }}</span>
      <span class="sep">·</span>
      <span>{{ meta.modelCalls }} model call{{ meta.modelCalls === 1 ? '' : 's' }}</span>
      <span class="sep">·</span>
      <span>{{ meta.toolCalls }} tool{{ meta.toolCalls === 1 ? '' : 's' }}</span>
      <span class="sep">·</span>
      <span>in {{ formatTokens(u.promptTokensTotal) }}<template v-if="u.cacheReadTotal"> (cached {{ formatTokens(u.cacheReadTotal) }})</template></span>
      <span class="sep">·</span>
      <span>out {{ formatTokens(u.completionTokensTotal) }}</span>
      <template v-if="u.contextEnd != null">
        <span class="sep">·</span>
        <span>ctx {{ formatTokens(u.contextEnd) }}<template v-if="ctxPct !== null"> ({{ ctxPct }}%)</template></span>
      </template>
      <template v-if="lastPrefill !== null">
        <span class="sep">·</span>
        <span>prefill {{ formatTps(lastPrefill) }}</span>
      </template>
      <template v-if="lastDecode !== null">
        <span class="sep">·</span>
        <span>decode {{ formatTps(lastDecode) }}</span>
      </template>
      <span v-if="u.compacted" class="badge badge-compacted">compacted</span>
      <span v-if="meta.cancelled" class="badge badge-cancelled">cancelled</span>
      <span v-if="isLength" class="badge badge-warning">output budget hit</span>
      <template v-if="meta.traceUrl">
        <span class="sep">·</span>
        <a
          class="trace-link"
          :href="meta.traceUrl"
          target="_blank"
          rel="noopener noreferrer"
          title="Open this turn's LangSmith trace in a new tab"
          @click.stop
        >
          trace
          <svg class="trace-icon" viewBox="0 0 12 12" aria-hidden="true">
            <path d="M4 2h6v6M10 2 3.5 8.5M2 4v6h6" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
        </a>
      </template>
      <span v-if="u.calls.length" class="toggle-hint">{{ open ? '▾' : '▸' }}</span>
    </div>

    <p v-if="isLength" class="warning-text">
      The model spent its whole output budget on reasoning and produced no visible answer
      ({{ formatTokens(u.completionTokensTotal) }} tokens written, {{ meta.chars }} characters shown).
    </p>

    <table v-if="open && u.calls.length" class="call-table">
      <thead>
        <tr>
          <th>call</th>
          <th>ctx in</th>
          <th>cached</th>
          <th>out</th>
          <th>prefill</th>
          <th>decode</th>
          <th>prompt</th>
          <th>predict</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="c in u.calls" :key="c.callIndex">
          <td>#{{ c.callIndex }}</td>
          <td>{{ formatTokens(c.inputTokens) }}</td>
          <td>{{ formatTokens(c.cacheRead) }}</td>
          <td>{{ formatTokens(c.outputTokens) }}</td>
          <td>{{ formatTps(c.prefillTps) }}</td>
          <td>{{ formatTps(c.decodeTps) }}</td>
          <td>{{ formatMs(c.promptMs) }}</td>
          <td>{{ formatMs(c.predictedMs) }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup lang="ts">
import type { TurnMeta } from '~/types/chat'
import { formatMs, formatSeconds, formatTokens, formatTps } from '~/utils/formatters'

interface Props {
  meta: TurnMeta
  /** Server window, for the ctx percentage. */
  nCtx?: number | null
}

const props = withDefaults(defineProps<Props>(), { nCtx: null })

const open = ref(false)
const u = computed(() => props.meta.usage)
const isLength = computed(() => props.meta.finishReason === 'length')

const ctxPct = computed(() => {
  if (!props.nCtx || u.value.contextEnd == null) return null
  return Math.round((u.value.contextEnd / props.nCtx) * 1000) / 10
})

const lastCall = computed(() => u.value.calls.length ? u.value.calls[u.value.calls.length - 1] : null)
const lastPrefill = computed(() => lastCall.value?.prefillTps ?? null)
const lastDecode = computed(() => lastCall.value?.decodeTps ?? null)
</script>

<style scoped>
.turn-footer {
  @apply mt-3 pt-2 border-t border-gray-200 dark:border-gray-700;
  @apply text-xs text-gray-500 dark:text-gray-400;
}

.turn-footer-warning {
  @apply border-red-300 dark:border-red-800;
}

.turn-line {
  @apply flex flex-wrap items-center gap-x-1.5 gap-y-1 cursor-pointer select-none;
}

.sep {
  @apply text-gray-300 dark:text-gray-600;
}

.badge {
  @apply ml-1 px-1.5 py-0.5 rounded text-[10px] uppercase tracking-wide font-semibold;
}

.badge-compacted {
  @apply bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300;
}

.badge-cancelled {
  @apply bg-gray-200 text-gray-700 dark:bg-gray-700 dark:text-gray-200;
}

.badge-warning {
  @apply bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300;
}

.toggle-hint {
  @apply ml-auto text-gray-400;
}

.trace-link {
  @apply inline-flex items-center gap-0.5 font-medium;
  @apply text-blue-600 dark:text-blue-400 hover:underline;
}

.trace-icon {
  @apply w-3 h-3;
}

.warning-text {
  @apply mt-2 text-red-600 dark:text-red-400;
}

.call-table {
  @apply mt-2 w-full text-[11px] font-mono border-collapse;
}

.call-table th {
  @apply text-left font-semibold text-gray-600 dark:text-gray-300 pr-3 pb-1 border-b border-gray-200 dark:border-gray-700;
}

.call-table td {
  @apply pr-3 py-0.5 text-gray-700 dark:text-gray-300 whitespace-nowrap;
}
</style>
