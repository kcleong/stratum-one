<script setup lang="ts">
import { computed } from 'vue'
import type { Provider } from '../api/types'
import { countryName, flag } from '../lib/country'
import { fmtNum } from '../lib/format'

const props = defineProps<{ providers: Provider[]; active: number }>()
// Share of all clients active in the last hour (the few LAN clients are in the total, not in any provider).
const rows = computed(() => props.providers.map((p) => ({ ...p, share: props.active ? (100 * p.clients) / props.active : null })))

// AS number, country and lifetime requests: detail for the tooltip, not a column.
const providerTitle = (p: Provider) =>
  [
    p.asn_org,
    p.asn != null ? `AS${p.asn}` : null,
    p.country ? `mostly ${countryName(p.country)}` : null,
    `${fmtNum(p.ntp_packets)} requests since chronyd start`,
  ]
    .filter(Boolean)
    .join(' · ')
</script>

<template>
  <p v-if="!rows.length" class="sub">No public clients in the last hour (or GEOIP_DIR is off).</p>
  <div v-else class="table-scroll">
    <table>
      <thead>
        <tr>
          <th>Provider</th>
          <th class="r">Clients</th>
          <th>Share</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="p in rows" :key="p.asn ?? 'unknown'">
          <td class="provider" :title="providerTitle(p)">
            <span v-if="p.country" class="flag" aria-hidden="true">{{ flag(p.country) }}</span>
            {{ p.asn_org ?? 'Unknown network' }}
          </td>
          <td class="r">{{ fmtNum(p.clients) }}</td>
          <td class="share">
            <span class="track" aria-hidden="true"><span class="bar" :style="{ width: `${p.share ?? 0}%` }" /></span>
            <span class="num">{{ fmtNum(p.share, 1, ' %') }}</span>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.provider {
  max-width: 32ch;
  overflow: hidden;
  text-overflow: ellipsis;
}
.flag {
  margin-right: 6px;
}
.share {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 14ch;
}
/* Fixed-width track so bar lengths compare across rows (100 % = all active clients). */
.track {
  display: inline-block;
  width: 8ch;
  flex: none;
}
.bar {
  display: block;
  height: 8px;
  min-width: 2px;
  border-radius: 2px;
  background: var(--series-1);
}
</style>
