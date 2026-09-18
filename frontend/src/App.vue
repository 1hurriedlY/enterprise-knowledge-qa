<script setup lang="ts">
import {
  ChatDotRound,
  Document,
  Setting,
  TrendCharts,
} from '@element-plus/icons-vue'
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()

const activeMenu = computed(() => route.name?.toString() ?? 'chat')

const navigate = (name: string) => {
  void router.push({ name })
}
</script>

<template>
  <el-container class="app-shell">
    <el-aside width="224px" class="sidebar">
      <div class="brand">
        <span class="brand-mark">AI</span>
        <span>企业知识库客服</span>
      </div>
      <el-menu class="nav-menu" :default-active="activeMenu" @select="navigate">
        <el-menu-item index="chat">
          <el-icon><ChatDotRound /></el-icon>
          <span>智能对话</span>
        </el-menu-item>
        <el-menu-item index="documents">
          <el-icon><Document /></el-icon>
          <span>知识文档</span>
        </el-menu-item>
        <el-menu-item index="admin">
          <el-icon><TrendCharts /></el-icon>
          <span>管理后台</span>
        </el-menu-item>
        <el-menu-item index="settings">
          <el-icon><Setting /></el-icon>
          <span>设置与 API Key</span>
        </el-menu-item>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header class="topbar">
        <span>{{ route.meta.title }}</span>
        <el-tag type="info" effect="plain">初级版</el-tag>
      </el-header>
      <el-main class="main-content">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>
