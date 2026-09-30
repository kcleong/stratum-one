<script setup lang="ts">
import { computed } from 'vue'
import VChart from 'vue-echarts'
import { useTokens } from '../lib/theme'

export interface Series {
  name: string
  slot?: number // --series-N; omit for a muted context line
  data: [number, number | null][] // [ms, value]
  dashed?: boolean
  step?: boolean
}

const props = defineProps<{
  title: string
  unit: string
  series: Series[]
  digits?: number
  includeZero?: boolean
  dimmed?: boolean
}>()

const tokens = useTokens()

const option = computed(() => {
  const t = tokens.value
  const digits = props.digits ?? 2
  const fmt = (v: number) => (v == null ? '–' : `${v.toFixed(digits)} ${props.unit}`)
  const color = (s: Series) => (s.slot ? t.series(s.slot) : t.muted)
  const multi = props.series.length > 1
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
      formatter: (items: { seriesIndex: number; value: [number, number | null] }[]) => {
        if (!items.length) return ''
        const time = new Date(items[0].value[0]).toLocaleTimeString(undefined, { hour12: false })
        const rows = items
          .map((it) => {
            const s = props.series[it.seriesIndex]
            const key = `<span style="display:inline-block;width:12px;height:2px;background:${color(s)};vertical-align:middle;margin-right:6px"></span>`
            return `<div>${key}<b>${fmt(it.value[1] as number)}</b> <span style="color:${t.ink2}">${s.name}</span></div>`
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
      type: 'value',
      scale: !props.includeZero,
      axisLabel: { color: t.muted, fontSize: 11, formatter: (v: number) => `${+v.toFixed(3)}` },
      splitLine: { lineStyle: { color: t.grid } },
    },
    dataZoom: [{ type: 'inside', filterMode: 'none' }],
    series: props.series.map((s) => ({
      type: 'line',
      name: s.name,
      data: s.data,
      step: s.step ? 'end' : false,
      showSymbol: false,
      sampling: 'lttb',
      lineStyle: { width: 2, color: color(s), type: s.dashed ? 'dashed' : 'solid' },
      itemStyle: { color: color(s) },
      emphasis: { disabled: true },
    })),
  }
})
</script>

<template>
  <section class="card" :class="{ dimmed }">
    <div class="card-head">
      <h2>{{ title }}</h2>
      <span class="sub">{{ unit }} · scroll to zoom</span>
    </div>
    <VChart class="chart" :option="option" group="history" autoresize />
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
