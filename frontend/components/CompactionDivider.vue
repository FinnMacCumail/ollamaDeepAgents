<template>
  <div class="compaction-divider" role="separator">
    <span class="line"></span>
    <span class="label">
      Context compacted: {{ formatTokens(beforeTokens) }} → {{ formatTokens(afterTokens) }} tokens
    </span>
    <span class="line"></span>
  </div>
</template>

<script setup lang="ts">
import { formatTokens } from '~/utils/formatters'

defineProps<{
  beforeTokens: number
  afterTokens: number
}>()
</script>

<style scoped>
.compaction-divider {
  @apply my-4 flex items-center gap-3 text-xs;
}

.line {
  @apply flex-1 h-px bg-purple-300 dark:bg-purple-700;
}

.label {
  @apply px-2 py-0.5 rounded-full font-medium;
  @apply bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300;
}
</style>
