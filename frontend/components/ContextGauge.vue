<template>
  <div class="context-gauge" :class="levelClass" :title="tooltip">
    <div class="gauge-label">
      <span class="gauge-title">Context</span>
      <span class="gauge-value">
        <template v-if="contextTokens != null && nCtx">
          {{ formatTokens(contextTokens) }} / {{ formatTokens(nCtx) }} ({{ pct }}%)
        </template>
        <template v-else-if="contextTokens != null">
          {{ formatTokens(contextTokens) }} tokens
        </template>
        <template v-else>n/a</template>
      </span>
    </div>
    <div class="gauge-track">
      <div class="gauge-fill" :style="{ width: fillWidth }"></div>
      <div v-if="triggerPct !== null" class="gauge-marker" :style="{ left: `${triggerPct}%` }" title="Compaction trigger (0.85 of window)"></div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { formatTokens } from '~/utils/formatters'

interface Props {
  /** Prompt tokens of the last model call (resident context). */
  contextTokens: number | null
  /** Server window (n_ctx). */
  nCtx: number | null
  /** Token count at which DeepAgents compacts (0.85 * n_ctx). */
  compactionTriggerTokens?: number | null
  /** True while a turn is streaming (gauge is live). */
  live?: boolean
}

const props = withDefaults(defineProps<Props>(), { compactionTriggerTokens: null, live: false })

const pct = computed(() => {
  if (props.contextTokens == null || !props.nCtx) return null
  return Math.round((props.contextTokens / props.nCtx) * 1000) / 10
})

const fillWidth = computed(() => (pct.value === null ? '0%' : `${Math.min(100, pct.value)}%`))

const triggerPct = computed(() => {
  if (!props.nCtx || !props.compactionTriggerTokens) return null
  return Math.min(100, Math.round((props.compactionTriggerTokens / props.nCtx) * 1000) / 10)
})

const levelClass = computed(() => {
  if (pct.value === null) return 'level-none'
  if (pct.value >= 85) return 'level-red'
  if (pct.value >= 50) return 'level-amber'
  return 'level-neutral'
})

const tooltip = computed(() => {
  const parts = [
    'Resident context = prompt tokens of the last model call, as reported by llama-server.',
    'Decode slows as context grows: measured 14.8 -> 12.6 t/s from 9k to 46k, and 5.1 -> 1.45 t/s by 76k.',
    props.compactionTriggerTokens
      ? `Compaction (summarisation) triggers at ${formatTokens(props.compactionTriggerTokens)} tokens.`
      : '',
    '"New conversation" resets it.'
  ]
  return parts.filter(Boolean).join(' ')
})
</script>

<style scoped>
.context-gauge {
  @apply flex flex-col gap-1 min-w-[180px];
}

.gauge-label {
  @apply flex items-center justify-between text-xs;
}

.gauge-title {
  @apply font-medium text-gray-600 dark:text-gray-300;
}

.gauge-value {
  @apply font-mono text-gray-700 dark:text-gray-200 whitespace-nowrap;
}

.gauge-track {
  @apply relative h-2 rounded-full bg-gray-200 dark:bg-gray-700 overflow-visible;
}

.gauge-fill {
  @apply h-full rounded-full transition-all duration-500;
}

.level-none .gauge-fill { @apply bg-gray-300 dark:bg-gray-600; }
.level-neutral .gauge-fill { @apply bg-blue-500; }
.level-amber .gauge-fill { @apply bg-amber-500; }
.level-red .gauge-fill { @apply bg-red-500; }

.level-amber .gauge-value { @apply text-amber-700 dark:text-amber-300; }
.level-red .gauge-value { @apply text-red-700 dark:text-red-300 font-semibold; }

.gauge-marker {
  @apply absolute top-[-3px] h-[14px] w-[2px] bg-gray-500 dark:bg-gray-300;
}
</style>
