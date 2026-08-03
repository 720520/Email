<script setup lang="ts">
import { Connection, Download, Lock, Refresh, Search, View } from '@element-plus/icons-vue'
import dayjs from 'dayjs'
import { ElMessage } from 'element-plus'
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import PageHeader from '@/components/PageHeader.vue'
import StatusTag from '@/components/StatusTag.vue'
import { apiErrorMessage } from '@/platform/api/http'
import { useAuthStore } from '@/platform/auth/auth.store'

import EmailDetailDialog from '../components/EmailDetailDialog.vue'
import {
  getEmailConnectionInfo,
  getEmails,
  syncEmailNow,
  testEmailConnection,
} from '../api'
import type {
  EmailConnectionInfo,
  EmailConnectionTest,
  EmailItem,
  EmailStatus,
  EmailSyncResult,
} from '../api/types'

const route = useRoute()
const auth = useAuthStore()
const loading = ref(false)
const connectionLoading = ref(false)
const syncLoading = ref(false)
const connectionInfo = ref<EmailConnectionInfo>()
const connectionResult = ref<EmailConnectionTest>()
const syncResult = ref<EmailSyncResult>()
const rows = ref<EmailItem[]>([])
const selectedEmailId = ref<number | null>(null)
const detailVisible = ref(false)
const total = ref(0)
const filters = reactive({
  keyword: '',
  status: (typeof route.query.status === 'string' ? route.query.status : '') as EmailStatus | '',
  dates: [] as string[],
  page: 1,
  pageSize: 20,
})
const canTestConnection = computed(
  () => auth.user?.role === 'admin' || auth.user?.role === 'operator',
)

const statusOptions: Array<{ value: EmailStatus; label: string }> = [
  { value: 'discovered', label: '已发现' },
  { value: 'archived', label: '已归档' },
  { value: 'processing', label: '处理中' },
  { value: 'success', label: '成功' },
  { value: 'partial_success', label: '部分成功' },
  { value: 'failed', label: '失败' },
  { value: 'skipped', label: '已跳过' },
]

async function loadRows() {
  loading.value = true
  try {
    const data = await getEmails({
      page: filters.page,
      page_size: filters.pageSize,
      keyword: filters.keyword.trim() || undefined,
      status: filters.status || undefined,
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

async function loadConnectionInfo() {
  try {
    connectionInfo.value = await getEmailConnectionInfo()
  } catch (error) {
    ElMessage.error(apiErrorMessage(error))
  }
}

async function checkConnection() {
  connectionLoading.value = true
  connectionResult.value = undefined
  try {
    connectionResult.value = await testEmailConnection()
    if (connectionResult.value.success) ElMessage.success('邮箱连接成功')
    else ElMessage.error(connectionResult.value.message)
  } catch (error) {
    ElMessage.error(apiErrorMessage(error))
  } finally {
    connectionLoading.value = false
  }
}

async function synchronizeMailbox() {
  syncLoading.value = true
  syncResult.value = undefined
  try {
    syncResult.value = await syncEmailNow()
    if (syncResult.value.success) {
      ElMessage.success(syncResult.value.message)
      // 已匹配邮件会立即进入成功或部分成功，不再停留在“已发现”。
      filters.status = ''
      filters.page = 1
      await loadRows()
    } else {
      ElMessage.error(syncResult.value.message)
    }
  } catch (error) {
    ElMessage.error(apiErrorMessage(error))
  } finally {
    syncLoading.value = false
  }
}

function search() {
  filters.page = 1
  void loadRows()
}

function reset() {
  filters.keyword = ''
  filters.status = ''
  filters.dates = []
  filters.page = 1
  void loadRows()
}

function openEmail(row: EmailItem) {
  selectedEmailId.value = row.id
  detailVisible.value = true
}

watch(() => filters.pageSize, search)
onMounted(() => {
  void loadRows()
  void loadConnectionInfo()
})
</script>

<template>
  <div>
    <PageHeader
      eyebrow="Mail Trace"
      title="邮件管理"
      description="按主题、发送人、收件日期和解析状态追溯原始邮件处理结果。"
    >
      <el-button
        v-if="canTestConnection"
        :icon="Download"
        type="primary"
        :loading="syncLoading"
        :disabled="!connectionInfo?.configured"
        @click="synchronizeMailbox"
      >立即同步</el-button>
      <el-button :icon="Refresh" :loading="loading" @click="loadRows">刷新</el-button>
    </PageHeader>

    <section class="panel mailbox-panel">
      <div class="panel-header">
        <div>
          <h2>当前邮箱连接</h2>
          <p>展示后端实际加载的 IMAP 配置；授权码和访问令牌不会返回页面</p>
        </div>
        <el-button
          v-if="canTestConnection"
          type="primary"
          plain
          :icon="Connection"
          :loading="connectionLoading"
          :disabled="!connectionInfo?.configured"
          @click="checkConnection"
        >检测连接</el-button>
      </div>
      <div v-if="connectionInfo" class="mailbox-panel__body">
        <div class="mailbox-identity">
          <span class="mailbox-identity__icon"><el-icon><Connection /></el-icon></span>
          <div>
            <small>IMAP 邮箱账号</small>
            <strong>{{ connectionInfo.username || '未配置账号' }}</strong>
            <span>{{ connectionInfo.host || '未配置服务器' }}<template v-if="connectionInfo.host">:{{ connectionInfo.port }}</template></span>
          </div>
          <el-tag :type="connectionInfo.configured ? 'success' : 'warning'" effect="light" round>
            {{ connectionInfo.configured ? '配置完整' : '配置不完整' }}
          </el-tag>
        </div>
        <dl class="mailbox-details">
          <div><dt>认证方式</dt><dd>{{ connectionInfo.auth_mode === 'oauth2' ? 'OAuth2' : '授权码 / 密码' }}</dd></div>
          <div><dt>连接加密</dt><dd>{{ connectionInfo.transport }}</dd></div>
          <div><dt>邮箱目录</dt><dd>{{ connectionInfo.folder }}</dd></div>
          <div><dt>连接超时</dt><dd class="numeric">{{ connectionInfo.timeout_seconds }} 秒</dd></div>
          <div><dt>认证凭据</dt><dd><el-icon><Lock /></el-icon>{{ connectionInfo.credential_configured ? '已安全配置' : '尚未配置' }}</dd></div>
        </dl>
        <el-alert
          v-if="!connectionInfo.configured"
          title="邮箱配置尚不完整，请检查 host、username 和授权码或 OAuth2 令牌。"
          type="warning"
          :closable="false"
          show-icon
        />
        <div
          v-if="connectionResult"
          class="connection-result"
          :class="connectionResult.success ? 'connection-result--success' : 'connection-result--failed'"
        >
          <span class="connection-result__dot"></span>
          <div>
            <strong>{{ connectionResult.success ? '连接成功' : '连接失败' }}</strong>
            <p>{{ connectionResult.message }}</p>
          </div>
          <div class="connection-result__meta">
            <span>{{ dayjs(connectionResult.checked_at).format('YYYY-MM-DD HH:mm:ss') }}</span>
            <span class="numeric">{{ connectionResult.latency_ms }} ms</span>
            <span v-if="connectionResult.message_count !== null" class="numeric">收件箱 {{ connectionResult.message_count }} 封</span>
            <span v-if="connectionResult.uid_validity" class="numeric">UID {{ connectionResult.uid_validity }}</span>
          </div>
        </div>
        <div v-if="syncResult" class="sync-result" :class="{ 'sync-result--failed': !syncResult.success }">
          <div><small>本次发现</small><strong class="numeric">{{ syncResult.discovered_count }}</strong></div>
          <div><small>新增归档</small><strong class="numeric">{{ syncResult.archived_count }}</strong></div>
          <div><small>已处理</small><strong class="numeric">{{ syncResult.duplicate_count }}</strong></div>
          <div><small>非候选邮件</small><strong class="numeric">{{ syncResult.ignored_count }}</strong></div>
          <div><small>处理失败</small><strong class="numeric">{{ syncResult.failed_count }}</strong></div>
          <p>{{ syncResult.message }} · 任务 #{{ syncResult.job_run_id }}</p>
        </div>
      </div>
      <div v-else v-loading="true" class="mailbox-panel__loading"></div>
    </section>

    <section class="panel filter-panel">
      <el-form class="filter-form" label-position="top" @submit.prevent="search">
        <el-form-item label="主题或发送人">
          <el-input v-model="filters.keyword" clearable placeholder="输入关键词" style="width: 260px" @keyup.enter="search" />
        </el-form-item>
        <el-form-item label="解析状态">
          <el-select v-model="filters.status" clearable placeholder="全部状态" style="width: 160px">
            <el-option v-for="option in statusOptions" :key="option.value" :label="option.label" :value="option.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="收件日期">
          <el-date-picker v-model="filters.dates" type="daterange" value-format="YYYY-MM-DD" start-placeholder="开始日期" end-placeholder="结束日期" />
        </el-form-item>
        <el-form-item class="filter-actions">
          <el-button :icon="Search" type="primary" @click="search">查询</el-button>
          <el-button @click="reset">重置</el-button>
        </el-form-item>
      </el-form>
    </section>

    <section class="panel data-panel">
      <el-table v-loading="loading" :data="rows" empty-text="没有符合条件的邮件记录">
        <el-table-column label="主题" min-width="300" show-overflow-tooltip>
          <template #default="{ row }"><strong class="table-primary">{{ row.subject }}</strong></template>
        </el-table-column>
        <el-table-column prop="sender" label="发送人" min-width="190" show-overflow-tooltip />
        <el-table-column label="收件时间" width="168">
          <template #default="{ row }"><span class="numeric">{{ dayjs(row.receive_time).format('YYYY-MM-DD HH:mm') }}</span></template>
        </el-table-column>
        <el-table-column prop="attachment_count" label="附件" width="82" align="center" />
        <el-table-column label="解析状态" width="118"><template #default="{ row }"><StatusTag :status="row.status" /></template></el-table-column>
        <el-table-column label="处理说明" min-width="190" show-overflow-tooltip>
          <template #default="{ row }"><span :class="row.error_message ? 'danger-text' : 'text-muted'">{{ row.error_message || '—' }}</span></template>
        </el-table-column>
        <el-table-column label="原邮件" width="108" fixed="right">
          <template #default="{ row }">
            <el-button text type="primary" :icon="View" @click="openEmail(row)">查看</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="pagination-wrap">
        <el-pagination
          v-model:current-page="filters.page"
          v-model:page-size="filters.pageSize"
          :total="total"
          :page-sizes="[20, 50, 100]"
          layout="total, sizes, prev, pager, next"
          @current-change="loadRows"
        />
      </div>
    </section>
    <EmailDetailDialog v-model="detailVisible" :email-id="selectedEmailId" />
  </div>
</template>
