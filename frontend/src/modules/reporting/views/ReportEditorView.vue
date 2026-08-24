<script setup lang="ts">
import { ArrowLeft, Download, Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { apiErrorMessage } from '@/platform/api/http'

import { createOnlyOfficeSession, downloadReport } from '../api'

type EditorInstance = { destroyEditor?: () => void }
type DocsApi = { DocEditor: new (id: string, config: Record<string, unknown>) => EditorInstance }

declare global {
  interface Window { DocsAPI?: DocsApi }
}

const route = useRoute()
const router = useRouter()
const loading = ref(false)
const errorMessage = ref('')
const editorMode = ref<'edit' | 'view'>('view')
const runId = Number(route.params.runId)
const embedded = route.query.embedded === '1'
let editor: EditorInstance | undefined
let loadedScript: HTMLScriptElement | undefined

function loadApiScript(url: string): Promise<void> {
  if (window.DocsAPI) return Promise.resolve()
  return new Promise((resolve, reject) => {
    const script = document.createElement('script')
    script.src = url
    script.async = true
    script.onload = () => window.DocsAPI ? resolve() : reject(new Error('OnlyOffice API 加载失败'))
    script.onerror = () => reject(new Error('OnlyOffice Document Server 无法访问'))
    document.head.appendChild(script)
    loadedScript = script
  })
}

async function openEditor() {
  if (!Number.isInteger(runId) || runId <= 0) {
    errorMessage.value = '报表编号无效'
    return
  }
  loading.value = true
  errorMessage.value = ''
  editor?.destroyEditor?.()
  try {
    const session = await createOnlyOfficeSession(runId)
    await loadApiScript(session.api_url)
    if (!window.DocsAPI) throw new Error('OnlyOffice API 未就绪')
    const editorConfig = session.config.editorConfig as { mode?: string } | undefined
    editorMode.value = editorConfig?.mode === 'edit' ? 'edit' : 'view'
    const config = {
      ...session.config,
      events: {
        onAppReady: () => {
          requestAnimationFrame(() => window.dispatchEvent(new Event('resize')))
        },
      },
    }
    editor = new window.DocsAPI.DocEditor('onlyoffice-editor', config)
  } catch (error) {
    errorMessage.value = apiErrorMessage(error)
  } finally {
    loading.value = false
  }
}

async function downloadFallback() {
  try {
    const blob = await downloadReport(runId)
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `report-${runId}.pptx`
    link.click()
    URL.revokeObjectURL(url)
  } catch (error) {
    ElMessage.error(apiErrorMessage(error))
  }
}

onMounted(openEditor)
onUnmounted(() => {
  editor?.destroyEditor?.()
  loadedScript?.remove()
})
</script>

<template>
  <div class="editor-page" :class="{ 'editor-page--embedded': embedded }">
    <header v-if="!embedded" class="editor-toolbar">
      <div class="editor-toolbar__title">
        <el-button text :icon="ArrowLeft" @click="router.push('/reports')">返回报表中心</el-button>
        <span class="editor-toolbar__divider" />
        <div>
          <strong>{{ editorMode === 'edit' ? '报表在线编辑' : '报表在线预览' }}</strong>
          <small>ONLYOFFICE · {{ editorMode === 'edit' ? '自动保存并保留版本' : '只读模式' }}</small>
        </div>
      </div>
      <div class="editor-toolbar__actions">
        <el-button :icon="Download" @click="downloadFallback">下载 PPTX</el-button>
        <el-button :icon="Refresh" :loading="loading" @click="openEditor">重新加载</el-button>
      </div>
    </header>
    <section class="editor-shell" v-loading="loading">
      <el-result v-if="errorMessage" icon="warning" title="暂时无法在线预览" :sub-title="errorMessage">
        <template #extra><el-button type="primary" @click="downloadFallback">下载后查看</el-button></template>
      </el-result>
      <div v-show="!errorMessage" id="onlyoffice-editor" />
    </section>
  </div>
</template>

<style scoped>
.editor-page {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  background: #eef3f3;
}
.editor-page--embedded { position: absolute; }
.editor-toolbar {
  flex: 0 0 58px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 0 18px 0 10px;
  border-bottom: 1px solid var(--line);
  background: #fff;
}
.editor-toolbar__title,
.editor-toolbar__actions { display: flex; align-items: center; gap: 10px; }
.editor-toolbar__title > div { display: flex; flex-direction: column; line-height: 1.2; }
.editor-toolbar__title strong { color: #173b4d; font-size: 15px; }
.editor-toolbar__title small { margin-top: 3px; color: #82969e; font-size: 10px; letter-spacing: .08em; }
.editor-toolbar__divider { width: 1px; height: 26px; background: var(--line); }
.editor-shell {
  flex: 1 1 auto;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  background: #fff;
}
#onlyoffice-editor { width: 100%; height: 100%; }
@media (max-width: 640px) {
  .editor-toolbar { padding-right: 8px; }
  .editor-toolbar__title small,
  .editor-toolbar__divider,
  .editor-toolbar__actions :deep(.el-button span) { display: none; }
}
</style>
