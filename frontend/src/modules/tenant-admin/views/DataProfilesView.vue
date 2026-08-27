<script setup lang="ts">
import dayjs from 'dayjs'
import { ElMessage } from 'element-plus'
import { computed, onMounted, reactive, ref } from 'vue'

import PageHeader from '@/components/PageHeader.vue'
import { apiErrorMessage } from '@/platform/api/http'
import { useAuthStore } from '@/platform/auth/auth.store'

import {
  assignProductMaterial,
  downloadGovernanceDocument,
  getCompanyProfile,
  getProductMaterialAttributions,
  getProductProfile,
  getProductProfiles,
} from '../api'
import type {
  FieldValueItem,
  ProductMaterialAttributionItem,
  ProductProfileSummary,
  ProfileDetail,
  SourceDocumentItem,
} from '../api/types'

const auth = useAuthStore()
const loading = ref(false)
const assigning = ref<number>()
const activeTab = ref('company')
const company = ref<ProfileDetail>()
const products = ref<ProductProfileSummary[]>([])
const selectedProductId = ref<number>()
const product = ref<ProfileDetail>()
const pending = ref<ProductMaterialAttributionItem[]>([])
const assignments = reactive<Record<number, number | undefined>>({})
const isAdmin = computed(() => auth.user?.role === 'admin')

function latestFact(profile: ProfileDetail | undefined, definitionId: number): FieldValueItem | undefined {
  return profile?.facts.find((item) => item.field_definition_id === definitionId)
}

function displayValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—'
  return typeof value === 'object' ? JSON.stringify(value) : String(value)
}

function sensitivityLabel(value: string): string {
  return { normal: '普通', sensitive: '敏感', highly_sensitive: '高度敏感' }[value] ?? value
}

function formatSize(size: number): string {
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}

async function loadProduct(entityId: number | undefined) {
  product.value = undefined
  if (!entityId) return
  try {
    product.value = await getProductProfile(entityId)
  } catch (error) {
    ElMessage.error(apiErrorMessage(error))
  }
}

async function load() {
  loading.value = true
  try {
    const [companyProfile, productProfiles] = await Promise.all([
      getCompanyProfile(),
      getProductProfiles(),
    ])
    company.value = companyProfile
    products.value = productProfiles
    selectedProductId.value = productProfiles[0]?.entity.id
    await Promise.all([
      loadProduct(selectedProductId.value),
      isAdmin.value ? loadPending() : Promise.resolve(),
    ])
  } catch (error) {
    ElMessage.error(apiErrorMessage(error))
  } finally {
    loading.value = false
  }
}

async function loadPending() {
  pending.value = await getProductMaterialAttributions()
}

async function assign(item: ProductMaterialAttributionItem) {
  const entityId = assignments[item.id]
  if (!entityId) {
    ElMessage.warning('请选择材料归属的产品')
    return
  }
  assigning.value = item.id
  try {
    await assignProductMaterial(item.id, entityId)
    ElMessage.success('材料已归入产品资料，原始文件版本保持不变')
    await Promise.all([loadPending(), loadProduct(selectedProductId.value)])
  } catch (error) {
    ElMessage.error(apiErrorMessage(error))
  } finally {
    assigning.value = undefined
  }
}

async function download(document: SourceDocumentItem) {
  try {
    const blob = await downloadGovernanceDocument(document.id)
    const href = URL.createObjectURL(blob)
    const anchor = window.document.createElement('a')
    anchor.href = href
    anchor.download = document.original_name
    anchor.click()
    URL.revokeObjectURL(href)
  } catch (error) {
    ElMessage.error(apiErrorMessage(error))
  }
}

onMounted(load)
</script>

<template>
  <div v-loading="loading">
    <PageHeader
      eyebrow="Governed Profiles"
      title="资料中心"
      description="公司资料与产品资料按独立主体管理；历史备案资料已保留原文件哈希和版本，并按用途迁入对应资料域。"
    />

    <el-alert
      title="旧备案资料库已切换为只读兼容接口；新增事实和文件统一通过资料主体、来源与权限底座管理。"
      type="info"
      :closable="false"
      show-icon
      class="notice"
    />

    <el-tabs v-model="activeTab" class="profile-tabs">
      <el-tab-pane label="公司资料" name="company">
        <section v-if="company" class="profile-grid">
          <el-card shadow="never">
            <template #header><strong>{{ company.entity.display_name }}</strong></template>
            <el-table :data="company.field_definitions" empty-text="暂无公司资料字段">
              <el-table-column prop="category" label="分类" width="140" />
              <el-table-column prop="label" label="资料项" min-width="180" />
              <el-table-column label="当前值" min-width="240">
                <template #default="{ row }">
                  {{ displayValue(latestFact(company, row.id)?.value) }}
                </template>
              </el-table-column>
              <el-table-column label="来源" width="130">
                <template #default="{ row }">
                  {{ latestFact(company, row.id)?.source_type ?? '—' }}
                </template>
              </el-table-column>
            </el-table>
          </el-card>
          <el-card shadow="never">
            <template #header><strong>公司文件</strong></template>
            <el-table :data="company.documents" empty-text="暂无公司文件">
              <el-table-column prop="original_name" label="文件" min-width="220" />
              <el-table-column label="版本" width="80"><template #default="{ row }">v{{ row.version }}</template></el-table-column>
              <el-table-column label="敏感级别" width="110"><template #default="{ row }">{{ sensitivityLabel(row.sensitivity) }}</template></el-table-column>
              <el-table-column label="大小" width="100"><template #default="{ row }">{{ formatSize(row.file_size) }}</template></el-table-column>
              <el-table-column label="操作" width="90"><template #default="{ row }"><el-button link type="primary" @click="download(row)">下载</el-button></template></el-table-column>
            </el-table>
          </el-card>
        </section>
      </el-tab-pane>

      <el-tab-pane label="产品资料" name="products">
        <el-card shadow="never">
          <div class="product-picker">
            <span>选择产品</span>
            <el-select v-model="selectedProductId" filterable placeholder="请选择产品" @change="loadProduct">
              <el-option v-for="item in products" :key="item.entity.id" :label="`${item.product_name}（${item.product_code}）`" :value="item.entity.id" />
            </el-select>
          </div>
          <template v-if="product">
            <el-descriptions :column="2" border class="product-summary">
              <el-descriptions-item label="产品主体">{{ product.entity.display_name }}</el-descriptions-item>
              <el-descriptions-item label="主体编码">{{ product.entity.external_code }}</el-descriptions-item>
            </el-descriptions>
            <el-table :data="product.documents" empty-text="该产品暂无资料文件">
              <el-table-column prop="original_name" label="文件" min-width="240" />
              <el-table-column prop="document_type" label="资料类型" width="160" />
              <el-table-column label="版本" width="80"><template #default="{ row }">v{{ row.version }}</template></el-table-column>
              <el-table-column label="归档时间" width="180"><template #default="{ row }">{{ dayjs(row.create_time).format('YYYY-MM-DD HH:mm') }}</template></el-table-column>
              <el-table-column label="操作" width="90"><template #default="{ row }"><el-button link type="primary" @click="download(row)">下载</el-button></template></el-table-column>
            </el-table>
          </template>
          <el-empty v-else description="暂无产品资料主体" />
        </el-card>
      </el-tab-pane>

      <el-tab-pane v-if="isAdmin" :label="`待归属材料（${pending.length}）`" name="attribution">
        <el-card shadow="never">
          <el-table :data="pending" empty-text="没有待归属的历史产品材料">
            <el-table-column prop="document.original_name" label="历史材料" min-width="220" />
            <el-table-column prop="document.document_type" label="原资料项" width="170" />
            <el-table-column label="文件标识" min-width="180"><template #default="{ row }"><code>{{ row.document.content_hash.slice(0, 12) }}…</code></template></el-table-column>
            <el-table-column label="归属产品" min-width="260">
              <template #default="{ row }">
                <el-select v-model="assignments[row.id]" filterable placeholder="选择产品">
                  <el-option v-for="item in products" :key="item.entity.id" :label="`${item.product_name}（${item.product_code}）`" :value="item.entity.id" />
                </el-select>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="100"><template #default="{ row }"><el-button type="primary" link :loading="assigning === row.id" @click="assign(row)">确认归属</el-button></template></el-table-column>
          </el-table>
        </el-card>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped>
.notice { margin-bottom: 18px; }
.profile-tabs { min-height: 420px; }
.profile-grid { display: grid; gap: 18px; }
.product-picker { display: flex; align-items: center; gap: 14px; margin-bottom: 18px; }
.product-picker .el-select { width: min(520px, 100%); }
.product-summary { margin-bottom: 18px; }
code { color: var(--el-text-color-secondary); }
</style>
