<script setup lang="ts">
import { connect } from 'echarts/core'
import { computed, ref, watch } from 'vue'
import { useClients, useHistory, useLiveStatus, usePool } from './api/live'
import ClientsTable from './components/ClientsTable.vue'
import ConstellationLegend from './components/ConstellationLegend.vue'
import HistoryChart, { type Series } from './components/HistoryChart.vue'
import KeyValues from './components/KeyValues.vue'
import ProvidersTable from './components/ProvidersTable.vue'
import SatelliteTable from './components/SatelliteTable.vue'
import SkyPlot from './components/SkyPlot.vue'
import SnrBars from './components/SnrBars.vue'
import SourcesTable from './components/SourcesTable.vue'
import StatTile from './components/StatTile.vue'
import StatusPill from './components/StatusPill.vue'
import UtcClock from './components/UtcClock.vue'
import './lib/echarts'
import { fmtAgo, fmtBytes, fmtNum, fmtOffset, fmtSpan, fmtUptime } from './lib/format'
import { INFO } from './lib/glossary'
import { cycleTheme, themePref } from './lib/theme'

connect('history') // shared crosshair and zoom across the history charts

const { status, connected, clockDelta } = useLiveStatus()
const RANGES = [
  { label: '1 h', minutes: 60 },
  { label: '6 h', minutes: 360 },
  { label: '24 h', minutes: 1440 },
  { label: '7 d', minutes: 7 * 1440 },
  { label: '30 d', minutes: 30 * 1440 },
]
const minutes = ref(60)
const { samples, bucketSeconds, loading } = useHistory(minutes)
const { clients, providers } = useClients()
const CLIENT_ROWS = 20
const { pool } = usePool(minutes)

const gps = computed(() => status.value?.gps)

// Sky view filter, remembered per browser.
const skyUsedOnly = ref(readFlag('skyUsedOnly'))
watch(skyUsedOnly, (v) => writeFlag('skyUsedOnly', v))
const skySatellites = computed(() => (gps.value?.satellites ?? []).filter((s) => !skyUsedOnly.value || s.used))

function readFlag(key: string): boolean {
  try {
    return localStorage.getItem(key) === '1'
  } catch {
    return false
  }
}
function writeFlag(key: string, v: boolean) {
  try {
    localStorage.setItem(key, v ? '1' : '0')
  } catch {
    /* storage blocked: keep in memory only */
  }
}
const chrony = computed(() => status.value?.chrony)
const tracking = computed(() => chrony.value?.tracking ?? null)
const sys = computed(() => status.value?.system)
const pps = computed(() => chrony.value?.sources.find((s) => s.mode === 'refclock' && s.name === 'PPS'))
const selected = computed(() => chrony.value?.sources.find((s) => s.state === 'selected'))

type Level = 'good' | 'warning' | 'serious' | 'critical' | 'neutral'
const pills = computed(() => {
  const out: { level: Level; label: string; title?: string }[] = []
  if (!connected.value) out.push({ level: 'critical', label: 'Disconnected', title: 'WebSocket to lobsang lost; retrying' })
  const c = chrony.value
  if (c && !c.ok) out.push({ level: 'critical', label: 'chrony unreachable', title: c.error ?? undefined })
  const sel = selected.value
  if (sel?.mode === 'refclock' && sel.name === 'PPS') out.push({ level: 'good', label: 'PPS locked' })
  else if (sel) out.push({ level: 'warning', label: `Fallback: ${sel.name}`, title: 'PPS not selected; using another source' })
  else if (c) out.push({ level: 'critical', label: 'No time source' })
  const g = gps.value
  if (g && !g.connected) out.push({ level: 'critical', label: 'gpsd down' })
  else if (g?.fix.mode === '3d') out.push({ level: 'good', label: '3D fix' })
  else if (g?.fix.mode === '2d') out.push({ level: 'warning', label: '2D fix' })
  else if (g) out.push({ level: 'critical', label: 'No GPS fix' })
  const leap = tracking.value?.leap_status
  if (leap && leap !== 'Normal') out.push({ level: leap === 'Not synchronised' ? 'critical' : 'warning', label: leap })
  return out
})

const ipv6Share = computed(() => {
  const c = chrony.value
  return c?.active_clients && c.active_clients_ipv6 != null ? (100 * c.active_clients_ipv6) / c.active_clients : null
})

const tiles = computed(() => {
  const t = tracking.value
  const g = gps.value
  const s = sys.value
  const p = pps.value
  return [
    { label: 'System offset', value: fmtOffset(t?.system_time_offset_s), sub: '+ = clock ahead of true time' },
    { label: 'RMS offset', value: fmtSpan(t?.rms_offset_s), sub: `last ${fmtOffset(t?.last_offset_s)}` },
    { label: 'PPS offset', value: fmtOffset(p?.offset_s), sub: p ? `± ${fmtSpan(p.error_s)}` : 'no PPS source' },
    { label: 'Frequency', value: fmtNum(t?.frequency_ppm, 3, ' ppm'), sub: `skew ${fmtNum(t?.skew_ppm, 3)} ppm` },
    { label: 'Stratum', value: t ? String(t.stratum) : '–', sub: `ref ${t?.ref_name ?? '–'}` },
    {
      label: 'Satellites used',
      value: g ? `${g.satellites_used} / ${g.satellites_visible}` : '–',
      sub: `HDOP ${fmtNum(g?.dop.hdop, 2)} · PDOP ${fmtNum(g?.dop.pdop, 2)}`,
    },
    {
      label: 'NTP clients',
      value: fmtNum(chrony.value?.active_clients),
      sub: `${fmtNum(ipv6Share.value, 0, ' %')} IPv6 · ${fmtNum(chrony.value?.ntp_requests_per_s, 1)} req/s · ${fmtNum(chrony.value?.client_count)} since start`,
    },
    { label: 'CPU temperature', value: fmtNum(s?.cpu_temp_c, 1, ' °C'), sub: `load ${fmtNum(s?.load?.[0], 2)}` },
  ].map((tile) => ({ ...tile, info: INFO[tile.label] }))
})

const us = (v: number | null | undefined) => (v == null ? null : v * 1e6)
const hist = computed(() => {
  const h = samples.value
  const at = <T,>(f: (s: (typeof h)[number]) => T) => h.map((s) => [s.t * 1000, f(s)] as [number, T])
  // Bucket-averaged ranges carry min/max per bucket: show them as a band so spikes stay visible.
  const bucketed = h.some((s) => s.system_time_offset_min_s != null)
  const band = (lo: (s: (typeof h)[number]) => number | null | undefined, hi: typeof lo) =>
    bucketed ? { min: h.map((s) => us(lo(s))), max: h.map((s) => us(hi(s))) } : undefined
  return {
    offset: [
      {
        name: 'System offset',
        slot: 1,
        data: at((s) => us(s.system_time_offset_s)),
        band: band((s) => s.system_time_offset_min_s, (s) => s.system_time_offset_max_s),
      },
      {
        name: 'PPS offset',
        slot: 2,
        data: at((s) => us(s.pps_offset_s)),
        band: band((s) => s.pps_offset_min_s, (s) => s.pps_offset_max_s),
      },
    ] as Series[],
    frequency: [{ name: 'Frequency', slot: 1, data: at((s) => s.frequency_ppm) }] as Series[],
    satellites: [
      { name: 'Used', slot: 1, data: at((s) => s.satellites_used), step: true },
      { name: 'Visible', data: at((s) => s.satellites_visible), step: true, dashed: true },
    ] as Series[],
    temperature: [{ name: 'CPU temperature', slot: 1, data: at((s) => s.cpu_temp_c) }] as Series[],
    load: [{ name: 'NTP requests', slot: 1, data: at((s) => s.ntp_requests_per_s ?? null) }] as Series[],
  }
})

// One line per POOL_SERVERS address, plus the DNS threshold across the history range
// (which also pins the x extent, so zoom stays in step with the other charts).
const POOL_DNS_SCORE = 10
const poolSeries = computed(() => {
  const p = pool.value
  if (!p?.servers.length) return null
  const h = samples.value
  const first = h[0]?.t ?? p.scores[0]?.t
  const last = h.at(-1)?.t ?? p.scores.at(-1)?.t
  const span = first != null && last != null ? [first * 1000, last * 1000] : []
  return [
    ...p.servers.map((server, i) => ({
      name: server,
      slot: i + 1,
      data: p.scores.filter((s) => s.server === server).map((s) => [s.t * 1000, s.score] as [number, number]),
    })),
    { name: 'Pool DNS threshold', dashed: true, data: span.map((x) => [x, POOL_DNS_SCORE] as [number, number]) },
  ] as Series[]
})

const resolution = computed(() => {
  const b = bucketSeconds.value
  if (b <= 5) return 'every 5 s'
  const label = b < 3600 ? `${b / 60} min` : `${b / 3600} h`
  return `${label} averages, band = min…max`
})

const serverStats = computed<[string, string][]>(() => {
  const s = chrony.value?.serverstats
  if (!s) return []
  return [
    ['NTP requests', fmtNum(s.ntp_packets_received)],
    ['NTP dropped', fmtNum(s.ntp_packets_dropped)],
    ['NTS-KE accepted', fmtNum(s.nts_ke_accepted)],
    ['Authenticated NTP', fmtNum(s.authenticated_ntp_packets)],
    ['Interleaved NTP', fmtNum(s.interleaved_ntp_packets)],
    ['Kernel RX timestamps', fmtNum(s.ntp_kernel_rx_timestamps)],
    ['Command requests', fmtNum(s.cmd_packets_received)],
  ]
})

const systemInfo = computed<[string, string][]>(() => {
  const s = sys.value
  const g = gps.value
  const t = tracking.value
  if (!s || !g) return []
  const fw = (g.device.subtype1 ?? '').split(',')[0].replace('FWVER=', '')
  return [
    ['Host', s.hostname],
    ['Uptime', fmtUptime(s.uptime_s)],
    ['Load', s.load?.map((l) => l.toFixed(2)).join(' · ') ?? '–'],
    ['Memory free', `${fmtBytes(s.mem_available_bytes)} of ${fmtBytes(s.mem_total_bytes)}`],
    ['Receiver', `${g.device.driver ?? '–'} ${fw}`.trim()],
    ['Serial', `${g.device.path ?? '–'} @ ${fmtNum(g.device.bps)} bps`],
    ['gpsd', `${g.gpsd_version ?? '–'} · last report ${fmtAgo(g.age_s)} ago`],
    ['Position', g.fix.lat != null ? `${g.fix.lat.toFixed(5)}, ${g.fix.lon?.toFixed(5)}` : '–'],
    ['Altitude (MSL)', `${fmtNum(g.fix.alt_msl_m, 1, ' m')} ± ${fmtNum(g.fix.epv_m, 0, ' m')}`],
    ['Root delay / dispersion', `${fmtSpan(t?.root_delay_s)} / ${fmtSpan(t?.root_dispersion_s)}`],
    ['Update interval', `${fmtNum(t?.update_interval_s, 1, ' s')}`],
  ]
})
</script>

<template>
  <header>
    <div class="brand">
      <strong>{{ sys?.hostname ?? 'stratum_one' }}</strong>
      <span class="sub">GPS/PPS stratum-1 NTP</span>
    </div>
    <div class="pills">
      <StatusPill v-for="p in pills" :key="p.label" v-bind="p" />
    </div>
    <nav>
      <a href="/docs" target="_blank" rel="noopener">API</a>
      <button type="button" class="ghost" :title="`Theme: ${themePref}`" @click="cycleTheme">
        {{ themePref === 'auto' ? '◐' : themePref === 'light' ? '☀' : '☾' }} {{ themePref }}
      </button>
    </nav>
  </header>

  <main v-if="status">
    <section class="hero">
      <UtcClock :clock-delta="clockDelta" :leapseconds="gps?.fix.leapseconds" :reference="tracking?.ref_name ?? null" />
      <div class="tiles">
        <StatTile v-for="t in tiles" :key="t.label" v-bind="t" />
      </div>
    </section>

    <div class="filters" role="group" aria-label="History range">
      <span class="sub">History</span>
      <button
        v-for="r in RANGES"
        :key="r.minutes"
        type="button"
        :class="{ active: minutes === r.minutes }"
        :aria-pressed="minutes === r.minutes"
        @click="minutes = r.minutes"
      >
        {{ r.label }}
      </button>
      <span class="sub">{{ samples.length }} points · {{ resolution }}</span>
    </div>

    <section class="charts">
      <HistoryChart title="Clock offset" unit="µs" :series="hist.offset" include-zero :dimmed="loading" />
      <HistoryChart title="Oscillator frequency" unit="ppm" :series="hist.frequency" :digits="3" :dimmed="loading" />
      <HistoryChart title="Satellites" unit="sats" :series="hist.satellites" :digits="0" include-zero :dimmed="loading" />
      <HistoryChart title="CPU temperature" unit="°C" :series="hist.temperature" :digits="1" :dimmed="loading" />
      <HistoryChart title="NTP load" unit="req/s" :series="hist.load" :digits="1" include-zero :dimmed="loading" />
      <HistoryChart v-if="poolSeries" title="NTP Pool score" unit="score" :series="poolSeries" :digits="1" include-zero :dimmed="loading" />
    </section>

    <section class="gnss">
      <div class="card">
        <div class="card-head">
          <h2>Sky view</h2>
          <label class="toggle">
            <input v-model="skyUsedOnly" type="checkbox" />
            Used only
          </label>
        </div>
        <SkyPlot v-if="gps" :satellites="skySatellites" />
        <ConstellationLegend v-if="gps" :gps="gps" />
      </div>
      <div class="card">
        <div class="card-head">
          <h2>Signal strength</h2>
          <span class="sub">{{ gps?.satellites_used }} used of {{ gps?.satellites.length }} tracked</span>
        </div>
        <SnrBars v-if="gps" :satellites="gps.satellites" />
        <SatelliteTable v-if="gps" :satellites="gps.satellites" />
      </div>
    </section>

    <section class="card">
      <div class="card-head">
        <h2>Time sources</h2>
        <span class="sub">chrony · selected: {{ chrony?.selected_source ?? 'none' }}</span>
      </div>
      <SourcesTable v-if="chrony" :sources="chrony.sources" :stats="chrony.sourcestats" />
    </section>

    <section class="card">
      <div class="card-head">
        <h2>NTP clients</h2>
        <span class="sub">busiest {{ Math.min(CLIENT_ROWS, chrony?.client_count ?? 0) }} of {{ fmtNum(chrony?.client_count) }} · since chronyd start</span>
      </div>
      <ClientsTable :clients="clients" :max="CLIENT_ROWS" />
    </section>

    <section class="card">
      <div class="card-head">
        <h2>Top providers</h2>
        <span class="sub">networks of the {{ fmtNum(chrony?.active_clients) }} clients active in the last hour</span>
      </div>
      <ProvidersTable :providers="providers" :active="chrony?.active_clients ?? 0" />
      <p class="sub credit">Country and provider: <a href="https://db-ip.com" target="_blank" rel="noopener">IP data by DB-IP</a> (CC BY 4.0)</p>
    </section>

    <section class="bottom">
      <div class="card">
        <div class="card-head"><h2>Server statistics</h2></div>
        <KeyValues :items="serverStats" />
      </div>
      <div class="card">
        <div class="card-head"><h2>System</h2></div>
        <KeyValues :items="systemInfo" />
      </div>
    </section>
  </main>
  <main v-else class="waiting">
    <p class="sub">{{ connected ? 'Waiting for data…' : 'Connecting to lobsang…' }}</p>
  </main>
</template>

<style scoped>
header {
  position: sticky;
  top: 0;
  z-index: 10;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 16px;
  padding: 10px 16px;
  background: var(--page);
  border-bottom: 1px solid var(--border);
}
.brand {
  display: flex;
  align-items: baseline;
  gap: 8px;
}
.brand strong {
  font-size: 16px;
}
.pills {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  flex: 1;
}
nav {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 13px;
}
main {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 12px 16px 32px;
  max-width: 1480px;
  margin: 0 auto;
}
.waiting {
  padding-top: 20vh;
  align-items: center;
}
.hero {
  display: grid;
  grid-template-columns: minmax(280px, 1fr) 2fr;
  gap: 12px;
}
.tiles {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}
.filters {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}
button {
  font: inherit;
  font-size: 13px;
  color: var(--ink);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 4px 10px;
  cursor: pointer;
}
button:hover {
  background: var(--surface-2);
}
button.active {
  border-color: var(--ink-2);
  font-weight: 600;
}
button.ghost {
  border-color: transparent;
  background: none;
  color: var(--ink-2);
}
.toggle {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--ink-2);
  cursor: pointer;
  user-select: none;
}
.toggle input {
  margin: 0;
  accent-color: var(--series-1);
}
.charts {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}
.gnss {
  display: grid;
  grid-template-columns: minmax(0, 2fr) minmax(0, 3fr);
  gap: 12px;
}
.bottom {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}
.credit {
  margin: 8px 0 0;
  font-size: 11px;
}
.credit a {
  color: inherit;
}
@media (max-width: 1100px) {
  .hero,
  .gnss,
  .bottom {
    grid-template-columns: 1fr;
  }
}
@media (max-width: 760px) {
  .tiles,
  .charts {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .charts {
    grid-template-columns: 1fr;
  }
}
</style>
