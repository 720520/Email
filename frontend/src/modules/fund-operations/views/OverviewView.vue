<script setup lang="ts">
import { ArrowRight, CircleCheck, Coin, Link, MessageBox, Warning } from '@element-plus/icons-vue'
import dayjs from 'dayjs'
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import PageHeader from '@/components/PageHeader.vue'
import { apiErrorMessage } from '@/platform/api/http'

import { getDashboard, getFundProductNavUpdateStatus, getFundProducts } from '../api'
import type { DashboardData, FundProductItem, FundProductNavUpdateSummary } from '../api/types'

const router = useRouter()
const loading = ref(false)
const errorMessage = ref('')
const dashboard = ref<DashboardData>()
const ledgerProducts = ref<FundProductItem[]>([])
const navStatus = ref<FundProductNavUpdateSummary>()
const statusDate = ref(dayjs().format('YYYY-MM-DD'))
const onlyPending = ref(false)
const statusLoading = ref(false)

const visibleStatusItems = computed(() => {
  const items = navStatus.value?.items ?? []
  return onlyPending.value ? items.filter((item) => item.status !== 'updated') : items
})

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
    const [dashboardData, productPage] = await Promise.all([
      getDashboard(),
      getFundProducts({ page: 1, page_size: 8 }),
    ])
    dashboard.value = dashboardData
    ledgerProducts.value = productPage.items
  } catch (error) {
    errorMessage.value = apiErrorMessage(error)
  } finally {
    loading.value = false
  }
}

onMounted(loadDashboard)

async function loadNavStatus() {
  statusLoading.value = true
  try {
    navStatus.value = await getFundProductNavUpdateStatus(statusDate.value)
  } catch (error) {
    errorMessage.value = apiErrorMessage(error)
  } finally {
    statusLoading.value = false
  }
}

function statusLabel(status: string) {
  return ({ updated: '已更新', partial: '部分更新', pending: '待更新' } as Record<string, string>)[status] ?? status
}

function statusType(status: string) {
  return status === 'updated' ? 'success' : status === 'partial' ? 'warning' : 'danger'
}

onMounted(loadNavStatus)
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

    <section class="panel home-ledger">
      <div class="panel-header">
        <div><h2>产品信息台账</h2><p>首页快速查看产品基础资料、最新净值和托管平台入口</p></div>
        <el-button text type="primary" @click="router.push('/fund-products')">查看完整台账</el-button>
      </div>
      <el-table :data="ledgerProducts" empty-text="暂无产品资料">
        <el-table-column label="产品" min-width="230">
          <template #default="{ row }"><strong class="table-primary">{{ row.product_name }}</strong><small class="cell-secondary numeric">{{ row.product_code }}</small></template>
        </el-table-column>
        <el-table-column prop="inception_date" label="成立日期" width="116"><template #default="{ row }">{{ row.inception_date || '—' }}</template></el-table-column>
        <el-table-column prop="strategy_category" label="策略" min-width="130"><template #default="{ row }">{{ row.strategy_category || '—' }}</template></el-table-column>
        <el-table-column prop="manager_name" label="管理人" min-width="150"><template #default="{ row }">{{ row.manager_name || '—' }}</template></el-table-column>
        <el-table-column prop="custodian_name" label="托管/外包" min-width="150"><template #default="{ row }">{{ row.custodian_name || '—' }}</template></el-table-column>
        <el-table-column label="最新净值" width="130" align="right"><template #default="{ row }"><strong class="numeric">{{ row.unit_nav || '多份额' }}</strong><small class="cell-secondary">{{ row.latest_source_date || '—' }}</small></template></el-table-column>
        <el-table-column label="托管平台" width="120" fixed="right">
          <template #default="{ row }">
            <a v-if="row.custodian_platform_url" class="platform-link" :href="row.custodian_platform_url" target="_blank" rel="noopener noreferrer"><el-icon><Link /></el-icon>打开平台</a>
            <span v-else class="text-muted">未配置</span>
          </template>
        </el-table-column>
      </el-table>
    </section>

    <section class="panel nav-status-ledger" v-loading="statusLoading">
      <div class="panel-header">
        <div><h2>净值更新状态</h2><p>按指定估值日核对每个产品及其份额是否完成更新</p></div>
        <div class="status-toolbar">
          <el-date-picker v-model="statusDate" type="date" value-format="YYYY-MM-DD" :clearable="false" style="width: 150px" @change="loadNavStatus" />
          <el-switch v-model="onlyPending" active-text="仅看待更新" />
          <el-button @click="loadNavStatus">刷新</el-button>
        </div>
      </div>
      <div class="status-summary">
        <span>全部 <strong>{{ navStatus?.total_count ?? 0 }}</strong></span>
        <span class="is-success">已更新 <strong>{{ navStatus?.updated_count ?? 0 }}</strong></span>
        <span class="is-warning">部分更新 <strong>{{ navStatus?.partial_count ?? 0 }}</strong></span>
        <span class="is-danger">待更新 <strong>{{ navStatus?.pending_count ?? 0 }}</strong></span>
      </div>
      <el-table :data="visibleStatusItems" empty-text="当前筛选条件下没有产品">
        <el-table-column label="产品" min-width="240"><template #default="{ row }"><strong class="table-primary">{{ row.product_name }}</strong><small class="cell-secondary numeric">{{ row.product_code }}</small></template></el-table-column>
        <el-table-column label="更新状态" width="120"><template #default="{ row }"><el-tag :type="statusType(row.status)">{{ statusLabel(row.status) }}</el-tag></template></el-table-column>
        <el-table-column label="份额完整度" width="130"><template #default="{ row }"><span class="numeric">{{ row.updated_share_count }} / {{ row.expected_share_count }}</span></template></el-table-column>
        <el-table-column label="缺少份额" min-width="180"><template #default="{ row }"><span :class="row.missing_share_codes.length ? 'missing-shares' : 'text-muted'">{{ row.missing_share_codes.join('、') || '—' }}</span></template></el-table-column>
        <el-table-column label="最近更新日期" width="130"><template #default="{ row }"><span class="numeric">{{ row.latest_update_date || '—' }}</span></template></el-table-column>
        <el-table-column label="操作" width="100"><template #default="{ row }"><el-button text type="primary" @click="router.push(`/fund-products?product=${row.product_id}`)">产品详情</el-button></template></el-table-column>
      </el-table>
    </section>
  </div>
</template>

<style scoped>
.home-ledger { margin-top: 20px; }
.nav-status-ledger { margin-top: 20px; }
.platform-link { display: inline-flex; align-items: center; gap: 5px; color: var(--el-color-primary); font-size: 12px; text-decoration: none; }
.platform-link:hover { text-decoration: underline; }
.status-toolbar { display: flex; align-items: center; gap: 12px; }
.status-summary { padding: 14px 18px; display: flex; gap: 24px; border-top: 1px solid var(--line); border-bottom: 1px solid var(--line); background: #fafcfc; color: var(--ink-600); font-size: 12px; }
.status-summary strong { margin-left: 5px; color: var(--ink-900); font-size: 18px; }
.status-summary .is-success, .status-summary .is-success strong { color: var(--el-color-success); }
.status-summary .is-warning, .status-summary .is-warning strong { color: var(--el-color-warning); }
.status-summary .is-danger, .status-summary .is-danger strong, .missing-shares { color: var(--el-color-danger); }
</style>
