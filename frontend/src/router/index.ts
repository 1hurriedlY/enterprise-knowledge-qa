import { createRouter, createWebHistory } from 'vue-router'

import AdminView from '@/views/AdminView.vue'
import AuthView from '@/views/AuthView.vue'
import ChatView from '@/views/ChatView.vue'
import DocumentsView from '@/views/DocumentsView.vue'
import SettingsView from '@/views/SettingsView.vue'
import { hasSessionApiKey } from '@/services/session'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: { name: 'chat' } },
    {
      path: '/auth',
      name: 'auth',
      component: AuthView,
      meta: { title: '登录与注册' },
    },
    {
      path: '/chat',
      name: 'chat',
      component: ChatView,
      meta: { title: '智能对话' },
    },
    {
      path: '/documents',
      name: 'documents',
      component: DocumentsView,
      meta: { title: '知识文档' },
    },
    {
      path: '/admin',
      name: 'admin',
      component: AdminView,
      meta: { title: '管理后台' },
    },
    {
      path: '/settings',
      name: 'settings',
      component: SettingsView,
      meta: { title: '设置与 API Key' },
    },
  ],
})

router.beforeEach((to) => {
  const authenticated = hasSessionApiKey()
  if (to.name === 'auth') {
    return authenticated ? { name: 'chat' } : true
  }
  if (!authenticated) {
    return { name: 'auth', query: { redirect: to.fullPath } }
  }
  return true
})

export default router
