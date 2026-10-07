<script setup lang="ts">
import { computed, ref } from 'vue'
import type { Burst, BurstClient } from '../api/types'
import { countryName, flag } from '../lib/country'
import { fmtLog2, fmtNum, fmtUptime } from '../lib/format'

const props = defineProps<{ bursts: Burst[]; max: number }>()

const ROWS = 8

// Newest `max` by default: on a busy pool server there are several bursts a day.
const all = ref(false)
const shown = computed(() => (all.value ? props.bursts : props.bursts.slice(0, props.max)))
const hidden = computed(() => props.bursts.length - shown.value.length)

const when = (t: number) =>
  new Date(t * 1000).toLocaleString(undefined, { hour12: false, month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
const duration = (b: Burst) => {
  const s = (b.end ?? Date.now() / 1000) - b.start
  return s < 90 ? `${Math.round(s)} s` : s < 3600 ? `${Math.round(s / 60)} min` : fmtUptime(s)
}
const droppedPct = (b: Burst) => (b.ntp_packets ? (100 * b.ntp_dropped) / b.ntp_packets : null)

// IPv6 shortened to its /64 network; the full address is in the tooltip.
const shortAddr = (a: string) => (a.includes(':') ? `${a.split(':').slice(0, 4).join(':')}:…` : a)
const clientTitle = (c: BurstClient) =>
  [c.address, c.country ? countryName(c.country) : null, c.asn ? `AS${c.asn} ${c.asn_org ?? ''}` : null, `polls every ${fmtLog2(c.ntp_interval)}`]
    .filter(Boolean)
    .join(' · ')
</script>

<template>
  <p v-if="!bursts.length" class="sub">No traffic bursts in the kept history.</p>
  <div v-else class="bursts">
    <details v-for="(b, i) in shown" :key="b.start" :open="i === 0">
      <summary>
        <span class="facts">
          <span><b>{{ when(b.start) }}</b> · {{ b.end ? duration(b) : `ongoing, ${duration(b)}` }}</span>
          <span>peak <b>{{ fmtNum(b.peak_req_s) }}</b> req/s</span>
          <span>{{ fmtNum(b.ntp_packets) }} requests, <b>{{ fmtNum(droppedPct(b), 0, ' %') }}</b> dropped</span>
          <span :title="`Addresses with a request in the ${b.window_s} s before the scan`">{{ fmtNum(b.clients) }} clients ({{ fmtNum(b.clients_ipv6) }} IPv6)</span>
        </span>
      </summary>
      <p v-if="b.scanned == null" class="sub pending">{{ b.end ? 'No client scan for this burst.' : 'Client scan pending.' }}</p>
      <div v-else class="detail">
        <div class="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Busiest addresses</th>
                <th class="r">Requests</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="c in b.top_clients.slice(0, ROWS)" :key="c.address">
                <td class="num" :title="clientTitle(c)">
                  <span v-if="c.country" class="flag" aria-hidden="true">{{ flag(c.country) }}</span>
                  {{ shortAddr(c.address) }}
                </td>
                <td class="r">
                  <span v-if="c.ntp_dropped" class="dropped" title="Not answered because of rate limiting">{{ fmtNum(c.ntp_dropped) }} dropped ·</span>
                  {{ fmtNum(c.ntp_packets) }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-if="b.prefixes.length" class="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Networks (/24, /48)</th>
                <th class="r">Clients</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="p in b.prefixes.slice(0, ROWS)" :key="p.prefix">
                <td class="num" :title="`${fmtNum(p.ntp_packets)} requests`">{{ p.prefix }}</td>
                <td class="r">{{ fmtNum(p.clients) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-if="b.providers.length" class="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Providers</th>
                <th class="r">Clients</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="p in b.providers.slice(0, ROWS)" :key="p.asn ?? 'unknown'">
                <td class="provider" :title="[p.asn != null ? `AS${p.asn}` : null, p.country ? `mostly ${countryName(p.country)}` : null].filter(Boolean).join(' · ')">
                  <span v-if="p.country" class="flag" aria-hidden="true">{{ flag(p.country) }}</span>
                  {{ p.asn_org ?? 'Unknown network' }}
                </td>
                <td class="r">{{ fmtNum(p.clients) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </details>
    <button v-if="hidden || all" type="button" class="more" :class="{ open: all }" @click="all = !all">
      <span v-if="all">Show the newest <b>{{ max }}</b></span>
      <span v-else><b>{{ hidden }}</b> older {{ hidden === 1 ? 'burst' : 'bursts' }} · show all</span>
    </button>
  </div>
</template>

<style scoped>
.bursts {
  display: grid;
  gap: 8px;
}
/* Marker in its own column, so wrapped facts line up under the first one. */
summary {
  display: grid;
  grid-template-columns: 10px minmax(0, 1fr);
  gap: 6px;
  cursor: pointer;
  color: var(--ink-2);
  list-style: none;
}
.facts {
  display: flex;
  flex-wrap: wrap;
  gap: 2px 14px;
}
.facts > span {
  white-space: nowrap;
}
summary::-webkit-details-marker {
  display: none;
}
/* flex hides the native marker; draw our own */
summary::before {
  content: '▸';
  align-self: start;
  text-align: center;
  color: var(--muted);
  transition: transform 0.15s;
}
details[open] > summary::before {
  transform: rotate(90deg);
}
summary b {
  color: var(--ink);
}
/* Columns only when each table fits without scrolling (address + dropped + requests). */
.detail {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 320px), 1fr));
  gap: 12px;
  margin: 8px 0 4px 16px;
}
.pending {
  margin: 6px 0 0 16px;
}
/* Reads as one more row: same marker column as the summaries, ▾ instead of ▸. */
.more {
  display: grid;
  grid-template-columns: 10px minmax(0, 1fr);
  gap: 6px;
  justify-self: start;
  padding: 2px 6px 2px 0;
  border: 0;
  border-radius: 4px;
  background: none;
  color: var(--ink-2);
  font-size: 13px;
  text-align: left;
}
.more::before {
  content: '▾';
  text-align: center;
  color: var(--muted);
  transition: transform 0.15s;
}
.more.open::before {
  transform: rotate(180deg);
}
.more:hover {
  background: none;
  color: var(--ink);
}
.more:hover::before {
  color: var(--ink-2);
}
.more:focus-visible {
  outline: 2px solid var(--series-1);
  outline-offset: 2px;
}
.more b {
  color: var(--ink);
}
.provider {
  max-width: 24ch;
  overflow: hidden;
  text-overflow: ellipsis;
}
.flag {
  margin-right: 6px;
}
.dropped {
  color: var(--ink);
  font-weight: 600;
}
</style>
