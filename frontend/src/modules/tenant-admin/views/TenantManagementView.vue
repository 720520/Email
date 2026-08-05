<script setup lang="ts">
import { Edit, Plus, Switch, UserFilled } from '@element-plus/icons-vue'
import dayjs from 'dayjs'
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'

import PageHeader from '@/components/PageHeader.vue'
import { apiErrorMessage } from '@/platform/api/http'
import type { UserRole } from '@/platform/api/types'
import { useAuthStore } from '@/platform/auth/auth.store'

import {
  createTenant,
  createTenantMember,
  getTenantMembers,
  getTenants,
  updateTenant,
  updateTenantMember,
} from '../api'
import type { TenantMember, TenantSummary } from '../api/types'

const router = useRouter()
const auth = useAuthStore()
const loading = ref(false)
const saving = ref(false)
const tenants = ref<TenantSummary[]>([])
const tenantDialogVisible = ref(false)
const editingTenant = ref<TenantSummary>()
const tenantForm = reactive({ code: '', name: '' })

const membersVisible = ref(false)
const memberLoading = ref(false)
const selectedTenant = ref<TenantSummary>()
const members = ref<TenantMember[]>([])
const memberOriginals = ref<Record<number, { role: UserRole; is_active: boolean }>>({})
const memberForm = reactive<{ username: string; password: string; role: UserRole }>({
  username: '',
  password: '',
  role: 'viewer',
})

const isPlatformAdmin = computed(() => auth.user?.is_platform_admin === true)
const roleLabels: Record<UserRole, string> = {
  admin: '租户管理员',
  operator: '运营人员',
  viewer: '只读用户',
}

function roleName(role: UserRole | null): string {
  return role ? roleLabels[role] : '平台管理'
}

async function load() {
  loading.value = true
  try {
    tenants.value = await getTenants()
  } catch (error) {
    ElMessage.error(apiErrorMessage(error))
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editingTenant.value = undefined
  tenantForm.code = ''
  tenantForm.name = ''
  tenantDialogVisible.value = true
}

function openEdit(row: TenantSummary) {
  editingTenant.value = row
  tenantForm.code = row.code
  tenantForm.name = row.name
  tenantDialogVisible.value = true
}

async function saveTenant() {
  if (!tenantForm.name.trim()) {
    ElMessage.warning('请填写租户名称')
    return
  }
  if (!editingTenant.value && !/^[a-z0-9][a-z0-9_-]+$/.test(tenantForm.code.trim())) {
    ElMessage.warning('租户代码只能使用小写字母、数字、下划线和短横线')
    return
  }
  saving.value = true
  try {
    if (editingTenant.value) {
      await updateTenant(editingTenant.value.id, { name: tenantForm.name.trim() })
      ElMessage.success('租户名称已更新')
    } else {
      await createTenant({ code: tenantForm.code.trim(), name: tenantForm.name.trim() })
      await auth.loadTenants()
      ElMessage.success('租户已创建，当前管理员已自动加入该租户')
    }
    tenantDialogVisible.value = false
    await load()
  } catch (error) {
    ElMessage.error(apiErrorMessage(error))
  } finally {
    saving.value = false
  }
}

async function toggleTenant(row: TenantSummary) {
  const action = row.is_active ? '停用' : '启用'
  try {
    await ElMessageBox.confirm(
      row.is_active
        ? `停用“${row.name}”后，该租户所有成员将无法登录。历史数据不会删除。`
        : `确认重新启用“${row.name}”？`,
      `${action}租户`,
      { type: row.is_active ? 'warning' : 'info', confirmButtonText: action },
    )
    await updateTenant(row.id, { is_active: !row.is_active })
    ElMessage.success(`租户已${action}`)
    await load()
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') ElMessage.error(apiErrorMessage(error))
  }
}

async function enterTenant(row: TenantSummary) {
  if (row.is_current) return
  try {
    await auth.switchTenant(row.id)
    await router.replace('/overview')
    window.location.reload()
  } catch (error) {
    ElMessage.error(apiErrorMessage(error))
  }
}

async function openMembers(row: TenantSummary) {
  selectedTenant.value = row
  membersVisible.value = true
  memberForm.username = ''
  memberForm.password = ''
  memberForm.role = 'viewer'
  await loadMembers()
}

async function loadMembers() {
  if (!selectedTenant.value) return
  memberLoading.value = true
  try {
    members.value = await getTenantMembers(selectedTenant.value.id)
    memberOriginals.value = Object.fromEntries(
      members.value.map((member) => [member.user_id, {
        role: member.role,
        is_active: member.is_active,
      }]),
    )
  } catch (error) {
    ElMessage.error(apiErrorMessage(error))
  } finally {
    memberLoading.value = false
  }
}

async function addMember() {
  if (!selectedTenant.value || !memberForm.username.trim()) {
    ElMessage.warning('请填写用户名')
    return
  }
  saving.value = true
  try {
    await createTenantMember(selectedTenant.value.id, {
      username: memberForm.username.trim(),
      password: memberForm.password || undefined,
      role: memberForm.role,
    })
    memberForm.username = ''
    memberForm.password = ''
    ElMessage.success('成员关系已建立；邮箱权限仍需在邮箱账户页单独授予')
    await Promise.all([loadMembers(), load()])
  } catch (error) {
    ElMessage.error(apiErrorMessage(error))
  } finally {
    saving.value = false
  }
}

function memberChanged(member: TenantMember): boolean {
  const original = memberOriginals.value[member.user_id]
  return Boolean(original && (original.role !== member.role || original.is_active !== member.is_active))
}

async function saveMember(member: TenantMember) {
  if (!selectedTenant.value || !memberChanged(member)) return
  try {
    await updateTenantMember(selectedTenant.value.id, member.user_id, {
      role: member.role,
      is_active: member.is_active,
    })
    ElMessage.success('成员权限已更新，已有会话将重新验证')
    await Promise.all([loadMembers(), load()])
  } catch (error) {
    ElMessage.error(apiErrorMessage(error))
    await loadMembers()
  }
}

function canEnter(row: TenantSummary): boolean {
  return auth.tenants.some((tenant) => tenant.id === row.id)
}

onMounted(load)
</script>

<template>
  <div>
    <PageHeader
      eyebrow="Tenant & Access"
      title="租户与成员"
      description="租户是最外层业务数据边界。成员角色只在所属租户内生效，邮箱内容权限需要另行授权。"
    >
      <template #actions>
        <el-button v-if="isPlatformAdmin" type="primary" :icon="Plus" @click="openCreate">新增租户</el-button>
      </template>
    </PageHeader>

    <el-alert
      class="page-alert"
      type="info"
      :closable="false"
      show-icon
      title="平台管理员负责创建和停用租户；租户管理员负责本租户成员。成员加入租户后不会自动获得任何邮箱内容权限。"
    />

    <section class="panel data-panel" v-loading="loading">
      <el-table :data="tenants" empty-text="暂无可管理的租户">
        <el-table-column label="租户" min-width="230">
          <template #default="{ row }">
            <strong class="table-primary">{{ row.name }}</strong>
            <el-tag v-if="row.is_current" class="mailbox-inline-tag" size="small" type="success">当前</el-tag>
            <span class="cell-secondary">{{ row.code }}</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }"><el-tag :type="row.is_active ? 'success' : 'info'">{{ row.is_active ? '启用' : '停用' }}</el-tag></template>
        </el-table-column>
        <el-table-column label="我的角色" width="130">
          <template #default="{ row }">{{ roleName(row.current_user_role) }}</template>
        </el-table-column>
        <el-table-column prop="member_count" label="有效成员" width="100" />
        <el-table-column prop="mailbox_count" label="邮箱数" width="90" />
        <el-table-column label="创建时间" width="170">
          <template #default="{ row }">{{ dayjs(row.create_time).format('YYYY-MM-DD HH:mm') }}</template>
        </el-table-column>
        <el-table-column label="操作" min-width="280" fixed="right">
          <template #default="{ row }">
            <el-button v-if="canEnter(row) && !row.is_current" link type="primary" :icon="Switch" @click="enterTenant(row)">进入</el-button>
            <el-button link type="primary" :icon="UserFilled" @click="openMembers(row)">成员</el-button>
            <el-button v-if="isPlatformAdmin" link type="primary" :icon="Edit" @click="openEdit(row)">编辑</el-button>
            <el-button v-if="isPlatformAdmin" link :type="row.is_active ? 'danger' : 'success'" :disabled="row.is_current && row.is_active" @click="toggleTenant(row)">
              {{ row.is_active ? '停用' : '启用' }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </section>

    <el-dialog v-model="tenantDialogVisible" :title="editingTenant ? '编辑租户' : '新增租户'" width="520px">
      <el-form label-position="top">
        <el-form-item label="租户代码">
          <el-input v-model="tenantForm.code" :disabled="Boolean(editingTenant)" placeholder="例如：jiyu、qianguo" />
          <span class="form-help">创建后不可修改，用于审计和系统识别，不使用中文名称。</span>
        </el-form-item>
        <el-form-item label="租户名称">
          <el-input v-model="tenantForm.name" maxlength="255" placeholder="例如：吉余私募" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="tenantDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveTenant">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="membersVisible" :title="`${selectedTenant?.name ?? ''} · 成员管理`" width="900px">
      <div class="member-create-bar">
        <el-input v-model="memberForm.username" placeholder="用户名" />
        <el-input v-model="memberForm.password" type="password" show-password :placeholder="isPlatformAdmin ? '新用户初始密码；已有用户留空' : '新用户初始密码'" />
        <el-select v-model="memberForm.role">
          <el-option v-for="(label, role) in roleLabels" :key="role" :label="label" :value="role" />
        </el-select>
        <el-button type="primary" :loading="saving" @click="addMember">添加成员</el-button>
      </div>
      <p class="member-create-help">
        新用户名至少设置 10 位初始密码；{{ isPlatformAdmin ? '输入系统内已有用户名时仅建立租户成员关系，不修改原密码。' : '跨租户关联已有登录身份只能由平台管理员执行。' }}
      </p>
      <el-table v-loading="memberLoading" :data="members" max-height="440">
        <el-table-column label="用户" min-width="190">
          <template #default="{ row }">
            <strong>{{ row.username }}</strong>
            <el-tag v-if="row.is_platform_admin" size="small" class="mailbox-inline-tag">平台管理员</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="租户角色" width="180">
          <template #default="{ row }">
            <el-select v-model="row.role" size="small">
              <el-option v-for="(label, role) in roleLabels" :key="role" :label="label" :value="role" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="成员状态" width="130">
          <template #default="{ row }"><el-switch v-model="row.is_active" active-text="启用" /></template>
        </el-table-column>
        <el-table-column label="登录身份" width="110">
          <template #default="{ row }"><el-tag :type="row.user_is_active ? 'success' : 'info'">{{ row.user_is_active ? '有效' : '停用' }}</el-tag></template>
        </el-table-column>
        <el-table-column label="加入时间" width="150">
          <template #default="{ row }">{{ dayjs(row.create_time).format('YYYY-MM-DD') }}</template>
        </el-table-column>
        <el-table-column label="操作" width="90" fixed="right">
          <template #default="{ row }"><el-button link type="primary" :disabled="!memberChanged(row)" @click="saveMember(row)">保存</el-button></template>
        </el-table-column>
      </el-table>
    </el-dialog>
  </div>
</template>
