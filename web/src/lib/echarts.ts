// Register only the ECharts pieces we use (keeps the bundle small).
import { BarChart, CustomChart, LineChart, ScatterChart } from 'echarts/charts'
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
  CustomChart, // sky coverage patches
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
