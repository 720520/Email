<script setup lang="ts">
import { DocumentChecked, UploadFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import type { UploadFile, UploadFiles, UploadInstance, UploadRawFile } from 'element-plus'
import { computed, onMounted, ref } from 'vue'

import PageHeader from '@/components/PageHeader.vue'
import StatusTag from '@/components/StatusTag.vue'
import { apiErrorMessage } from '@/platform/api/http'

import { getMailboxes, uploadForReparse } from '../api'
import type { MailboxAccount, ManualReparseResult } from '../api/types'

const upload = ref<UploadInstance>()
const selectedFile = ref<UploadRawFile>()
const sourceAttachmentId = ref<number>()
const mailboxAccountId = ref<number>()
const mailboxes = ref<MailboxAccount[]>([])
const submitting = ref(false)
const result = ref<ManualReparseResult>()
const canSubmit = computed(
  () => Boolean(selectedFile.value && mailboxAccountId.value) && !submitting.value,
)

function onChange(file: UploadFile, files: UploadFiles) {
  selectedFile.value = file.raw
  result.value = undefined
  if (files.length > 1) upload.value?.handleRemove(files[0]!)
}

function onRemove() {
  selectedFile.value = undefined
  result.value = undefined
}

async function submit() {
  if (!selectedFile.value) return
  submitting.value = true
  try {
    result.value = await uploadForReparse(
      selectedFile.value,
      sourceAttachmentId.value,
      mailboxAccountId.value,
    )
    ElMessage.success('文件重新解析完成')
    upload.value?.clearFiles()
    selectedFile.value = undefined
  } catch (error) {
    ElMessage.error(apiErrorMessage(error))
  } finally {
    submitting.value = false
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
  } catch (error) {
    ElMessage.error(apiErrorMessage(error))
  }
})
</script>

<template>
  <div>
    <PageHeader
      eyebrow="Manual Operations"
      title="人工处理"
      description="重新上传失败附件并触发同一套识别、标准化和入库流程，原始文件与操作记录不会被覆盖。"
    />

    <section class="operations-grid">
      <article class="panel reparse-panel">
        <div class="panel-header"><div><h2>上传 Excel 重新解析</h2><p>支持 .xls / .xlsx，单次只处理一个文件</p></div></div>
        <div class="panel-body">
          <el-upload
            ref="upload"
            drag
            action="#"
            :auto-upload="false"
            :limit="1"
            accept=".xls,.xlsx"
            :on-change="onChange"
            :on-remove="onRemove"
          >
            <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
            <div class="el-upload__text">拖放文件到这里，或 <em>点击选择</em></div>
            <template #tip><div class="el-upload__tip">文件将归档到当前日期目录；数据库仍按“产品代码 + 日期”防重复。</div></template>
          </el-upload>
          <el-form label-position="top" class="source-link-form">
            <el-form-item label="归属邮箱">
              <el-select v-model="mailboxAccountId" placeholder="选择该附件所属邮箱" style="width: 320px">
                <el-option v-for="item in mailboxes" :key="item.id" :label="`${item.display_name} · ${item.username}`" :value="item.id" />
              </el-select>
              <span class="form-help">人工上传的数据、归档和审计记录都将绑定到所选邮箱。</span>
            </el-form-item>
            <el-form-item label="关联原附件 ID（可选）">
              <el-input-number v-model="sourceAttachmentId" :min="1" :controls="false" placeholder="用于审计追溯" style="width: 220px" />
              <span class="form-help">如果来自某条失败附件，可填写其 ID 建立来源关联。</span>
            </el-form-item>
          </el-form>
          <el-button type="primary" size="large" :disabled="!canSubmit" :loading="submitting" @click="submit">开始重新解析</el-button>
        </div>
      </article>

      <aside class="panel audit-panel">
        <div class="panel-header"><div><h2>处理原则</h2><p>面向真实运营留痕设计</p></div></div>
        <div class="panel-body audit-rules">
          <div><span>1</span><p><strong>原始文件保留</strong><small>上传文件以日期分层归档，不修改已归档附件。</small></p></div>
          <div><span>2</span><p><strong>历史数据不覆盖</strong><small>已存在的产品代码与净值日期会记录为重复。</small></p></div>
          <div><span>3</span><p><strong>全过程可追溯</strong><small>每次人工操作单独创建邮件、附件和任务审计记录。</small></p></div>
        </div>
      </aside>
    </section>

    <section v-if="result" class="panel result-panel">
      <div class="result-panel__icon"><el-icon><DocumentChecked /></el-icon></div>
      <div><small>本次处理结果</small><h2>重新解析已完成</h2><p class="source-text">{{ result.source_file }}</p></div>
      <div class="result-metrics"><span><strong class="numeric">{{ result.inserted_count }}</strong><small>新增净值</small></span><span><strong class="numeric">{{ result.duplicate_count }}</strong><small>重复数据</small></span><span><strong class="numeric">{{ result.exception_count }}</strong><small>异常记录</small></span></div>
      <StatusTag :status="result.status" />
    </section>
  </div>
</template>
