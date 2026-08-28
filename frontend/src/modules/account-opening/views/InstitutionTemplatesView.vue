<script setup lang="ts">
import dayjs from 'dayjs'
import { ElMessage } from 'element-plus'
import { computed, onMounted, reactive, ref } from 'vue'

import PageHeader from '@/components/PageHeader.vue'
import { apiErrorMessage } from '@/platform/api/http'
import { useAuthStore } from '@/platform/auth/auth.store'

import {
  createInstitution,
  createRequirementTemplate,
  listInstitutions,
  listRequirementTemplates,
  setRequirementTemplateState,
  updateInstitution,
} from '../api'
import type {
  InstitutionItem,
  InstitutionPayload,
  RequirementTemplate,
  RequirementTemplateItem,
  RequirementTemplatePayload,
} from '../api/types'

const auth = useAuthStore()
const loading = ref(false)
const saving = ref(false)
const activeTab = ref('institutions')
const institutionDialog = ref(false)
const templateDialog = ref(false)
const institutions = ref<InstitutionItem[]>([])
const templates = ref<RequirementTemplate[]>([])
const isAdmin = computed(() => auth.user?.role === 'admin')

const institutionForm = reactive<InstitutionPayload>({
  institution_type: 'broker',
  full_name: '',
  short_name: '',
  license_code: '',
  contact_information: {},
})
const contact = reactive({ name: '', phone: '', email: '' })

function blankTemplateItem(sortOrder: number): RequirementTemplateItem {
  return {
    requirement_code: '',
    name: '',
    source_scope: 'organization',
    required: true,
    condition: {},
    seal_requirement: '',
    original_required: false,
    sort_order: sortOrder,
  }
}

const templateForm = reactive<RequirementTemplatePayload>({
  template_scope: 'institution',
  institution_id: undefined,
  account_type: 'securities',
  fund_type: 'all',
  name: '',
  version: 1,
  effective_from: dayjs().format('YYYY-MM-DD'),
  effective_to: undefined,
  items: [blankTemplateItem(1)],
})

const institutionTypes: Record<string, string> = {
  broker: '证券公司',
  futures_company: '期货公司',
  custodian_bank: '托管银行',
  commercial_bank: '商业银行',
  fund_service_provider: '基金服务机构',
  other: '其他机构',
}
const accountTypes: Record<string, string> = {
  securities: '证券账户',
  futures: '期货账户',
  custody: '托管账户',
  bank: '银行账户',
}
const sourceScopes: Record<string, string> = {
  organization: '公司资料',
  product: '产品资料',
  account_application: '本次开户资料',
}

async function load() {
  loading.value = true
  try {
    ;[institutions.value, templates.value] = await Promise.all([
      listInstitutions(true),
      listRequirementTemplates(true),
    ])
  } catch (error) {
    ElMessage.error(apiErrorMessage(error))
  } finally {
    loading.value = false
  }
}

function openInstitutionDialog() {
  Object.assign(institutionForm, {
    institution_type: 'broker',
    full_name: '',
    short_name: '',
    license_code: '',
    contact_information: {},
  })
  Object.assign(contact, { name: '', phone: '', email: '' })
  institutionDialog.value = true
}

async function saveInstitution() {
  if (!institutionForm.full_name.trim()) {
    ElMessage.warning('请填写机构全称')
    return
  }
  saving.value = true
  try {
    await createInstitution({
      ...institutionForm,
      contact_information: Object.fromEntries(
        Object.entries(contact).filter(([, value]) => value.trim()),
      ),
    })
    ElMessage.success('开户机构已建立')
    institutionDialog.value = false
    await load()
  } catch (error) {
    ElMessage.error(apiErrorMessage(error))
  } finally {
    saving.value = false
  }
}

async function toggleInstitution(item: InstitutionItem) {
  try {
    await updateInstitution(item.id, { is_active: !item.is_active })
    ElMessage.success(item.is_active ? '机构已停用' : '机构已启用')
    await load()
  } catch (error) {
    ElMessage.error(apiErrorMessage(error))
  }
}

function openTemplateDialog() {
  Object.assign(templateForm, {
    template_scope: 'institution',
    institution_id: institutions.value.find((item) => item.is_active)?.id,
    account_type: 'securities',
    fund_type: 'all',
    name: '',
    version: 1,
    effective_from: dayjs().format('YYYY-MM-DD'),
    effective_to: undefined,
    items: [blankTemplateItem(1)],
  })
  templateDialog.value = true
}

function addTemplateItem() {
  templateForm.items.push(blankTemplateItem(templateForm.items.length + 1))
}

function removeTemplateItem(index: number) {
  if (templateForm.items.length === 1) return
  templateForm.items.splice(index, 1)
  templateForm.items.forEach((item, itemIndex) => { item.sort_order = itemIndex + 1 })
}

async function saveTemplate() {
  if (!templateForm.name.trim() || templateForm.items.some((item) => !item.name || !item.requirement_code)) {
    ElMessage.warning('请补全模板名称和材料项')
    return
  }
  if (templateForm.template_scope === 'institution' && !templateForm.institution_id) {
    ElMessage.warning('机构模板必须选择机构')
    return
  }
  saving.value = true
  try {
    const payload: RequirementTemplatePayload = {
      ...templateForm,
      institution_id: templateForm.template_scope === 'institution'
        ? templateForm.institution_id
        : undefined,
      items: templateForm.items.map((item, index) => ({ ...item, sort_order: index + 1 })),
    }
    await createRequirementTemplate(payload)
    ElMessage.success('材料模板已创建，新开户申请将按生效日期使用')
    templateDialog.value = false
    await load()
  } catch (error) {
    ElMessage.error(apiErrorMessage(error))
  } finally {
    saving.value = false
  }
}

async function toggleTemplate(item: RequirementTemplate) {
  try {
    await setRequirementTemplateState(item.id, !item.is_active)
    ElMessage.success(item.is_active ? '模板已停用' : '模板已启用')
    await load()
  } catch (error) {
    ElMessage.error(apiErrorMessage(error))
  }
}

onMounted(load)
</script>

<template>
  <div v-loading="loading">
    <PageHeader
      eyebrow="Institution Registry"
      title="机构与材料模板"
      description="维护开户机构，以及按机构、账户类型和基金类型生效的材料清单。监管基础模板会与机构模板合并。"
    >
      <template #actions>
        <el-button v-if="isAdmin && activeTab === 'institutions'" type="primary" @click="openInstitutionDialog">新增机构</el-button>
        <el-button v-if="isAdmin && activeTab === 'templates'" type="primary" @click="openTemplateDialog">新增模板</el-button>
      </template>
    </PageHeader>

    <el-alert
      v-if="!isAdmin"
      title="当前账号可查看机构和模板；只有管理员可以新增、启用或停用。"
      type="info"
      :closable="false"
      class="notice"
    />

    <el-tabs v-model="activeTab">
      <el-tab-pane label="开户机构" name="institutions">
        <el-card shadow="never">
          <el-table :data="institutions" empty-text="暂无开户机构">
            <el-table-column prop="full_name" label="机构全称" min-width="230" />
            <el-table-column prop="short_name" label="简称" width="140" />
            <el-table-column label="机构类型" width="140">
              <template #default="{ row }">{{ institutionTypes[row.institution_type] ?? row.institution_type }}</template>
            </el-table-column>
            <el-table-column prop="license_code" label="牌照/机构代码" width="170" />
            <el-table-column label="联系人" min-width="180">
              <template #default="{ row }">
                {{ row.contact_information.name || '—' }}
                <span v-if="row.contact_information.phone"> · {{ row.contact_information.phone }}</span>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="90">
              <template #default="{ row }"><el-tag :type="row.is_active ? 'success' : 'info'">{{ row.is_active ? '启用' : '停用' }}</el-tag></template>
            </el-table-column>
            <el-table-column v-if="isAdmin" label="操作" width="100">
              <template #default="{ row }"><el-button link :type="row.is_active ? 'danger' : 'primary'" @click="toggleInstitution(row)">{{ row.is_active ? '停用' : '启用' }}</el-button></template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-tab-pane>

      <el-tab-pane label="材料模板" name="templates">
        <el-card shadow="never">
          <el-table :data="templates" row-key="id" empty-text="暂无材料模板">
            <el-table-column type="expand">
              <template #default="{ row }">
                <el-table :data="row.items" class="inner-table">
                  <el-table-column prop="requirement_code" label="材料编码" width="180" />
                  <el-table-column prop="name" label="材料名称" min-width="200" />
                  <el-table-column label="资料来源" width="130"><template #default="scope">{{ sourceScopes[scope.row.source_scope] }}</template></el-table-column>
                  <el-table-column label="必需" width="75"><template #default="scope">{{ scope.row.required ? '是' : '否' }}</template></el-table-column>
                  <el-table-column label="原件" width="75"><template #default="scope">{{ scope.row.original_required ? '是' : '否' }}</template></el-table-column>
                  <el-table-column prop="seal_requirement" label="盖章要求" min-width="160" />
                </el-table>
              </template>
            </el-table-column>
            <el-table-column prop="name" label="模板名称" min-width="220" />
            <el-table-column label="范围" width="120"><template #default="{ row }">{{ row.template_scope === 'regulatory' ? '监管基础' : '机构模板' }}</template></el-table-column>
            <el-table-column prop="institution_name" label="适用机构" min-width="200"><template #default="{ row }">{{ row.institution_name ?? '全部机构' }}</template></el-table-column>
            <el-table-column label="账户类型" width="120"><template #default="{ row }">{{ accountTypes[row.account_type] ?? row.account_type }}</template></el-table-column>
            <el-table-column label="版本" width="70"><template #default="{ row }">v{{ row.version }}</template></el-table-column>
            <el-table-column label="生效日期" width="120"><template #default="{ row }">{{ row.effective_from }}</template></el-table-column>
            <el-table-column label="状态" width="90"><template #default="{ row }"><el-tag :type="row.is_active ? 'success' : 'info'">{{ row.is_active ? '启用' : '停用' }}</el-tag></template></el-table-column>
            <el-table-column v-if="isAdmin" label="操作" width="100"><template #default="{ row }"><el-button link :type="row.is_active ? 'danger' : 'primary'" @click="toggleTemplate(row)">{{ row.is_active ? '停用' : '启用' }}</el-button></template></el-table-column>
          </el-table>
        </el-card>
      </el-tab-pane>
    </el-tabs>

    <el-dialog v-model="institutionDialog" title="新增开户机构" width="620px">
      <el-form label-position="top">
        <el-row :gutter="16">
          <el-col :span="12"><el-form-item label="机构类型"><el-select v-model="institutionForm.institution_type"><el-option v-for="(label, value) in institutionTypes" :key="value" :label="label" :value="value" /></el-select></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="机构全称"><el-input v-model="institutionForm.full_name" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="机构简称"><el-input v-model="institutionForm.short_name" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="牌照/机构代码"><el-input v-model="institutionForm.license_code" /></el-form-item></el-col>
          <el-col :span="8"><el-form-item label="联系人"><el-input v-model="contact.name" /></el-form-item></el-col>
          <el-col :span="8"><el-form-item label="联系电话"><el-input v-model="contact.phone" /></el-form-item></el-col>
          <el-col :span="8"><el-form-item label="联系邮箱"><el-input v-model="contact.email" /></el-form-item></el-col>
        </el-row>
      </el-form>
      <template #footer><el-button @click="institutionDialog = false">取消</el-button><el-button type="primary" :loading="saving" @click="saveInstitution">保存</el-button></template>
    </el-dialog>

    <el-dialog v-model="templateDialog" title="新增材料模板" width="min(1100px, 92vw)">
      <el-form label-position="top">
        <el-row :gutter="14">
          <el-col :span="4"><el-form-item label="模板范围"><el-select v-model="templateForm.template_scope"><el-option label="机构模板" value="institution" /><el-option label="监管基础" value="regulatory" /></el-select></el-form-item></el-col>
          <el-col :span="6"><el-form-item label="适用机构"><el-select v-model="templateForm.institution_id" :disabled="templateForm.template_scope === 'regulatory'" filterable><el-option v-for="item in institutions.filter((row) => row.is_active)" :key="item.id" :label="item.full_name" :value="item.id" /></el-select></el-form-item></el-col>
          <el-col :span="4"><el-form-item label="账户类型"><el-select v-model="templateForm.account_type" allow-create filterable><el-option v-for="(label, value) in accountTypes" :key="value" :label="label" :value="value" /></el-select></el-form-item></el-col>
          <el-col :span="4"><el-form-item label="基金类型"><el-input v-model="templateForm.fund_type" /></el-form-item></el-col>
          <el-col :span="6"><el-form-item label="模板名称"><el-input v-model="templateForm.name" /></el-form-item></el-col>
          <el-col :span="4"><el-form-item label="版本"><el-input-number v-model="templateForm.version" :min="1" /></el-form-item></el-col>
          <el-col :span="6"><el-form-item label="生效日期"><el-date-picker v-model="templateForm.effective_from" type="date" value-format="YYYY-MM-DD" /></el-form-item></el-col>
        </el-row>
      </el-form>
      <div class="item-heading"><strong>材料清单</strong><el-button link type="primary" @click="addTemplateItem">添加材料项</el-button></div>
      <div v-for="(item, index) in templateForm.items" :key="index" class="template-item">
        <el-input v-model="item.requirement_code" placeholder="材料编码，如 business_license" />
        <el-input v-model="item.name" placeholder="材料名称" />
        <el-select v-model="item.source_scope"><el-option v-for="(label, value) in sourceScopes" :key="value" :label="label" :value="value" /></el-select>
        <el-input v-model="item.seal_requirement" placeholder="盖章要求（可选）" />
        <el-checkbox v-model="item.required">必需</el-checkbox>
        <el-checkbox v-model="item.original_required">原件</el-checkbox>
        <el-button link type="danger" :disabled="templateForm.items.length === 1" @click="removeTemplateItem(index)">删除</el-button>
      </div>
      <template #footer><el-button @click="templateDialog = false">取消</el-button><el-button type="primary" :loading="saving" @click="saveTemplate">创建模板</el-button></template>
    </el-dialog>
  </div>
</template>

<style scoped>
.notice { margin-bottom: 18px; }
.inner-table { margin: 10px 54px; width: calc(100% - 70px); }
.item-heading { display: flex; align-items: center; justify-content: space-between; margin: 10px 0; }
.template-item { display: grid; grid-template-columns: 1.25fr 1.4fr 1fr 1.1fr auto auto auto; gap: 10px; align-items: center; padding: 10px 0; border-top: 1px solid var(--el-border-color-lighter); }
@media (max-width: 900px) { .template-item { grid-template-columns: 1fr 1fr; } }
</style>
