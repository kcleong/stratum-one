<script setup lang="ts">
import { computed } from 'vue'
import type { Satellite } from '../api/types'
import { constellation, satLabel } from '../lib/gnss'

const props = defineProps<{ satellites: Satellite[] }>()
const rows = computed(() => [...props.satellites].sort((a, b) => (b.snr ?? 0) - (a.snr ?? 0)))
</script>

<template>
  <details>
    <summary>Satellite table ({{ satellites.length }})</summary>
    <div class="table-scroll">
      <table>
        <thead>
          <tr>
            <th>Sat</th>
            <th>System</th>
            <th class="r">PRN</th>
            <th class="r">SNR dB-Hz</th>
            <th class="r">Elevation</th>
            <th class="r">Azimuth</th>
            <th>Used</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="s in rows" :key="s.prn ?? `${s.gnss}-${s.svid}`">
            <td>
              <span :style="{ color: `var(--series-${constellation(s.gnss).slot})` }" aria-hidden="true">{{ constellation(s.gnss).glyph }}</span>
              {{ satLabel(s.gnss, s.svid, s.prn) }}
            </td>
            <td>{{ s.gnss }}</td>
            <td class="r">{{ s.prn ?? '–' }}</td>
            <td class="r">{{ s.snr ?? '–' }}</td>
            <td class="r">{{ s.elevation ?? '–' }}°</td>
            <td class="r">{{ s.azimuth ?? '–' }}°</td>
            <td>{{ s.used ? 'yes' : '–' }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </details>
</template>
