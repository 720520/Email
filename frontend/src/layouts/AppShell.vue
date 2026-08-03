<script setup lang="ts">
import { ArrowDown, Expand, Fold, Grid, SwitchButton } from '@element-plus/icons-vue'
import dayjs from 'dayjs'
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { businessModules } from '@/modules'
import { useAuthStore } from '@/platform/auth/auth.store'
import type { UserRole } from '@/platform/api/types'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const collapsed = ref(false)
const mobileOpen = ref(false)
const roleRank: Record<UserRole, number> = { viewer: 1, operator: 2, admin: 3 }
const currentModule = computed(() =>
  businessModules.find((module) =>
    module.navigation.some((item) => item.path === route.path),
  ) ?? businessModules[0],
)

const visibleModules = computed(() =>
  businessModules.map((module) => ({
    ...module,
    navigation: module.navigation.filter((item) => {
      if (!item.permission || !auth.user) return true
      return roleRank[auth.user.role] >= roleRank[item.permission]
    }),
  })),
)

const roleLabel = computed(() => ({ admin: '管理员', operator: '运营人员', viewer: '只读用户' })[auth.user?.role ?? 'viewer'])

async function signOut() {
  await auth.logout()
  await router.replace('/login')
}

function navigate(path: string) {
  mobileOpen.value = false
  void router.push(path)
}
</script>

<template>
  <div class="app-shell" :class="{ 'is-collapsed': collapsed }">
    <aside class="sidebar desktop-sidebar">
      <div class="brand" @click="navigate('/overview')">
        <span class="brand__mark"><el-icon><Grid /></el-icon></span>
        <span v-if="!collapsed" class="brand__copy">
          <strong>运营工作台</strong>
          <small>Operations Hub</small>
        </span>
      </div>

      <nav class="module-navigation" aria-label="业务导航">
        <section v-for="module in visibleModules" :key="module.id" class="nav-module">
          <div v-if="!collapsed" class="nav-module__header">
            <span>{{ module.title }}</span>
            <small>{{ module.description }}</small>
          </div>
          <button
            v-for="item in module.navigation"
            :key="item.path"
            class="nav-item"
            :class="{ active: route.path === item.path }"
            :title="collapsed ? item.title : undefined"
            @click="navigate(item.path)"
          >
            <el-icon><component :is="item.icon" /></el-icon>
            <span v-if="!collapsed">{{ item.title }}</span>
          </button>
        </section>
      </nav>

      <button class="collapse-button" @click="collapsed = !collapsed">
        <el-icon><component :is="collapsed ? Expand : Fold" /></el-icon>
        <span v-if="!collapsed">收起导航</span>
      </button>
    </aside>

    <el-drawer v-model="mobileOpen" direction="ltr" size="280px" :with-header="false">
      <div class="mobile-menu">
        <div class="brand">
          <span class="brand__mark"><el-icon><Grid /></el-icon></span>
          <span class="brand__copy"><strong>运营工作台</strong><small>Operations Hub</small></span>
        </div>
        <section v-for="module in visibleModules" :key="module.id" class="nav-module">
          <div class="nav-module__header"><span>{{ module.title }}</span><small>{{ module.description }}</small></div>
          <button v-for="item in module.navigation" :key="item.path" class="nav-item" @click="navigate(item.path)">
            <el-icon><component :is="item.icon" /></el-icon><span>{{ item.title }}</span>
          </button>
        </section>
      </div>
    </el-drawer>

    <main class="main-area">
      <header class="topbar">
        <button class="mobile-menu-button" aria-label="打开导航" @click="mobileOpen = true">
          <el-icon><Expand /></el-icon>
        </button>
        <div class="workspace-indicator">
          <span class="workspace-indicator__dot"></span>
          <div><small>当前业务模块</small><strong>{{ currentModule?.title ?? '运营工作台' }}</strong></div>
        </div>
        <div class="topbar__right">
          <span class="business-date">{{ dayjs().format('YYYY年MM月DD日') }}</span>
          <el-dropdown trigger="click">
            <button class="user-menu">
              <span class="user-avatar">{{ auth.user?.username.slice(0, 1).toUpperCase() }}</span>
              <span class="user-copy"><strong>{{ auth.user?.username }}</strong><small>{{ roleLabel }}</small></span>
              <el-icon><ArrowDown /></el-icon>
            </button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item :icon="SwitchButton" @click="signOut">退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </header>
      <section class="content-area">
        <router-view v-slot="{ Component }">
          <transition name="page" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </section>
    </main>
  </div>
</template>
