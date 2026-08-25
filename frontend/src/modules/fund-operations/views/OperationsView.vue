<script setup lang="ts">
import { DocumentChecked, Refresh, UploadFilled } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { UploadFile, UploadFiles, UploadInstance, UploadRawFile } from 'element-plus'
import { computed, nextTick, onMounted, reactive, ref } from 'vue'

import PageHeader from '@/components/PageHeader.vue'
import StatusTag from '@/components/StatusTag.vue'
import { apiErrorMessage } from '@/platform/api/http'
import { useAuthStore } from '@/platform/auth/auth.store'

import {
  confirmParseSession,
  getMailboxes,
  getParseSession,
  getParseTaskSummary,
  getRecentParseSessions,
  retryParseTask,
  updateParseResultRow,
  uploadForReparse,
  validateParseSession,
} from '../api'
import type {
  MailboxAccount,
  ParseReviewRow,
  ParseReviewRowUpdate,
  ParseReviewSession,
  ParseTaskSummary,
} from '../api/types'

const auth = useAuthStore()
const upload = ref<UploadInstance>()
const selectedFile = ref<UploadRawFile>()
const sourceAttachmentId = ref<number>()
const mailboxAccountId = ref<number>()
const mailboxes = ref<MailboxAccount[]>([])
const recentSessions = ref<ParseReviewSession[]>([])
const taskSummary = ref<ParseTaskSummary>()
const activeSession = ref<ParseReviewSession>()
const resultMessage = ref('')
const resultPanel = ref<HTMLElement>()
const submitting = ref(false)
const loadingSession = ref(false)
const confirming = ref(false)
const editVisible = ref(false)
const savingRow = ref(false)
const editingRow = ref<ParseReviewRow>()
const editForm = reactive<Record<string, string | boolean | null>>({})

const canSubmit = computed(
  () => Boolean(selectedFile.value && mailboxAccountId.value) && !submitting.value,
)
const canConfirm = computed(() => activeSession.value?.status === 'ready')

function onChange(file: UploadFile, files: UploadFiles) {
  selectedFile.value = file.raw
  if (files.length > 1) upload.value?.handleRemove(files[0]!)
}

function onRemove() {
  selectedFile.value = undefined
}

async function loadOverview() {
  const [sessions, tasks] = await Promise.all([getRecentParseSessions(), getParseTaskSummary()])
  recentSessions.value = sessions
  taskSummary.value = tasks
}

async function submit() {
  if (!selectedFile.value) return
  submitting.value = true
  try {
    const result = await uploadForReparse(
      selectedFile.value,
      sourceAttachmentId.value,
      mailboxAccountId.value,
    )
    resultMessage.value = result.message
    ElMessage.warning(result.message)
    upload.value?.clearFiles()
    selectedFile.value = undefined
    await openSession(result.parse_session_id)
    await loadOverview()
  } catch (error) {
    ElMessage.error(apiErrorMessage(error))
  } finally {
    submitting.value = false
  }
}

async function openSession(id: number) {
  loadingSession.value = true
  try {
    activeSession.value = await getParseSession(id)
    resultMessage.value = activeSession.value.status === 'committed'
      ? '本次解析结果已确认入库'
      : '解析结果等待人工核对'
    await nextTick()
    resultPanel.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  } catch (error) {
    ElMessage.error(apiErrorMessage(error))
  } finally {
    loadingSession.value = false
  }
}

function editRow(row: ParseReviewRow) {
  editingRow.value = row
  Object.assign(editForm, {
    product_name: row.product_name,
    product_code: row.product_code,
    asset_code: row.asset_code,
    registration_code: row.registration_code,
    share_class: row.share_class,
    nav_date: row.nav_date,
    unit_nav: row.unit_nav,
    total_nav: row.total_nav,
    asset_value: row.asset_value,
    asset_share: row.asset_share,
    paid_in_capital: row.paid_in_capital,
    parent_product_code: row.parent_product_code,
    parent_product_name: row.parent_product_name,
    notes: row.notes,
    ignored: row.status === 'ignored',
    conflict_action: row.conflict_action,
    edit_reason: row.edit_reason ?? '',
  })
  editVisible.value = true
}

async function saveRow() {
  const row = editingRow.value
  const review = activeSession.value
  if (!row || !review) return
  if (!String(editForm.edit_reason ?? '').trim()) {
    ElMessage.warning('请填写人工修正原因')
    return
  }
  savingRow.value = true
  try {
    const payload: ParseReviewRowUpdate = {
      product_name: editForm.product_name as string | null,
      product_code: editForm.product_code as string | null,
      asset_code: editForm.asset_code as string | null,
      registration_code: editForm.registration_code as string | null,
      share_class: editForm.share_class as string | null,
      nav_date: editForm.nav_date as string | null,
      unit_nav: editForm.unit_nav as string | null,
      total_nav: editForm.total_nav as string | null,
      asset_value: editForm.asset_value as string | null,
      asset_share: editForm.asset_share as string | null,
      paid_in_capital: editForm.paid_in_capital as string | null,
      parent_product_code: editForm.parent_product_code as string | null,
      parent_product_name: editForm.parent_product_name as string | null,
      notes: editForm.notes as string | null,
      ignored: Boolean(editForm.ignored),
      conflict_action: editForm.conflict_action as ParseReviewRowUpdate['conflict_action'],
      edit_reason: String(editForm.edit_reason),
      expected_version: row.row_version,
    }
    activeSession.value = await updateParseResultRow(review.id, row.id, payload)
    editVisible.value = false
    ElMessage.success('修正已保存并重新校验')
    await loadOverview()
  } catch (error) {
    ElMessage.error(apiErrorMessage(error))
  } finally {
    savingRow.value = false
  }
}

async function revalidate() {
  if (!activeSession.value) return
  try {
    activeSession.value = await validateParseSession(activeSession.value.id)
    ElMessage.success(activeSession.value.status === 'ready' ? '校验通过，可以确认入库' : '校验完成，请继续处理提示项')
  } catch (error) {
    ElMessage.error(apiErrorMessage(error))
  }
}

async function confirmReview() {
  if (!activeSession.value || !canConfirm.value) return
  try {
    await ElMessageBox.confirm(
      '确认后，新增数据将写入正式净值台账；历史更正会生成不可覆盖的审计快照。',
      '确认入库',
      { type: 'warning', confirmButtonText: '确认入库', cancelButtonText: '继续核对' },
    )
  } catch {
    return
  }
  confirming.value = true
  try {
    const committed = await confirmParseSession(activeSession.value.id)
    ElMessage.success(committed.message)
    await openSession(activeSession.value.id)
    await loadOverview()
  } catch (error) {
    ElMessage.error(apiErrorMessage(error))
  } finally {
    confirming.value = false
  }
}

async function retryTask(id: number) {
  try {
    await retryParseTask(id)
    ElMessage.success('任务已重新进入解析队列')
    taskSummary.value = await getParseTaskSummary()
  } catch (error) {
    ElMessage.error(apiErrorMessage(error))
  }
}

onMounted(async () => {
  try {
    mailboxes.value = (await getMailboxes()).filter(
      (item) => item.is_enabled && item.permissions.can_operate,
    )
    mailboxAccountId.value = (
      mailboxes.value.find((item) => item.is_default) ?? mailboxes.value[0]
    )?.id
    await loadOverview()
  } catch (error) {
    ElMessage.error(apiErrorMessage(error))
  }
})
</script>

<template>
  <div>
    <PageHeader eyebrow="Parse Operations" title="解析与人工复核" description="邮件同步仅负责安全归档，Excel 由独立队列解析；人工上传先暂存、修正和校验，确认后才进入正式净值台账。" />

    <section class="parse-status-grid">
      <article class="panel parse-status-card"><small>等待解析</small><strong>{{ taskSummary?.queued ?? 0 }}</strong></article>
      <article class="panel parse-status-card"><small>正在解析</small><strong>{{ taskSummary?.running ?? 0 }}</strong></article>
      <article class="panel parse-status-card"><small>解析成功</small><strong>{{ taskSummary?.success ?? 0 }}</strong></article>
      <article class="panel parse-status-card"><small>部分成功/重复</small><strong>{{ (taskSummary?.partial_success ?? 0) + (taskSummary?.duplicate ?? 0) }}</strong></article>
      <article class="panel parse-status-card parse-status-card--danger"><small>解析失败</small><strong>{{ taskSummary?.failed ?? 0 }}</strong></article>
    </section>

    <section class="operations-grid">
      <article class="panel reparse-panel">
        <div class="panel-header"><div><h2>上传 Excel 重新解析</h2><p>解析结果不会直接写入正式台账</p></div></div>
        <div class="panel-body">
          <el-upload ref="upload" drag action="#" :auto-upload="false" :limit="1" accept=".xls,.xlsx" :on-change="onChange" :on-remove="onRemove">
            <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
            <div class="el-upload__text">拖放文件到这里，或 <em>点击选择</em></div>
            <template #tip><div class="el-upload__tip">文件先归档并进入人工复核暂存区，确认前不影响正式净值。</div></template>
          </el-upload>
          <el-form label-position="top" class="source-link-form">
            <el-form-item label="归属邮箱"><el-select v-model="mailboxAccountId" placeholder="选择该附件所属邮箱" style="width: 320px"><el-option v-for="item in mailboxes" :key="item.id" :label="`${item.display_name} · ${item.username}`" :value="item.id" /></el-select><span class="form-help">暂存结果、正式数据和审计记录均绑定所选邮箱。</span></el-form-item>
            <el-form-item label="关联原附件 ID（可选）"><el-input-number v-model="sourceAttachmentId" :min="1" :controls="false" placeholder="用于审计追溯" style="width: 220px" /></el-form-item>
          </el-form>
          <el-button type="primary" size="large" :disabled="!canSubmit" :loading="submitting" @click="submit">上传并解析到暂存区</el-button>
        </div>
      </article>

      <aside class="panel audit-panel">
        <div class="panel-header"><div><h2>最近人工解析</h2><p>刷新页面后仍可继续处理</p></div></div>
        <div class="recent-review-list">
          <button v-for="item in recentSessions" :key="item.id" type="button" class="recent-review-item" @click="openSession(item.id)"><span><strong>{{ item.source_file }}</strong><small>#{{ item.id }} · {{ item.parser_version }}</small></span><StatusTag :status="item.status" /></button>
          <el-empty v-if="!recentSessions.length" description="暂无人工解析记录" :image-size="60" />
        </div>
      </aside>
    </section>

    <section v-if="activeSession" ref="resultPanel" v-loading="loadingSession" class="panel result-detail-panel">
      <div class="result-panel result-summary">
        <div class="result-panel__icon"><el-icon><DocumentChecked /></el-icon></div>
        <div><small>人工复核会话 #{{ activeSession.id }}</small><h2>{{ resultMessage }}</h2><p>{{ activeSession.source_file }} · 解析器 {{ activeSession.parser_version }}</p></div>
        <div class="result-metrics"><span><strong>{{ activeSession.valid_count }}</strong><small>可入库</small></span><span><strong>{{ activeSession.duplicate_count }}</strong><small>重复</small></span><span><strong>{{ activeSession.invalid_count }}</strong><small>待修正</small></span><span><strong>{{ activeSession.ignored_count }}</strong><small>已忽略</small></span></div>
        <StatusTag :status="activeSession.status" />
      </div>

      <div v-if="activeSession.file_issues.length" class="file-issue-list"><div v-for="(issue, index) in activeSession.file_issues" :key="index"><el-tag :type="issue.severity === 'error' ? 'danger' : 'warning'" size="small">{{ issue.severity === 'error' ? '错误' : '警告' }}</el-tag><span>{{ issue.message }}</span></div></div>

      <div class="review-actions"><el-button :icon="Refresh" @click="revalidate">重新校验</el-button><span>所有无效行已修正、重复行已选择处理方式后才能确认。</span><el-button type="primary" :disabled="!canConfirm" :loading="confirming" @click="confirmReview">确认写入正式台账</el-button></div>

      <el-table :data="activeSession.rows" stripe row-key="id" class="review-table">
        <el-table-column label="状态" width="110"><template #default="{ row }"><StatusTag :status="row.status" /></template></el-table-column>
        <el-table-column prop="product_name" label="产品" min-width="220"><template #default="{ row }"><strong>{{ row.product_name || '—' }}</strong><br><small>{{ row.product_code || '代码缺失' }}{{ row.share_class ? ` · ${row.share_class}` : '' }}</small></template></el-table-column>
        <el-table-column prop="nav_date" label="净值日期" width="120"><template #default="{ row }">{{ row.nav_date || '—' }}</template></el-table-column>
        <el-table-column prop="unit_nav" label="单位净值" width="120"><template #default="{ row }">{{ row.unit_nav ?? '—' }}</template></el-table-column>
        <el-table-column prop="total_nav" label="累计净值" width="120"><template #default="{ row }">{{ row.total_nav ?? '—' }}</template></el-table-column>
        <el-table-column prop="asset_value" label="资产净值" width="150"><template #default="{ row }">{{ row.asset_value ?? '—' }}</template></el-table-column>
        <el-table-column label="来源/提示" min-width="250"><template #default="{ row }"><span>{{ row.source_sheet }} / 第 {{ row.source_row }} 行</span><small v-if="row.validation_message" class="row-error">{{ row.validation_message }}</small></template></el-table-column>
        <el-table-column label="重复处理" width="150"><template #default="{ row }"><span v-if="row.status === 'duplicate'">{{ row.conflict_action === 'keep_existing' ? '保留已有' : row.conflict_action === 'replace_existing' ? '更正已有' : '待选择' }}</span><span v-else>—</span></template></el-table-column>
        <el-table-column label="操作" width="100" fixed="right"><template #default="{ row }"><el-button v-if="activeSession?.status !== 'committed'" link type="primary" @click="editRow(row)">修正</el-button></template></el-table-column>
      </el-table>
    </section>

    <section class="panel parse-task-panel">
      <div class="panel-header"><div><h2>自动附件解析任务</h2><p>与邮件同步独立运行，失败任务可重试</p></div><el-button :icon="Refresh" @click="loadOverview">刷新</el-button></div>
      <el-table :data="taskSummary?.recent ?? []" stripe>
        <el-table-column prop="source_file" label="附件" min-width="230"><template #default="{ row }"><strong>{{ row.source_file }}</strong><br><small>{{ row.mailbox_name }} · 附件 #{{ row.attachment_id }}</small></template></el-table-column>
        <el-table-column label="状态" width="110"><template #default="{ row }"><StatusTag :status="row.status" /></template></el-table-column>
        <el-table-column label="处理统计" width="210"><template #default="{ row }">新增 {{ row.inserted_count }} · 重复 {{ row.duplicate_count }} · 异常 {{ row.exception_count }}</template></el-table-column>
        <el-table-column label="尝试" width="100"><template #default="{ row }">{{ row.attempt_count }} / {{ row.max_attempts }}</template></el-table-column>
        <el-table-column prop="parser_version" label="解析器版本" width="140"><template #default="{ row }">{{ row.parser_version ?? '等待执行' }}</template></el-table-column>
        <el-table-column prop="error_message" label="错误" min-width="220"><template #default="{ row }">{{ row.error_message ?? '—' }}</template></el-table-column>
        <el-table-column label="操作" width="100"><template #default="{ row }"><el-button v-if="['failed', 'duplicate', 'partial_success'].includes(row.status)" link type="primary" @click="retryTask(row.id)">重试</el-button></template></el-table-column>
      </el-table>
    </section>

    <el-dialog v-model="editVisible" title="修正解析结果" width="820px" destroy-on-close>
      <div v-if="editingRow" class="original-value-panel"><strong>机器原始识别</strong><span>产品：{{ editingRow.original_data.product_name ?? '—' }}</span><span>代码：{{ editingRow.original_data.product_code ?? '—' }}</span><span>日期：{{ editingRow.original_data.nav_date ?? '—' }}</span><span>单位净值：{{ editingRow.original_data.unit_nav ?? '—' }}</span></div>
      <el-form label-position="top" class="review-edit-grid">
        <el-form-item label="产品名称"><el-input v-model="editForm.product_name" /></el-form-item><el-form-item label="产品代码"><el-input v-model="editForm.product_code" /></el-form-item>
        <el-form-item label="资产代码"><el-input v-model="editForm.asset_code" /></el-form-item><el-form-item label="备案/主体代码"><el-input v-model="editForm.registration_code" /></el-form-item>
        <el-form-item label="份额类别"><el-input v-model="editForm.share_class" /></el-form-item><el-form-item label="净值日期"><el-date-picker v-model="editForm.nav_date" value-format="YYYY-MM-DD" style="width:100%" /></el-form-item>
        <el-form-item label="单位净值"><el-input v-model="editForm.unit_nav" /></el-form-item><el-form-item label="累计净值"><el-input v-model="editForm.total_nav" /></el-form-item>
        <el-form-item label="资产净值"><el-input v-model="editForm.asset_value" /></el-form-item><el-form-item label="资产份额"><el-input v-model="editForm.asset_share" /></el-form-item>
        <el-form-item label="实缴资本"><el-input v-model="editForm.paid_in_capital" /></el-form-item><el-form-item label="母产品代码"><el-input v-model="editForm.parent_product_code" /></el-form-item>
        <el-form-item label="母产品名称"><el-input v-model="editForm.parent_product_name" /></el-form-item>
        <el-form-item v-if="editingRow?.status === 'duplicate'" label="重复数据处理"><el-select v-model="editForm.conflict_action" style="width:100%"><el-option label="请选择" value="unresolved" /><el-option label="保留正式台账已有数据" value="keep_existing" /><el-option v-if="auth.user?.role === 'admin'" label="更正正式台账已有数据" value="replace_existing" /></el-select></el-form-item>
        <el-form-item label="忽略本行"><el-switch v-model="editForm.ignored" /></el-form-item>
        <el-form-item label="备注" class="review-edit-grid__wide"><el-input v-model="editForm.notes" type="textarea" :rows="2" /></el-form-item>
        <el-form-item label="人工修正原因" class="review-edit-grid__wide" required><el-input v-model="editForm.edit_reason" type="textarea" :rows="2" placeholder="请说明修正依据；该内容会写入审计记录" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="editVisible = false">取消</el-button><el-button type="primary" :loading="savingRow" @click="saveRow">保存并重新校验</el-button></template>
    </el-dialog>
  </div>
</template>
