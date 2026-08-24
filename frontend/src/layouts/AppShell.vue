<script setup lang="ts">
import { ArrowDown, Check, Expand, Fold, OfficeBuilding, Search, SwitchButton } from '@element-plus/icons-vue'
import dayjs from 'dayjs'
import { ElMessage } from 'element-plus'
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { businessModules } from '@/modules'
import { apiErrorMessage } from '@/platform/api/http'
import { useAuthStore } from '@/platform/auth/auth.store'
import type { UserRole } from '@/platform/api/types'
import type { ModuleNavigationItem } from '@/platform/modules/types'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const collapsed = ref(false)
const mobileOpen = ref(false)
const commandVisible = ref(false)
const commandQuery = ref('')
const roleRank: Record<UserRole, number> = { viewer: 1, operator: 2, admin: 3 }

function navigationMatches(item: ModuleNavigationItem, path: string): boolean {
  return item.path === path || (item.children?.some((child) => navigationMatches(child, path)) ?? false)
}

function activeGroupPaths(path: string): string[] {
  return businessModules.flatMap((module) =>
    module.navigation
      .filter((item) => item.children?.length && navigationMatches(item, path))
      .map((item) => item.path),
  )
}

const expandedGroups = ref<Set<string>>(new Set(activeGroupPaths(route.path)))

const currentModule = computed(() =>
  businessModules.find((module) =>
    module.navigation.some((item) => navigationMatches(item, route.path)),
  ) ?? businessModules[0],
)

function canAccessNavigation(item: ModuleNavigationItem): boolean {
  if (!item.permission || !auth.user) return true
  if (auth.user.is_platform_admin) return true
  return roleRank[auth.user.role] >= roleRank[item.permission]
}

function filterNavigation(items: ModuleNavigationItem[]): ModuleNavigationItem[] {
  return items
    .filter(canAccessNavigation)
    .map((item) => ({ ...item, children: item.children ? filterNavigation(item.children) : undefined }))
    .filter((item) => !item.children || item.children.length > 0)
}

const visibleModules = computed(() =>
  businessModules.map((module) => ({
    ...module,
    navigation: filterNavigation(module.navigation),
  })),
)

const commandItems = computed(() => visibleModules.value.flatMap((module) =>
  module.navigation.flatMap((item) => item.children?.length ? item.children : [item]),
).filter((item) => !commandQuery.value.trim() || item.title.includes(commandQuery.value.trim())))

watch(() => route.path, (path) => {
  const next = new Set(expandedGroups.value)
  activeGroupPaths(path).forEach((groupPath) => next.add(groupPath))
  expandedGroups.value = next
})

const roleLabel = computed(() => ({ admin: '管理员', operator: '运营人员', viewer: '只读用户' })[auth.user?.role ?? 'viewer'])
const currentTenantName = computed(() => auth.user?.tenant_name ?? '未选择租户')

async function switchTenant(command: string | number) {
  const tenantId = Number(command)
  if (!tenantId || tenantId === auth.user?.tenant_id) return
  try {
    await auth.switchTenant(tenantId)
    ElMessage.success(`已切换到 ${auth.user?.tenant_name}`)
    await router.replace('/overview')
    window.location.reload()
  } catch (error) {
    ElMessage.error(apiErrorMessage(error))
  }
}

async function signOut() {
  await auth.logout()
  await router.replace('/login')
}

function navigate(path: string) {
  mobileOpen.value = false
  commandVisible.value = false
  commandQuery.value = ''
  void router.push(path)
}

function isGroupExpanded(item: ModuleNavigationItem): boolean {
  return expandedGroups.value.has(item.path)
}

function toggleGroup(item: ModuleNavigationItem) {
  if (collapsed.value) collapsed.value = false
  const next = new Set(expandedGroups.value)
  if (isGroupExpanded(item)) next.delete(item.path)
  else next.add(item.path)
  expandedGroups.value = next
}

function handleCommandShortcut(event: KeyboardEvent) {
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
    event.preventDefault()
    commandVisible.value = true
  }
}

onMounted(() => window.addEventListener('keydown', handleCommandShortcut))
onUnmounted(() => window.removeEventListener('keydown', handleCommandShortcut))
</script>

<template>
  <div class="app-shell" :class="{ 'is-collapsed': collapsed }">
    <aside class="sidebar desktop-sidebar">
      <div class="brand" @click="navigate('/overview')">
        <span class="brand__mark">✣</span>
        <span v-if="!collapsed" class="brand__copy">
          <strong>Fundfolio</strong>
          <small>Operations atelier</small>
        </span>
      </div>

      <nav class="module-navigation" aria-label="业务导航">
        <section v-for="module in visibleModules" :key="module.id" class="nav-module">
          <div v-if="!collapsed" class="nav-module__header">
            <span>{{ module.title }}</span>
            <small>{{ module.description }}</small>
          </div>
          <template v-for="item in module.navigation" :key="item.path">
            <div v-if="item.children?.length" class="nav-group" :class="{ 'has-active-child': navigationMatches(item, route.path) }">
              <button
                class="nav-item nav-group__trigger"
                :title="collapsed ? item.title : undefined"
                :aria-expanded="isGroupExpanded(item)"
                @click="toggleGroup(item)"
              >
                <el-icon><component :is="item.icon" /></el-icon>
                <span v-if="!collapsed">{{ item.title }}</span>
                <el-icon v-if="!collapsed" class="nav-group__arrow" :class="{ 'is-open': isGroupExpanded(item) }"><ArrowDown /></el-icon>
              </button>
              <div v-if="!collapsed && isGroupExpanded(item)" class="nav-group__children">
                <button
                  v-for="child in item.children"
                  :key="child.path"
                  class="nav-item nav-item--child"
                  :class="{ active: route.path === child.path }"
                  @click="navigate(child.path)"
                >
                  <el-icon><component :is="child.icon" /></el-icon>
                  <span>{{ child.title }}</span>
                </button>
              </div>
            </div>
            <button
              v-else
              class="nav-item"
              :class="{ active: route.path === item.path }"
              :title="collapsed ? item.title : undefined"
              @click="navigate(item.path)"
            >
              <el-icon><component :is="item.icon" /></el-icon>
              <span v-if="!collapsed">{{ item.title }}</span>
            </button>
          </template>
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
          <span class="brand__mark">✣</span>
          <span class="brand__copy"><strong>Fundfolio</strong><small>Operations atelier</small></span>
        </div>
        <section v-for="module in visibleModules" :key="module.id" class="nav-module">
          <div class="nav-module__header"><span>{{ module.title }}</span><small>{{ module.description }}</small></div>
          <template v-for="item in module.navigation" :key="item.path">
            <div v-if="item.children?.length" class="nav-group has-active-child">
              <div class="nav-item nav-group__trigger nav-group__trigger--static">
                <el-icon><component :is="item.icon" /></el-icon><span>{{ item.title }}</span>
              </div>
              <div class="nav-group__children">
                <button
                  v-for="child in item.children"
                  :key="child.path"
                  class="nav-item nav-item--child"
                  :class="{ active: route.path === child.path }"
                  @click="navigate(child.path)"
                >
                  <el-icon><component :is="child.icon" /></el-icon><span>{{ child.title }}</span>
                </button>
              </div>
            </div>
            <button v-else class="nav-item" :class="{ active: route.path === item.path }" @click="navigate(item.path)">
              <el-icon><component :is="item.icon" /></el-icon><span>{{ item.title }}</span>
            </button>
          </template>
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
        <button class="command-trigger" @click="commandVisible = true">
          <el-icon><Search /></el-icon><span>搜索页面或执行命令</span><kbd>⌘ K</kbd>
        </button>
        <div class="topbar__right">
          <el-dropdown trigger="click" @command="switchTenant">
            <button class="tenant-switcher" :title="`当前租户：${currentTenantName}`">
              <el-icon><OfficeBuilding /></el-icon>
              <span><small>当前租户</small><strong>{{ currentTenantName }}</strong></span>
              <el-icon v-if="auth.tenants.length > 1"><ArrowDown /></el-icon>
            </button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item
                  v-for="tenant in auth.tenants"
                  :key="tenant.id"
                  :command="tenant.id"
                  :disabled="tenant.is_current"
                >
                  <el-icon v-if="tenant.is_current"><Check /></el-icon>
                  <span class="tenant-dropdown-item"><strong>{{ tenant.name }}</strong><small>{{ tenant.code }}</small></span>
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
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

    <el-dialog v-model="commandVisible" width="min(560px, 92vw)" class="command-dialog" :show-close="false" append-to-body>
      <el-input v-model="commandQuery" size="large" placeholder="搜索产品台账、邮件、净值或报表…" :prefix-icon="Search" autofocus />
      <div class="command-results">
        <button v-for="item in commandItems" :key="item.path" @click="navigate(item.path)">
          <span><el-icon><component :is="item.icon" /></el-icon>{{ item.title }}</span><small>{{ item.path }}</small>
        </button>
        <el-empty v-if="!commandItems.length" :image-size="54" description="没有匹配页面" />
      </div>
    </el-dialog>
  </div>
</template>
