<script setup lang="ts">
import { Lock, MessageBox, TrendCharts, User } from '@element-plus/icons-vue'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { apiErrorMessage } from '@/platform/api/http'
import { useAuthStore } from '@/platform/auth/auth.store'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const formRef = ref<FormInstance>()
const loading = ref(false)
const form = reactive({ username: '', password: '' })
const rules: FormRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

async function submit() {
  if (!(await formRef.value?.validate().catch(() => false))) return
  loading.value = true
  try {
    await auth.login(form.username, form.password)
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/overview'
    await router.replace(redirect)
  } catch (error) {
    ElMessage.error(apiErrorMessage(error))
  } finally {
    loading.value = false
  }
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
          <div><el-icon><Lock /></el-icon><span><strong>全流程审计</strong><small>重复保护、异常定位与人工复核</small></span></div>
        </div>
      </div>
      <div class="login-story__footer">可扩展运营中台 · 基金运营模块</div>
    </section>

    <section class="login-form-panel">
      <div class="login-form-card">
        <div class="login-form-card__header">
          <p>欢迎回来</p>
          <h2>登录运营工作台</h2>
          <span>使用本地管理员分配的账号登录</span>
        </div>
        <el-form ref="formRef" :model="form" :rules="rules" label-position="top" @keyup.enter="submit">
          <el-form-item label="用户名" prop="username">
            <el-input v-model="form.username" size="large" :prefix-icon="User" autocomplete="username" placeholder="请输入用户名" />
          </el-form-item>
          <el-form-item label="密码" prop="password">
            <el-input v-model="form.password" size="large" :prefix-icon="Lock" type="password" show-password autocomplete="current-password" placeholder="请输入密码" />
          </el-form-item>
          <el-button type="primary" size="large" class="login-submit" :loading="loading" @click="submit">进入工作台</el-button>
        </el-form>
        <p class="login-security-note"><span></span>账号验证和数据均保留在本地环境</p>
      </div>
    </section>
  </main>
</template>
