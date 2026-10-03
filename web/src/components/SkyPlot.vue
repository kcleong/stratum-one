<script setup lang="ts">
import { computed } from 'vue'
import VChart from 'vue-echarts'
import type { Satellite, SkyCoverage } from '../api/types'
import { CONSTELLATIONS, satLabel } from '../lib/gnss'
import { coverageColor } from '../lib/sky'
import { useTokens } from '../lib/theme'

const props = defineProps<{ satellites: Satellite[]; coverage?: SkyCoverage | null }>()
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
    },
    series: props.coverage ? [coverageSeries(props.coverage, t.ink2)] : satelliteSeries(placed, t),
  }
})

type Tokens = (typeof tokens)['value']

function satelliteSeries(placed: Satellite[], t: Tokens) {
  return CONSTELLATIONS.map((c) => {
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
      tooltip: {
        formatter: (p: { data: { sat: Satellite } }) => {
          const s = p.data.sat
          return `<b>${satLabel(s.gnss, s.svid, s.prn)}</b> <span style="color:${t.ink2}">${s.gnss} · PRN ${s.prn}</span><br>
            SNR <b>${s.snr ?? '–'}</b> dB-Hz · el ${s.elevation}° · az ${s.azimuth}°<br>
            <span style="color:${t.ink2}">${s.used ? 'used in fix' : 'not used'}</span>`
        },
      },
    }
  })
}

function coverageSeries(cov: SkyCoverage, ink2: string) {
  const deg = Math.PI / 180
  return {
    type: 'custom',
    coordinateSystem: 'polar',
    data: cov.cells.map((c) => ({ value: [c.az, c.el], cell: c })),
    // One annular sector per patch. Canvas angles run clockwise from east; azimuth runs clockwise from north.
    renderItem: (params: { coordSys: { cx: number; cy: number; r: number }; dataIndex: number }) => {
      const c = cov.cells[params.dataIndex]
      const { cx, cy, r } = params.coordSys
      const radius = (el: number) => (r * (90 - el)) / 90
      return {
        type: 'sector',
        shape: {
          cx,
          cy,
          r0: radius(c.el + cov.el_step),
          r: radius(c.el),
          startAngle: (c.az - 90) * deg,
          endAngle: (c.az + cov.az_step - 90) * deg,
        },
        style: { fill: coverageColor(c) },
      }
    },
    tooltip: {
      formatter: (p: { data: { cell: SkyCoverage['cells'][number] } }) => {
        const c = p.data.cell
        const pct = Math.round((100 * c.received) / c.samples)
        return `<b>az ${c.az}–${c.az + cov.az_step}° · el ${c.el}–${c.el + cov.el_step}°</b><br>
          ${c.mean_snr != null ? `average SNR <b>${c.mean_snr}</b> dB-Hz (max ${c.max_snr})` : '<b>no signal</b>'}<br>
          <span style="color:${ink2}">${pct}% of ${c.samples} sightings received</span>`
      },
    },
    z: 1,
  }
}
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
