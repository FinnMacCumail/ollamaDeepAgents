/**
 * Polls GET /status on the backend: model alias, llama-server slot state,
 * context window and queue depth. Singleton; polls every 10 s while a turn
 * is running and every 60 s when idle.
 */
import type { ServerStatus, ServerStatusWire } from '~/types/chat'

const status = ref<ServerStatus | null>(null)
const statusError = ref<string | null>(null)
const lastFetchedAt = ref<string | null>(null)

let timer: ReturnType<typeof setTimeout> | null = null
let mountedCount = 0
let fetching = false

const RUNNING_INTERVAL_MS = 10_000
const IDLE_INTERVAL_MS = 60_000

const fromWire = (w: ServerStatusWire): ServerStatus => ({
  model: w.model,
  backend: w.backend,
  nCtx: w.n_ctx ?? null,
  compactionTriggerTokens: w.compaction_trigger_tokens ?? null,
  slotBusy: w.slot_busy ?? null,
  promptCacheTokens: w.prompt_cache_tokens ?? null,
  turnRunning: Boolean(w.turn_running),
  queueDepth: Number(w.queue_depth ?? 0),
  generatedAt: w.generated_at
})

const fetchStatus = async () => {
  if (fetching) return
  fetching = true
  const config = useRuntimeConfig()
  try {
    const wire = await $fetch<ServerStatusWire>(`${config.public.apiUrl}/status`, { timeout: 5000 })
    status.value = fromWire(wire)
    statusError.value = null
    lastFetchedAt.value = new Date().toISOString()
  } catch (error) {
    statusError.value = error instanceof Error ? error.message : 'Status unavailable'
  } finally {
    fetching = false
  }
}

const schedule = () => {
  if (timer) clearTimeout(timer)
  const { isProcessing } = useChatSocket()
  const interval = isProcessing.value || status.value?.turnRunning ? RUNNING_INTERVAL_MS : IDLE_INTERVAL_MS
  timer = setTimeout(async () => {
    await fetchStatus()
    if (mountedCount > 0) schedule()
  }, interval)
}

export const useServerStatus = () => {
  const { isProcessing } = useChatSocket()

  onMounted(() => {
    mountedCount++
    if (mountedCount === 1) {
      fetchStatus().then(schedule)
    }
  })

  onUnmounted(() => {
    mountedCount--
    if (mountedCount <= 0) {
      mountedCount = 0
      if (timer) clearTimeout(timer)
      timer = null
    }
  })

  // Re-schedule promptly when a turn starts or ends so the busy indicator is fresh.
  watch(isProcessing, () => {
    if (mountedCount > 0) {
      fetchStatus().then(schedule)
    }
  })

  return {
    status,
    statusError,
    lastFetchedAt,
    refresh: fetchStatus
  }
}
