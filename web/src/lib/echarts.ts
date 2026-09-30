// Register only the ECharts pieces we use (keeps the bundle small).
import { BarChart, LineChart, ScatterChart } from 'echarts/charts'
import {
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  PolarComponent,
  TooltipComponent,
} from 'echarts/components'
import { use } from 'echarts/core'
import { LabelLayout } from 'echarts/features'
import { CanvasRenderer } from 'echarts/renderers'

use([
  BarChart,
  LineChart,
  ScatterChart,
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  PolarComponent,
  TooltipComponent,
  LabelLayout, // needed for labelLayout.hideOverlap
  CanvasRenderer,
])
