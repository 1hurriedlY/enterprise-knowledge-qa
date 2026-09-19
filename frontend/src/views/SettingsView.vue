<script setup lang="ts">
import { CircleCheck, CircleClose, RefreshRight } from '@element-plus/icons-vue'
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import {
  type CurrentUser,
  type DependencyStatus,
  type HealthResponse,
  getCurrentUser,
  getHealth,
  verifyApiKey,
} from '@/services/api'
import {
  clearSessionApiKey,
  getSessionApiKey,
  hasSessionApiKey,
  saveSessionApiKey,
} from '@/services/session'

type CheckState = 'idle' | 'loading' | 'success' | 'error'

const apiKeyInput = ref('')
const router = useRouter()
const apiKeySaved = ref(hasSessionApiKey())
const apiKeyState = ref<CheckState>('idle')
const userState = ref<CheckState>('idle')
const currentUser = ref<CurrentUser>()
const healthState = ref<CheckState>('idle')
const health = ref<HealthResponse>()

const healthTagType = computed(() => {
  if (healthState.value === 'error') return 'danger'
  if (healthState.value === 'loading') return 'warning'
  if (health.value?.status === 'degraded') return 'warning'
  return health.value?.status === 'ok' ? 'success' : 'info'
})

const healthLabel = computed(() => {
  if (healthState.value === 'loading') return '检查中'
  if (healthState.value === 'error') return '不可用'
  if (health.value?.status === 'degraded') return '部分降级'
  if (health.value?.status === 'ok') return '运行正常'
  return '尚未检查'
})

const dependencyLabel: Record<
  keyof Pick<HealthResponse, 'database' | 'vector_db' | 'redis' | 'llm'>,
  string
> = {
  database: 'PostgreSQL',
  vector_db: 'Qdrant 向量库',
  redis: 'Redis 队列',
  llm: 'LLM 配置',
}

const dependencies = computed(() =>
  health.value
    ? (Object.keys(dependencyLabel) as Array<keyof typeof dependencyLabel>).map(
        (key) => ({
          label: dependencyLabel[key],
          status: health.value?.[key] as DependencyStatus,
        }),
      )
    : [],
)

const checkHealth = async () => {
  healthState.value = 'loading'
  try {
    health.value = await getHealth()
    healthState.value = 'success'
  } catch {
    health.value = undefined
    healthState.value = 'error'
  }
}

const saveApiKey = () => {
  try {
    saveSessionApiKey(apiKeyInput.value)
    apiKeyInput.value = ''
    apiKeySaved.value = true
    apiKeyState.value = 'idle'
    void loadCurrentUser(getSessionApiKey())
  } catch {
    apiKeyState.value = 'error'
  }
}

const testApiKey = async () => {
  const apiKey = apiKeyInput.value.trim() || getSessionApiKey()
  if (!apiKey) {
    apiKeyState.value = 'error'
    return
  }

  apiKeyState.value = 'loading'
  try {
    await verifyApiKey(apiKey)
    await loadCurrentUser(apiKey)
    apiKeyState.value = 'success'
  } catch {
    apiKeyState.value = 'error'
  }
}

const clearApiKey = () => {
  clearSessionApiKey()
  apiKeyInput.value = ''
  apiKeySaved.value = false
  apiKeyState.value = 'idle'
  currentUser.value = undefined
  userState.value = 'idle'
  void router.push({ name: 'auth', query: { redirect: '/chat' } })
}

const loadCurrentUser = async (apiKey: string | undefined) => {
  if (!apiKey) {
    currentUser.value = undefined
    userState.value = 'idle'
    return
  }
  userState.value = 'loading'
  try {
    currentUser.value = await getCurrentUser(apiKey)
    userState.value = 'success'
  } catch {
    currentUser.value = undefined
    userState.value = 'error'
  }
}

onMounted(() => {
  void checkHealth()
  void loadCurrentUser(getSessionApiKey())
})
</script>

<template>
  <section class="settings-page">
    <div class="page-heading">
      <div>
        <h1>设置与 API Key</h1>
        <p>配置当前浏览器会话与后端 API 的连接，不会保存模型服务密钥。</p>
      </div>
    </div>

    <el-row :gutter="20">
      <el-col :xs="24" :lg="14">
        <el-card v-if="currentUser" shadow="never" class="identity-card">
          <template #header>
            <div class="card-header">
              <span>我的账号</span>
              <el-tag type="success" effect="plain">已登录</el-tag>
            </div>
          </template>
          <el-descriptions :column="1" border>
            <el-descriptions-item label="姓名">{{
              currentUser.name
            }}</el-descriptions-item>
            <el-descriptions-item label="邮箱">{{
              currentUser.email
            }}</el-descriptions-item>
            <el-descriptions-item label="角色">
              <el-tag
                :type="currentUser.role === 'admin' ? 'warning' : 'info'"
                effect="plain"
              >
                {{ currentUser.role === 'admin' ? '管理员' : '普通用户' }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="用户 ID">
              <span class="breakable-text">{{ currentUser.user_id }}</span>
            </el-descriptions-item>
          </el-descriptions>
        </el-card>
        <el-alert
          v-else-if="userState === 'error'"
          class="identity-alert"
          title="当前 API Key 无效或已失效，请重新登录或更换 API Key。"
          type="warning"
          :closable="false"
          show-icon
        />
        <el-card shadow="never">
          <template #header>
            <div class="card-header">
              <span>X-API-Key</span>
              <el-tag :type="apiKeySaved ? 'success' : 'info'" effect="plain">
                {{ apiKeySaved ? '本会话已保存' : '尚未设置' }}
              </el-tag>
            </div>
          </template>

          <el-alert
            title="API Key 只保存到当前浏览器会话中；关闭此标签页后将自动清除。"
            type="info"
            :closable="false"
            show-icon
          />

          <el-form class="api-key-form" @submit.prevent="saveApiKey">
            <el-form-item label="API Key" required>
              <el-input
                v-model="apiKeyInput"
                type="password"
                show-password
                autocomplete="off"
                placeholder="粘贴后端生成的 API Key"
              />
            </el-form-item>
            <div class="action-row">
              <el-button
                type="primary"
                :disabled="!apiKeyInput.trim()"
                @click="saveApiKey"
              >
                保存到本会话
              </el-button>
              <el-button
                :loading="apiKeyState === 'loading'"
                @click="testApiKey"
              >
                验证 API Key
              </el-button>
              <el-button
                v-if="apiKeySaved"
                type="danger"
                plain
                @click="clearApiKey"
              >
                退出登录
              </el-button>
            </div>
          </el-form>

          <el-alert
            v-if="apiKeyState === 'success'"
            class="result-alert"
            title="API Key 验证成功，服务端已识别当前用户。"
            type="success"
            :closable="false"
            show-icon
          />
          <el-alert
            v-else-if="apiKeyState === 'error'"
            class="result-alert"
            title="无法保存或验证 API Key。请确认长度至少为 16 位，并检查 Key 是否有效。"
            type="error"
            :closable="false"
            show-icon
          />
        </el-card>
      </el-col>

      <el-col :xs="24" :lg="10" class="health-column">
        <el-card shadow="never">
          <template #header>
            <div class="card-header">
              <span>后端健康状态</span>
              <el-button
                text
                :loading="healthState === 'loading'"
                @click="checkHealth"
              >
                <el-icon><RefreshRight /></el-icon>
                刷新
              </el-button>
            </div>
          </template>

          <div class="health-summary">
            <el-icon
              :class="healthState === 'error' ? 'is-error' : 'is-ok'"
              :size="28"
            >
              <CircleClose v-if="healthState === 'error'" />
              <CircleCheck v-else />
            </el-icon>
            <div>
              <strong>后端服务</strong>
              <el-tag :type="healthTagType" effect="plain">{{
                healthLabel
              }}</el-tag>
            </div>
          </div>

          <el-descriptions
            v-if="dependencies.length"
            :column="1"
            border
            class="health-details"
          >
            <el-descriptions-item
              v-for="dependency in dependencies"
              :key="dependency.label"
              :label="dependency.label"
            >
              <el-tag
                :type="dependency.status === 'ok' ? 'success' : 'danger'"
                effect="plain"
              >
                {{ dependency.status === 'ok' ? '正常' : '异常' }}
              </el-tag>
            </el-descriptions-item>
          </el-descriptions>
          <el-alert
            v-else-if="healthState === 'error'"
            title="无法连接后端。请确认 Docker Compose 服务已启动，并检查 http://localhost:8000/health。"
            type="error"
            :closable="false"
            show-icon
          />
          <el-skeleton
            v-else-if="healthState === 'loading'"
            :rows="4"
            animated
          />
        </el-card>
      </el-col>
    </el-row>
  </section>
</template>
