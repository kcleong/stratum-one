<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import VChart from 'vue-echarts'
import { joinHistory } from '../lib/historySync'
import { useTokens } from '../lib/theme'

export interface Series {
  name: string
  slot?: number // --series-N; omit for a muted context line
  data: [number, number | null][] // [ms, value]
  dashed?: boolean
  step?: boolean
  /** leave out of the tooltip (e.g. a constant reference line, whose sparse points would win the nearest-in-time match) */
  noTip?: boolean
  /** min/max per point (bucket-averaged ranges), drawn as a shaded band behind the line */
  band?: { min: (number | null)[]; max: (number | null)[] }
}

type Rendered = { kind: 'line' | 'band-base' | 'band-range'; s: Series }

const props = defineProps<{
  title: string
  unit: string
  series: Series[]
  digits?: number
  includeZero?: boolean
  /** log y-axis, for positive values spanning decades (e.g. RMS offset: ~0.1 µs normally, ms after a restart) */
  logScale?: boolean
  dimmed?: boolean
  /** selected history range, e.g. "last 24 h" */
  range?: string
}>()

const tokens = useTokens()

// Shared crosshair and zoom with the other history charts (see lib/historySync).
const chartRef = ref<InstanceType<typeof VChart>>()
let leave: (() => void) | undefined
watch(
  () => chartRef.value?.chart,
  (chart) => {
    leave?.()
    leave = chart ? joinHistory(chart) : undefined
  },
  { immediate: true },
)
onBeforeUnmount(() => leave?.())

const option = computed(() => {
  const t = tokens.value
  const digits = props.digits ?? 2
  const fmt = (v: number) => (v == null ? '–' : `${v.toFixed(digits)} ${props.unit}`)
  const color = (s: Series) => (s.slot ? t.series(s.slot) : t.muted)
  const multi = props.series.length > 1
  const rendered: Rendered[] = props.series.flatMap((s) => [
    ...(s.band ? [{ kind: 'band-base', s } as Rendered, { kind: 'band-range', s } as Rendered] : []),
    { kind: 'line', s } as Rendered,
  ])
  return {
    animation: false,
    grid: { left: 8, right: 12, top: multi ? 30 : 10, bottom: 4 },
    legend: multi
      ? {
          top: 0,
          left: 0,
          icon: 'rect',
          itemWidth: 14,
          itemHeight: 2,
          textStyle: { color: t.ink2, fontSize: 12 },
          data: props.series.map((s) => ({ name: s.name, itemStyle: { color: color(s) } })),
        }
      : undefined,
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'line', lineStyle: { color: t.axis } },
      backgroundColor: t.surface,
      borderColor: t.grid,
      textStyle: { color: t.ink, fontSize: 12 },
      formatter: (items: { seriesIndex: number; dataIndex: number; value: [number, number | null] }[]) => {
        const lines = items.filter((it) => rendered[it.seriesIndex]?.kind === 'line')
        if (!lines.length) return ''
        const when = new Date(lines[0].value[0])
        const time = when.toLocaleString(undefined, { hour12: false, month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit' })
        const rows = lines
          .map((it) => {
            const s = rendered[it.seriesIndex].s
            const key = `<span style="display:inline-block;width:12px;height:2px;background:${color(s)};vertical-align:middle;margin-right:6px"></span>`
            const lo = s.band?.min[it.dataIndex]
            const hi = s.band?.max[it.dataIndex]
            const range = lo != null && hi != null ? ` <span style="color:${t.muted}">${fmt(lo)} … ${fmt(hi)}</span>` : ''
            return `<div>${key}<b>${fmt(it.value[1] as number)}</b> <span style="color:${t.ink2}">${s.name}</span>${range}</div>`
          })
          .join('')
        return `<div style="color:${t.muted};margin-bottom:2px">${time}</div>${rows}`
      },
    },
    xAxis: {
      type: 'time',
      axisLine: { lineStyle: { color: t.axis } },
      axisTick: { show: false },
      axisLabel: { color: t.muted, fontSize: 11, hideOverlap: true },
      splitLine: { show: false },
    },
    yAxis: {
      type: props.logScale ? 'log' : 'value',
      scale: !props.includeZero,
      axisLabel: { color: t.muted, fontSize: 11, formatter: (v: number) => `${+v.toFixed(3)}` },
      splitLine: { lineStyle: { color: t.grid } },
    },
    // Ctrl+wheel (and trackpad pinch, which browsers send as ctrl+wheel) zooms; plain wheel scrolls the page.
    dataZoom: [{ type: 'inside', filterMode: 'none', zoomOnMouseWheel: 'ctrl', moveOnMouseWheel: false }],
    series: rendered.map(({ kind, s }, i) => {
      if (kind === 'line')
        return {
          type: 'line',
          name: s.name,
          data: s.data,
          step: s.step ? 'end' : false,
          showSymbol: false,
          sampling: 'lttb',
          lineStyle: { width: 2, color: color(s), type: s.dashed ? 'dashed' : 'solid' },
          itemStyle: { color: color(s) },
          emphasis: { disabled: true },
          tooltip: s.noTip ? { show: false } : undefined,
          z: 3,
        }
      // Band = invisible base at min, stacked with (max - min) filled on top.
      const band = s.band!
      const stack = `band-${i - (kind === 'band-range' ? 1 : 0)}`
      const data =
        kind === 'band-base'
          ? s.data.map(([x], j) => [x, band.min[j]])
          : s.data.map(([x], j) => [x, band.max[j] != null && band.min[j] != null ? band.max[j]! - band.min[j]! : null])
      return {
        type: 'line',
        name: `${s.name} range`,
        data,
        stack,
        stackStrategy: 'all', // base can be negative; stack the range on it regardless of sign
        showSymbol: false,
        silent: true,
        lineStyle: { opacity: 0 },
        areaStyle: kind === 'band-range' ? { color: color(s), opacity: 0.18 } : undefined,
        emphasis: { disabled: true },
        tooltip: { show: false },
        z: 1,
      }
    }),
  }
})
</script>

<template>
  <section class="card" :class="{ dimmed }">
    <div class="card-head">
      <h2>{{ title }}</h2>
      <span class="sub" title="ctrl+scroll or pinch to zoom">{{ unit }}<template v-if="range"> · {{ range }}</template></span>
    </div>
    <VChart ref="chartRef" class="chart" :option="option" autoresize />
  </section>
</template>

<style scoped>
.chart {
  height: 200px;
}
.dimmed .chart {
  opacity: 0.55;
  transition: opacity 0.2s;
}
</style>
