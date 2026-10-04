import { onBeforeUnmount, onMounted, ref, shallowRef, watch, type Ref } from 'vue'
import type { Burst, Client, HistoryPoint, PoolHistory, Provider, SkyCoverage, Status } from './types'

/** Live /api/status over the WebSocket, reconnecting on loss. */
export function useLiveStatus() {
  const status = shallowRef<Status | null>(null)
  const connected = ref(false)
  /** Server clock minus browser clock, seconds (so the clock shows lobsang's time). */
  const clockDelta = ref(0)
  let ws: WebSocket | null = null
  let retry: number | undefined
  let stopped = false

  function connect() {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    ws = new WebSocket(`${proto}://${location.host}/api/ws?interval=1`)
    ws.onopen = () => (connected.value = true)
    ws.onmessage = (e) => {
      const s: Status = JSON.parse(e.data)
      status.value = s
      clockDelta.value = s.time - Date.now() / 1000
    }
    ws.onclose = () => {
      connected.value = false
      if (!stopped) retry = window.setTimeout(connect, 2000)
    }
  }

  onMounted(connect)
  onBeforeUnmount(() => {
    stopped = true
    clearTimeout(retry)
    ws?.close()
  })
  return { status, connected, clockDelta }
}

/** Ranges up to this many minutes are raw 5 s samples served from memory. */
export const RAW_MAX_MINUTES = 24 * 60

/**
 * /api/history for the last `minutes`. Raw ranges (≤ 24 h) are topped up
 * incrementally every 5 s; longer, bucket-averaged ranges refetch every minute.
 */
export function useHistory(minutes: Ref<number>) {
  const samples = shallowRef<HistoryPoint[]>([])
  const bucketSeconds = ref(5)
  const loading = ref(false)
  let timer: number | undefined
  let slowTimer: number | undefined

  async function fetchSince(mins: number): Promise<HistoryPoint[]> {
    const res = await fetch(`/api/history?minutes=${mins}`)
    if (!res.ok) throw new Error(`history: HTTP ${res.status}`)
    bucketSeconds.value = Number(res.headers.get('X-History-Bucket-Seconds')) || 5
    return res.json()
  }

  async function reload(dim = true) {
    loading.value = dim
    try {
      samples.value = await fetchSince(minutes.value)
    } catch (e) {
      console.warn(e)
    } finally {
      loading.value = false
    }
  }

  async function topUp() {
    if (minutes.value > RAW_MAX_MINUTES) return // handled by the slow refresh
    const last = samples.value.at(-1)
    if (!last) return reload(false)
    try {
      const gap = (Date.now() / 1000 - last.t) / 60 + 0.25
      const fresh = (await fetchSince(Math.max(gap, 0.1))).filter((s) => s.t > last.t)
      if (!fresh.length) return
      const cutoff = Date.now() / 1000 - minutes.value * 60
      samples.value = [...samples.value.filter((s) => s.t >= cutoff), ...fresh]
    } catch (e) {
      console.warn(e)
    }
  }

  watch(minutes, () => reload())
  onMounted(() => {
    reload()
    timer = window.setInterval(topUp, 5000)
    slowTimer = window.setInterval(() => minutes.value > RAW_MAX_MINUTES && reload(false), 60000)
  })
  onBeforeUnmount(() => {
    clearInterval(timer)
    clearInterval(slowTimer)
  })
  return { samples, bucketSeconds, loading }
}

/** Sky coverage (sampled every 30 s by the API), fetched only while `enabled`, every minute. */
export function useSky(enabled: Ref<boolean>) {
  const sky = shallowRef<SkyCoverage | null>(null)
  let timer: number | undefined
  async function load() {
    if (!enabled.value) return
    try {
      const res = await fetch('/api/gps/sky')
      if (res.ok) sky.value = await res.json()
    } catch (e) {
      console.warn(e)
    }
  }
  watch(enabled, load)
  onMounted(() => {
    load()
    timer = window.setInterval(load, 60000)
  })
  onBeforeUnmount(() => clearInterval(timer))
  return { sky }
}

/** NTP Pool scores for the last `minutes`; fetched every POOL_INTERVAL by the API, so refetch every minute. */
export function usePool(minutes: Ref<number>) {
  const pool = shallowRef<PoolHistory | null>(null)
  let timer: number | undefined
  async function load() {
    try {
      const res = await fetch(`/api/pool?minutes=${minutes.value}`)
      if (res.ok) pool.value = await res.json()
    } catch (e) {
      console.warn(e)
    }
  }
  watch(minutes, load)
  onMounted(() => {
    load()
    timer = window.setInterval(load, 60000)
  })
  onBeforeUnmount(() => clearInterval(timer))
  return { pool }
}

/** NTP clients, their top providers and traffic bursts change slowly; poll every 30 s. */
export function useClients() {
  const clients = shallowRef<Client[]>([])
  const providers = shallowRef<Provider[]>([])
  const bursts = shallowRef<Burst[]>([])
  let timer: number | undefined
  async function load() {
    try {
      const [c, p, b] = await Promise.all([fetch('/api/chrony/clients'), fetch('/api/chrony/providers'), fetch('/api/bursts')])
      if (c.ok) clients.value = await c.json()
      if (p.ok) providers.value = await p.json()
      if (b.ok) bursts.value = await b.json()
    } catch (e) {
      console.warn(e)
    }
  }
  onMounted(() => {
    load()
    timer = window.setInterval(load, 30000)
  })
  onBeforeUnmount(() => clearInterval(timer))
  return { clients, providers, bursts }
}
