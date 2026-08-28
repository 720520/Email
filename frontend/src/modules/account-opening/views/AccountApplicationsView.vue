<script setup lang="ts">
import dayjs from 'dayjs'
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onMounted, reactive, ref } from 'vue'

import PageHeader from '@/components/PageHeader.vue'
import { getProductProfiles } from '@/modules/tenant-admin/api'
import type { ProductProfileSummary } from '@/modules/tenant-admin/api/types'
import { apiErrorMessage } from '@/platform/api/http'
import { useAuthStore } from '@/platform/auth/auth.store'

import {
  addApplicationSupplement,
  attachRequirementDocument,
  createAccountApplication,
  getAccountApplication,
  listAccountApplications,
  listAvailableDocuments,
  listInstitutions,
  reviewAccountApplication,
  submitAccountApplication,
} from '../api'
import type {
  AccountApplicationDetail,
  AccountApplicationPayload,
  AccountApplicationSummary,
  ApplicationRequirement,
  AvailableDocument,
  InstitutionItem,
  SourceScope,
} from '../api/types'

const auth = useAuthStore()
const loading = ref(false)
const saving = ref(false)
const drawerLoading = ref(false)
const createDialog = ref(false)
const detailDrawer = ref(false)
const applications = ref<AccountApplicationSummary[]>([])
const institutions = ref<InstitutionItem[]>([])
const products = ref<ProductProfileSummary[]>([])
const detail = ref<AccountApplicationDetail>()
const selectedReviewRequirements = ref<number[]>([])
const selectedDocuments = reactive<Record<number, number | undefined>>({})
const availableDocuments = reactive<Record<SourceScope, AvailableDocument[]>>({
  organization: [],
  product: [],
  account_application: [],
})

const createForm = reactive<AccountApplicationPayload>({
  product_id: 0,
  institution_id: 0,
  account_type: 'securities',
  settlement_mode: 'broker_settlement',
  fund_type: 'all',
  application_date: dayjs().format('YYYY-MM-DD'),
})

const isAdmin = computed(() => auth.user?.role === 'admin')
const canCreate = computed(() => auth.user?.role !== 'viewer')
const isEditor = computed(() => {
  if (!detail.value || auth.user?.role === 'viewer') return false
  return isAdmin.value || detail.value.owner_user_id === auth.user?.id
})
const editable = computed(() =>
  Boolean(detail.value && ['draft', 'preparing', 'pending_seal'].includes(detail.value.status)),
)

const statuses: Record<string, { label: string; type: 'info' | 'primary' | 'warning' | 'success' | 'danger' }> = {
  draft: { label: '草稿', type: 'info' },
  preparing: { label: '准备中', type: 'primary' },
  pending_seal: { label: '待盖章', type: 'warning' },
  submitted: { label: '已提交', type: 'primary' },
  supplement_required: { label: '待补件', type: 'warning' },
  approved: { label: '已批准', type: 'success' },
  opened: { label: '已开户', type: 'success' },
  rejected: { label: '已拒绝', type: 'danger' },
  closed: { label: '已销户', type: 'info' },
}
const requirementStatuses: Record<string, string> = {
  missing: '缺失',
  provided: '已选材料',
  submitted: '已提交',
  supplement_required: '需补件',
  accepted: '已通过',
}
const sourceScopes: Record<string, string> = {
  organization: '公司资料',
  product: '产品资料',
  account_application: '本次开户资料',
}
const eventLabels: Record<string, string> = {
  created: '创建申请',
  status_changed: '状态调整',
  material_attached: '选择材料',
  submitted: '提交申请',
  supplement_requested: '要求补件',
  supplement_added: '补充材料',
  approved: '审批通过',
  rejected: '审批拒绝',
  opened: '确认开户',
  closed: '确认销户',
}

function statusInfo(value: string) {
  return statuses[value] ?? { label: value, type: 'info' as const }
}

function documentsFor(scope: string): AvailableDocument[] {
  return availableDocuments[scope as SourceScope] ?? []
}

function onApplicationRowClick(row: AccountApplicationSummary) {
  void showDetail(row.id)
}

async function load() {
  loading.value = true
  try {
    ;[applications.value, institutions.value, products.value] = await Promise.all([
      listAccountApplications(),
      listInstitutions(),
      getProductProfiles(),
    ])
  } catch (error) {
    ElMessage.error(apiErrorMessage(error))
  } finally {
    loading.value = false
  }
}

function openCreateDialog() {
  Object.assign(createForm, {
    product_id: products.value[0]?.fund_product_id ?? 0,
    institution_id: institutions.value[0]?.id ?? 0,
    account_type: 'securities',
    settlement_mode: 'broker_settlement',
    fund_type: 'all',
    application_date: dayjs().format('YYYY-MM-DD'),
  })
  createDialog.value = true
}

async function createApplication() {
  if (!createForm.product_id || !createForm.institution_id) {
    ElMessage.warning('请选择产品和开户机构')
    return
  }
  saving.value = true
  try {
    const created = await createAccountApplication(createForm)
    ElMessage.success('开户申请已创建，材料清单已按模板固化')
    createDialog.value = false
    await load()
    await showDetail(created.id)
  } catch (error) {
    ElMessage.error(apiErrorMessage(error))
  } finally {
    saving.value = false
  }
}

async function loadDocuments(application: AccountApplicationDetail) {
  const scopes = [...new Set(application.requirements.map((item) => item.source_scope))]
  const results = await Promise.all(
    scopes.map(async (scope) => [scope, await listAvailableDocuments(application.id, scope)] as const),
  )
  for (const [scope, documents] of results) availableDocuments[scope] = documents
}

async function showDetail(id: number) {
  detailDrawer.value = true
  drawerLoading.value = true
  selectedReviewRequirements.value = []
  try {
    detail.value = await getAccountApplication(id)
    Object.keys(selectedDocuments).forEach((key) => delete selectedDocuments[Number(key)])
    for (const requirement of detail.value.requirements) {
      selectedDocuments[requirement.id] = requirement.document_id ?? undefined
    }
    await loadDocuments(detail.value)
  } catch (error) {
    ElMessage.error(apiErrorMessage(error))
  } finally {
    drawerLoading.value = false
  }
}

async function refreshDetail(value: AccountApplicationDetail) {
  detail.value = value
  await load()
}

async function attach(requirement: ApplicationRequirement) {
  if (!detail.value || !selectedDocuments[requirement.id]) {
    ElMessage.warning('请选择资料文件')
    return
  }
  saving.value = true
  try {
    await refreshDetail(await attachRequirementDocument(
      detail.value.id,
      requirement.id,
      selectedDocuments[requirement.id]!,
    ))
    ElMessage.success('材料版本已关联')
  } catch (error) {
    ElMessage.error(apiErrorMessage(error))
  } finally {
    saving.value = false
  }
}

async function submit() {
  if (!detail.value) return
  try {
    await ElMessageBox.confirm('提交后主材料文件及版本将被冻结，只能按补件流程追加。', '确认提交')
    saving.value = true
    await refreshDetail(await submitAccountApplication(detail.value.id))
    ElMessage.success('申请已提交，材料版本已固定')
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') ElMessage.error(apiErrorMessage(error))
  } finally {
    saving.value = false
  }
}

async function supplement(requirement: ApplicationRequirement) {
  if (!detail.value || !selectedDocuments[requirement.id]) {
    ElMessage.warning('请选择补件文件')
    return
  }
  try {
    const { value } = await ElMessageBox.prompt('填写补件说明（可选）', '追加补件', {
      inputPlaceholder: '例如：按机构反馈补充最新盖章版本',
    })
    saving.value = true
    await refreshDetail(await addApplicationSupplement(
      detail.value.id,
      requirement.id,
      selectedDocuments[requirement.id]!,
      value,
    ))
    ElMessage.success('补件已追加，原提交材料仍保持不变')
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') ElMessage.error(apiErrorMessage(error))
  } finally {
    saving.value = false
  }
}

function selectRequirements(rows: ApplicationRequirement[]) {
  selectedReviewRequirements.value = rows.map((item) => item.id)
}

async function review(action: 'request_supplement' | 'approve' | 'reject' | 'open' | 'close') {
  if (!detail.value) return
  if (action === 'request_supplement' && !selectedReviewRequirements.value.length) {
    ElMessage.warning('请勾选需要补充的材料')
    return
  }
  const actionName = {
    request_supplement: '要求补件', approve: '审批通过', reject: '拒绝申请', open: '确认开户', close: '确认销户',
  }[action]
  try {
    const { value } = await ElMessageBox.prompt(`请填写“${actionName}”意见（可选）`, actionName, {
      confirmButtonText: '确认',
      inputPlaceholder: '审批或处理意见',
    })
    saving.value = true
    await refreshDetail(await reviewAccountApplication(detail.value.id, {
      action,
      requirement_ids: action === 'request_supplement' ? selectedReviewRequirements.value : [],
      comment: value,
    }))
    selectedReviewRequirements.value = []
    ElMessage.success(`${actionName}已记录`)
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') ElMessage.error(apiErrorMessage(error))
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<template>
  <div v-loading="loading">
    <PageHeader
      eyebrow="Account Opening Ledger"
      title="开户台账"
      description="一个产品可向多家机构发起不同账户类型的开户申请；材料提交、补件、审批、开户和销户均保留完整事件。"
    >
      <template #actions><el-button v-if="canCreate" type="primary" @click="openCreateDialog">新建开户申请</el-button></template>
    </PageHeader>

    <el-card shadow="never">
      <el-table :data="applications" row-key="id" empty-text="暂无开户申请" @row-click="onApplicationRowClick">
        <el-table-column prop="product_name" label="产品" min-width="210">
          <template #default="{ row }"><strong>{{ row.product_name }}</strong><div class="muted">{{ row.product_code }}</div></template>
        </el-table-column>
        <el-table-column prop="institution_name" label="开户机构" min-width="220" />
        <el-table-column prop="account_type" label="账户类型" width="130" />
        <el-table-column prop="settlement_mode" label="结算模式" width="150" />
        <el-table-column label="材料进度" width="120"><template #default="{ row }">{{ row.completed_requirement_count }} / {{ row.requirement_count }}</template></el-table-column>
        <el-table-column label="申请日期" width="120"><template #default="{ row }">{{ row.application_date }}</template></el-table-column>
        <el-table-column label="状态" width="100"><template #default="{ row }"><el-tag :type="statusInfo(row.status).type">{{ statusInfo(row.status).label }}</el-tag></template></el-table-column>
        <el-table-column label="操作" width="90"><template #default="{ row }"><el-button link type="primary" @click.stop="showDetail(row.id)">查看</el-button></template></el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="createDialog" title="新建开户申请" width="680px">
      <el-form label-position="top">
        <el-row :gutter="16">
          <el-col :span="12"><el-form-item label="开户产品"><el-select v-model="createForm.product_id" filterable><el-option v-for="item in products" :key="item.fund_product_id" :label="`${item.product_name}（${item.product_code}）`" :value="item.fund_product_id" /></el-select></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="开户机构"><el-select v-model="createForm.institution_id" filterable><el-option v-for="item in institutions" :key="item.id" :label="item.full_name" :value="item.id" /></el-select></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="账户类型"><el-select v-model="createForm.account_type" allow-create filterable><el-option label="证券账户" value="securities" /><el-option label="期货账户" value="futures" /><el-option label="托管账户" value="custody" /><el-option label="银行账户" value="bank" /></el-select></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="结算模式"><el-select v-model="createForm.settlement_mode" allow-create filterable><el-option label="券商结算" value="broker_settlement" /><el-option label="托管行结算" value="custodian_settlement" /><el-option label="银证转账" value="bank_securities_transfer" /></el-select></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="基金类型"><el-input v-model="createForm.fund_type" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="申请日期"><el-date-picker v-model="createForm.application_date" type="date" value-format="YYYY-MM-DD" /></el-form-item></el-col>
        </el-row>
      </el-form>
      <el-alert title="必须先在“机构与模板”中建立当前机构、账户类型对应的生效模板。" type="info" :closable="false" />
      <template #footer><el-button @click="createDialog = false">取消</el-button><el-button type="primary" :loading="saving" @click="createApplication">创建申请</el-button></template>
    </el-dialog>

    <el-drawer v-model="detailDrawer" size="min(1060px, 92vw)" title="开户申请详情">
      <div v-if="detail" v-loading="drawerLoading" class="drawer-content">
        <el-descriptions :column="3" border>
          <el-descriptions-item label="产品">{{ detail.product_name }}（{{ detail.product_code }}）</el-descriptions-item>
          <el-descriptions-item label="开户机构">{{ detail.institution_name }}</el-descriptions-item>
          <el-descriptions-item label="状态"><el-tag :type="statusInfo(detail.status).type">{{ statusInfo(detail.status).label }}</el-tag></el-descriptions-item>
          <el-descriptions-item label="账户类型">{{ detail.account_type }}</el-descriptions-item>
          <el-descriptions-item label="结算模式">{{ detail.settlement_mode }}</el-descriptions-item>
          <el-descriptions-item label="申请日期">{{ detail.application_date }}</el-descriptions-item>
        </el-descriptions>

        <div class="section-heading">
          <div><h3>材料清单</h3><span>首次提交后主材料版本冻结；补件不会覆盖原版本。</span></div>
          <el-button v-if="isEditor && (editable || detail.status === 'supplement_required')" type="primary" :loading="saving" @click="submit">{{ detail.status === 'supplement_required' ? '重新提交' : '提交申请' }}</el-button>
        </div>
        <el-table :data="detail.requirements" row-key="id" @selection-change="selectRequirements">
          <el-table-column v-if="isAdmin && detail.status === 'submitted'" type="selection" width="46" />
          <el-table-column prop="name" label="材料" min-width="180"><template #default="{ row }"><strong>{{ row.name }}</strong><div class="muted">{{ row.requirement_code }}</div></template></el-table-column>
          <el-table-column label="来源" width="110"><template #default="{ row }">{{ sourceScopes[row.source_scope] }}</template></el-table-column>
          <el-table-column label="要求" width="120"><template #default="{ row }"><span v-if="row.required">必需</span><span v-else>选填</span><span v-if="row.original_required"> · 原件</span><div class="muted">{{ row.seal_requirement }}</div></template></el-table-column>
          <el-table-column label="已固化文件" min-width="210"><template #default="{ row }"><template v-if="row.document_name">{{ row.document_name }} <el-tag size="small">v{{ row.document_version }}</el-tag><div class="muted">{{ row.document_hash?.slice(0, 12) }}…</div></template><span v-else>—</span></template></el-table-column>
          <el-table-column label="状态" width="100"><template #default="{ row }"><el-tag :type="row.status === 'supplement_required' || row.status === 'missing' ? 'warning' : 'success'">{{ requirementStatuses[row.status] ?? row.status }}</el-tag><div v-if="row.review_comment" class="muted">{{ row.review_comment }}</div></template></el-table-column>
          <el-table-column v-if="isEditor && (editable || detail.status === 'supplement_required')" label="选择资料" min-width="260">
            <template #default="{ row }">
              <div class="document-picker">
                <el-select v-model="selectedDocuments[row.id]" filterable placeholder="选择该主体的资料版本">
                  <el-option v-for="document in documentsFor(row.source_scope)" :key="document.id" :label="`${document.original_name} · v${document.version}`" :value="document.id" />
                </el-select>
                <el-button v-if="editable" link type="primary" :loading="saving" @click="attach(row)">关联</el-button>
                <el-button v-else-if="row.status === 'supplement_required'" link type="warning" :loading="saving" @click="supplement(row)">补件</el-button>
              </div>
            </template>
          </el-table-column>
        </el-table>

        <div v-if="isAdmin" class="review-bar">
          <el-button v-if="detail.status === 'submitted'" type="warning" plain @click="review('request_supplement')">要求所选材料补件</el-button>
          <el-button v-if="detail.status === 'submitted'" type="success" @click="review('approve')">审批通过</el-button>
          <el-button v-if="detail.status === 'submitted'" type="danger" plain @click="review('reject')">拒绝申请</el-button>
          <el-button v-if="detail.status === 'approved'" type="success" @click="review('open')">确认已开户</el-button>
          <el-button v-if="detail.status === 'opened'" type="danger" plain @click="review('close')">确认销户</el-button>
        </div>

        <template v-if="detail.supplements.length">
          <div class="section-heading"><div><h3>补件记录</h3><span>追加保存，不替换首次提交的文件。</span></div></div>
          <el-table :data="detail.supplements">
            <el-table-column prop="document_name" label="补件文件" min-width="240" />
            <el-table-column label="版本" width="80"><template #default="{ row }">v{{ row.document_version }}</template></el-table-column>
            <el-table-column prop="comment" label="说明" min-width="220" />
            <el-table-column label="时间" width="170"><template #default="{ row }">{{ dayjs(row.create_time).format('YYYY-MM-DD HH:mm') }}</template></el-table-column>
          </el-table>
        </template>

        <div class="section-heading"><div><h3>流转记录</h3><span>缺件、补件、审批、开户和销户全程留痕。</span></div></div>
        <el-timeline>
          <el-timeline-item v-for="event in detail.events" :key="event.id" :timestamp="dayjs(event.create_time).format('YYYY-MM-DD HH:mm')" placement="top">
            <strong>{{ eventLabels[event.event_type] ?? event.event_type }}</strong>
            <span v-if="event.from_status || event.to_status"> · {{ event.from_status ? statusInfo(event.from_status).label : '—' }} → {{ event.to_status ? statusInfo(event.to_status).label : '—' }}</span>
            <div v-if="event.comment" class="muted">{{ event.comment }}</div>
          </el-timeline-item>
        </el-timeline>
      </div>
    </el-drawer>
  </div>
</template>

<style scoped>
.muted { margin-top: 3px; color: var(--el-text-color-secondary); font-size: 12px; }
.drawer-content { padding: 0 6px 30px; }
.section-heading { display: flex; align-items: center; justify-content: space-between; gap: 20px; margin: 26px 0 12px; }
.section-heading h3 { margin: 0 0 4px; }
.section-heading span { color: var(--el-text-color-secondary); font-size: 13px; }
.document-picker { display: flex; align-items: center; gap: 8px; }
.document-picker .el-select { flex: 1; }
.review-bar { display: flex; justify-content: flex-end; gap: 8px; margin-top: 18px; }
</style>
