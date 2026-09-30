<script setup lang="ts">
import { computed } from 'vue'
import VChart from 'vue-echarts'
import type { Satellite } from '../api/types'
import { CONSTELLATIONS, satLabel } from '../lib/gnss'
import { useTokens } from '../lib/theme'

const props = defineProps<{ satellites: Satellite[] }>()
const tokens = useTokens()
const COMPASS: Record<number, string> = { 0: 'N', 90: 'E', 180: 'S', 270: 'W' }

const option = computed(() => {
  const t = tokens.value
  const placed = props.satellites.filter((s) => s.elevation != null && s.azimuth != null && s.elevation >= 0)
  return {
    animation: false,
    polar: { radius: ['0%', '82%'] },
    angleAxis: {
      type: 'value',
      min: 0,
      max: 360,
      interval: 45,
      startAngle: 90,
      clockwise: true,
      axisLine: { lineStyle: { color: t.axis } },
      axisTick: { show: false },
      axisLabel: { color: t.ink2, fontSize: 12, formatter: (v: number) => COMPASS[v] ?? '' },
      splitLine: { lineStyle: { color: t.grid } },
    },
    radiusAxis: {
      type: 'value',
      min: 0,
      max: 90,
      interval: 30,
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: t.muted, fontSize: 10, formatter: (v: number) => (v === 0 ? '' : `${90 - v}°`) },
      splitLine: { lineStyle: { color: t.grid } },
    },
    tooltip: {
      trigger: 'item',
      backgroundColor: t.surface,
      borderColor: t.grid,
      textStyle: { color: t.ink, fontSize: 12 },
      formatter: (p: { data: { sat: Satellite } }) => {
        const s = p.data.sat
        return `<b>${satLabel(s.gnss, s.svid, s.prn)}</b> <span style="color:${t.ink2}">${s.gnss} · PRN ${s.prn}</span><br>
          SNR <b>${s.snr ?? '–'}</b> dB-Hz · el ${s.elevation}° · az ${s.azimuth}°<br>
          <span style="color:${t.ink2}">${s.used ? 'used in fix' : 'not used'}</span>`
      },
    },
    series: CONSTELLATIONS.map((c) => {
      const color = t.series(c.slot)
      return {
        type: 'scatter',
        name: c.name,
        coordinateSystem: 'polar',
        symbol: c.symbol,
        symbolSize: 12,
        data: placed
          .filter((s) => s.gnss === c.name)
          .map((s) => ({
            value: [90 - (s.elevation as number), s.azimuth],
            sat: s,
            itemStyle: s.used
              ? { color, borderColor: t.surface, borderWidth: 2 }
              : { color: t.surface, borderColor: color, borderWidth: 2 },
          })),
        label: {
          show: true,
          position: 'right',
          distance: 4,
          color: t.muted,
          fontSize: 10,
          formatter: (p: { data: { sat: Satellite } }) => satLabel(p.data.sat.gnss, p.data.sat.svid, p.data.sat.prn),
        },
        labelLayout: { hideOverlap: true }, // hidden labels stay in the tooltip and table
        emphasis: { scale: 1.4 },
      }
    }),
  }
})
</script>

<template>
  <VChart class="sky" :option="option" autoresize />
</template>

<style scoped>
.sky {
  /* Explicit height: aspect-ratio let the canvas outgrow the card on phones. */
  width: 100%;
  height: clamp(260px, calc(100vw - 64px), 380px);
}
</style>
