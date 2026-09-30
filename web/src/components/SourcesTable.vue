<script setup lang="ts">
import { computed } from 'vue'
import type { Source, SourceStats } from '../api/types'
import { fmtAgo, fmtLog2, fmtNum, fmtOffset, fmtSpan } from '../lib/format'

const props = defineProps<{ sources: Source[]; stats: SourceStats[] }>()

const STATE: Record<Source['state'], { icon: string; label: string; cls: string }> = {
  selected: { icon: '✓', label: 'selected', cls: 'good' },
  combined: { icon: '+', label: 'combined', cls: 'ok' },
  not_combined: { icon: '−', label: 'not combined', cls: 'muted' },
  unusable: { icon: '?', label: 'unusable', cls: 'muted' },
  falseticker: { icon: '✕', label: 'falseticker', cls: 'critical' },
  too_variable: { icon: '~', label: 'too variable', cls: 'warning' },
}

const rows = computed(() => {
  const byName = new Map(props.stats.map((s) => [s.name, s]))
  return props.sources.map((s) => ({ ...s, st: STATE[s.state], stats: byName.get(s.name) }))
})

// reach is the last 8 polls, oldest bit first.
const bits = (reach: number) => Array.from({ length: 8 }, (_, i) => (reach >> (7 - i)) & 1)
</script>

<template>
  <div class="table-scroll">
    <table>
      <thead>
        <tr>
          <th>State</th>
          <th>Source</th>
          <th class="r">Stratum</th>
          <th class="r">Poll</th>
          <th>Reach</th>
          <th class="r">Last</th>
          <th class="r">Offset</th>
          <th class="r">± error</th>
          <th class="r">Std dev</th>
          <th class="r">Freq</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="s in rows" :key="s.name" :class="{ sel: s.state === 'selected' }">
          <td>
            <span class="state" :class="s.st.cls"><span aria-hidden="true">{{ s.st.icon }}</span> {{ s.st.label }}</span>
          </td>
          <td>
            <span class="name">{{ s.name }}</span>
            <span class="sub mode">{{ s.mode }}</span>
          </td>
          <td class="r">{{ s.stratum }}</td>
          <td class="r">{{ fmtLog2(s.poll) }}</td>
          <td>
            <span class="reach" :title="`reach ${s.reach.toString(8)} (octal)`">
              <i v-for="(b, i) in bits(s.reach)" :key="i" :class="{ on: b }" />
            </span>
          </td>
          <td class="r">{{ fmtAgo(s.last_rx_s) }}</td>
          <td class="r">{{ fmtOffset(s.offset_s) }}</td>
          <td class="r">{{ fmtSpan(s.error_s) }}</td>
          <td class="r">{{ fmtSpan(s.stats?.std_dev_s) }}</td>
          <td class="r">{{ fmtNum(s.stats?.frequency_ppm, 3, ' ppm') }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.sel td {
  background: var(--surface-2);
}
.name {
  font-weight: 500;
}
.mode {
  margin-left: 6px;
}
.state {
  font-size: 12px;
}
.state.good { color: var(--good-ink); font-weight: 600; }
.state.critical { color: var(--critical); font-weight: 600; }
.state.warning { color: var(--ink); }
.state.muted { color: var(--muted); }
.reach {
  display: inline-flex;
  gap: 2px;
  vertical-align: middle;
}
.reach i {
  width: 6px;
  height: 12px;
  border-radius: 2px;
  background: var(--grid);
}
.reach i.on {
  background: var(--ink-2);
}
</style>
