<script setup lang="ts">
import { Download, Message, Paperclip } from '@element-plus/icons-vue'
import dayjs from 'dayjs'
import { ElMessage } from 'element-plus'
import { computed, ref, watch } from 'vue'

import StatusTag from '@/components/StatusTag.vue'
import { apiErrorMessage } from '@/platform/api/http'

import { downloadRawEmail, getEmailDetail } from '../api'
import type { EmailDetail } from '../api/types'

const props = defineProps<{
  modelValue: boolean
  emailId: number | null
}>()
const emit = defineEmits<{ 'update:modelValue': [value: boolean] }>()

const visible = computed({
  get: () => props.modelValue,
  set: (value: boolean) => emit('update:modelValue', value),
})
const loading = ref(false)
const downloading = ref(false)
const detail = ref<EmailDetail>()

async function loadDetail(emailId: number) {
  loading.value = true
  detail.value = undefined
  try {
    detail.value = await getEmailDetail(emailId)
  } catch (error) {
    ElMessage.error(apiErrorMessage(error))
  } finally {
    loading.value = false
  }
}

async function downloadOriginal() {
  if (!detail.value) return
  downloading.value = true
  try {
    const blob = await downloadRawEmail(detail.value.id)
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `原始邮件_${detail.value.id}.eml`
    document.body.appendChild(anchor)
    anchor.click()
    anchor.remove()
    URL.revokeObjectURL(url)
  } catch (error) {
    ElMessage.error(apiErrorMessage(error))
  } finally {
    downloading.value = false
  }
}

watch(
  [() => props.modelValue, () => props.emailId],
  ([isVisible, emailId]) => {
    if (isVisible && emailId) void loadDetail(emailId)
  },
  { immediate: true },
)
</script>

<template>
  <el-dialog v-model="visible" width="min(900px, 92vw)" destroy-on-close>
    <template #header>
      <div class="dialog-heading">
        <span>原始邮件</span>
        <small>安全纯文本预览 · 邮件编号 #{{ emailId ?? '—' }}</small>
      </div>
    </template>

    <div v-loading="loading" class="email-detail">
      <template v-if="detail">
        <div class="email-detail__title">
          <span class="email-detail__icon"><el-icon><Message /></el-icon></span>
          <div>
            <h3>{{ detail.subject || '（无主题）' }}</h3>
            <p>{{ detail.sender || '未知发送人' }}</p>
          </div>
          <StatusTag :status="detail.status" />
        </div>

        <el-descriptions :column="2" border class="email-detail__meta">
          <el-descriptions-item label="收件时间">
            <span class="numeric">{{ dayjs(detail.receive_time).format('YYYY-MM-DD HH:mm:ss') }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="附件数量">{{ detail.attachments.length }}</el-descriptions-item>
        </el-descriptions>

        <el-alert
          v-if="detail.error_message"
          :title="detail.error_message"
          type="error"
          :closable="false"
          show-icon
        />

        <section class="email-detail__section">
          <h4><el-icon><Paperclip /></el-icon>附件清单</h4>
          <el-table v-if="detail.attachments.length" :data="detail.attachments" size="small">
            <el-table-column prop="original_name" label="附件名称" min-width="260" show-overflow-tooltip />
            <el-table-column prop="file_type" label="格式" width="90">
              <template #default="{ row }">{{ row.file_type || '—' }}</template>
            </el-table-column>
            <el-table-column label="解析状态" width="120">
              <template #default="{ row }"><StatusTag :status="row.parse_status" /></template>
            </el-table-column>
            <el-table-column label="说明" min-width="180" show-overflow-tooltip>
              <template #default="{ row }">{{ row.error_message || '—' }}</template>
            </el-table-column>
          </el-table>
          <el-empty v-else description="该邮件没有附件" :image-size="50" />
        </section>

        <section class="email-detail__section">
          <h4><el-icon><Message /></el-icon>邮件正文</h4>
          <pre v-if="detail.body_text" class="email-detail__body">{{ detail.body_text }}</pre>
          <el-empty v-else description="邮件正文为空或未归档" :image-size="50" />
          <el-alert
            v-if="detail.body_truncated"
            title="正文较长，页面仅展示前 10 万字符；可下载 EML 查看完整内容。"
            type="warning"
            :closable="false"
            show-icon
          />
        </section>
      </template>
    </div>

    <template #footer>
      <el-button @click="visible = false">关闭</el-button>
      <el-button
        v-if="detail?.original_available"
        type="primary"
        :icon="Download"
        :loading="downloading"
        @click="downloadOriginal"
      >下载原始 EML</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.email-detail { min-height: 220px; display: grid; gap: 18px; }
.email-detail__title { display: flex; align-items: center; gap: 13px; }
.email-detail__title > div { min-width: 0; flex: 1; }
.email-detail__title h3 { margin: 0; overflow-wrap: anywhere; color: var(--ink-900); font-size: 17px; line-height: 1.5; }
.email-detail__title p { margin: 4px 0 0; color: var(--ink-600); font-size: 12px; }
.email-detail__icon { width: 42px; height: 42px; flex: 0 0 42px; display: grid; place-items: center; border-radius: 12px; color: var(--teal-600); background: var(--teal-100); font-size: 20px; }
.email-detail__meta { margin-top: 2px; }
.email-detail__section { display: grid; gap: 10px; }
.email-detail__section h4 { margin: 0; display: flex; align-items: center; gap: 7px; color: #385561; font-size: 13px; }
.email-detail__body { max-height: 360px; margin: 0; padding: 16px; overflow: auto; border: 1px solid #e2eae9; border-radius: 10px; color: #304b57; background: #f7faf9; font: 12px/1.75 "SFMono-Regular", Consolas, "Microsoft YaHei", monospace; white-space: pre-wrap; overflow-wrap: anywhere; }
</style>
