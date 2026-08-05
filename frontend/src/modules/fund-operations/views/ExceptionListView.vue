<script setup lang="ts">
import { CircleCheck, DocumentAdd, Search, View } from '@element-plus/icons-vue'
import dayjs from 'dayjs'
import { ElMessage } from 'element-plus'
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import PageHeader from '@/components/PageHeader.vue'
import StatusTag from '@/components/StatusTag.vue'
import { apiErrorMessage } from '@/platform/api/http'

import EmailDetailDialog from '../components/EmailDetailDialog.vue'
import { getExceptions, getMailboxes, updateExceptionStatus } from '../api'
import type { ExceptionItem, ExceptionSeverity, ExceptionStatus, MailboxAccount } from '../api/types'

const route = useRoute()
const router = useRouter()
const mailboxes = ref<MailboxAccount[]>([])
const canOperate = computed(() => mailboxes.value.some((item) => item.permissions.can_operate))
const loading = ref(false)
const rows = ref<ExceptionItem[]>([])
const selectedEmailId = ref<number | null>(null)
const detailVisible = ref(false)
const total = ref(0)
const filters = reactive({
  category: typeof route.query.category === 'string' ? route.query.category : '',
  severity: '' as ExceptionSeverity | '',
  status: (typeof route.query.status === 'string' ? route.query.status : '') as ExceptionStatus | '',
  dates: [] as string[],
  page: 1,
  pageSize: 20,
  mailboxAccountId: '' as number | '',
})
const categories = ['日期缺失', '产品重复', '净值为空', '字段缺失', '格式错误', '文件异常', '其他异常']

async function loadRows() {
  loading.value = true
  try {
    const data = await getExceptions({
      page: filters.page,
      page_size: filters.pageSize,
      category: filters.category || undefined,
      severity: filters.severity || undefined,
      status: filters.status || undefined,
      date_from: filters.dates[0] || undefined,
      date_to: filters.dates[1] || undefined,
      mailbox_account_id: filters.mailboxAccountId || undefined,
    })
    rows.value = data.items
    total.value = data.total
  } catch (error) {
    ElMessage.error(apiErrorMessage(error))
  } finally {
    loading.value = false
  }
}

function search() { filters.page = 1; void loadRows() }
function reset() { filters.category = ''; filters.severity = ''; filters.status = ''; filters.mailboxAccountId = ''; filters.dates = []; filters.page = 1; void loadRows() }

function canOperateRow(row: ExceptionItem) {
  return mailboxes.value.find((item) => item.id === row.mailbox_account_id)?.permissions.can_operate === true
}

async function changeStatus(row: ExceptionItem, status: ExceptionStatus) {
  try {
    const updated = await updateExceptionStatus(row.id, status)
    Object.assign(row, updated)
    ElMessage.success(status === 'resolved' ? '异常已标记为解决' : '异常已忽略')
  } catch (error) {
    ElMessage.error(apiErrorMessage(error))
  }
}

function openEmail(row: ExceptionItem) {
  if (!row.email_id) return
  selectedEmailId.value = row.email_id
  detailVisible.value = true
}

watch(() => filters.pageSize, search)
onMounted(async () => {
  try { mailboxes.value = await getMailboxes() }
  catch (error) { ElMessage.error(apiErrorMessage(error)) }
  await loadRows()
})
</script>

<template>
  <div>
    <PageHeader
      eyebrow="Exception Queue"
      title="异常管理"
      description="集中复核解析失败、字段缺失和重复数据；每次处置都保留原始异常记录。"
    >
      <el-button v-if="canOperate" :icon="DocumentAdd" type="primary" @click="router.push('/operations')">上传重解析</el-button>
    </PageHeader>

    <section class="panel filter-panel">
      <el-form class="filter-form" label-position="top">
        <el-form-item label="异常类别"><el-select v-model="filters.category" clearable placeholder="全部类别" style="width: 150px"><el-option v-for="item in categories" :key="item" :label="item" :value="item" /></el-select></el-form-item>
        <el-form-item label="严重程度"><el-select v-model="filters.severity" clearable placeholder="全部" style="width: 130px"><el-option label="错误" value="error" /><el-option label="警告" value="warning" /></el-select></el-form-item>
        <el-form-item label="处理状态"><el-select v-model="filters.status" clearable placeholder="全部" style="width: 140px"><el-option label="待处理" value="open" /><el-option label="已解决" value="resolved" /><el-option label="已忽略" value="ignored" /></el-select></el-form-item>
        <el-form-item label="来源邮箱"><el-select v-model="filters.mailboxAccountId" clearable placeholder="全部邮箱" style="width: 170px"><el-option v-for="item in mailboxes" :key="item.id" :label="item.display_name" :value="item.id" /></el-select></el-form-item>
        <el-form-item label="发生日期"><el-date-picker v-model="filters.dates" type="daterange" value-format="YYYY-MM-DD" start-placeholder="开始日期" end-placeholder="结束日期" /></el-form-item>
        <el-form-item class="filter-actions"><el-button :icon="Search" type="primary" @click="search">查询</el-button><el-button @click="reset">重置</el-button></el-form-item>
      </el-form>
    </section>

    <section class="panel data-panel">
      <el-table v-loading="loading" :data="rows" empty-text="没有符合条件的异常记录">
        <el-table-column label="类别" width="110"><template #default="{ row }"><strong>{{ row.category }}</strong></template></el-table-column>
        <el-table-column label="级别" width="78"><template #default="{ row }"><span class="severity-label" :class="`severity-label--${row.severity}`">{{ row.severity === 'error' ? '错误' : '警告' }}</span></template></el-table-column>
        <el-table-column label="产品" min-width="190" show-overflow-tooltip><template #default="{ row }"><span>{{ row.product_name || row.product_code || '—' }}</span><small v-if="row.product_name && row.product_code" class="cell-secondary numeric">{{ row.product_code }}</small></template></el-table-column>
        <el-table-column label="异常说明" min-width="250" show-overflow-tooltip><template #default="{ row }"><span>{{ row.message }}</span><small v-if="row.field_name || row.row_number" class="cell-secondary">{{ row.sheet_name || '工作表' }} · 第 {{ row.row_number ?? '—' }} 行 · {{ row.field_name || '未知字段' }}</small></template></el-table-column>
        <el-table-column label="来源" min-width="190" show-overflow-tooltip><template #default="{ row }"><span>{{ row.mailbox_name }}</span><small class="cell-secondary">{{ row.source }}</small></template></el-table-column>
        <el-table-column label="发生时间" width="150"><template #default="{ row }"><span class="numeric">{{ dayjs(row.create_time).format('YYYY-MM-DD HH:mm') }}</span></template></el-table-column>
        <el-table-column label="状态" width="104"><template #default="{ row }"><StatusTag :status="row.status" /></template></el-table-column>
        <el-table-column v-if="canOperate" label="处置" width="146" fixed="right">
          <template #default="{ row }">
            <template v-if="canOperateRow(row) && row.status === 'open'">
              <el-button text type="success" :icon="CircleCheck" @click="changeStatus(row, 'resolved')">解决</el-button>
              <el-button text @click="changeStatus(row, 'ignored')">忽略</el-button>
            </template>
            <el-button v-else-if="canOperateRow(row)" text @click="changeStatus(row, 'open')">重新打开</el-button>
            <span v-else class="text-muted">只读</span>
          </template>
        </el-table-column>
        <el-table-column label="原邮件" width="108" fixed="right">
          <template #default="{ row }">
            <el-button v-if="row.email_id" text type="primary" :icon="View" @click="openEmail(row)">查看</el-button>
            <span v-else class="text-muted">—</span>
          </template>
        </el-table-column>
      </el-table>
      <div class="pagination-wrap"><el-pagination v-model:current-page="filters.page" v-model:page-size="filters.pageSize" :total="total" :page-sizes="[20, 50, 100]" layout="total, sizes, prev, pager, next" @current-change="loadRows" /></div>
    </section>
    <EmailDetailDialog v-model="detailVisible" :email-id="selectedEmailId" />
  </div>
</template>
