<template>
  <div class="loading-spinner" :class="sizeClass" role="status" :aria-label="ariaLabel">
    <svg class="spinner" viewBox="0 0 50 50">
      <circle
        class="spinner-path"
        cx="25"
        cy="25"
        r="20"
        fill="none"
        stroke-width="5"
      ></circle>
    </svg>
  </div>
</template>

<script setup lang="ts">
interface Props {
  size?: 'sm' | 'md' | 'lg'
  ariaLabel?: string
}

const props = withDefaults(defineProps<Props>(), {
  size: 'md',
  ariaLabel: 'Loading'
})

const sizeClass = computed(() => {
  switch (props.size) {
    case 'sm':
      return 'spinner-sm'
    case 'lg':
      return 'spinner-lg'
    default:
      return 'spinner-md'
  }
})
</script>

<style scoped>
.loading-spinner {
  display: inline-block;
  flex-shrink: 0;
}

.spinner {
  animation: rotate 1s linear infinite;
}

.spinner-path {
  stroke: currentColor;
  stroke-linecap: round;
  animation: dash 1.5s ease-in-out infinite;
}

/* Size variants */
.spinner-sm {
  @apply w-4 h-4;
}

.spinner-md {
  @apply w-6 h-6;
}

.spinner-lg {
  @apply w-8 h-8;
}

/* Color variants */
.loading-spinner {
  @apply text-blue-600 dark:text-blue-400;
}

/* Animations */
@keyframes rotate {
  100% {
    transform: rotate(360deg);
  }
}

@keyframes dash {
  0% {
    stroke-dasharray: 1, 150;
    stroke-dashoffset: 0;
  }
  50% {
    stroke-dasharray: 90, 150;
    stroke-dashoffset: -35;
  }
  100% {
    stroke-dasharray: 90, 150;
    stroke-dashoffset: -124;
  }
}
</style>
