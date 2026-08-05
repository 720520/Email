<script setup lang="ts">
import { Connection, Edit, Key, Plus, Refresh, Upload } from '@element-plus/icons-vue'
import dayjs from 'dayjs'
import { ElMessage } from 'element-plus'
import { computed, onMounted, reactive, ref } from 'vue'

import PageHeader from '@/components/PageHeader.vue'
import { apiErrorMessage } from '@/platform/api/http'
import { useAuthStore } from '@/platform/auth/auth.store'

import {
  createMailbox,
  getMailboxGrants,
  getMailboxes,
  getMailboxSecurityStatus,
  syncMailbox,
  testMailboxConnection,
  updateMailbox,
  updateMailboxGrant,
} from '../api'
import type {
  MailboxAccount,
  MailboxAccountPayload,
  MailboxGrant,
  MailboxGrantPayload,
  MailboxSecurityStatus,
} from '../api/types'

interface MailboxForm {
  display_name: string
  host: string
  port: number
  username: string
  auth_mode: 'password' | 'oauth2'
  credential: string
  use_ssl: boolean
  start_tls: boolean
  timeout_seconds: number
  folder: string
  lookback_days: number
  max_messages_per_run: number
  is_default: boolean
  is_enabled: boolean
  clear_credential: boolean
}

const auth = useAuthStore()
const loading = ref(false)
const saving = ref(false)
const busyId = ref<number>()
const rows = ref<MailboxAccount[]>([])
const security = ref<MailboxSecurityStatus>()
const editorVisible = ref(false)
const editingId = ref<number>()
const grantsVisible = ref(false)
const grantMailbox = ref<MailboxAccount>()
const grants = ref<MailboxGrant[]>([])
const grantLoading = ref(false)
const isAdmin = computed(() => auth.user?.role === 'admin')
const securityReady = computed(() => security.value?.ready_for_credentials === true)

const form = reactive<MailboxForm>(emptyForm())

function emptyForm(): MailboxForm {
  return {
    display_name: '',
    host: '',
    port: 993,
    username: '',
    auth_mode: 'password',
    credential: '',
    use_ssl: true,
    start_tls: false,
    timeout_seconds: 30,
    folder: 'INBOX',
    lookback_days: 7,
    max_messages_per_run: 200,
    is_default: false,
    is_enabled: true,
    clear_credential: false,
  }
}

async function load() {
  loading.value = true
  try {
    const [accounts, status] = await Promise.all([
      getMailboxes(),
      getMailboxSecurityStatus(),
    ])
    rows.value = accounts
    security.value = status
  } catch (error) {
    ElMessage.error(apiErrorMessage(error))
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editingId.value = undefined
  Object.assign(form, emptyForm())
  editorVisible.value = true
}

function openEdit(row: MailboxAccount) {
  editingId.value = row.id
  Object.assign(form, {
    ...emptyForm(),
    display_name: row.display_name,
    host: row.host,
    port: row.port,
    username: row.username,
    auth_mode: row.auth_mode,
    use_ssl: row.use_ssl,
    start_tls: row.start_tls,
    timeout_seconds: row.timeout_seconds,
    folder: row.folder,
    lookback_days: row.lookback_days,
    max_messages_per_run: row.max_messages_per_run,
    is_default: row.is_default,
    is_enabled: row.is_enabled,
  })
  editorVisible.value = true
}

async function saveMailbox() {
  if (!form.display_name.trim() || !form.host.trim() || !form.username.trim()) {
    ElMessage.warning('请完整填写邮箱名称、IMAP 服务器和邮箱账号')
    return
  }
  if (form.use_ssl && form.start_tls) {
    ElMessage.warning('SSL/TLS 与 STARTTLS 不能同时启用')
    return
  }
  saving.value = true
  try {
    const payload: MailboxAccountPayload = {
      display_name: form.display_name.trim(),
      host: form.host.trim(),
      port: form.port,
      username: form.username.trim(),
      auth_mode: form.auth_mode,
      use_ssl: form.use_ssl,
      start_tls: form.start_tls,
      timeout_seconds: form.timeout_seconds,
      folder: form.folder.trim(),
      lookback_days: form.lookback_days,
      max_messages_per_run: form.max_messages_per_run,
      is_default: form.is_default,
      is_enabled: form.is_enabled,
    }
    if (form.credential.trim()) payload.credential = form.credential.trim()
    if (editingId.value && form.clear_credential) payload.clear_credential = true
    if (editingId.value) await updateMailbox(editingId.value, payload)
    else await createMailbox(payload)
    ElMessage.success(editingId.value ? '邮箱配置已更新' : '邮箱账户已创建')
    editorVisible.value = false
    await load()
  } catch (error) {
    ElMessage.error(apiErrorMessage(error))
  } finally {
    saving.value = false
  }
}

async function checkConnection(row: MailboxAccount) {
  busyId.value = row.id
  try {
    const result = await testMailboxConnection(row.id)
    if (result.success) ElMessage.success(`${row.display_name}连接成功`)
    else ElMessage.error(result.message)
    await load()
  } catch (error) {
    ElMessage.error(apiErrorMessage(error))
  } finally {
    busyId.value = undefined
  }
}

async function synchronize(row: MailboxAccount) {
  busyId.value = row.id
  try {
    const result = await syncMailbox(row.id)
    if (result.success) ElMessage.success(result.message)
    else ElMessage.error(result.message)
    await load()
  } catch (error) {
    ElMessage.error(apiErrorMessage(error))
  } finally {
    busyId.value = undefined
  }
}

async function openGrants(row: MailboxAccount) {
  grantsVisible.value = true
  grantMailbox.value = row
  grantLoading.value = true
  try {
    grants.value = await getMailboxGrants(row.id)
  } catch (error) {
    ElMessage.error(apiErrorMessage(error))
  } finally {
    grantLoading.value = false
  }
}

async function saveGrant(row: MailboxGrant) {
  if (!grantMailbox.value) return
  if (row.can_read_content || row.can_operate || row.can_manage_credentials) {
    row.can_read_metadata = true
  }
  const payload: MailboxGrantPayload = {
    can_read_metadata: row.can_read_metadata,
    can_read_content: row.can_read_content,
    can_operate: row.can_operate,
    can_manage_credentials: row.can_manage_credentials,
    is_active: row.is_active,
  }
  try {
    await updateMailboxGrant(grantMailbox.value.id, row.user_id, payload)
    ElMessage.success(`已保存 ${row.username} 的邮箱权限`)
  } catch (error) {
    ElMessage.error(apiErrorMessage(error))
    grants.value = await getMailboxGrants(grantMailbox.value.id)
  }
}

function statusLabel(value: string | null) {
  if (value === 'success') return '成功'
  if (value === 'partial_success') return '部分成功'
  if (value === 'failed') return '失败'
  if (value === 'running') return '执行中'
  return '未执行'
}

onMounted(load)
</script>

<template>
  <div>
    <PageHeader
      eyebrow="Mailbox Isolation"
      title="邮箱账户"
      description="按业务账套集中配置多个 IMAP 邮箱，并以邮箱为最小单位隔离查看、正文、操作和凭据管理权限。"
    >
      <el-button
        v-if="isAdmin"
        type="primary"
        :icon="Plus"
        :disabled="!securityReady"
        @click="openCreate"
      >新增邮箱</el-button>
      <el-button :icon="Refresh" :loading="loading" @click="load">刷新</el-button>
    </PageHeader>

    <el-alert
      v-if="security && !security.ready_for_credentials"
      class="page-alert"
      type="error"
      :closable="false"
      show-icon
      title="多邮箱安全门禁尚未解除"
      description="必须同时配置独立的邮箱凭据加密密钥和审计签名密钥；当前只允许查看，不允许保存凭据、测试连接或同步邮件。"
    />

    <section class="panel data-panel">
      <el-table v-loading="loading" :data="rows" empty-text="当前账号没有可访问的邮箱">
        <el-table-column label="邮箱" min-width="220">
          <template #default="{ row }">
            <strong class="table-primary">{{ row.display_name }}</strong>
            <span class="cell-secondary">{{ row.username }}</span>
          </template>
        </el-table-column>
        <el-table-column label="IMAP 连接" min-width="210">
          <template #default="{ row }">
            <span class="numeric">{{ row.host }}:{{ row.port }}</span>
            <span class="cell-secondary">{{ row.use_ssl ? 'SSL/TLS' : row.start_tls ? 'STARTTLS' : '未加密' }} · {{ row.folder }}</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="140">
          <template #default="{ row }">
            <el-tag :type="row.is_enabled ? 'success' : 'info'" effect="light">
              {{ row.is_enabled ? '启用' : '已停用' }}
            </el-tag>
            <el-tag v-if="row.is_default" class="mailbox-inline-tag" effect="plain">默认</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="凭据" width="110">
          <template #default="{ row }">
            <el-tag :type="row.credential_configured ? 'success' : 'warning'" effect="plain">
              {{ row.credential_configured ? '已加密' : '未配置' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="最近连接" min-width="170">
          <template #default="{ row }">
            <span :class="row.last_connection_status === 'failed' ? 'danger-text' : ''">
              {{ statusLabel(row.last_connection_status) }}
            </span>
            <span class="cell-secondary">{{ row.last_connection_at ? dayjs(row.last_connection_at).format('YYYY-MM-DD HH:mm') : '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="最近同步" min-width="170">
          <template #default="{ row }">
            <span :class="row.last_sync_status === 'failed' ? 'danger-text' : ''">
              {{ statusLabel(row.last_sync_status) }}
            </span>
            <span class="cell-secondary">{{ row.last_sync_at ? dayjs(row.last_sync_at).format('YYYY-MM-DD HH:mm') : '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="330" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="row.permissions.can_operate"
              text
              type="primary"
              :icon="Connection"
              :loading="busyId === row.id"
              :disabled="!securityReady || !row.credential_configured || !row.is_enabled"
              @click="checkConnection(row)"
            >检测</el-button>
            <el-button
              v-if="row.permissions.can_operate"
              text
              type="primary"
              :icon="Upload"
              :loading="busyId === row.id"
              :disabled="!securityReady || !row.credential_configured || !row.is_enabled"
              @click="synchronize(row)"
            >同步</el-button>
            <el-button
              v-if="isAdmin && row.permissions.can_manage_credentials"
              text
              :icon="Edit"
              :disabled="!securityReady"
              @click="openEdit(row)"
            >编辑</el-button>
            <el-button
              v-if="isAdmin && row.permissions.can_manage_credentials"
              text
              :icon="Key"
              :disabled="!securityReady"
              @click="openGrants(row)"
            >权限</el-button>
          </template>
        </el-table-column>
      </el-table>
    </section>

    <el-dialog v-model="editorVisible" :title="editingId ? '编辑邮箱账户' : '新增邮箱账户'" width="720px">
      <el-form label-position="top" class="mailbox-editor-grid">
        <el-form-item label="显示名称"><el-input v-model="form.display_name" /></el-form-item>
        <el-form-item label="邮箱账号"><el-input v-model="form.username" autocomplete="off" /></el-form-item>
        <el-form-item label="IMAP 服务器"><el-input v-model="form.host" placeholder="例如 imap.163.com" /></el-form-item>
        <el-form-item label="端口"><el-input-number v-model="form.port" :min="1" :max="65535" /></el-form-item>
        <el-form-item label="认证方式">
          <el-select v-model="form.auth_mode"><el-option label="授权码 / 密码" value="password" /><el-option label="OAuth2" value="oauth2" /></el-select>
        </el-form-item>
        <el-form-item :label="editingId ? '更新凭据（留空则不变）' : '授权码 / 访问令牌'">
          <el-input v-model="form.credential" type="password" show-password autocomplete="new-password" />
        </el-form-item>
        <el-form-item label="邮箱目录"><el-input v-model="form.folder" /></el-form-item>
        <el-form-item label="回看天数"><el-input-number v-model="form.lookback_days" :min="1" :max="365" /></el-form-item>
        <el-form-item label="单次最大邮件数"><el-input-number v-model="form.max_messages_per_run" :min="1" :max="5000" /></el-form-item>
        <el-form-item label="连接超时（秒）"><el-input-number v-model="form.timeout_seconds" :min="1" :max="300" /></el-form-item>
        <el-form-item label="连接安全">
          <el-checkbox v-model="form.use_ssl">SSL/TLS</el-checkbox>
          <el-checkbox v-model="form.start_tls">STARTTLS</el-checkbox>
        </el-form-item>
        <el-form-item label="账户状态">
          <el-checkbox v-model="form.is_enabled">启用</el-checkbox>
          <el-checkbox v-model="form.is_default">设为默认</el-checkbox>
          <el-checkbox v-if="editingId" v-model="form.clear_credential">清空已保存凭据</el-checkbox>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editorVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveMailbox">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="grantsVisible" :title="`${grantMailbox?.display_name ?? ''} · 用户权限`" width="820px">
      <el-table v-loading="grantLoading" :data="grants">
        <el-table-column prop="username" label="用户" min-width="150" />
        <el-table-column prop="role" label="租户角色" width="100" />
        <el-table-column label="启用" width="80"><template #default="{ row }"><el-switch v-model="row.is_active" /></template></el-table-column>
        <el-table-column label="元数据" width="90"><template #default="{ row }"><el-checkbox v-model="row.can_read_metadata" /></template></el-table-column>
        <el-table-column label="邮件正文" width="100"><template #default="{ row }"><el-checkbox v-model="row.can_read_content" /></template></el-table-column>
        <el-table-column label="连接/同步" width="110"><template #default="{ row }"><el-checkbox v-model="row.can_operate" /></template></el-table-column>
        <el-table-column label="凭据管理" width="100"><template #default="{ row }"><el-checkbox v-model="row.can_manage_credentials" :disabled="row.role !== 'admin'" /></template></el-table-column>
        <el-table-column label="操作" width="90"><template #default="{ row }"><el-button text type="primary" @click="saveGrant(row)">保存</el-button></template></el-table-column>
      </el-table>
      <el-alert class="grant-note" type="info" :closable="false" show-icon title="正文、连接同步或凭据管理权限会自动包含邮箱元数据查看权限。" />
    </el-dialog>
  </div>
</template>
