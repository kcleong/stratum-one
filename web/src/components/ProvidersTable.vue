<script setup lang="ts">
import { computed } from 'vue'
import type { Provider } from '../api/types'
import { fmtNum } from '../lib/format'

const props = defineProps<{ providers: Provider[]; active: number }>()
// Share of all clients active in the last hour (the few LAN clients are in the total, not in any provider).
const rows = computed(() => props.providers.map((p) => ({ ...p, share: props.active ? (100 * p.clients) / props.active : null })))
</script>

<template>
  <p v-if="!rows.length" class="sub">No public clients in the last hour (or GEOIP_DIR is off).</p>
  <div v-else class="table-scroll">
    <table>
      <thead>
        <tr>
          <th>Provider</th>
          <th class="r">AS</th>
          <th class="r">Clients</th>
          <th class="r">Share</th>
          <th class="r">Requests</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="p in rows" :key="p.asn ?? 'unknown'">
          <td class="provider" :title="p.asn_org ?? undefined">{{ p.asn_org ?? 'Unknown network' }}</td>
          <td class="r num">{{ p.asn ?? '–' }}</td>
          <td class="r">{{ fmtNum(p.clients) }}</td>
          <td class="r">{{ fmtNum(p.share, 1, ' %') }}</td>
          <td class="r">{{ fmtNum(p.ntp_packets) }}</td>
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
</style>
