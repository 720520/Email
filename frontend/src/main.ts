import 'element-plus/dist/index.css'
import '@/styles/index.css'

import ElementPlus from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import { createPinia } from 'pinia'
import { createApp } from 'vue'

import App from './App.vue'
import { setUnauthorizedHandler } from './platform/api/http'
import { useAuthStore } from './platform/auth/auth.store'
import { router } from './router'

const pinia = createPinia()
setUnauthorizedHandler(async () => {
  useAuthStore(pinia).clearSession()
  if (router.currentRoute.value.name !== 'login') {
    await router.replace({
      name: 'login',
      query: { redirect: router.currentRoute.value.fullPath },
    })
  }
})

createApp(App).use(pinia).use(router).use(ElementPlus, { locale: zhCn }).mount('#app')
