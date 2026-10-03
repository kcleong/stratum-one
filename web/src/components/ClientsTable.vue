<script setup lang="ts">
import { computed } from 'vue'
import type { Client } from '../api/types'
import { countryName, flag } from '../lib/country'
import { fmtAgo, fmtLog2, fmtNum } from '../lib/format'

const props = defineProps<{ clients: Client[]; max?: number }>()
const rows = computed(() =>
  // Server-side: the busiest 50 plus LAN clients. Busiest first.
  props.clients
    .filter((c) => c.ntp_packets > 0)
    .sort((a, b) => b.ntp_packets - a.ntp_packets)
    .slice(0, props.max),
)

// Private/loopback/link-local: no country or provider to show.
const isLan = (a: string) => /^(10\.|127\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.|f[cd][0-9a-f]{2}:|fe80:|::1$)/i.test(a)

// IPv6 shortened to its /64 network; the full address is in the tooltip.
const shortAddr = (a: string) => (a.includes(':') ? `${a.split(':').slice(0, 4).join(':')}:…` : a)

// Full address, country and polling interval: detail that doesn't need its own column.
const clientTitle = (c: Client) =>
  [c.address, c.country ? countryName(c.country) : isLan(c.address) ? 'LAN' : null, `polls every ${fmtLog2(c.ntp_interval)}`]
    .filter(Boolean)
    .join(' · ')
</script>

<template>
  <p v-if="!rows.length" class="sub">No NTP clients since chronyd started.</p>
  <div v-else class="table-scroll">
    <table>
      <thead>
        <tr>
          <th>Client</th>
          <th>Provider</th>
          <th class="r">Requests</th>
          <th class="r">Last seen</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="c in rows" :key="c.address">
          <td class="num" :title="clientTitle(c)">
            <span v-if="c.country" class="flag" aria-hidden="true">{{ flag(c.country) }}</span>
            <span v-else-if="isLan(c.address)" class="flag sub">LAN</span>
            {{ shortAddr(c.address) }}
          </td>
          <td class="provider" :title="c.asn ? `AS${c.asn} ${c.asn_org ?? ''}` : undefined">{{ c.asn_org ?? '' }}</td>
          <td class="r">
            <!-- Dropped first, so the request counts stay aligned on the right. -->
            <span v-if="c.ntp_dropped" class="dropped" title="Not answered because of rate limiting">{{ fmtNum(c.ntp_dropped) }} dropped ·</span>
            {{ fmtNum(c.ntp_packets) }}
          </td>
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
.flag {
  margin-right: 6px;
}
.dropped {
  color: var(--ink);
  font-weight: 600;
}
</style>
