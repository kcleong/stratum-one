<script setup lang="ts">
import { computed } from 'vue'
import type { Client } from '../api/types'
import { fmtAgo, fmtLog2, fmtNum } from '../lib/format'

const props = defineProps<{ clients: Client[]; max?: number }>()
const rows = computed(() =>
  // Server-side: the busiest 50 plus LAN clients. Busiest first.
  props.clients
    .filter((c) => c.ntp_packets > 0)
    .sort((a, b) => b.ntp_packets - a.ntp_packets)
    .slice(0, props.max),
)

// Regional-indicator pair: "NL" -> 🇳🇱
const flag = (cc: string) => String.fromCodePoint(...[...cc.toUpperCase()].map((ch) => 0x1f1a5 + ch.charCodeAt(0)))

// Private/loopback/link-local: no country or provider to show.
const isLan = (a: string) => /^(10\.|127\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.|f[cd][0-9a-f]{2}:|fe80:|::1$)/i.test(a)

// IPv6 shortened to its /64 network; the full address is in the tooltip.
const shortAddr = (a: string) => (a.includes(':') ? `${a.split(':').slice(0, 4).join(':')}:…` : a)

const regionName = new Intl.DisplayNames(undefined, { type: 'region' })
const country = (cc: string) => {
  try {
    return regionName.of(cc) ?? cc
  } catch {
    return cc
  }
}
</script>

<template>
  <p v-if="!rows.length" class="sub">No NTP clients since chronyd started.</p>
  <div v-else class="table-scroll">
    <table>
      <thead>
        <tr>
          <th>Client</th>
          <th>Country</th>
          <th>Provider</th>
          <th class="r">Requests</th>
          <th class="r">Dropped</th>
          <th class="r">Interval</th>
          <th class="r">Last seen</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="c in rows" :key="c.address">
          <td class="num" :title="c.address">{{ shortAddr(c.address) }}</td>
          <td>
            <template v-if="c.country">
              <span aria-hidden="true">{{ flag(c.country) }}</span> <span :title="country(c.country)">{{ c.country }}</span>
            </template>
            <span v-else-if="isLan(c.address)" class="sub">LAN</span>
          </td>
          <td class="provider" :title="c.asn ? `AS${c.asn} ${c.asn_org ?? ''}` : undefined">{{ c.asn_org ?? '' }}</td>
          <td class="r">{{ fmtNum(c.ntp_packets) }}</td>
          <td class="r">{{ fmtNum(c.ntp_dropped) }}</td>
          <td class="r">{{ fmtLog2(c.ntp_interval) }}</td>
          <td class="r">{{ fmtAgo(c.ntp_last_rx_s) }} ago</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.provider {
  max-width: 24ch;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
