import { onBeforeUnmount, onMounted, ref, shallowRef, watch, type Ref } from 'vue'
import type { Client, HistorySample, Status } from './types'

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

/** /api/history for the last `minutes`, topped up incrementally every 5 s. */
export function useHistory(minutes: Ref<number>) {
  const samples = shallowRef<HistorySample[]>([])
  const loading = ref(false)
  let timer: number | undefined

  async function fetchSince(mins: number): Promise<HistorySample[]> {
    const res = await fetch(`/api/history?minutes=${Math.min(mins, 1440)}`)
    if (!res.ok) throw new Error(`history: HTTP ${res.status}`)
    return res.json()
  }

  async function reload() {
    loading.value = true
    try {
      samples.value = await fetchSince(minutes.value)
    } catch (e) {
      console.warn(e)
    } finally {
      loading.value = false
    }
  }

  async function topUp() {
    const last = samples.value.at(-1)
    if (!last) return reload()
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

  watch(minutes, reload)
  onMounted(() => {
    reload()
    timer = window.setInterval(topUp, 5000)
  })
  onBeforeUnmount(() => clearInterval(timer))
  return { samples, loading }
}

/** NTP clients change slowly; poll every 30 s. */
export function useClients() {
  const clients = shallowRef<Client[]>([])
  let timer: number | undefined
  async function load() {
    try {
      const res = await fetch('/api/chrony/clients')
      if (res.ok) clients.value = await res.json()
    } catch (e) {
      console.warn(e)
    }
  }
  onMounted(() => {
    load()
    timer = window.setInterval(load, 30000)
  })
  onBeforeUnmount(() => clearInterval(timer))
  return { clients }
}
