<script setup lang="ts">
import { EditPen, Grid, Link, List, RefreshRight, Search, View } from '@element-plus/icons-vue'
import dayjs from 'dayjs'
import { ElMessage } from 'element-plus'
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import PageHeader from '@/components/PageHeader.vue'
import { apiErrorMessage } from '@/platform/api/http'
import { useAuthStore } from '@/platform/auth/auth.store'
import FundNavView from './FundNavView.vue'

import {
  getFundProduct,
  getFundProductNavUpdateStatus,
  getFundProducts,
  getFundProductSummary,
  updateFundProductProfile,
} from '../api'
import type {
  FundProductDetail,
  FundProductItem,
  FundProductNavUpdateItem,
  FundProductNavUpdateSummary,
  FundProductProfilePayload,
  FundProductSnapshot,
  FundProductSummary,
} from '../api/types'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const workspaceTab = ref<'ledger' | 'nav'>(route.query.view === 'nav' ? 'nav' : 'ledger')
const loading = ref(false)
const detailLoading = ref(false)
const saving = ref(false)
const rows = ref<FundProductItem[]>([])
const total = ref(0)
const summary = ref<FundProductSummary>()
const detail = ref<FundProductDetail>()
const detailVisible = ref(false)
const selectedSnapshotId = ref<number>()
const editVisible = ref(false)
const filters = reactive({ keyword: '', page: 1, pageSize: 20 })
const viewMode = ref<'cards' | 'table'>('cards')
const statusDate = ref(dayjs().format('YYYY-MM-DD'))
const onlyPending = ref(false)
const navStatus = ref<FundProductNavUpdateSummary>()
const profileForm = reactive({ manager: '', strategy: '', platformUrl: '' })
const canEdit = computed(() => auth.user?.is_platform_admin || auth.user?.role !== 'viewer')
const navStatusMap = computed(() => new Map(
  (navStatus.value?.items ?? []).map((item) => [item.product_id, item]),
))
const visibleRows = computed(() => onlyPending.value
  ? rows.value.filter((item) => navStatusMap.value.get(item.id)?.status !== 'updated')
  : rows.value)

function formatMoney(value: string | null | undefined) {
  if (!value) return '—'
  return Number(value).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function formatRatio(value: string | null) {
  if (!value) return '—'
  return `${(Number(value) * 100).toFixed(2)}%`
}

function text(value: string | null | undefined) { return value || '—' }

async function loadRows() {
  loading.value = true
  try {
    const data = await getFundProducts({
      page: filters.page,
      page_size: filters.pageSize,
      keyword: filters.keyword.trim() || undefined,
    })
    rows.value = data.items
    total.value = data.total
  } catch (error) {
    ElMessage.error(apiErrorMessage(error))
  } finally {
    loading.value = false
  }
}

async function loadSummary() {
  try { summary.value = await getFundProductSummary() }
  catch (error) { ElMessage.error(apiErrorMessage(error)) }
}

async function loadNavStatus() {
  try { navStatus.value = await getFundProductNavUpdateStatus(statusDate.value) }
  catch (error) { ElMessage.error(apiErrorMessage(error)) }
}

function productStatus(productId: number): FundProductNavUpdateItem | undefined {
  return navStatusMap.value.get(productId)
}

function statusLabel(status?: string) {
  return ({ updated: '已更新', partial: '部分更新', pending: '待更新' } as Record<string, string>)[status ?? ''] ?? '待核对'
}

function statusType(status?: string) {
  return status === 'updated' ? 'success' : status === 'partial' ? 'warning' : 'danger'
}

function search() { filters.page = 1; void loadRows() }
function reset() { filters.keyword = ''; filters.page = 1; void loadRows() }

async function showDetail(id: number) {
  detailVisible.value = true
  detailLoading.value = true
  detail.value = undefined
  selectedSnapshotId.value = undefined
  try {
    detail.value = await getFundProduct(id)
    selectedSnapshotId.value = detail.value.latest_snapshots[0]?.id
  }
  catch (error) { ElMessage.error(apiErrorMessage(error)) }
  finally { detailLoading.value = false }
}

function openEdit() {
  if (!detail.value) return
  profileForm.manager = detail.value.investment_manager_info ?? ''
  profileForm.strategy = detail.value.investment_strategy_info ?? ''
  profileForm.platformUrl = detail.value.custodian_platform_url ?? ''
  editVisible.value = true
}

async function saveProfile() {
  if (!detail.value) return
  saving.value = true
  try {
    detail.value = await updateFundProductProfile(detail.value.id, {
      investment_manager_info: profileForm.manager,
      investment_strategy_info: profileForm.strategy,
      custodian_platform_url: profileForm.platformUrl.trim() || null,
    })
    editVisible.value = false
    ElMessage.success('产品说明已保存并写入审计日志')
    void loadRows()
    void loadSummary()
  } catch (error) {
    ElMessage.error(apiErrorMessage(error))
  } finally {
    saving.value = false
  }
}

async function restoreSource(field: 'manager' | 'strategy') {
  if (!detail.value) return
  saving.value = true
  const payload: FundProductProfilePayload = field === 'manager'
    ? { restore_investment_manager_from_source: true }
    : { restore_investment_strategy_from_source: true }
  try {
    detail.value = await updateFundProductProfile(detail.value.id, payload)
    ElMessage.success('已恢复使用附件来源值')
    void loadRows()
    void loadSummary()
  } catch (error) {
    ElMessage.error(apiErrorMessage(error))
  } finally {
    saving.value = false
  }
}

function snapshotLabel(item: FundProductSnapshot) {
  return item.share_class ? `${item.share_class} · ${item.product_code}` : item.product_code
}

const selectedSnapshot = computed(() => detail.value?.latest_snapshots.find(
  (item) => item.id === selectedSnapshotId.value,
))

function summarySourceLabel(source?: FundProductItem['summary_source']) {
  return ({
    total_share: '总份额原值',
    single_share: '单份额',
    share_aggregate: '分类份额汇总',
    unavailable: '暂无可靠总值',
  } as Record<string, string>)[source ?? ''] ?? '暂无可靠总值'
}

watch(() => filters.pageSize, search)
watch(workspaceTab, (value) => {
  const query = { ...route.query }
  if (value === 'nav') query.view = 'nav'
  else delete query.view
  void router.replace({ query })
})
watch(() => route.query.view, (value) => { workspaceTab.value = value === 'nav' ? 'nav' : 'ledger' })
onMounted(() => {
  void loadRows()
  void loadSummary()
  void loadNavStatus()
  const productId = Number(route.query.product)
  if (Number.isInteger(productId) && productId > 0) void showDetail(productId)
})
</script>

<template>
  <div>
    <PageHeader
      eyebrow="Product Master"
      title="产品中心"
      description="在一个视图中理解产品、托管机构、投资策略、净值覆盖和外部平台入口。"
    />

    <nav class="product-center-tabs" aria-label="产品中心视图">
      <button :class="{ active: workspaceTab === 'ledger' }" type="button" @click="workspaceTab = 'ledger'">产品台账</button>
      <button :class="{ active: workspaceTab === 'nav' }" type="button" @click="workspaceTab = 'nav'">净值明细</button>
    </nav>

    <template v-if="workspaceTab === 'ledger'">

    <section class="product-metrics">
      <article class="product-metric"><small>产品主体</small><strong>{{ summary?.product_count ?? '—' }}</strong><span>按备案/产品代码归并</span></article>
      <article class="product-metric"><small>最新份额记录</small><strong>{{ summary?.share_count ?? '—' }}</strong><span>{{ summary?.latest_nav_date ?? '暂无估值日' }}</span></article>
      <article class="product-metric"><small>最新资产净值</small><strong class="money-value">{{ formatMoney(summary?.latest_asset_value) }}</strong><span>有总份额时不重复汇总 A/B/C 类</span></article>
      <article class="product-metric"><small>待补充说明</small><strong>{{ (summary?.missing_manager_count ?? 0) + (summary?.missing_strategy_count ?? 0) }}</strong><span>经理 {{ summary?.missing_manager_count ?? 0 }} · 策略 {{ summary?.missing_strategy_count ?? 0 }}</span></article>
    </section>

    <section class="panel filter-panel">
      <el-form class="filter-form" label-position="top" @submit.prevent="search">
        <el-form-item label="产品名称或备案代码">
          <el-input v-model="filters.keyword" clearable placeholder="输入关键词" style="width: 320px" @keyup.enter="search" />
        </el-form-item>
        <el-form-item label="净值核对日期">
          <el-date-picker v-model="statusDate" type="date" value-format="YYYY-MM-DD" :clearable="false" style="width: 150px" @change="loadNavStatus" />
        </el-form-item>
        <el-form-item label="显示范围"><el-switch v-model="onlyPending" active-text="仅看待更新" /></el-form-item>
        <el-form-item class="filter-actions">
          <el-button :icon="Search" type="primary" @click="search">查询</el-button>
          <el-button @click="reset">重置</el-button>
          <el-button-group><el-button :type="viewMode === 'cards' ? 'primary' : 'default'" :icon="Grid" @click="viewMode = 'cards'">卡片</el-button><el-button :type="viewMode === 'table' ? 'primary' : 'default'" :icon="List" @click="viewMode = 'table'">列表</el-button></el-button-group>
        </el-form-item>
      </el-form>
    </section>

    <section v-if="viewMode === 'cards'" v-loading="loading" class="product-card-grid">
      <article v-for="row in visibleRows" :key="row.id" class="product-ledger-card" :class="`is-${productStatus(row.id)?.status ?? 'pending'}`" @click="showDetail(row.id)">
        <header>
          <div><small>{{ row.strategy_category || '策略待补充' }}</small><h2>{{ row.product_name }}</h2><span class="numeric">{{ row.product_code }}</span></div>
          <el-tag :type="statusType(productStatus(row.id)?.status)" effect="plain">{{ statusLabel(productStatus(row.id)?.status) }}</el-tag>
        </header>
        <div class="product-card-meta"><span><small>管理人</small><strong>{{ row.manager_name || '—' }}</strong></span><span><small>托管/外包</small><strong>{{ row.custodian_name || '—' }}</strong></span></div>
        <footer><span><small>总平层净值</small><strong class="numeric">{{ row.unit_nav ?? (row.share_count > 1 ? '详见份额' : '—') }}</strong></span><span><small>{{ summarySourceLabel(row.summary_source) }}</small><strong class="numeric">{{ productStatus(row.id)?.latest_update_date || '—' }}</strong></span><el-button text type="primary" :icon="View">查看详情</el-button></footer>
      </article>
      <el-empty v-if="!visibleRows.length" description="当前条件下没有产品" />
    </section>

    <section v-else class="panel data-panel">
      <el-table v-loading="loading" :data="visibleRows" empty-text="尚未从附件归纳出产品要素">
        <el-table-column label="产品主体" min-width="260">
          <template #default="{ row }"><strong class="table-primary">{{ row.product_name }}</strong><small class="cell-secondary numeric">{{ row.product_code }}</small></template>
        </el-table-column>
        <el-table-column label="最新估值日" width="122"><template #default="{ row }"><span class="numeric">{{ row.latest_source_date ?? '—' }}</span></template></el-table-column>
        <el-table-column label="份额" width="76" align="center"><template #default="{ row }"><el-tag size="small" type="info">{{ row.share_count }}</el-tag></template></el-table-column>
        <el-table-column label="更新状态" width="110"><template #default="{ row }"><el-tag :type="statusType(productStatus(row.id)?.status)">{{ statusLabel(productStatus(row.id)?.status) }}</el-tag></template></el-table-column>
        <el-table-column label="总平层净值" width="150" align="right"><template #default="{ row }"><strong class="numeric">{{ row.unit_nav ?? (row.share_count > 1 ? '详见份额' : '—') }}</strong><small class="cell-secondary">{{ summarySourceLabel(row.summary_source) }}</small></template></el-table-column>
        <el-table-column label="资产净值" width="160" align="right"><template #default="{ row }"><span class="numeric">{{ formatMoney(row.asset_value) }}</span></template></el-table-column>
        <el-table-column label="实收资本" width="160" align="right"><template #default="{ row }"><span class="numeric">{{ formatMoney(row.paid_in_capital) }}</span></template></el-table-column>
        <el-table-column label="经理 / 策略" width="140" align="center">
          <template #default="{ row }">
            <el-tag :type="row.investment_manager_info ? 'success' : 'warning'" size="small">经理{{ row.investment_manager_info ? '已录' : '缺失' }}</el-tag>
            <el-tag :type="row.investment_strategy_info ? 'success' : 'warning'" size="small" style="margin-left: 5px">策略{{ row.investment_strategy_info ? '已录' : '缺失' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="96" fixed="right"><template #default="{ row }"><el-button text type="primary" :icon="View" @click="showDetail(row.id)">详情</el-button></template></el-table-column>
      </el-table>
      <div class="pagination-wrap"><el-pagination v-model:current-page="filters.page" v-model:page-size="filters.pageSize" :total="total" :page-sizes="[20, 50, 100]" layout="total, sizes, prev, pager, next" @current-change="loadRows" /></div>
    </section>
    <div v-if="viewMode === 'cards'" class="pagination-wrap card-pagination"><el-pagination v-model:current-page="filters.page" v-model:page-size="filters.pageSize" :total="total" :page-sizes="[20, 50, 100]" layout="total, sizes, prev, pager, next" @current-change="loadRows" /></div>

    <el-drawer v-model="detailVisible" size="min(980px, 92vw)" destroy-on-close>
      <template #header>
        <div class="dialog-heading"><span>{{ detail?.product_name ?? '产品要素详情' }}</span><small>{{ detail?.product_code }} · 表格字段只读</small></div>
      </template>
      <div v-loading="detailLoading" class="product-detail">
        <template v-if="detail">
          <section class="profile-section">
            <div class="profile-section__header"><div><h3>运营补充信息</h3><p>优先显示人工值；恢复来源后继续跟随托管附件。</p></div><el-button v-if="canEdit" :icon="EditPen" type="primary" plain @click="openEdit">编辑</el-button></div>
            <div class="profile-grid">
              <article><header><strong>投资经理信息</strong><el-tag size="small" :type="detail.investment_manager_manual ? 'warning' : 'info'">{{ detail.investment_manager_manual ? '人工维护' : '附件来源' }}</el-tag></header><p>{{ text(detail.investment_manager_info) }}</p><el-button v-if="canEdit && detail.investment_manager_manual" text type="primary" :icon="RefreshRight" :loading="saving" @click="restoreSource('manager')">恢复附件来源</el-button></article>
              <article><header><strong>投资策略信息</strong><el-tag size="small" :type="detail.investment_strategy_manual ? 'warning' : 'info'">{{ detail.investment_strategy_manual ? '人工维护' : '附件来源' }}</el-tag></header><p>{{ text(detail.investment_strategy_info) }}</p><el-button v-if="canEdit && detail.investment_strategy_manual" text type="primary" :icon="RefreshRight" :loading="saving" @click="restoreSource('strategy')">恢复附件来源</el-button></article>
            </div>
            <el-descriptions :column="3" border size="small" style="margin-top: 14px">
              <el-descriptions-item label="成立日期">{{ text(detail.inception_date) }}</el-descriptions-item>
              <el-descriptions-item label="策略分类">{{ text(detail.strategy_category) }}</el-descriptions-item>
              <el-descriptions-item label="风险等级">{{ text(detail.risk_level) }}</el-descriptions-item>
              <el-descriptions-item label="管理人">{{ text(detail.manager_name) }}</el-descriptions-item>
              <el-descriptions-item label="托管/外包机构">{{ text(detail.custodian_name) }}</el-descriptions-item>
              <el-descriptions-item label="托管平台">
                <a v-if="detail.custodian_platform_url" class="platform-link" :href="detail.custodian_platform_url" target="_blank" rel="noopener noreferrer"><el-icon><Link /></el-icon>打开托管平台</a>
                <span v-else>未配置</span>
              </el-descriptions-item>
            </el-descriptions>
          </section>

          <section class="snapshot-section">
            <div class="snapshot-section__header">
              <div><h3>份额明细</h3><span>{{ detail.latest_source_date }} · {{ detail.latest_snapshots.length }} 个份额</span></div>
            </div>
            <el-empty v-if="!detail.latest_snapshots.length" description="暂无可见快照" />
            <template v-else>
              <div v-if="detail.latest_snapshots.length > 1" class="share-picker" role="list" aria-label="产品份额列表">
                <button
                  v-for="item in detail.latest_snapshots"
                  :key="item.id"
                  type="button"
                  :class="{ active: selectedSnapshotId === item.id }"
                  @click="selectedSnapshotId = item.id"
                >
                  <strong>{{ snapshotLabel(item) }}</strong>
                  <small>{{ item.nav_date }} · 点击查看详情</small>
                </button>
              </div>
              <div v-if="selectedSnapshot" class="share-detail-panel">
                <div class="field-completeness">本附件 21 项字段中有值 {{ selectedSnapshot.available_field_count }} 项；空值仍按原表留空，不做推断。</div>
                <el-descriptions :column="3" border size="small">
                  <el-descriptions-item label="日期">{{ selectedSnapshot.nav_date }}</el-descriptions-item><el-descriptions-item label="资产代码">{{ text(selectedSnapshot.asset_code) }}</el-descriptions-item><el-descriptions-item label="资产名称">{{ selectedSnapshot.product_name }}</el-descriptions-item>
                  <el-descriptions-item label="份额净值">{{ text(selectedSnapshot.unit_nav) }}</el-descriptions-item><el-descriptions-item label="累计净值">{{ text(selectedSnapshot.total_nav) }}</el-descriptions-item><el-descriptions-item label="资产净值">{{ formatMoney(selectedSnapshot.asset_value) }}</el-descriptions-item>
                  <el-descriptions-item label="实收资本">{{ formatMoney(selectedSnapshot.paid_in_capital) }}</el-descriptions-item><el-descriptions-item label="持有份额">{{ formatMoney(selectedSnapshot.holding_shares) }}</el-descriptions-item><el-descriptions-item label="参考市值">{{ formatMoney(selectedSnapshot.reference_market_value) }}</el-descriptions-item>
                  <el-descriptions-item label="总资产">{{ formatMoney(selectedSnapshot.total_assets) }}</el-descriptions-item><el-descriptions-item label="总资产/净资产">{{ formatRatio(selectedSnapshot.total_assets_nav_ratio) }}</el-descriptions-item><el-descriptions-item label="资产份额">{{ formatMoney(selectedSnapshot.asset_share) }}</el-descriptions-item>
                  <el-descriptions-item label="投资者名称">{{ text(selectedSnapshot.investor_name) }}</el-descriptions-item><el-descriptions-item label="投资者基金账号">{{ text(selectedSnapshot.investor_account) }}</el-descriptions-item><el-descriptions-item label="协会备案代码">{{ text(selectedSnapshot.registration_code) }}</el-descriptions-item>
                  <el-descriptions-item label="母基金单位净值">{{ text(selectedSnapshot.parent_unit_nav) }}</el-descriptions-item><el-descriptions-item label="母基金累计净值">{{ text(selectedSnapshot.parent_total_nav) }}</el-descriptions-item><el-descriptions-item label="母基金资产净值">{{ formatMoney(selectedSnapshot.parent_asset_value) }}</el-descriptions-item>
                  <el-descriptions-item label="母基金产品代码">{{ text(selectedSnapshot.parent_product_code) }}</el-descriptions-item><el-descriptions-item label="母基金产品名称">{{ text(selectedSnapshot.parent_product_name) }}</el-descriptions-item><el-descriptions-item label="母基金实收资本">{{ formatMoney(selectedSnapshot.parent_paid_in_capital) }}</el-descriptions-item>
                  <el-descriptions-item label="备注" :span="3">{{ text(selectedSnapshot.notes) }}</el-descriptions-item><el-descriptions-item label="来源附件" :span="3">{{ selectedSnapshot.source_file }}</el-descriptions-item>
                </el-descriptions>
              </div>
              <el-empty v-else description="点击一个份额查看托管字段" :image-size="72" />
            </template>
          </section>
        </template>
      </div>
    </el-drawer>

    <el-dialog v-model="editVisible" title="编辑投资经理与策略信息" width="min(720px, 92vw)" append-to-body>
      <el-form label-position="top">
        <el-form-item label="投资经理信息"><el-input v-model="profileForm.manager" type="textarea" :rows="6" maxlength="20000" show-word-limit /></el-form-item>
        <el-form-item label="投资策略信息"><el-input v-model="profileForm.strategy" type="textarea" :rows="6" maxlength="20000" show-word-limit /></el-form-item>
        <el-form-item label="托管平台链接"><el-input v-model="profileForm.platformUrl" maxlength="2000" placeholder="https://托管平台地址" /><small class="field-hint">仅支持 http:// 或 https://，首页和产品台账将以新窗口打开。</small></el-form-item>
      </el-form>
      <template #footer><el-button @click="editVisible = false">取消</el-button><el-button type="primary" :loading="saving" @click="saveProfile">保存并留痕</el-button></template>
    </el-dialog>
    </template>
    <FundNavView v-else embedded />
  </div>
</template>

<style scoped>
.product-center-tabs { width: fit-content; margin: -8px 0 22px; padding: 4px; display: flex; gap: 3px; border: 1px solid #e2dbd2; border-radius: 11px; background: #eee8df; }
.product-center-tabs button { min-width: 104px; padding: 9px 18px; border: 0; border-radius: 8px; color: #77736c; background: transparent; font: inherit; font-size: 12px; font-weight: 700; cursor: pointer; transition: color .18s ease, background .18s ease, box-shadow .18s ease; }
.product-center-tabs button:hover { color: #292724; }
.product-center-tabs button.active { color: #fff; background: #181715; box-shadow: 0 3px 10px rgba(24,23,21,.16); }
.product-metrics { margin-bottom: 20px; display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 16px; }
.product-metric { min-height: 122px; padding: 20px; display: grid; align-content: center; gap: 7px; border: 1px solid var(--line); border-radius: 12px; background: #efe9de; }
.product-metric small { color: #6f828a; font-weight: 700; }
.product-metric strong { color: var(--navy-800); font-size: 28px; }
.product-metric strong.money-value { font-size: 20px; }
.product-metric span { color: #93a1a6; font-size: 10px; }
.product-metric:nth-child(2) { color: #faf9f5; background: #181715; border-color: #181715; }
.product-metric:nth-child(2) small,.product-metric:nth-child(2) strong,.product-metric:nth-child(2) span { color: #faf9f5; }
.product-metric:nth-child(4) { color: #fff; background: #cc785c; border-color: #cc785c; }
.product-metric:nth-child(4) small,.product-metric:nth-child(4) strong,.product-metric:nth-child(4) span { color: #fff; }
.product-detail { min-height: 360px; }
.product-card-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; }
.product-ledger-card { min-width: 0; padding: 18px; display: grid; gap: 16px; border: 1px solid #e6dfd8; border-top: 4px solid #5db872; border-radius: 12px; background: #fffefa; cursor: pointer; transition: transform .2s ease, box-shadow .2s ease; }
.product-ledger-card:hover { transform: translateY(-2px); box-shadow: 0 8px 24px rgba(45,35,28,.08); }
.product-ledger-card.is-partial { border-top-color: #d4a017; }
.product-ledger-card.is-pending { border-top-color: #c64545; }
.product-ledger-card > header { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
.product-ledger-card > header > div { min-width: 0; flex: 1; }
.product-ledger-card > header .el-tag { flex: 0 0 auto; }
.product-ledger-card > header small { color: #cc785c; font-size: 10px; letter-spacing: .08em; }
.product-ledger-card h2 { min-height: 52px; margin: 5px 0 4px; display: -webkit-box; overflow: hidden; color: #141413; font-family: Georgia, "Times New Roman", serif; font-size: 21px; font-weight: 400; line-height: 1.25; overflow-wrap: anywhere; -webkit-box-orient: vertical; -webkit-line-clamp: 2; }
.product-ledger-card > header span { color: #8e8b82; font-size: 10px; }
.product-card-meta { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
.product-card-meta > span { min-width: 0; padding: 10px; display: grid; gap: 4px; border-radius: 8px; background: #f5f0e8; }
.product-card-meta small,.product-ledger-card footer small { color: #8e8b82; font-size: 9px; }
.product-card-meta strong { overflow: hidden; color: #3d3d3a; font-size: 11px; font-weight: 500; text-overflow: ellipsis; white-space: nowrap; }
.product-ledger-card footer { min-width: 0; display: grid; grid-template-columns: minmax(84px, 1fr) minmax(100px, 1fr) auto; align-items: end; gap: 12px; }
.product-ledger-card footer > span { min-width: 0; display: grid; gap: 3px; }
.product-ledger-card footer strong { color: #252523; font-size: 12px; font-weight: 500; }
.product-ledger-card footer .el-button { min-width: 0; margin-left: 0; padding-right: 4px; padding-left: 4px; }
.card-pagination { margin-top: 14px; border: 1px solid #e6dfd8; border-radius: 10px; background: #fffefa; }
.profile-section, .snapshot-section { margin-bottom: 24px; }
.profile-section__header, .snapshot-section__header { margin-bottom: 14px; display: flex; justify-content: space-between; align-items: center; }
.profile-section h3, .snapshot-section h3 { margin: 0; color: var(--ink-900); font-size: 16px; }
.profile-section__header p, .snapshot-section__header span { margin: 4px 0 0; color: #87969d; font-size: 11px; }
.share-picker { margin-bottom: 14px; display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }
.share-picker button { min-width: 0; padding: 13px; display: grid; gap: 5px; border: 1px solid #e6dfd8; border-radius: 9px; color: #3d3d3a; background: #fffefa; text-align: left; cursor: pointer; }
.share-picker button:hover, .share-picker button.active { border-color: #cc785c; background: #fbf0eb; }
.share-picker strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.share-picker small { color: #87969d; }
.share-detail-panel { padding-top: 2px; }
.profile-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
.profile-grid article { padding: 16px; border: 1px solid #e6dfd8; border-radius: 12px; background: #f5f0e8; }
.profile-grid header { display: flex; justify-content: space-between; gap: 10px; }
.profile-grid p { min-height: 90px; margin: 13px 0 4px; color: #526971; font-size: 12px; line-height: 1.75; white-space: pre-wrap; }
.field-completeness { margin-bottom: 12px; padding: 10px 13px; border-radius: 8px; color: #557078; background: #eef7f5; font-size: 11px; }
.platform-link { display: inline-flex; align-items: center; gap: 5px; color: var(--el-color-primary); text-decoration: none; }
.field-hint { margin-top: 5px; color: #87969d; font-size: 11px; }
@media (max-width: 1180px) { .product-card-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 900px) { .product-metrics, .profile-grid { grid-template-columns: 1fr 1fr; } }
@media (max-width: 620px) { .product-metrics, .profile-grid, .product-card-grid, .share-picker { grid-template-columns: 1fr; } }
@media (max-width: 420px) { .product-ledger-card footer { grid-template-columns: 1fr 1fr; } .product-ledger-card footer .el-button { grid-column: 1 / -1; justify-self: start; } }
</style>
