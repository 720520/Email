<script setup lang="ts">
import { ArrowRight, CircleCheck, Coin, MessageBox, Warning } from '@element-plus/icons-vue'
import dayjs from 'dayjs'
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import PageHeader from '@/components/PageHeader.vue'
import { apiErrorMessage } from '@/platform/api/http'

import { getDashboard } from '../api'
import type { DashboardData } from '../api/types'

const router = useRouter()
const loading = ref(false)
const errorMessage = ref('')
const dashboard = ref<DashboardData>()

const metrics = computed(() => [
  {
    label: '今日邮件',
    value: dashboard.value?.today_email_count ?? 0,
    helper: '今日收到的基金运营邮件',
    icon: MessageBox,
    tone: 'navy',
    route: '/emails',
  },
  {
    label: '解析成功',
    value: dashboard.value?.success_email_count ?? 0,
    helper: '已完成归档、解析与入库',
    icon: CircleCheck,
    tone: 'teal',
    route: '/emails?status=success',
  },
  {
    label: '基金数量',
    value: dashboard.value?.fund_count ?? 0,
    helper: '数据库内的唯一产品数量',
    icon: Coin,
    tone: 'sand',
    route: '/fund-nav',
  },
  {
    label: '待处理异常',
    value: dashboard.value?.open_exception_count ?? 0,
    helper: '需要运营复核的开放事项',
    icon: Warning,
    tone: 'coral',
    route: '/exceptions?status=open',
  },
])

async function loadDashboard() {
  loading.value = true
  errorMessage.value = ''
  try {
    dashboard.value = await getDashboard()
  } catch (error) {
    errorMessage.value = apiErrorMessage(error)
  } finally {
    loading.value = false
  }
}

onMounted(loadDashboard)
</script>

<template>
  <div v-loading="loading">
    <PageHeader
      eyebrow="Fund Operations"
      title="基金运营数据概览"
      description="聚合当天邮件、净值与异常状态，优先暴露需要人工介入的运营事项。"
    >
      <el-button :loading="loading" @click="loadDashboard">刷新数据</el-button>
    </PageHeader>

    <el-alert v-if="errorMessage" :title="errorMessage" type="error" show-icon class="page-alert" />

    <section class="metric-grid" aria-label="运营指标">
      <button
        v-for="metric in metrics"
        :key="metric.label"
        class="metric-card"
        :class="`metric-card--${metric.tone}`"
        @click="router.push(metric.route)"
      >
        <span class="metric-card__icon"><el-icon><component :is="metric.icon" /></el-icon></span>
        <span class="metric-card__copy">
          <small>{{ metric.label }}</small>
          <strong class="numeric">{{ metric.value }}</strong>
          <span>{{ metric.helper }}</span>
        </span>
        <el-icon class="metric-card__arrow"><ArrowRight /></el-icon>
      </button>
    </section>

    <section class="overview-grid">
      <article class="panel latest-panel">
        <div class="panel-header">
          <div><h2>最新净值批次</h2><p>用于快速确认最新估值日的数据覆盖情况</p></div>
          <el-button text type="primary" @click="router.push('/fund-nav')">查看净值</el-button>
        </div>
        <div class="latest-panel__body">
          <div class="latest-date">
            <span>最新估值日</span>
            <strong>{{ dashboard?.latest_nav_date ? dayjs(dashboard.latest_nav_date).format('YYYY-MM-DD') : '暂无数据' }}</strong>
          </div>
          <div class="latest-count">
            <span class="numeric">{{ dashboard?.latest_nav_count ?? 0 }}</span>
            <small>只产品已入库</small>
          </div>
        </div>
        <div class="workflow-strip">
          <div><span>01</span><strong>收取邮件</strong><small>IMAP 拉取并留痕</small></div>
          <i></i>
          <div><span>02</span><strong>识别解析</strong><small>按字段适配托管表格</small></div>
          <i></i>
          <div><span>03</span><strong>净值入库</strong><small>产品代码 + 日期去重</small></div>
          <i></i>
          <div><span>04</span><strong>异常复核</strong><small>人工闭环并保留历史</small></div>
        </div>
      </article>

      <article class="panel exception-preview">
        <div class="panel-header">
          <div><h2>最近待处理异常</h2><p>按发生时间倒序展示最新五条</p></div>
          <el-button text type="primary" @click="router.push('/exceptions?status=open')">全部异常</el-button>
        </div>
        <div v-if="dashboard?.recent_exceptions.length" class="exception-preview__list">
          <button
            v-for="item in dashboard.recent_exceptions"
            :key="item.id"
            @click="router.push({ path: '/exceptions', query: { status: 'open' } })"
          >
            <span class="severity-dot" :class="`severity-dot--${item.severity}`"></span>
            <span class="exception-preview__copy">
              <strong>{{ item.category }}</strong>
              <small>{{ item.message }}</small>
              <em>{{ item.source }} · {{ dayjs(item.create_time).format('MM-DD HH:mm') }}</em>
            </span>
            <el-icon><ArrowRight /></el-icon>
          </button>
        </div>
        <el-empty v-else description="当前没有待处理异常" :image-size="76" />
      </article>
    </section>
  </div>
</template>
