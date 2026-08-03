<script setup lang="ts">
import { DataLine, Download, Search } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { computed, onMounted, reactive, ref, watch } from 'vue'

import PageHeader from '@/components/PageHeader.vue'
import { apiErrorMessage } from '@/platform/api/http'

import NavHistoryChart from '../components/NavHistoryChart.vue'
import { downloadDailyExport, getFundHistory, getFundNav, getLatestFundNavDate, searchProducts } from '../api'
import type { FundHistory, FundNavItem, ProductOption } from '../api/types'
import { resolveExportDate } from '../utils/export-date'
import { groupProductOptions, productOptionLabel } from '../utils/product-options'

const loading = ref(false)
const exporting = ref(false)
const latestDateLoading = ref(false)
const productsLoading = ref(false)
const rows = ref<FundNavItem[]>([])
const total = ref(0)
const latestNavDate = ref<string | null>(null)
const filters = reactive({ productCode: '', dates: [] as string[], page: 1, pageSize: 20 })

const historyVisible = ref(false)
const historyLoading = ref(false)
const selectedProductCode = ref('')
const productOptions = ref<ProductOption[]>([])
const history = ref<FundHistory>()
const exportDate = computed(() => resolveExportDate(filters.dates, latestNavDate.value))
const groupedProductOptions = computed(() => groupProductOptions(productOptions.value))

function formatMoney(value: string | null) {
  if (value === null) return '—'
  return Number(value).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

async function loadRows() {
  loading.value = true
  try {
    const data = await getFundNav({
      page: filters.page,
      page_size: filters.pageSize,
      product_code: filters.productCode || undefined,
      date_from: filters.dates[0] || undefined,
      date_to: filters.dates[1] || undefined,
    })
    rows.value = data.items
    total.value = data.total
  } catch (error) {
    ElMessage.error(apiErrorMessage(error))
  } finally {
    loading.value = false
  }
}

async function loadLatestNavDate() {
  latestDateLoading.value = true
  try {
    latestNavDate.value = (await getLatestFundNavDate()).latest_nav_date
  } catch (error) {
    ElMessage.error(apiErrorMessage(error))
  } finally {
    latestDateLoading.value = false
  }
}

async function loadProductOptions() {
  productsLoading.value = true
  try {
    productOptions.value = await searchProducts()
  } catch (error) {
    ElMessage.error(apiErrorMessage(error))
  } finally {
    productsLoading.value = false
  }
}

function search() { filters.page = 1; void loadRows() }
function reset() { filters.productCode = ''; filters.dates = []; filters.page = 1; void loadRows() }

async function exportReport() {
  if (!exportDate.value) {
    ElMessage.warning('数据库中暂无可导出的基金净值')
    return
  }
  exporting.value = true
  try {
    const blob = await downloadDailyExport(exportDate.value)
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `每日基金净值汇总_${exportDate.value.replaceAll('-', '')}.xlsx`
    anchor.click()
    URL.revokeObjectURL(url)
    ElMessage.success('汇总文件已生成')
  } catch (error) {
    ElMessage.error(apiErrorMessage(error))
  } finally {
    exporting.value = false
  }
}

async function loadHistory(productCode: string) {
  historyLoading.value = true
  history.value = undefined
  try { history.value = await getFundHistory(productCode) }
  catch (error) { ElMessage.error(apiErrorMessage(error)) }
  finally { historyLoading.value = false }
}

function showHistory(productCode: string) {
  historyVisible.value = true
  if (selectedProductCode.value === productCode) void loadHistory(productCode)
  else selectedProductCode.value = productCode
}

watch(selectedProductCode, (value) => { if (value) void loadHistory(value) })
watch(() => filters.pageSize, search)
onMounted(() => {
  void loadRows()
  void loadLatestNavDate()
  void loadProductOptions()
})
</script>

<template>
  <div>
    <PageHeader
      eyebrow="NAV Ledger"
      title="基金净值"
      description="查询标准化后的历史净值，查看单只产品曲线，并按估值日导出运营汇总。"
    >
      <el-button
        :icon="Download"
        type="primary"
        :loading="exporting || latestDateLoading"
        :disabled="!exportDate"
        @click="exportReport"
      >{{ exportDate ? `导出 ${exportDate}` : '暂无可导出净值' }}</el-button>
    </PageHeader>

    <section class="panel filter-panel">
      <el-form class="filter-form" label-position="top" @submit.prevent="search">
        <el-form-item label="已归档基金">
          <el-select
            v-model="filters.productCode"
            clearable
            filterable
            :loading="productsLoading"
            placeholder="选择或输入基金名称、代码"
            style="width: 340px"
            @change="search"
          >
            <el-option-group
              v-for="group in groupedProductOptions"
              :key="group.fundGroupName"
              :label="group.options.length > 1 ? `${group.fundGroupName} · ${group.options.length}个份额` : group.fundGroupName"
            >
              <el-option
                v-for="item in group.options"
                :key="item.product_code"
                :label="productOptionLabel(item)"
                :value="item.product_code"
              />
            </el-option-group>
          </el-select>
        </el-form-item>
        <el-form-item label="估值日期">
          <el-date-picker v-model="filters.dates" type="daterange" value-format="YYYY-MM-DD" start-placeholder="开始日期" end-placeholder="结束日期" />
        </el-form-item>
        <el-form-item class="filter-actions">
          <el-button :icon="Search" type="primary" @click="search">查询</el-button>
          <el-button @click="reset">重置</el-button>
        </el-form-item>
      </el-form>
    </section>

    <section class="panel data-panel">
      <el-table v-loading="loading" :data="rows" empty-text="没有符合条件的净值数据">
        <el-table-column prop="product_name" label="产品名称" min-width="250" show-overflow-tooltip>
          <template #default="{ row }">
            <strong class="table-primary">{{ row.product_name }}</strong>
            <el-tag v-if="row.share_class" size="small" type="info" style="margin-left: 8px">{{ row.share_class }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="product_code" label="产品代码" width="138"><template #default="{ row }"><span class="numeric">{{ row.product_code }}</span></template></el-table-column>
        <el-table-column prop="nav_date" label="估值日期" width="120"><template #default="{ row }"><span class="numeric">{{ row.nav_date }}</span></template></el-table-column>
        <el-table-column label="单位净值" width="126" align="right"><template #default="{ row }"><strong class="numeric">{{ row.unit_nav ?? '—' }}</strong></template></el-table-column>
        <el-table-column label="累计净值" width="126" align="right"><template #default="{ row }"><span class="numeric">{{ row.total_nav ?? '—' }}</span></template></el-table-column>
        <el-table-column label="资产净值" width="170" align="right"><template #default="{ row }"><span class="numeric">{{ formatMoney(row.asset_value) }}</span></template></el-table-column>
        <el-table-column label="来源" min-width="170" show-overflow-tooltip><template #default="{ row }"><span class="source-text">{{ row.source_file }}</span></template></el-table-column>
        <el-table-column label="操作" width="92" fixed="right"><template #default="{ row }"><el-button text type="primary" :icon="DataLine" @click="showHistory(row.product_code)">曲线</el-button></template></el-table-column>
      </el-table>
      <div class="pagination-wrap">
        <el-pagination v-model:current-page="filters.page" v-model:page-size="filters.pageSize" :total="total" :page-sizes="[20, 50, 100]" layout="total, sizes, prev, pager, next" @current-change="loadRows" />
      </div>
    </section>

    <el-dialog v-model="historyVisible" width="min(920px, 92vw)" destroy-on-close>
      <template #header>
        <div class="dialog-heading"><span>历史净值曲线</span><small>最多展示最近 5,000 个数据点</small></div>
      </template>
      <el-select
        v-model="selectedProductCode"
        filterable
        placeholder="输入产品名称或代码切换产品"
        :loading="productsLoading"
        style="width: min(480px, 100%); margin-bottom: 20px"
      >
        <el-option-group
          v-for="group in groupedProductOptions"
          :key="group.fundGroupName"
          :label="group.options.length > 1 ? `${group.fundGroupName} · ${group.options.length}个份额` : group.fundGroupName"
        >
          <el-option
            v-for="item in group.options"
            :key="item.product_code"
            :label="productOptionLabel(item)"
            :value="item.product_code"
          />
        </el-option-group>
      </el-select>
      <div v-loading="historyLoading" class="history-panel">
        <div v-if="history" class="history-panel__meta"><strong>{{ history.product_name }}</strong><span class="numeric">{{ history.product_code }} · {{ history.points.length }} 条</span></div>
        <NavHistoryChart v-if="history" :points="history.points" />
      </div>
    </el-dialog>
  </div>
</template>
