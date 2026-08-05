<script setup lang="ts">
import { ArrowLeft, Lock, MessageBox, OfficeBuilding, TrendCharts, User } from '@element-plus/icons-vue'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { computed, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { apiErrorMessage } from '@/platform/api/http'
import type { TenantOption, UserRole } from '@/platform/api/types'
import { useAuthStore } from '@/platform/auth/auth.store'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const formRef = ref<FormInstance>()
const loading = ref(false)
const tenantOptions = ref<TenantOption[]>([])
const selectedTenantId = ref<number>()
const form = reactive({ username: '', password: '' })
const choosingTenant = computed(() => tenantOptions.value.length > 0)
const roleLabels: Record<UserRole, string> = {
  admin: '租户管理员',
  operator: '运营人员',
  viewer: '只读用户',
}
const rules: FormRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

async function submit() {
  if (!(await formRef.value?.validate().catch(() => false))) return
  if (choosingTenant.value && !selectedTenantId.value) {
    ElMessage.warning('请选择本次要进入的业务租户')
    return
  }
  loading.value = true
  try {
    const result = await auth.login(form.username, form.password, selectedTenantId.value)
    if (result.requires_tenant_selection) {
      tenantOptions.value = result.tenants
      selectedTenantId.value = result.tenants[0]?.id
      return
    }
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/overview'
    await router.replace(redirect)
  } catch (error) {
    ElMessage.error(apiErrorMessage(error))
  } finally {
    loading.value = false
  }
}

function editAccount() {
  tenantOptions.value = []
  selectedTenantId.value = undefined
  form.password = ''
}
</script>

<template>
  <main class="login-page">
    <section class="login-story">
      <div class="login-story__content">
        <div class="login-brand"><span>OP</span> 运营工作台</div>
        <p class="login-kicker">PRIVATE FUND OPERATIONS</p>
        <h1>把重复劳动交给系统，<br />把判断留给运营人员。</h1>
        <p class="login-lead">从托管邮件、净值归集到异常复核，所有原始证据和处理结果都可追溯。</p>
        <div class="login-capabilities">
          <div><el-icon><MessageBox /></el-icon><span><strong>邮件自动归档</strong><small>不改变已读状态，保留原始附件</small></span></div>
          <div><el-icon><TrendCharts /></el-icon><span><strong>净值统一口径</strong><small>多托管格式识别与历史曲线</small></span></div>
          <div><el-icon><Lock /></el-icon><span><strong>租户数据隔离</strong><small>会话绑定租户，关键操作全程留痕</small></span></div>
        </div>
      </div>
      <div class="login-story__footer">可扩展运营中台 · 基金运营模块</div>
    </section>

    <section class="login-form-panel">
      <div class="login-form-card">
        <div class="login-form-card__header">
          <p>{{ choosingTenant ? 'SELECT TENANT' : '欢迎回来' }}</p>
          <h2>{{ choosingTenant ? '选择业务租户' : '登录运营工作台' }}</h2>
          <span v-if="choosingTenant">账号 {{ form.username }} 属于多个租户，请确认本次工作范围</span>
          <span v-else>使用本地管理员分配的账号登录</span>
        </div>
        <el-form ref="formRef" :model="form" :rules="rules" label-position="top" @keyup.enter="submit">
          <template v-if="!choosingTenant">
            <el-form-item label="用户名" prop="username">
              <el-input v-model="form.username" size="large" :prefix-icon="User" autocomplete="username" placeholder="请输入用户名" />
            </el-form-item>
            <el-form-item label="密码" prop="password">
              <el-input v-model="form.password" size="large" :prefix-icon="Lock" type="password" show-password autocomplete="current-password" placeholder="请输入密码" />
            </el-form-item>
          </template>
          <template v-else>
            <el-form-item label="业务租户">
              <el-select v-model="selectedTenantId" size="large" class="login-tenant-select" placeholder="请选择租户">
                <el-option v-for="tenant in tenantOptions" :key="tenant.id" :value="tenant.id" :label="tenant.name">
                  <div class="tenant-option">
                    <el-icon><OfficeBuilding /></el-icon>
                    <span><strong>{{ tenant.name }}</strong><small>{{ tenant.code }} · {{ roleLabels[tenant.role] }}</small></span>
                  </div>
                </el-option>
              </el-select>
            </el-form-item>
            <el-button text :icon="ArrowLeft" class="login-back" @click="editAccount">返回修改账号</el-button>
          </template>
          <el-button type="primary" size="large" class="login-submit" :loading="loading" @click="submit">
            {{ choosingTenant ? '进入所选租户' : '继续' }}
          </el-button>
        </el-form>
        <p class="login-security-note"><span></span>一次会话只绑定一个租户，切换将重新校验权限</p>
      </div>
    </section>
  </main>
</template>
