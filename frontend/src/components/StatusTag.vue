<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ status: string }>()

const labels: Record<string, string> = {
  discovered: '已发现',
  archived: '已归档',
  processing: '处理中',
  success: '成功',
  partial_success: '部分成功',
  failed: '失败',
  skipped: '已跳过',
  pending: '待处理',
  parsing: '解析中',
  duplicate: '重复',
  unsupported: '不支持',
  open: '待处理',
  resolved: '已解决',
  ignored: '已忽略',
}

const tagType = computed(() => {
  if (['success', 'resolved'].includes(props.status)) return 'success'
  if (['failed', 'open'].includes(props.status)) return 'danger'
  if (['partial_success', 'duplicate', 'ignored'].includes(props.status)) return 'warning'
  return 'info'
})
</script>

<template>
  <el-tag :type="tagType" effect="light" round>{{ labels[status] ?? status }}</el-tag>
</template>
