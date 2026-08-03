<script setup lang="ts">
import * as echarts from 'echarts/core'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import { LineChart } from 'echarts/charts'
import { CanvasRenderer } from 'echarts/renderers'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

import type { HistoryPoint } from '../api/types'

echarts.use([LineChart, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer])

const props = defineProps<{ points: HistoryPoint[] }>()
const chartElement = ref<HTMLDivElement>()
let chart: echarts.ECharts | null = null
let observer: ResizeObserver | null = null

function render() {
  if (!chart) return
  chart.setOption({
    color: ['#177a73', '#d18452'],
    tooltip: { trigger: 'axis', valueFormatter: (value: unknown) => Number(value).toFixed(8) },
    legend: { top: 4, right: 4, textStyle: { color: '#60727c' } },
    grid: { left: 18, right: 22, top: 48, bottom: 18, containLabel: true },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: props.points.map((item) => item.nav_date),
      axisLine: { lineStyle: { color: '#d7e2e1' } },
      axisLabel: { color: '#71828a', hideOverlap: true },
    },
    yAxis: {
      type: 'value',
      scale: true,
      axisLabel: { color: '#71828a', formatter: (value: number) => value.toFixed(4) },
      splitLine: { lineStyle: { color: '#edf2f1' } },
    },
    series: [
      {
        name: '单位净值', type: 'line', smooth: 0.25, showSymbol: props.points.length < 40,
        symbolSize: 6, data: props.points.map((item) => item.unit_nav ? Number(item.unit_nav) : null),
        areaStyle: { color: 'rgba(23,122,115,.08)' }, lineStyle: { width: 2.4 },
      },
      {
        name: '累计净值', type: 'line', smooth: 0.25, showSymbol: false,
        data: props.points.map((item) => item.total_nav ? Number(item.total_nav) : null),
        lineStyle: { width: 1.8, type: 'dashed' },
      },
    ],
  })
}

onMounted(() => {
  if (!chartElement.value) return
  chart = echarts.init(chartElement.value)
  observer = new ResizeObserver(() => chart?.resize())
  observer.observe(chartElement.value)
  render()
})
watch(() => props.points, render, { deep: true })
onBeforeUnmount(() => { observer?.disconnect(); chart?.dispose() })
</script>

<template><div ref="chartElement" class="nav-history-chart"></div></template>

<style scoped>
.nav-history-chart { width: 100%; height: 360px; }
</style>
