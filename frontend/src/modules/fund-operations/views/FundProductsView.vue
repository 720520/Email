<script setup lang="ts">
import { EditPen, RefreshRight, Search, View } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { computed, onMounted, reactive, ref, watch } from 'vue'

import PageHeader from '@/components/PageHeader.vue'
import { apiErrorMessage } from '@/platform/api/http'
import { useAuthStore } from '@/platform/auth/auth.store'

import {
  getFundProduct,
  getFundProducts,
  getFundProductSummary,
  updateFundProductProfile,
} from '../api'
import type {
  FundProductDetail,
  FundProductItem,
  FundProductProfilePayload,
  FundProductSnapshot,
  FundProductSummary,
} from '../api/types'

const auth = useAuthStore()
const loading = ref(false)
const detailLoading = ref(false)
const saving = ref(false)
const rows = ref<FundProductItem[]>([])
const total = ref(0)
const summary = ref<FundProductSummary>()
const detail = ref<FundProductDetail>()
const detailVisible = ref(false)
const editVisible = ref(false)
const filters = reactive({ keyword: '', page: 1, pageSize: 20 })
const profileForm = reactive({ manager: '', strategy: '' })
const canEdit = computed(() => auth.user?.is_platform_admin || auth.user?.role !== 'viewer')

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

function search() { filters.page = 1; void loadRows() }
function reset() { filters.keyword = ''; filters.page = 1; void loadRows() }

async function showDetail(id: number) {
  detailVisible.value = true
  detailLoading.value = true
  detail.value = undefined
  try { detail.value = await getFundProduct(id) }
  catch (error) { ElMessage.error(apiErrorMessage(error)) }
  finally { detailLoading.value = false }
}

function openEdit() {
  if (!detail.value) return
  profileForm.manager = detail.value.investment_manager_info ?? ''
  profileForm.strategy = detail.value.investment_strategy_info ?? ''
  editVisible.value = true
}

async function saveProfile() {
  if (!detail.value) return
  saving.value = true
  try {
    detail.value = await updateFundProductProfile(detail.value.id, {
      investment_manager_info: profileForm.manager,
      investment_strategy_info: profileForm.strategy,
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

watch(() => filters.pageSize, search)
onMounted(() => { void loadRows(); void loadSummary() })
</script>

<template>
  <div>
    <PageHeader
      eyebrow="Product Master"
      title="产品要素"
      description="以托管附件表格为产品要素事实来源，按备案代码归并份额；投资经理和投资策略可人工维护并保留审计轨迹。"
    />

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
        <el-form-item class="filter-actions">
          <el-button :icon="Search" type="primary" @click="search">查询</el-button>
          <el-button @click="reset">重置</el-button>
        </el-form-item>
      </el-form>
    </section>

    <section class="panel data-panel">
      <el-table v-loading="loading" :data="rows" empty-text="尚未从附件归纳出产品要素">
        <el-table-column label="产品主体" min-width="260">
          <template #default="{ row }"><strong class="table-primary">{{ row.product_name }}</strong><small class="cell-secondary numeric">{{ row.product_code }}</small></template>
        </el-table-column>
        <el-table-column label="最新估值日" width="122"><template #default="{ row }"><span class="numeric">{{ row.latest_source_date ?? '—' }}</span></template></el-table-column>
        <el-table-column label="份额" width="76" align="center"><template #default="{ row }"><el-tag size="small" type="info">{{ row.share_count }}</el-tag></template></el-table-column>
        <el-table-column label="单位 / 累计净值" width="150" align="right"><template #default="{ row }"><strong class="numeric">{{ row.unit_nav ?? '多份额' }}</strong><small class="cell-secondary numeric">{{ row.total_nav ?? '—' }}</small></template></el-table-column>
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
          </section>

          <section class="snapshot-section">
            <div class="snapshot-section__header"><h3>最新托管要素快照</h3><span>{{ detail.latest_source_date }} · {{ detail.latest_snapshots.length }} 个份额</span></div>
            <el-empty v-if="!detail.latest_snapshots.length" description="暂无可见快照" />
            <el-tabs v-else type="border-card">
              <el-tab-pane v-for="item in detail.latest_snapshots" :key="item.id" :label="snapshotLabel(item)">
                <div class="field-completeness">本附件 21 项字段中有值 {{ item.available_field_count }} 项；空值仍按原表留空，不做推断。</div>
                <el-descriptions :column="3" border size="small">
                  <el-descriptions-item label="日期">{{ item.nav_date }}</el-descriptions-item><el-descriptions-item label="资产代码">{{ text(item.asset_code) }}</el-descriptions-item><el-descriptions-item label="资产名称">{{ item.product_name }}</el-descriptions-item>
                  <el-descriptions-item label="份额净值">{{ text(item.unit_nav) }}</el-descriptions-item><el-descriptions-item label="累计净值">{{ text(item.total_nav) }}</el-descriptions-item><el-descriptions-item label="资产净值">{{ formatMoney(item.asset_value) }}</el-descriptions-item>
                  <el-descriptions-item label="实收资本">{{ formatMoney(item.paid_in_capital) }}</el-descriptions-item><el-descriptions-item label="持有份额">{{ formatMoney(item.holding_shares) }}</el-descriptions-item><el-descriptions-item label="参考市值">{{ formatMoney(item.reference_market_value) }}</el-descriptions-item>
                  <el-descriptions-item label="总资产">{{ formatMoney(item.total_assets) }}</el-descriptions-item><el-descriptions-item label="总资产/净资产">{{ formatRatio(item.total_assets_nav_ratio) }}</el-descriptions-item><el-descriptions-item label="资产份额">{{ formatMoney(item.asset_share) }}</el-descriptions-item>
                  <el-descriptions-item label="投资者名称">{{ text(item.investor_name) }}</el-descriptions-item><el-descriptions-item label="投资者基金账号">{{ text(item.investor_account) }}</el-descriptions-item><el-descriptions-item label="协会备案代码">{{ text(item.registration_code) }}</el-descriptions-item>
                  <el-descriptions-item label="母基金单位净值">{{ text(item.parent_unit_nav) }}</el-descriptions-item><el-descriptions-item label="母基金累计净值">{{ text(item.parent_total_nav) }}</el-descriptions-item><el-descriptions-item label="母基金资产净值">{{ formatMoney(item.parent_asset_value) }}</el-descriptions-item>
                  <el-descriptions-item label="母基金产品代码">{{ text(item.parent_product_code) }}</el-descriptions-item><el-descriptions-item label="母基金产品名称">{{ text(item.parent_product_name) }}</el-descriptions-item><el-descriptions-item label="母基金实收资本">{{ formatMoney(item.parent_paid_in_capital) }}</el-descriptions-item>
                  <el-descriptions-item label="备注" :span="3">{{ text(item.notes) }}</el-descriptions-item><el-descriptions-item label="来源附件" :span="3">{{ item.source_file }}</el-descriptions-item>
                </el-descriptions>
              </el-tab-pane>
            </el-tabs>
          </section>
        </template>
      </div>
    </el-drawer>

    <el-dialog v-model="editVisible" title="编辑投资经理与策略信息" width="min(720px, 92vw)" append-to-body>
      <el-form label-position="top">
        <el-form-item label="投资经理信息"><el-input v-model="profileForm.manager" type="textarea" :rows="6" maxlength="20000" show-word-limit /></el-form-item>
        <el-form-item label="投资策略信息"><el-input v-model="profileForm.strategy" type="textarea" :rows="6" maxlength="20000" show-word-limit /></el-form-item>
      </el-form>
      <template #footer><el-button @click="editVisible = false">取消</el-button><el-button type="primary" :loading="saving" @click="saveProfile">保存并留痕</el-button></template>
    </el-dialog>
  </div>
</template>

<style scoped>
.product-metrics { margin-bottom: 20px; display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 16px; }
.product-metric { min-height: 122px; padding: 20px; display: grid; align-content: center; gap: 7px; border: 1px solid var(--line); border-radius: 16px; background: #fff; box-shadow: 0 8px 28px rgba(28,60,72,.04); }
.product-metric small { color: #6f828a; font-weight: 700; }
.product-metric strong { color: var(--navy-800); font-size: 28px; }
.product-metric strong.money-value { font-size: 20px; }
.product-metric span { color: #93a1a6; font-size: 10px; }
.product-detail { min-height: 360px; }
.profile-section, .snapshot-section { margin-bottom: 24px; }
.profile-section__header, .snapshot-section__header { margin-bottom: 14px; display: flex; justify-content: space-between; align-items: center; }
.profile-section h3, .snapshot-section h3 { margin: 0; color: var(--ink-900); font-size: 16px; }
.profile-section__header p, .snapshot-section__header span { margin: 4px 0 0; color: #87969d; font-size: 11px; }
.profile-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
.profile-grid article { padding: 16px; border: 1px solid #e1eae9; border-radius: 12px; background: #f8fbfa; }
.profile-grid header { display: flex; justify-content: space-between; gap: 10px; }
.profile-grid p { min-height: 90px; margin: 13px 0 4px; color: #526971; font-size: 12px; line-height: 1.75; white-space: pre-wrap; }
.field-completeness { margin-bottom: 12px; padding: 10px 13px; border-radius: 8px; color: #557078; background: #eef7f5; font-size: 11px; }
@media (max-width: 900px) { .product-metrics, .profile-grid { grid-template-columns: 1fr 1fr; } }
@media (max-width: 620px) { .product-metrics, .profile-grid { grid-template-columns: 1fr; } }
</style>
