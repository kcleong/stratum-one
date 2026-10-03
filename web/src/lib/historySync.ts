// Shared crosshair and zoom across the history charts.
// echarts' connect() replays the hovered chart's seriesIndex/dataIndex on the other charts, so a
// chart with fewer points (the 15-min pool scores) finds no point at that index and hides its
// tooltip. Here the other charts follow by time instead.
import type { ECharts } from 'echarts/core'

const charts = new Set<ECharts>()
let syncing = false // our own dispatchAction calls fire 'datazoom' on the other charts too

function others(chart: ECharts, fn: (other: ECharts) => void) {
  for (const other of charts) if (other !== chart && !other.isDisposed()) fn(other)
}

export function joinHistory(chart: ECharts): () => void {
  charts.add(chart)
  const zr = chart.getZr()

  const hide = (o: ECharts) => {
    o.dispatchAction({ type: 'hideTip' })
    o.dispatchAction({ type: 'updateAxisPointer', currTrigger: 'leave' }) // hideTip leaves the crosshair line
  }
  const hideOthers = () => others(chart, hide)

  const onMove = (e: { offsetX: number; offsetY: number }) => {
    const at = [e.offsetX, e.offsetY]
    if (!chart.containPixel({ gridIndex: 0 }, at)) return hideOthers()
    const t = (chart.convertFromPixel({ gridIndex: 0 }, at) as number[])[0]
    others(chart, (o) => {
      const x = o.convertToPixel({ xAxisIndex: 0 }, t) as number
      const y = o.getHeight() / 2
      if (o.containPixel({ gridIndex: 0 }, [x, y])) o.dispatchAction({ type: 'showTip', x, y })
      else hide(o)
    })
  }

  const onZoom = () => {
    if (syncing) return
    const dz = (chart.getOption().dataZoom as { startValue?: number; endValue?: number }[] | undefined)?.[0]
    if (dz?.startValue == null || dz.endValue == null) return
    syncing = true
    try {
      others(chart, (o) => o.dispatchAction({ type: 'dataZoom', startValue: dz.startValue, endValue: dz.endValue }))
    } finally {
      syncing = false
    }
  }

  zr.on('mousemove', onMove)
  zr.on('globalout', hideOthers)
  chart.on('datazoom', onZoom)
  return () => {
    charts.delete(chart)
    if (chart.isDisposed()) return
    zr.off('mousemove', onMove)
    zr.off('globalout', hideOthers)
    chart.off('datazoom', onZoom)
  }
}
