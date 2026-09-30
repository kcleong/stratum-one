<script setup lang="ts">
import { computed } from 'vue'
import type { Client } from '../api/types'
import { fmtAgo, fmtLog2, fmtNum } from '../lib/format'

const props = defineProps<{ clients: Client[] }>()
const rows = computed(() =>
  props.clients.filter((c) => c.ntp_packets > 0).sort((a, b) => (a.ntp_last_rx_s ?? 1e12) - (b.ntp_last_rx_s ?? 1e12)),
)
</script>

<template>
  <p v-if="!rows.length" class="sub">No NTP clients since chronyd started.</p>
  <div v-else class="table-scroll">
    <table>
      <thead>
        <tr>
          <th>Client</th>
          <th class="r">Requests</th>
          <th class="r">Dropped</th>
          <th class="r">Interval</th>
          <th class="r">Last seen</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="c in rows" :key="c.address">
          <td class="num">{{ c.address }}</td>
          <td class="r">{{ fmtNum(c.ntp_packets) }}</td>
          <td class="r">{{ fmtNum(c.ntp_dropped) }}</td>
          <td class="r">{{ fmtLog2(c.ntp_interval) }}</td>
          <td class="r">{{ fmtAgo(c.ntp_last_rx_s) }} ago</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
