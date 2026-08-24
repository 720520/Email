<script setup lang="ts">
import { CirclePlus, Delete, EditPen, Refresh, Search } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onMounted, reactive, ref, watch } from 'vue'

import PageHeader from '@/components/PageHeader.vue'
import { getFundProducts } from '@/modules/fund-operations/api'
import type { FundProductItem } from '@/modules/fund-operations/api/types'
import { apiErrorMessage } from '@/platform/api/http'
import { useAuthStore } from '@/platform/auth/auth.store'

import {
  createDynamicReportField,
  disableDynamicReportField,
  getDynamicReportFields,
  getProductReportFieldValues,
  resolveDynamicReportFields,
  setProductReportFieldValue,
  updateDynamicReportField,
} from '../api'
import type {
  DynamicReportField,
  ProductReportFieldValue,
  ReportFieldDataType,
  ResolvedDynamicField,
} from '../api/types'

const auth = useAuthStore()
const loading = ref(false)
const fields = ref<DynamicReportField[]>([])
const products = ref<FundProductItem[]>([])
const values = ref<ProductReportFieldValue[]>([])
const resolved = ref<Record<string, ResolvedDynamicField>>({})
const selectedProductId = ref<number>()
const reportDate = ref('')
const showInactive = ref(false)
const fieldDialog = ref(false)
const valueDialog = ref(false)
const editingField = ref<DynamicReportField>()
const editingValue = ref<ProductReportFieldValue>()
const canManageDefinitions = computed(() => auth.user?.role === 'admin')
const canEditValues = computed(() => auth.user?.role !== 'viewer')
const customFields = computed(() => fields.value.filter((item) => !item.is_system && item.is_active))

const dataTypes: Array<{ value: ReportFieldDataType; label: string }> = [
  { value: 'string', label: '文本' }, { value: 'rich_text', label: '长文本' },
  { value: 'number', label: '数值' }, { value: 'percentage', label: '百分比' },
  { value: 'date', label: '日期' }, { value: 'boolean', label: '布尔值' },
  { value: 'image', label: '图片' }, { value: 'list', label: '列表' },
  { value: 'table', label: '表格' }, { value: 'chart', label: '图表' },
  { value: 'json', label: 'JSON' },
]

const fieldForm = reactive({
  field_key: 'custom.', label: '', description: '', data_type: 'string' as ReportFieldDataType,
  default_value: '', is_required: false, is_sensitive: false,
})
const valueForm = reactive({ value: '', effective_date: '', source_reference: '' })

function valueKind(type: ReportFieldDataType) {
  return ['image', 'list', 'table', 'chart', 'json'].includes(type) ? type : 'scalar'
}

function sourceLabel(source: string) {
  return ({ model: '产品主档', custom: '自定义', contract: '合同', metric: '指标', system: '系统' } as Record<string, string>)[source] ?? source
}

function displayValue(value: unknown) {
  if (value === null || value === undefined || value === '') return '—'
  return typeof value === 'object' ? JSON.stringify(value) : String(value)
}

async function load() {
  loading.value = true
  try {
    const [fieldRows, productPage] = await Promise.all([
      getDynamicReportFields(showInactive.value),
      getFundProducts({ page: 1, page_size: 100 }),
    ])
    fields.value = fieldRows
    products.value = productPage.items
    if (!selectedProductId.value && products.value.length) selectedProductId.value = products.value[0].id
    await loadValues()
  } catch (error) {
    ElMessage.error(apiErrorMessage(error))
  } finally {
    loading.value = false
  }
}

async function loadValues() {
  if (!selectedProductId.value) {
    values.value = []
    return
  }
  try {
    values.value = await getProductReportFieldValues(selectedProductId.value)
  } catch (error) {
    ElMessage.error(apiErrorMessage(error))
  }
}

function openCreate() {
  editingField.value = undefined
  Object.assign(fieldForm, {
    field_key: 'custom.', label: '', description: '', data_type: 'string',
    default_value: '', is_required: false, is_sensitive: false,
  })
  fieldDialog.value = true
}

function openEdit(item: DynamicReportField) {
  editingField.value = item
  Object.assign(fieldForm, {
    field_key: item.field_key, label: item.label, description: item.description ?? '',
    data_type: item.data_type, default_value: item.default_value ?? '',
    is_required: item.is_required, is_sensitive: item.is_sensitive,
  })
  fieldDialog.value = true
}

async function saveField() {
  if (!fieldForm.label.trim() || !/^custom\.[a-z][a-z0-9_.]*$/.test(fieldForm.field_key)) {
    ElMessage.warning('请填写合法的 custom.* 字段标识和名称')
    return
  }
  const payload = {
    label: fieldForm.label.trim(), description: fieldForm.description.trim() || undefined,
    data_type: fieldForm.data_type, value_kind: valueKind(fieldForm.data_type),
    default_value: fieldForm.default_value || undefined, is_required: fieldForm.is_required,
    is_sensitive: fieldForm.is_sensitive, format_config: {},
  }
  try {
    if (editingField.value?.id) await updateDynamicReportField(editingField.value.id, payload)
    else await createDynamicReportField({ field_key: fieldForm.field_key, ...payload })
    fieldDialog.value = false
    ElMessage.success(editingField.value ? '字段已更新并记录版本' : '自定义字段已创建')
    await load()
  } catch (error) {
    ElMessage.error(apiErrorMessage(error))
  }
}

async function disableField(item: DynamicReportField) {
  if (!item.id) return
  await ElMessageBox.confirm(`停用 ${item.field_key}？已保存的值和审计记录不会删除。`, '停用字段', { type: 'warning' })
  try {
    await disableDynamicReportField(item.id)
    ElMessage.success('字段已停用')
    await load()
  } catch (error) {
    ElMessage.error(apiErrorMessage(error))
  }
}

function openValue(item: ProductReportFieldValue) {
  editingValue.value = item
  valueForm.value = displayValue(item.value) === '—' ? '' : displayValue(item.value)
  valueForm.effective_date = item.effective_date ?? ''
  valueForm.source_reference = item.source_reference ?? ''
  valueDialog.value = true
}

async function saveValue() {
  if (!selectedProductId.value || !editingValue.value) return
  let value: unknown = valueForm.value
  if (['list', 'table', 'chart', 'json'].includes(editingValue.value.data_type) && valueForm.value) {
    try { value = JSON.parse(valueForm.value) } catch { ElMessage.warning('请输入有效 JSON'); return }
  }
  try {
    await setProductReportFieldValue(selectedProductId.value, editingValue.value.field_key, {
      value, effective_date: valueForm.effective_date || undefined,
      source_reference: valueForm.source_reference.trim() || undefined,
    })
    valueDialog.value = false
    ElMessage.success('产品字段值已保存并留痕')
    await loadValues()
  } catch (error) {
    ElMessage.error(apiErrorMessage(error))
  }
}

async function testResolve() {
  try {
    const result = await resolveDynamicReportFields({
      field_keys: fields.value.filter((item) => item.is_active).map((item) => item.field_key),
      product_id: selectedProductId.value, report_date: reportDate.value || undefined,
    })
    resolved.value = result.fields
    ElMessage.success(`已解析 ${Object.keys(result.fields).length} 个字段`)
  } catch (error) {
    ElMessage.error(apiErrorMessage(error))
  }
}

watch(selectedProductId, () => { void loadValues(); resolved.value = {} })
watch(showInactive, () => { void load() })
onMounted(load)
</script>

<template>
  <div v-loading="loading">
    <PageHeader eyebrow="Field Registry" title="字段中心" description="统一管理报表可调用字段、产品自定义值和解析来源；系统字段只读，自定义字段按租户隔离。">
      <template #actions><el-button :icon="Refresh" @click="load">刷新</el-button><el-button v-if="canManageDefinitions" type="primary" :icon="CirclePlus" @click="openCreate">新建字段</el-button></template>
    </PageHeader>

    <section class="panel">
      <div class="panel-header"><div><h2>字段注册表</h2><p>模板将通过稳定 field_key 调用字段</p></div><el-switch v-model="showInactive" active-text="显示已停用" /></div>
      <el-table :data="fields">
        <el-table-column prop="field_key" label="字段标识" min-width="230" />
        <el-table-column prop="label" label="显示名称" min-width="160" />
        <el-table-column label="来源" width="120"><template #default="{ row }"><el-tag :type="row.is_system ? 'info' : 'success'" effect="plain">{{ sourceLabel(row.source_type) }}</el-tag></template></el-table-column>
        <el-table-column prop="data_type" label="类型" width="120" />
        <el-table-column label="属性" width="160"><template #default="{ row }"><el-tag v-if="row.is_system" size="small">系统</el-tag><el-tag v-if="row.is_required" size="small" type="warning">必填</el-tag><el-tag v-if="!row.is_active" size="small" type="danger">已停用</el-tag></template></el-table-column>
        <el-table-column prop="version" label="版本" width="80" />
        <el-table-column label="操作" width="140"><template #default="{ row }"><template v-if="canManageDefinitions && !row.is_system"><el-button text type="primary" :icon="EditPen" @click="openEdit(row)">编辑</el-button><el-button v-if="row.is_active" text type="danger" :icon="Delete" @click="disableField(row)">停用</el-button></template><span v-else class="muted">只读</span></template></el-table-column>
      </el-table>
    </section>

    <section class="panel value-panel">
      <div class="panel-header"><div><h2>产品自定义字段值</h2><p>选择产品维护 custom.* 值，可按报告日期测试所有字段的最终解析结果</p></div><div class="value-tools"><el-select v-model="selectedProductId" filterable placeholder="选择基金" style="width: 300px"><el-option v-for="item in products" :key="item.id" :label="`${item.product_name} · ${item.product_code}`" :value="item.id" /></el-select><el-date-picker v-model="reportDate" value-format="YYYY-MM-DD" type="date" placeholder="报告日期" /><el-button :icon="Search" @click="testResolve">测试解析</el-button></div></div>
      <el-table :data="values" empty-text="当前租户尚未建立自定义字段">
        <el-table-column prop="field_key" label="字段标识" min-width="220" /><el-table-column prop="label" label="名称" min-width="150" /><el-table-column label="当前值" min-width="240"><template #default="{ row }">{{ displayValue(row.value) }}</template></el-table-column><el-table-column prop="effective_date" label="生效日" width="120" /><el-table-column label="操作" width="100"><template #default="{ row }"><el-button v-if="canEditValues" text type="primary" @click="openValue(row)">维护</el-button></template></el-table-column>
      </el-table>
      <div v-if="Object.keys(resolved).length" class="resolved-grid"><article v-for="item in resolved" :key="item.field_key"><code>{{ item.field_key }}</code><strong>{{ displayValue(item.value) }}</strong><small>{{ sourceLabel(item.source_type ?? '未提供') }}<template v-if="item.used_default"> · 默认值</template></small></article></div>
    </section>

    <el-dialog v-model="fieldDialog" :title="editingField ? '编辑自定义字段' : '新建自定义字段'" width="620px"><el-form label-position="top"><el-form-item label="字段标识"><el-input v-model="fieldForm.field_key" :disabled="Boolean(editingField)" placeholder="custom.roadshow_contact" /></el-form-item><el-form-item label="显示名称"><el-input v-model="fieldForm.label" /></el-form-item><el-form-item label="说明"><el-input v-model="fieldForm.description" type="textarea" /></el-form-item><div class="form-grid"><el-form-item label="数据类型"><el-select v-model="fieldForm.data_type" style="width: 100%"><el-option v-for="item in dataTypes" :key="item.value" :label="item.label" :value="item.value" /></el-select></el-form-item><el-form-item label="默认值"><el-input v-model="fieldForm.default_value" /></el-form-item></div><el-checkbox v-model="fieldForm.is_required">必填字段</el-checkbox><el-checkbox v-model="fieldForm.is_sensitive">敏感字段</el-checkbox></el-form><template #footer><el-button @click="fieldDialog = false">取消</el-button><el-button type="primary" @click="saveField">保存</el-button></template></el-dialog>

    <el-dialog v-model="valueDialog" :title="`维护：${editingValue?.label ?? ''}`" width="620px"><el-form label-position="top"><el-form-item label="字段值"><el-input v-model="valueForm.value" type="textarea" :rows="5" :placeholder="['list', 'table', 'chart', 'json'].includes(editingValue?.data_type ?? '') ? '请输入 JSON' : ''" /></el-form-item><el-form-item label="生效日期（可选）"><el-date-picker v-model="valueForm.effective_date" value-format="YYYY-MM-DD" type="date" /></el-form-item><el-form-item label="来源说明"><el-input v-model="valueForm.source_reference" placeholder="例如：产品路演资料 2026-08" /></el-form-item></el-form><template #footer><el-button @click="valueDialog = false">取消</el-button><el-button type="primary" @click="saveValue">保存</el-button></template></el-dialog>
  </div>
</template>

<style scoped>
.value-panel { margin-top: 18px; }
.value-tools { display: flex; gap: 10px; align-items: center; }
.muted { color: #94a3a8; font-size: 12px; }
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.resolved-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; padding: 18px; border-top: 1px solid var(--line); }
.resolved-grid article { min-width: 0; display: grid; gap: 6px; padding: 12px; border: 1px solid var(--line); border-radius: 10px; }
.resolved-grid code { overflow: hidden; color: var(--ink-600); text-overflow: ellipsis; }
.resolved-grid strong { overflow-wrap: anywhere; }
.resolved-grid small { color: #84949b; }
@media (max-width: 900px) { .value-tools { align-items: stretch; flex-direction: column; } .resolved-grid { grid-template-columns: 1fr; } }
</style>
