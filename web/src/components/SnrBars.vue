<script setup lang="ts">
import { computed } from 'vue'
import VChart from 'vue-echarts'
import type { Satellite } from '../api/types'
import { CONSTELLATIONS, constellation, satLabel } from '../lib/gnss'
import { useTokens } from '../lib/theme'

const props = defineProps<{ satellites: Satellite[] }>()
const tokens = useTokens()
const order = new Map(CONSTELLATIONS.map((c, i) => [c.name, i]))

const sorted = computed(() =>
  [...props.satellites].sort(
    (a, b) => (order.get(a.gnss) ?? 99) - (order.get(b.gnss) ?? 99) || (a.svid ?? a.prn ?? 0) - (b.svid ?? b.prn ?? 0),
  ),
)

const option = computed(() => {
  const t = tokens.value
  const sats = sorted.value
  return {
    animation: false,
    grid: { left: 8, right: 8, top: 18, bottom: 4 },
    tooltip: {
      trigger: 'item',
      backgroundColor: t.surface,
      borderColor: t.grid,
      textStyle: { color: t.ink, fontSize: 12 },
      formatter: (p: { dataIndex: number }) => {
        const s = sats[p.dataIndex]
        return `<b>${s.snr ?? '–'} dB-Hz</b> <span style="color:${t.ink2}">${satLabel(s.gnss, s.svid, s.prn)} · ${s.gnss}</span><br>
          <span style="color:${t.ink2}">${s.used ? 'used in fix' : 'not used'} · el ${s.elevation ?? '–'}°</span>`
      },
    },
    xAxis: {
      type: 'category',
      data: sats.map((s) => satLabel(s.gnss, s.svid, s.prn)),
      axisLine: { lineStyle: { color: t.axis } },
      axisTick: { show: false },
      axisLabel: { color: t.muted, fontSize: 10, interval: 0, rotate: sats.length > 24 ? 90 : 0 },
    },
    yAxis: {
      type: 'value',
      min: 0,
      max: (v: { max: number }) => Math.max(50, Math.ceil(v.max / 10) * 10),
      interval: 10,
      name: 'dB-Hz',
      nameTextStyle: { color: t.muted, fontSize: 11, align: 'left' },
      axisLabel: { color: t.muted, fontSize: 11 },
      splitLine: { lineStyle: { color: t.grid } },
    },
    series: [
      {
        type: 'bar',
        barCategoryGap: '25%',
        data: sats.map((s) => ({
          value: s.snr ?? 0,
          itemStyle: {
            color: t.series(constellation(s.gnss).slot),
            opacity: s.used ? 1 : 0.35,
            borderRadius: [4, 4, 0, 0],
          },
        })),
        emphasis: { itemStyle: { opacity: 1 } },
      },
    ],
  }
})
</script>

<template>
  <VChart class="bars" :option="option" autoresize />
</template>

<style scoped>
.bars {
  height: 220px;
}
</style>
