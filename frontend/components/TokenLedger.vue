<template>
  <section class="token-ledger">
    <button class="ledger-toggle" type="button" @click="open = !open">
      <span>{{ open ? '▾' : '▸' }}</span>
      <span class="ledger-title">Token ledger</span>
      <span class="ledger-summary">
        read {{ formatTokens(usage.promptTokensTotal) }} · written {{ formatTokens(usage.completionTokensTotal) }} · {{ formatSeconds(usage.elapsedSTotal) }}
      </span>
    </button>

    <div v-if="open" class="ledger-body">
      <dl class="totals">
        <div><dt>Turns</dt><dd>{{ usage.turns }}</dd></div>
        <div><dt>Model calls</dt><dd>{{ usage.modelCallsTotal }}</dd></div>
        <div><dt>Tokens read</dt><dd>{{ formatTokens(usage.promptTokensTotal) }}</dd></div>
        <div><dt>of which cached</dt><dd>{{ formatTokens(usage.cacheReadTotal) }}<span v-if="cachedPct !== null" class="muted"> ({{ cachedPct }}%)</span></dd></div>
        <div><dt>Tokens written</dt><dd>{{ formatTokens(usage.completionTokensTotal) }}</dd></div>
        <div><dt>Wall time</dt><dd>{{ formatSeconds(usage.elapsedSTotal) }}</dd></div>
        <div><dt>Context now</dt><dd>{{ formatTokens(usage.contextEnd) }}<span v-if="nCtx" class="muted"> / {{ formatTokens(nCtx) }}</span></dd></div>
      </dl>

      <table v-if="turns.length" class="turn-table">
        <thead>
          <tr>
            <th>turn</th>
            <th>in</th>
            <th>cached</th>
            <th>out</th>
            <th>calls</th>
            <th>ctx end</th>
            <th>time</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(t, i) in turns" :key="i">
            <td>{{ i + 1 }}</td>
            <td>{{ formatTokens(t.promptTokensTotal) }}</td>
            <td>{{ formatTokens(t.cacheReadTotal) }}</td>
            <td>{{ formatTokens(t.completionTokensTotal) }}</td>
            <td>{{ t.modelCalls }}</td>
            <td>{{ formatTokens(t.contextEnd) }}</td>
            <td>{{ formatSeconds(t.elapsedS) }}</td>
            <td><span v-if="t.compacted" class="badge">compacted</span></td>
          </tr>
        </tbody>
        <tfoot>
          <tr>
            <td>sum</td>
            <td>{{ formatTokens(sum.promptTokensTotal) }}</td>
            <td>{{ formatTokens(sum.cacheReadTotal) }}</td>
            <td>{{ formatTokens(sum.completionTokensTotal) }}</td>
            <td>{{ sum.modelCalls }}</td>
            <td></td>
            <td>{{ formatSeconds(sum.elapsedS) }}</td>
            <td></td>
          </tr>
        </tfoot>
      </table>
      <p v-else class="muted">No completed turns yet.</p>
    </div>
  </section>
</template>

<script setup lang="ts">
import type { ChatMessage, ConversationUsage, TurnUsage } from '~/types/chat'
import { formatSeconds, formatTokens } from '~/utils/formatters'

interface Props {
  usage: ConversationUsage
  messages: ChatMessage[]
  nCtx?: number | null
}

const props = withDefaults(defineProps<Props>(), { nCtx: null })

const open = ref(false)

const turns = computed<TurnUsage[]>(() =>
  props.messages
    .filter(m => m.role === 'assistant' && !m.kind && m.meta?.usage)
    .map(m => m.meta!.usage)
)

const sum = computed(() => turns.value.reduce(
  (acc, t) => ({
    promptTokensTotal: acc.promptTokensTotal + t.promptTokensTotal,
    cacheReadTotal: acc.cacheReadTotal + t.cacheReadTotal,
    completionTokensTotal: acc.completionTokensTotal + t.completionTokensTotal,
    modelCalls: acc.modelCalls + t.modelCalls,
    elapsedS: acc.elapsedS + t.elapsedS
  }),
  { promptTokensTotal: 0, cacheReadTotal: 0, completionTokensTotal: 0, modelCalls: 0, elapsedS: 0 }
))

const cachedPct = computed(() => {
  if (!props.usage.promptTokensTotal) return null
  return Math.round((props.usage.cacheReadTotal / props.usage.promptTokensTotal) * 100)
})
</script>

<style scoped>
.token-ledger {
  @apply border-t border-gray-200 dark:border-gray-700 text-xs;
}

.ledger-toggle {
  @apply w-full flex items-center gap-2 px-4 py-2 text-left;
  @apply text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800;
}

.ledger-title {
  @apply font-semibold;
}

.ledger-summary {
  @apply ml-auto font-mono text-gray-500 dark:text-gray-400 truncate;
}

.ledger-body {
  @apply px-4 pb-3 space-y-3;
}

.totals {
  @apply grid grid-cols-2 gap-x-4 gap-y-1;
}

.totals dt {
  @apply text-gray-500 dark:text-gray-400;
}

.totals dd {
  @apply font-mono text-gray-800 dark:text-gray-100;
}

.muted {
  @apply text-gray-400 dark:text-gray-500;
}

.turn-table {
  @apply w-full font-mono text-[11px] border-collapse;
}

.turn-table th {
  @apply text-left font-semibold text-gray-600 dark:text-gray-300 pr-2 pb-1 border-b border-gray-200 dark:border-gray-700;
}

.turn-table td {
  @apply pr-2 py-0.5 text-gray-700 dark:text-gray-300 whitespace-nowrap;
}

.turn-table tfoot td {
  @apply border-t border-gray-200 dark:border-gray-700 font-semibold;
}

.badge {
  @apply px-1.5 py-0.5 rounded text-[10px] uppercase tracking-wide font-semibold;
  @apply bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300;
}
</style>
