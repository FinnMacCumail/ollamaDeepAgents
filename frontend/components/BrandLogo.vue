<template>
  <a
    class="brand"
    :href="href"
    target="_blank"
    rel="noopener noreferrer"
    title="RTF research — open rtf.spc.org in a new tab"
    aria-label="RTF research (opens rtf.spc.org in a new tab)"
  >
    <!-- Mark: three linked nodes (a network) with the active node lit — research on live infrastructure. -->
    <svg
      class="brand-mark"
      :width="size"
      :height="size"
      viewBox="0 0 40 40"
      role="img"
      aria-hidden="true"
    >
      <defs>
        <linearGradient id="rtf-bg" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stop-color="#1e3a8a" />
          <stop offset="1" stop-color="#2563eb" />
        </linearGradient>
      </defs>
      <rect x="1" y="1" width="38" height="38" rx="10" fill="url(#rtf-bg)" />
      <!-- links -->
      <path
        d="M12.5 27.5 L20 12.5 L27.5 27.5 Z"
        fill="none"
        stroke="rgba(255,255,255,0.55)"
        stroke-width="2"
        stroke-linejoin="round"
      />
      <!-- nodes -->
      <circle cx="12.5" cy="27.5" r="3.4" fill="#ffffff" />
      <circle cx="27.5" cy="27.5" r="3.4" fill="#ffffff" />
      <circle cx="20" cy="12.5" r="4.2" fill="#93c5fd" />
      <circle cx="20" cy="12.5" r="1.7" fill="#1e3a8a" />
    </svg>

    <span class="brand-text">
      <span class="brand-name">RTF</span>
      <span class="brand-suffix">research</span>
    </span>
  </a>
</template>

<script setup lang="ts">
withDefaults(defineProps<{ size?: number; href?: string }>(), {
  size: 34,
  href: 'https://rtf.spc.org/'
})
</script>

<style scoped>
.brand {
  @apply inline-flex items-center gap-2.5 select-none;
  @apply no-underline;
  @apply rounded-lg px-1 py-0.5 -ml-1;
  @apply transition-colors;
}
.brand:hover {
  @apply bg-gray-100 dark:bg-gray-700/60;
}
.brand:focus-visible {
  @apply outline-none ring-2 ring-blue-500;
}
.brand-mark {
  @apply flex-shrink-0;
  filter: drop-shadow(0 1px 1px rgba(30, 58, 138, 0.25));
}
.brand-text {
  @apply flex items-baseline gap-1.5 whitespace-nowrap leading-none;
}
.brand-name {
  @apply text-lg font-extrabold tracking-tight;
  @apply text-blue-800 dark:text-blue-300;
}
.brand-suffix {
  @apply text-base font-medium tracking-wide;
  @apply text-gray-600 dark:text-gray-300;
}
</style>
