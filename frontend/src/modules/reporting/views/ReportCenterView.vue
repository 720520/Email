<script setup lang="ts">
import { DocumentAdd, Download, EditPen, Plus, Refresh, UploadFilled, View } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import PageHeader from '@/components/PageHeader.vue'
import { getFundProducts } from '@/modules/fund-operations/api'
import type { FundProductItem, HistoryPoint } from '@/modules/fund-operations/api/types'
import NavHistoryChart from '@/modules/fund-operations/components/NavHistoryChart.vue'
import { apiErrorMessage } from '@/platform/api/http'
import { useAuthStore } from '@/platform/auth/auth.store'

import {
  cancelReportBatch,
  createReportBatch,
  createReportDefinition,
  downloadReportBatch,
  downloadReport,
  generateReport,
  getReportDefinitions,
  getReportBatch,
  getReportBatchItems,
  getReportProductFields,
  getReportRuns,
  getReportTemplates,
  previewReport,
  regenerateReport,
  retryReportBatch,
  publishReportTemplate,
  updateReportProductField,
  uploadProductContract,
  uploadReportTemplate,
  validateReportTemplate,
} from '../api'
import type {
  ReportBatch,
  ReportBatchItem,
  ReportDefinition,
  ReportPreview,
  ReportProductField,
  ReportRun,
  ReportTemplateItem,
} from '../api/types'

const auth = useAuthStore()
const router = useRouter()
const loading = ref(false)
const previewLoading = ref(false)
const generating = ref(false)
const batchCreating = ref(false)
const batch = ref<ReportBatch>()
const batchItems = ref<ReportBatchItem[]>([])
const batchProductIds = ref<number[]>([])
let batchPollTimer: number | undefined
const products = ref<FundProductItem[]>([])
const templates = ref<ReportTemplateItem[]>([])
const definitions = ref<ReportDefinition[]>([])
const runs = ref<ReportRun[]>([])
const fields = ref<ReportProductField[]>([])
const preview = ref<ReportPreview>()
const contractInput = ref<HTMLInputElement>()
const templateInput = ref<HTMLInputElement>()
const templateFile = ref<File>()
const templateDialogVisible = ref(false)
const fieldDialogVisible = ref(false)
const canEdit = computed(() => auth.user?.is_platform_admin || auth.user?.role !== 'viewer')

const sectionOptions = [
  { key: 'product_info', label: '产品信息' },
  { key: 'performance', label: '收益指标' },
  { key: 'nav_chart', label: '净值曲线' },
  { key: 'strategy', label: '策略介绍' },
  { key: 'contract_terms', label: '合同要素' },
  { key: 'disclaimer', label: '免责声明' },
]

const builder = reactive({
  definitionId: undefined as number | undefined,
  name: '',
  productId: undefined as number | undefined,
  templateKey: 'builtin:weekly',
  reportDate: '',
  sections: sectionOptions.map((item) => item.key),
})
const fieldForm = reactive({ key: '', label: '', value: '', reason: '' })
const templateForm = reactive({ name: '', description: '' })

const groupedFields = computed(() => {
  const result = new Map<string, ReportProductField[]>()
  for (const item of fields.value) {
    const group = result.get(item.group) ?? []
    group.push(item)
    result.set(item.group, group)
  }
  return [...result.entries()].map(([group, items]) => ({ group, items }))
})

const chartPoints = computed<HistoryPoint[]>(() =>
  (preview.value?.nav_series ?? []).map((item) => ({
    nav_date: item.date,
    unit_nav: item.unit_nav,
    total_nav: item.total_nav,
  })),
)

const metricItems = computed<Array<[string, string | null | undefined]>>(() => {
  const metrics = preview.value?.performance
  if (!metrics) return []
  return [
    ['年化收益率', metrics.annualized_return],
    ['夏普比率', metrics.sharpe_ratio],
    ['今年以来', metrics.return_ytd],
    ['成立以来', metrics.return_since],
    ['今年最大回撤', metrics.max_drawdown_ytd],
    ['成立最大回撤', metrics.max_drawdown_since],
  ]
})

async function loadBaseData() {
  loading.value = true
  try {
    const [productPage, templateRows, definitionRows, runRows] = await Promise.all([
      getFundProducts({ page: 1, page_size: 100 }),
      getReportTemplates(),
      getReportDefinitions(),
      getReportRuns(),
    ])
    products.value = productPage.items
    templates.value = templateRows
    definitions.value = definitionRows
    runs.value = runRows
    if (!builder.productId && products.value.length) builder.productId = products.value[0].id
  } catch (error) {
    ElMessage.error(apiErrorMessage(error))
  } finally {
    loading.value = false
  }
}

async function loadProductContext() {
  if (!builder.productId) {
    fields.value = []
    preview.value = undefined
    return
  }
  try {
    const data = await getReportProductFields(builder.productId)
    fields.value = data.fields
    const product = products.value.find((item) => item.id === builder.productId)
    if (!builder.name) builder.name = `${product?.product_name ?? data.product_name}周报`
    if (!builder.reportDate && product?.latest_source_date) builder.reportDate = product.latest_source_date
    await refreshPreview()
  } catch (error) {
    ElMessage.error(apiErrorMessage(error))
  }
}

async function refreshPreview() {
  if (!builder.productId) return
  previewLoading.value = true
  try {
    preview.value = await previewReport({
      fund_product_id: builder.productId,
      report_date: builder.reportDate || undefined,
    })
    if (!builder.reportDate) builder.reportDate = preview.value.report_date
  } catch (error) {
    preview.value = undefined
    ElMessage.error(apiErrorMessage(error))
  } finally {
    previewLoading.value = false
  }
}

function applyDefinition(id?: number) {
  const item = definitions.value.find((definition) => definition.id === id)
  if (!item) return
  builder.name = item.name
  builder.productId = item.fund_product_id
  builder.templateKey = item.template_key
  builder.sections = [...item.sections]
}

async function saveDefinition() {
  if (!builder.productId || !builder.name.trim()) {
    ElMessage.warning('请选择产品并填写报表名称')
    return
  }
  try {
    const created = await createReportDefinition({
      name: builder.name.trim(),
      fund_product_id: builder.productId,
      template_key: builder.templateKey,
      report_type: builder.templateKey === 'builtin:weekly' ? 'weekly' : 'custom',
      sections: builder.sections,
      settings: {},
    })
    definitions.value.unshift(created)
    builder.definitionId = created.id
    ElMessage.success('报表配置已保存并写入审计日志')
  } catch (error) {
    ElMessage.error(apiErrorMessage(error))
  }
}

async function makeReport() {
  if (!builder.productId) {
    ElMessage.warning('请先选择产品')
    return
  }
  if (!builder.sections.length) {
    ElMessage.warning('至少选择一个报表区域')
    return
  }
  generating.value = true
  try {
    const result = await generateReport({
      fund_product_id: builder.productId,
      template_key: builder.templateKey,
      report_date: builder.reportDate || undefined,
      sections: builder.sections,
    })
    runs.value.unshift(result.run)
    ElMessage.success('报表已生成，输入快照和操作记录已留存')
    await downloadRun(result.run)
  } catch (error) {
    ElMessage.error(apiErrorMessage(error))
    runs.value = await getReportRuns().catch(() => runs.value)
  } finally {
    generating.value = false
  }
}

const batchProgress = computed(() => {
  if (!batch.value?.total_count) return 0
  const done = batch.value.success_count + batch.value.failed_count + batch.value.cancelled_count
  return Math.round(done * 100 / batch.value.total_count)
})

async function refreshBatch() {
  if (!batch.value) return
  try {
    const [current, items] = await Promise.all([
      getReportBatch(batch.value.id),
      getReportBatchItems(batch.value.id),
    ])
    batch.value = current
    batchItems.value = items
    if (!['pending', 'processing'].includes(current.status) && batchPollTimer) {
      window.clearInterval(batchPollTimer)
      batchPollTimer = undefined
    }
  } catch (error) {
    ElMessage.error(apiErrorMessage(error))
  }
}

function startBatchPolling() {
  if (batchPollTimer) window.clearInterval(batchPollTimer)
  batchPollTimer = window.setInterval(() => void refreshBatch(), 2000)
}

async function makeBatch() {
  if (!batchProductIds.value.length || !builder.reportDate) {
    ElMessage.warning('请选择基金产品和报告日期')
    return
  }
  batchCreating.value = true
  try {
    batch.value = await createReportBatch({
      product_ids: batchProductIds.value,
      template_key: builder.templateKey,
      report_date: builder.reportDate,
      sections: builder.sections,
      settings: {},
      idempotency_key: crypto.randomUUID(),
    })
    await refreshBatch()
    startBatchPolling()
    ElMessage.success(`已创建 ${batch.value.total_count} 份报表的异步任务`)
  } catch (error) {
    ElMessage.error(apiErrorMessage(error))
  } finally {
    batchCreating.value = false
  }
}

async function retryBatch() {
  if (!batch.value) return
  batch.value = await retryReportBatch(batch.value.id)
  startBatchPolling()
}

async function cancelBatch() {
  if (!batch.value) return
  batch.value = await cancelReportBatch(batch.value.id)
  await refreshBatch()
}

async function downloadBatch() {
  if (!batch.value) return
  const blob = await downloadReportBatch(batch.value.id)
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `report-batch-${batch.value.id}.zip`
  link.click()
  URL.revokeObjectURL(url)
}

async function downloadRun(run: ReportRun) {
  try {
    const blob = await downloadReport(run.id)
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = run.output_filename ?? `基金周报_${run.report_date}.pptx`
    link.click()
    URL.revokeObjectURL(url)
  } catch (error) {
    ElMessage.error(apiErrorMessage(error))
  }
}

async function regenerateRun(run: ReportRun) {
  try {
    await regenerateReport(run.id)
    runs.value = await getReportRuns()
    ElMessage.success('已按原始快照重新生成，并创建新的文件版本')
  } catch (error) {
    ElMessage.error(apiErrorMessage(error))
  }
}

function previewRun(run: ReportRun) {
  void router.push({ name: 'report-editor', params: { runId: run.id } })
}

function openFieldEditor(item: ReportProductField) {
  fieldForm.key = item.key
  fieldForm.label = item.label
  fieldForm.value = item.value ?? ''
  fieldForm.reason = ''
  fieldDialogVisible.value = true
}

async function saveField(restoreSource = false) {
  if (!builder.productId || !fieldForm.reason.trim()) {
    ElMessage.warning('请填写修改原因，作为审计留痕')
    return
  }
  try {
    const data = await updateReportProductField(builder.productId, fieldForm.key, {
      value: restoreSource ? undefined : fieldForm.value,
      reason: fieldForm.reason.trim(),
      restore_source: restoreSource,
    })
    fields.value = data.fields
    fieldDialogVisible.value = false
    ElMessage.success(restoreSource ? '已恢复来源值并留痕' : '人工值已保存并留痕')
    await refreshPreview()
  } catch (error) {
    ElMessage.error(apiErrorMessage(error))
  }
}

function chooseContract() {
  if (!builder.productId) {
    ElMessage.warning('请先选择产品')
    return
  }
  contractInput.value?.click()
}

async function onContractSelected(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file || !builder.productId) return
  try {
    const result = await uploadProductContract(builder.productId, file)
    ElMessage.success(`合同已归档，自动提取 ${result.extracted_count} 个字段，请逐项复核`)
    await loadProductContext()
  } catch (error) {
    ElMessage.error(apiErrorMessage(error))
  }
}

function onTemplateSelected(event: Event) {
  const input = event.target as HTMLInputElement
  templateFile.value = input.files?.[0]
}

async function saveTemplate() {
  if (!templateFile.value || !templateForm.name.trim()) {
    ElMessage.warning('请选择 PPTX 并填写模板名称')
    return
  }
  try {
    const item = await uploadReportTemplate(
      templateFile.value,
      templateForm.name.trim(),
      templateForm.description.trim() || undefined,
    )
    templates.value.push(item)
    templateFile.value = undefined
    templateForm.name = ''
    templateForm.description = ''
    if (templateInput.value) templateInput.value.value = ''
    ElMessage.success(
      item.validation_errors.length
        ? `草稿已创建，发现 ${item.validation_errors.length} 个校验问题`
        : '草稿已创建并通过校验，请确认发布',
    )
  } catch (error) {
    ElMessage.error(apiErrorMessage(error))
  }
}

async function validateTemplate(item: ReportTemplateItem) {
  if (!item.id) return
  try {
    const validated = await validateReportTemplate(item.id)
    templates.value = templates.value.map((row) => row.id === item.id ? validated : row)
    ElMessage[validated.validation_errors.length ? 'warning' : 'success'](
      validated.validation_errors.length
        ? `校验未通过：${validated.validation_errors.length} 个问题`
        : '模板校验通过，可以发布',
    )
  } catch (error) {
    ElMessage.error(apiErrorMessage(error))
  }
}

async function publishTemplate(item: ReportTemplateItem) {
  if (!item.id) return
  try {
    const published = await publishReportTemplate(item.id)
    templates.value = await getReportTemplates()
    builder.templateKey = published.key
    ElMessage.success(`模板 v${published.version} 已发布并锁定`)
  } catch (error) {
    ElMessage.error(apiErrorMessage(error))
  }
}

function sourceLabel(item: ReportProductField) {
  return ({ manual: '人工', contract: '合同', email: '邮件' } as Record<string, string>)[item.source_type ?? ''] ?? '未提供'
}

function sourceType(item: ReportProductField) {
  return item.is_manual ? 'warning' : item.source_type === 'contract' ? 'success' : item.source_type === 'email' ? 'info' : 'danger'
}

function templateValidationMessage(item: ReportTemplateItem) {
  return item.validation_errors.map((error) => error.message).join('；')
}

watch(() => builder.productId, () => { void loadProductContext() })
watch(() => builder.definitionId, applyDefinition)
onMounted(async () => { await loadBaseData(); await loadProductContext() })
onUnmounted(() => { if (batchPollTimer) window.clearInterval(batchPollTimer) })
</script>

<template>
  <div v-loading="loading">
    <PageHeader
      eyebrow="Report Studio"
      title="报表中心"
      description="选择模板或自定义报表区域；产品要素显示合同、邮件或人工来源，净值曲线只使用已归档的邮箱净值数据。"
    >
      <template #actions>
        <el-button v-if="canEdit" :icon="UploadFilled" @click="templateDialogVisible = true">上传模板</el-button>
        <el-button v-if="canEdit" type="primary" :icon="DocumentAdd" :loading="generating" @click="makeReport">生成 PPTX</el-button>
      </template>
    </PageHeader>

    <section class="report-workspace">
      <article class="panel builder-panel">
        <div class="panel-header"><div><h2>报表配置</h2><p>配置可以保存复用，报告日期为空时采用数据库最新净值日</p></div></div>
        <div class="panel-body">
          <el-form label-position="top">
            <el-form-item label="已保存配置">
              <el-select v-model="builder.definitionId" clearable placeholder="新建自定义报表" style="width: 100%">
                <el-option v-for="item in definitions" :key="item.id" :label="item.name" :value="item.id" />
              </el-select>
            </el-form-item>
            <div class="form-grid">
              <el-form-item label="基金产品">
                <el-select v-model="builder.productId" filterable placeholder="选择产品" style="width: 100%">
                  <el-option v-for="item in products" :key="item.id" :label="`${item.product_name} · ${item.product_code}`" :value="item.id" />
                </el-select>
              </el-form-item>
              <el-form-item label="报告日期">
                <el-date-picker v-model="builder.reportDate" value-format="YYYY-MM-DD" type="date" placeholder="默认最新净值日" style="width: 100%" @change="refreshPreview" />
              </el-form-item>
            </div>
            <el-form-item label="报表名称"><el-input v-model="builder.name" maxlength="200" /></el-form-item>
            <el-form-item label="报表模板">
              <el-select v-model="builder.templateKey" style="width: 100%">
                <el-option v-for="item in templates" :key="item.key" :label="item.name" :value="item.key" :disabled="item.status !== 'builtin' && item.status !== 'published'">
                  <span>{{ item.name }}</span><small class="option-note">{{ item.kind === 'builtin' ? '内置' : '租户模板' }}</small>
                </el-option>
              </el-select>
            </el-form-item>
            <el-form-item label="报表区域">
              <el-checkbox-group v-model="builder.sections" class="section-checkboxes">
                <el-checkbox v-for="item in sectionOptions" :key="item.key" :value="item.key">{{ item.label }}</el-checkbox>
              </el-checkbox-group>
            </el-form-item>
            <div class="builder-actions">
              <el-button :icon="Refresh" @click="refreshPreview">刷新预览</el-button>
              <el-button v-if="canEdit" :icon="Plus" @click="saveDefinition">保存配置</el-button>
              <el-button v-if="canEdit" type="primary" :icon="DocumentAdd" :loading="generating" @click="makeReport">生成并下载</el-button>
            </div>
          </el-form>
        </div>
      </article>

      <article class="panel preview-panel" v-loading="previewLoading">
        <div class="panel-header"><div><h2>数据预览</h2><p>{{ preview ? `${preview.product_name} · ${preview.report_date}` : '请选择有净值数据的产品' }}</p></div></div>
        <div v-if="preview" class="panel-body">
          <div class="preview-metrics">
            <div v-for="item in metricItems" :key="item[0]"><small>{{ item[0] }}</small><strong>{{ item[1] ?? '—' }}</strong></div>
          </div>
          <NavHistoryChart :points="chartPoints" />
          <p class="data-note">曲线共 {{ preview.nav_series.length }} 个净值点，截止 {{ preview.report_date }}；不接受人工录入净值。</p>
        </div>
        <el-empty v-else description="暂无可预览数据" />
      </article>
    </section>

    <section class="panel batch-panel">
      <div class="panel-header"><div><h2>批量生成</h2><p>任务由独立 Worker 异步处理，单份失败不影响其他产品</p></div></div>
      <div class="panel-body">
        <el-select v-model="batchProductIds" multiple filterable collapse-tags collapse-tags-tooltip placeholder="选择需要生成的基金" style="width: 100%">
          <el-option v-for="item in products" :key="item.id" :label="`${item.product_name} · ${item.product_code}`" :value="item.id" />
        </el-select>
        <div class="batch-actions">
          <el-button @click="batchProductIds = products.map((item) => item.id)">全选当前产品列表</el-button>
          <el-button @click="batchProductIds = []">清空</el-button>
          <el-button v-if="canEdit" type="primary" :loading="batchCreating" @click="makeBatch">创建批量任务</el-button>
          <template v-if="batch">
            <el-button v-if="batch.failed_count" @click="retryBatch">重试失败项</el-button>
            <el-button v-if="['pending', 'processing'].includes(batch.status)" type="danger" plain @click="cancelBatch">取消未开始项</el-button>
            <el-button :icon="Download" @click="downloadBatch">下载 ZIP</el-button>
          </template>
        </div>
        <template v-if="batch">
          <el-progress :percentage="batchProgress" :status="batch.failed_count ? 'exception' : batchProgress === 100 ? 'success' : undefined" />
          <p class="data-note">共 {{ batch.total_count }} 份；成功 {{ batch.success_count }}，失败 {{ batch.failed_count }}，取消 {{ batch.cancelled_count }}</p>
          <el-table :data="batchItems" max-height="320" empty-text="任务初始化中">
            <el-table-column prop="product_name" label="产品" min-width="220" />
            <el-table-column prop="status" label="状态" width="110" />
            <el-table-column prop="attempt_count" label="尝试次数" width="90" />
            <el-table-column prop="error_message" label="失败原因" min-width="240" show-overflow-tooltip />
          </el-table>
        </template>
      </div>
    </section>

    <section class="panel field-panel">
      <div class="panel-header">
        <div><h2>产品要素与来源</h2><p>合同和邮件提取值保留原始来源；人工覆盖必须填写原因并进入审计日志</p></div>
        <div><input ref="contractInput" hidden type="file" accept=".pdf,.docx,.txt" @change="onContractSelected"><el-button v-if="canEdit" :icon="UploadFilled" @click="chooseContract">上传合同并提取</el-button></div>
      </div>
      <div class="field-groups">
        <article v-for="group in groupedFields" :key="group.group" class="field-group">
          <h3>{{ group.group }}</h3>
          <div v-for="item in group.items" :key="item.key" class="field-row">
            <div class="field-copy"><span>{{ item.label }}</span><strong>{{ item.value || '—' }}</strong><small v-if="item.source_reference">{{ item.source_reference }}</small></div>
            <el-tag :type="sourceType(item)" effect="plain" size="small">{{ sourceLabel(item) }}</el-tag>
            <el-button v-if="canEdit && item.editable" text type="primary" :icon="EditPen" @click="openFieldEditor(item)">修改</el-button>
          </div>
        </article>
      </div>
    </section>

    <section class="panel run-panel">
      <div class="panel-header"><div><h2>生成记录</h2><p>每次生成均保存字段来源、净值序列、计算指标和模板版本快照</p></div></div>
      <el-table :data="runs" empty-text="尚未生成报表">
        <el-table-column prop="product_name" label="产品" min-width="230" />
        <el-table-column prop="report_date" label="报告日期" width="120" />
        <el-table-column prop="template_key" label="模板" min-width="150" />
        <el-table-column label="文件版本" width="90"><template #default="{ row }">v{{ row.current_version ?? '—' }}</template></el-table-column>
        <el-table-column label="状态" width="100"><template #default="{ row }"><el-tag :type="row.status === 'success' ? 'success' : 'danger'">{{ row.status === 'success' ? '成功' : '失败' }}</el-tag></template></el-table-column>
        <el-table-column prop="create_time" label="生成时间" width="185" />
        <el-table-column label="操作" width="260"><template #default="{ row }"><template v-if="row.status === 'success'"><el-button text type="primary" :icon="View" @click="previewRun(row)">在线预览</el-button><el-button text type="primary" :icon="Download" @click="downloadRun(row)">下载</el-button><el-button v-if="canEdit" text type="success" @click="regenerateRun(row)">按快照重生成</el-button></template><el-tooltip v-else :content="`${row.error_stage || '生成'}：${row.error_message || '生成失败'}`"><el-button text :icon="View">原因</el-button></el-tooltip></template></el-table-column>
      </el-table>
    </section>

    <el-dialog v-model="fieldDialogVisible" :title="`人工修改：${fieldForm.label}`" width="620px">
      <el-alert type="warning" :closable="false" show-icon title="人工值将覆盖合同或邮件来源值，但不会删除原始值；恢复来源同样会留痕。" />
      <el-form label-position="top" style="margin-top: 18px">
        <el-form-item label="字段值"><el-input v-model="fieldForm.value" type="textarea" :rows="5" maxlength="20000" show-word-limit /></el-form-item>
        <el-form-item label="修改原因（必填）"><el-input v-model="fieldForm.reason" maxlength="500" placeholder="例如：依据补充协议第 3 条修订" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="fieldDialogVisible = false">取消</el-button><el-button type="warning" @click="saveField(true)">恢复来源值</el-button><el-button type="primary" @click="saveField(false)">保存人工值</el-button></template>
    </el-dialog>

    <el-dialog v-model="templateDialogVisible" title="模板草稿与发布" width="760px">
      <el-alert type="info" :closable="false" show-icon title="支持 {{product_name}} 等字段占位符；已知产品表、收益表、合同要素表和折线图也会按结构自动识别。" />
      <el-form label-position="top" style="margin-top: 18px">
        <el-form-item label="模板名称"><el-input v-model="templateForm.name" /></el-form-item>
        <el-form-item label="模板说明"><el-input v-model="templateForm.description" type="textarea" :rows="2" /></el-form-item>
        <el-form-item label="PPTX 文件"><input ref="templateInput" type="file" accept=".pptx" @change="onTemplateSelected"><small class="file-note">{{ templateFile?.name ?? '尚未选择文件' }}</small></el-form-item>
      </el-form>
      <el-divider />
      <el-table :data="templates.filter((item) => item.kind === 'uploaded')" empty-text="尚未上传自定义模板" max-height="300">
        <el-table-column prop="name" label="模板" min-width="160" />
        <el-table-column label="版本" width="80"><template #default="{ row }">v{{ row.version }}</template></el-table-column>
        <el-table-column label="状态" width="100"><template #default="{ row }"><el-tag :type="row.status === 'published' ? 'success' : row.validation_errors.length ? 'danger' : 'warning'">{{ row.status === 'published' ? '已发布' : row.status === 'validating' ? '校验中' : '草稿' }}</el-tag></template></el-table-column>
        <el-table-column label="字段/组件" min-width="130"><template #default="{ row }">{{ row.required_fields.length }} / {{ row.required_components.length }}</template></el-table-column>
        <el-table-column label="校验" min-width="170"><template #default="{ row }"><span v-if="!row.validation_errors.length">通过</span><el-tooltip v-else :content="templateValidationMessage(row)"><span class="template-error">{{ row.validation_errors.length }} 个问题</span></el-tooltip></template></el-table-column>
        <el-table-column label="操作" width="150"><template #default="{ row }"><template v-if="row.status === 'draft'"><el-button text type="primary" @click="validateTemplate(row)">校验</el-button><el-button text type="success" :disabled="row.validation_errors.length > 0" @click="publishTemplate(row)">发布</el-button></template></template></el-table-column>
      </el-table>
      <template #footer><el-button @click="templateDialogVisible = false">取消</el-button><el-button type="primary" @click="saveTemplate">上传模板</el-button></template>
    </el-dialog>
  </div>
</template>

<style scoped>
.report-workspace { display: grid; grid-template-columns: minmax(360px, .82fr) minmax(500px, 1.4fr); gap: 18px; margin-bottom: 18px; }
.builder-panel, .preview-panel { min-width: 0; }
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.section-checkboxes { display: grid; grid-template-columns: repeat(3, 1fr); width: 100%; }
.builder-actions { display: flex; justify-content: flex-end; gap: 8px; }
.option-note { float: right; margin-left: 24px; color: #84949b; }
.preview-metrics { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1px; overflow: hidden; margin-bottom: 12px; border: 1px solid var(--line); border-radius: 12px; background: var(--line); }
.preview-metrics div { padding: 12px 14px; display: grid; gap: 5px; background: #fff; }
.preview-metrics small { color: var(--ink-600); }
.preview-metrics strong { color: var(--navy-800); font-size: 20px; font-variant-numeric: tabular-nums; }
.data-note { margin: 8px 0 0; color: var(--ink-600); font-size: 12px; text-align: right; }
.field-panel, .run-panel, .batch-panel { margin-top: 18px; }
.batch-actions { display: flex; justify-content: flex-end; gap: 8px; margin: 14px 0; }
.field-groups { padding: 18px; display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
.field-group { overflow: hidden; border: 1px solid var(--line); border-radius: 12px; }
.field-group h3 { margin: 0; padding: 11px 14px; color: var(--navy-800); background: #f5f8f7; font-size: 13px; }
.field-row { min-height: 58px; padding: 9px 12px; display: grid; grid-template-columns: minmax(0, 1fr) auto auto; align-items: center; gap: 9px; border-top: 1px solid #edf2f1; }
.field-copy { min-width: 0; display: grid; gap: 2px; }
.field-copy span, .field-copy small { overflow: hidden; color: #829198; font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }
.field-copy strong { overflow: hidden; color: var(--ink-900); font-size: 13px; line-height: 1.45; text-overflow: ellipsis; white-space: nowrap; }
.file-note { margin-left: 12px; color: var(--ink-600); }
.template-error { color: var(--el-color-danger); cursor: help; }
@media (max-width: 1080px) { .report-workspace { grid-template-columns: 1fr; } .field-groups { grid-template-columns: 1fr; } }
@media (max-width: 640px) { .form-grid, .section-checkboxes, .preview-metrics { grid-template-columns: 1fr; } }
</style>
