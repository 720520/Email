<script setup lang="ts">
import { Clock, CopyDocument, Delete, Download, EditPen, Lock, Plus, Select, UploadFilled } from '@element-plus/icons-vue'
import dayjs from 'dayjs'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { UploadRequestOptions } from 'element-plus'
import { computed, onMounted, reactive, ref } from 'vue'

import PageHeader from '@/components/PageHeader.vue'
import { apiErrorMessage } from '@/platform/api/http'

import {
  createFilingField,
  deleteFilingField,
  downloadFilingFile,
  downloadFilingProfile,
  getFilingProfile,
  updateFilingField,
  updateFilingProfile,
  uploadFilingFile,
} from '../api'
import type { FilingFieldDefinition, FilingFieldPayload, FilingProfile } from '../api/types'

const loading = ref(false)
const saving = ref(false)
const editingValues = ref(false)
const profile = ref<FilingProfile>()
const fieldValues = ref<Record<string, string>>({})
const fieldDialogVisible = ref(false)
const editingField = ref<FilingFieldDefinition>()
const historyField = ref<FilingFieldDefinition>()
const historyVisible = ref(false)
const sourceFormsText = ref('')
const fieldForm = reactive<FilingFieldPayload>({
  label: '', category: '', field_type: 'text', sensitive: false, multiline: false,
  source_forms: [], sort_order: 0,
})

const fieldCategories = computed(() => [...new Set(profile.value?.fields.map((item) => item.category) ?? [])])
const completedFields = computed(() => profile.value?.fields.filter((item) => (
  item.field_type === 'text' ? fieldValues.value[item.key]?.trim() : item.file_versions.length
)).length ?? 0)
const fileFieldCount = computed(() => profile.value?.fields.filter((item) => item.field_type === 'file').length ?? 0)

async function load() {
  loading.value = true
  try {
    profile.value = await getFilingProfile()
    fieldValues.value = { ...profile.value.field_values }
  } catch (error) { ElMessage.error(apiErrorMessage(error)) }
  finally { loading.value = false }
}

function categoryFields(category: string) {
  return profile.value?.fields.filter((item) => item.category === category) ?? []
}

function plainText() {
  if (!profile.value) return ''
  const lines = [`${profile.value.tenant_name}｜开户与备案复用资料`, '']
  for (const category of fieldCategories.value) {
    lines.push(`【${category}】`)
    for (const field of categoryFields(category)) {
      const latest = field.file_versions[0]
      lines.push(field.field_type === 'text'
        ? `${field.label}：${fieldValues.value[field.key] ?? ''}`
        : `${field.label}：${latest ? `${latest.original_name}（v${latest.version}）` : '未上传'}`)
    }
    lines.push('')
  }
  return lines.join('\n')
}

async function copyAll() {
  await navigator.clipboard.writeText(plainText())
  ElMessage.success('全部字段和文件清单已复制')
}

async function copyValue(label: string, value: string | undefined) {
  if (!value) return ElMessage.warning('该字段尚未填写')
  await navigator.clipboard.writeText(value)
  ElMessage.success(`已复制：${label}`)
}

async function downloadProfile() {
  try {
    saveBlob(await downloadFilingProfile(), `${profile.value?.tenant_name ?? '租户'}_开户备案复用资料.txt`)
  } catch (error) { ElMessage.error(apiErrorMessage(error)) }
}

async function downloadVersion(field: FilingFieldDefinition, version = field.file_versions[0]) {
  if (!version) return
  try {
    saveBlob(await downloadFilingFile(version.download_url), version.original_name)
  } catch (error) { ElMessage.error(apiErrorMessage(error)) }
}

function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(url)
}

function cancelValueEdit() {
  if (!profile.value) return
  fieldValues.value = { ...profile.value.field_values }
  editingValues.value = false
}

async function saveValues() {
  saving.value = true
  try {
    profile.value = await updateFilingProfile({ field_values: fieldValues.value })
    editingValues.value = false
    ElMessage.success('文本资料已保存并留痕')
  } catch (error) { ElMessage.error(apiErrorMessage(error)) }
  finally { saving.value = false }
}

function openCreateField() {
  editingField.value = undefined
  Object.assign(fieldForm, { label: '', category: fieldCategories.value[0] ?? '自定义资料', field_type: 'text', sensitive: false, multiline: false, source_forms: [], sort_order: (profile.value?.fields.length ?? 0) * 10 })
  sourceFormsText.value = ''
  fieldDialogVisible.value = true
}

function openEditField(field: FilingFieldDefinition) {
  editingField.value = field
  Object.assign(fieldForm, { label: field.label, category: field.category, field_type: field.field_type, sensitive: field.sensitive, multiline: field.multiline, source_forms: [...field.source_forms], sort_order: field.sort_order })
  sourceFormsText.value = field.source_forms.join('、')
  fieldDialogVisible.value = true
}

async function saveField() {
  if (!fieldForm.label.trim() || !fieldForm.category.trim()) return ElMessage.warning('请填写字段名称和分类')
  saving.value = true
  try {
    const payload = { ...fieldForm, source_forms: sourceFormsText.value.split(/[、,，\n]/).map((item) => item.trim()).filter(Boolean) }
    if (editingField.value) await updateFilingField(editingField.value.id, payload)
    else await createFilingField(payload)
    fieldDialogVisible.value = false
    ElMessage.success(editingField.value ? '字段设置已修改并留痕' : '字段已新增并留痕')
    await load()
  } catch (error) { ElMessage.error(apiErrorMessage(error)) }
  finally { saving.value = false }
}

async function removeField(field: FilingFieldDefinition) {
  try {
    await ElMessageBox.confirm(
      field.field_type === 'file' && field.file_versions.length
        ? `删除“${field.label}”后页面将不再显示，但 ${field.file_versions.length} 个历史文件版本和审计记录仍会保留。`
        : `确认删除字段“${field.label}”？删除操作会记录到审计日志。`,
      '删除备案字段',
      { type: 'warning', confirmButtonText: '删除字段' },
    )
    await deleteFilingField(field.id)
    ElMessage.success('字段已删除，历史记录已保留')
    await load()
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') ElMessage.error(apiErrorMessage(error))
  }
}

async function uploadVersion(field: FilingFieldDefinition, options: UploadRequestOptions) {
  try {
    await uploadFilingFile(field.id, options.file)
    ElMessage.success(`${field.label}已上传新版本并留痕`)
    await load()
  } catch (error) {
    ElMessage.error(apiErrorMessage(error))
    throw error
  }
}

function uploadRequest(field: FilingFieldDefinition) {
  return (options: UploadRequestOptions) => uploadVersion(field, options)
}

function showHistory(field: FilingFieldDefinition) {
  historyField.value = field
  historyVisible.value = true
}

function formatSize(size: number) {
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}

onMounted(load)
</script>

<template>
  <div v-loading="loading">
    <PageHeader eyebrow="Reusable Filing Kit" title="备案资料库" description="管理员自由维护文本与文件字段；文件只追加版本，上传、更新和下载全程留痕。">
      <template #actions>
        <el-button :icon="CopyDocument" @click="copyAll">复制全部</el-button>
        <el-button :icon="Download" @click="downloadProfile">下载清单</el-button>
        <el-button v-if="profile?.can_edit" :icon="Plus" @click="openCreateField">新增字段</el-button>
        <el-button v-if="profile?.can_edit && !editingValues" type="primary" :icon="EditPen" @click="editingValues = true">编辑文本</el-button>
        <template v-if="editingValues"><el-button @click="cancelValueEdit">取消</el-button><el-button type="primary" :icon="Select" :loading="saving" @click="saveValues">保存文本</el-button></template>
      </template>
    </PageHeader>

    <el-alert v-if="profile && !profile.can_edit" class="page-alert" type="info" :closable="false" show-icon title="当前为只读模式：可以复制文本、下载文件和查看版本，只有租户管理员可以维护字段或上传新版本。" />

    <section v-if="profile" class="filing-overview">
      <article><small>当前私募牌照</small><strong>{{ profile.tenant_name }}</strong><span>资料严格按租户隔离</span></article>
      <article><small>资料完整度</small><strong>{{ completedFields }} / {{ profile.fields.length }}</strong><span>文本和文件字段统一统计</span></article>
      <article><small>文件字段</small><strong>{{ fileFieldCount }}</strong><span>历史版本永久保留</span></article>
      <article><small>权限与留痕</small><strong>{{ profile.can_edit ? '管理员' : '只读' }}</strong><span><el-icon><Lock /></el-icon>更新、下载均记审计日志</span></article>
    </section>

    <template v-if="profile">
      <section v-for="category in fieldCategories" :key="category" class="filing-section">
        <header><div><small>Reusable Materials</small><h2>{{ category }}</h2></div><span>{{ categoryFields(category).length }} 个字段</span></header>
        <div class="field-card-grid">
          <article v-for="field in categoryFields(category)" :key="field.id" class="field-card" :class="{ empty: field.field_type === 'text' ? !fieldValues[field.key] : !field.file_versions.length, 'is-file': field.field_type === 'file' }">
            <div class="field-card__head">
              <div><label>{{ field.label }}</label><span>{{ field.field_type === 'file' ? '文件' : '文本' }}</span></div>
              <div><el-tag v-if="field.sensitive" size="small" type="warning">敏感</el-tag><template v-if="profile.can_edit"><el-button link :icon="EditPen" @click="openEditField(field)" /><el-button link type="danger" :icon="Delete" @click="removeField(field)" /></template></div>
            </div>

            <template v-if="field.field_type === 'text'">
              <el-input v-if="editingValues" v-model="fieldValues[field.key]" :type="field.multiline ? 'textarea' : 'text'" :rows="3" clearable />
              <button v-else class="copy-value" type="button" @click="copyValue(field.label, fieldValues[field.key])"><span>{{ fieldValues[field.key] || '待管理员补充' }}</span><el-icon><CopyDocument /></el-icon></button>
            </template>
            <template v-else>
              <div v-if="field.file_versions[0]" class="latest-file">
                <span class="file-version">V{{ field.file_versions[0].version }}</span>
                <div><strong>{{ field.file_versions[0].original_name }}</strong><small>{{ formatSize(field.file_versions[0].file_size) }} · {{ dayjs(field.file_versions[0].create_time).format('YYYY-MM-DD HH:mm') }}</small></div>
              </div>
              <div v-else class="file-empty">尚未上传文件</div>
              <div class="file-actions">
                <el-button v-if="field.file_versions[0]" size="small" :icon="Download" @click="downloadVersion(field)">下载最新版</el-button>
                <el-button v-if="field.file_versions.length" size="small" :icon="Clock" @click="showHistory(field)">版本 {{ field.file_versions.length }}</el-button>
                <el-upload v-if="profile.can_edit" :show-file-list="false" :http-request="uploadRequest(field)"><el-button size="small" type="primary" :icon="UploadFilled">{{ field.file_versions.length ? '上传新版本' : '上传文件' }}</el-button></el-upload>
              </div>
            </template>
            <small class="field-source">{{ field.source_forms.length ? `来源/说明：${field.source_forms.join('、')}` : '无来源说明' }}</small>
          </article>
        </div>
      </section>
    </template>

    <el-dialog v-model="fieldDialogVisible" :title="editingField ? '修改备案字段' : '新增备案字段'" width="min(620px, 92vw)" append-to-body>
      <el-form label-position="top">
        <div class="field-dialog-grid"><el-form-item label="字段名称"><el-input v-model="fieldForm.label" maxlength="200" /></el-form-item><el-form-item label="所属分类"><el-input v-model="fieldForm.category" maxlength="100" /></el-form-item></div>
        <el-form-item label="字段类型"><el-radio-group v-model="fieldForm.field_type" :disabled="Boolean(editingField)"><el-radio-button value="text">可复制文本</el-radio-button><el-radio-button value="file">上传文件</el-radio-button></el-radio-group><small v-if="editingField" class="form-hint">已有字段不能切换类型，需要时请新建字段。</small></el-form-item>
        <div class="field-dialog-grid"><el-form-item label="显示顺序"><el-input-number v-model="fieldForm.sort_order" :min="0" :max="100000" /></el-form-item><el-form-item label="选项"><el-checkbox v-model="fieldForm.sensitive">敏感信息</el-checkbox><el-checkbox v-if="fieldForm.field_type === 'text'" v-model="fieldForm.multiline">多行文本</el-checkbox></el-form-item></div>
        <el-form-item label="来源表单或复用说明"><el-input v-model="sourceFormsText" type="textarea" :rows="3" placeholder="多个来源可使用顿号或换行分隔" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="fieldDialogVisible = false">取消</el-button><el-button type="primary" :loading="saving" @click="saveField">保存字段</el-button></template>
    </el-dialog>

    <el-dialog v-model="historyVisible" :title="`${historyField?.label ?? ''} · 文件版本`" width="min(820px, 94vw)" append-to-body>
      <el-alert type="info" :closable="false" show-icon title="每次上传都会生成不可变的新版本；下载行为会记录操作人、时间和文件哈希。" />
      <el-table :data="historyField?.file_versions ?? []" style="margin-top: 14px">
        <el-table-column label="版本" width="72"><template #default="{ row }">V{{ row.version }}</template></el-table-column>
        <el-table-column prop="original_name" label="文件名" min-width="230" show-overflow-tooltip />
        <el-table-column label="大小" width="100"><template #default="{ row }">{{ formatSize(row.file_size) }}</template></el-table-column>
        <el-table-column prop="created_by" label="上传人" width="120" />
        <el-table-column label="上传时间" width="165"><template #default="{ row }">{{ dayjs(row.create_time).format('YYYY-MM-DD HH:mm') }}</template></el-table-column>
        <el-table-column label="操作" width="90"><template #default="{ row }"><el-button link type="primary" :icon="Download" @click="historyField && downloadVersion(historyField, row)">下载</el-button></template></el-table-column>
      </el-table>
    </el-dialog>
  </div>
</template>

<style scoped>
.filing-overview { margin-bottom: 24px; display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; }
.filing-overview article { min-width: 0; padding: 18px; display: grid; gap: 6px; border: 1px solid #e4ddd4; border-radius: 12px; background: #fffefa; }
.filing-overview article:nth-child(2) { color: white; background: #181715; border-color: #181715; }
.filing-overview small,.filing-overview span { color: #8d8981; font-size: 10px; }
.filing-overview article:nth-child(2) small,.filing-overview article:nth-child(2) span { color: #bcb8b0; }
.filing-overview strong { overflow-wrap: anywhere; color: inherit; font-family: Georgia, serif; font-size: 21px; font-weight: 400; }
.filing-overview span { display: flex; align-items: center; gap: 4px; }
.filing-section { margin-bottom: 22px; padding: 22px; border: 1px solid #e4ddd4; border-radius: 14px; background: #fffefa; }
.filing-section > header { margin-bottom: 18px; display: flex; align-items: end; justify-content: space-between; gap: 20px; }
.filing-section header small { color: #cc785c; font-size: 9px; font-weight: 700; letter-spacing: .1em; text-transform: uppercase; }
.filing-section h2 { margin: 3px 0 0; font-family: Georgia, serif; font-size: 23px; font-weight: 400; }
.filing-section > header > span { color: #8d8981; font-size: 10px; }
.field-card-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }
.field-card { min-width: 0; padding: 14px; display: grid; align-content: start; gap: 10px; border: 1px solid #e8e1d8; border-radius: 10px; background: #f7f2ea; }
.field-card.is-file { background: #fffefa; border-top: 3px solid #cc785c; }
.field-card.empty { background: #fbf9f5; }
.field-card__head,.field-card__head > div { display: flex; align-items: center; justify-content: space-between; gap: 7px; }
.field-card__head > div:first-child { min-width: 0; display: grid; justify-items: start; gap: 2px; }
.field-card label { color: #56524c; font-size: 11px; font-weight: 700; }
.field-card__head > div:first-child span { color: #aaa39a; font-size: 8px; text-transform: uppercase; }
.field-card__head .el-button + .el-button { margin-left: 0; }
.copy-value { min-width: 0; min-height: 34px; padding: 0; display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; border: 0; color: #252320; background: none; text-align: left; cursor: pointer; }
.copy-value span { min-width: 0; overflow-wrap: anywhere; white-space: pre-wrap; }
.field-card.empty .copy-value span { color: #aaa59d; }
.copy-value .el-icon { flex: 0 0 auto; color: #cc785c; }
.field-source { color: #a09b93; font-size: 9px; }
.latest-file { min-width: 0; padding: 10px; display: flex; align-items: center; gap: 9px; border-radius: 8px; background: #f3ede5; }
.file-version { width: 30px; height: 30px; flex: 0 0 auto; display: grid; place-items: center; border-radius: 7px; color: #fff; background: #181715; font-size: 9px; }
.latest-file > div { min-width: 0; display: grid; gap: 3px; }
.latest-file strong { overflow: hidden; font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
.latest-file small,.file-empty { color: #969188; font-size: 9px; }
.file-empty { padding: 15px; border: 1px dashed #dcd3c9; border-radius: 8px; text-align: center; }
.file-actions { display: flex; flex-wrap: wrap; gap: 6px; }
.file-actions .el-button { margin-left: 0; }
.field-dialog-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.form-hint { margin-left: 10px; color: #99938a; font-size: 10px; }
@media (max-width: 1000px) { .filing-overview,.field-card-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 650px) { .filing-overview,.field-card-grid,.field-dialog-grid { grid-template-columns: 1fr; } }
</style>
