<script setup lang="ts">
import { Lock, RefreshRight, Tickets } from '@element-plus/icons-vue'
import { computed, onMounted, ref } from 'vue'

import {
  type AdminConversation,
  type AdminMessage,
  type RequestLog,
  type ToolCallRecord,
  getAdminConversations,
  getAdminMessages,
  getRequestLogs,
  getToolCalls,
} from '@/services/admin'
import { getCurrentUser, type CurrentUserResponse } from '@/services/documents'
import { getSessionApiKey } from '@/services/session'

const currentUser = ref<CurrentUserResponse>()
const requestLogs = ref<RequestLog[]>([])
const toolCalls = ref<ToolCallRecord[]>([])
const conversations = ref<AdminConversation[]>([])
const selectedConversation = ref<AdminConversation>()
const messages = ref<AdminMessage[]>([])
const isLoading = ref(false)
const isMessagesLoading = ref(false)
const messageDialogVisible = ref(false)
const errorMessage = ref('')

const hasApiKey = computed(() => Boolean(getSessionApiKey()))
const isAdmin = computed(() => currentUser.value?.role === 'admin')

const formatDate = (value: string): string => {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('zh-CN', {
    dateStyle: 'medium',
    timeStyle: 'medium',
  }).format(date)
}

const shortId = (value: string | null): string =>
  value ? `${value.slice(0, 8)}…` : '—'

const statusType = (status: number): 'success' | 'warning' | 'danger' => {
  if (status < 300) return 'success'
  if (status < 500) return 'warning'
  return 'danger'
}

const toolStatusType = (
  status: ToolCallRecord['status'],
): 'info' | 'success' | 'warning' | 'danger' => {
  if (status === 'success') return 'success'
  if (status === 'failed') return 'danger'
  if (status === 'timeout') return 'warning'
  return 'info'
}

const toolStatusLabel = (status: ToolCallRecord['status']): string => {
  if (status === 'success') return '成功'
  if (status === 'failed') return '失败'
  if (status === 'timeout') return '超时'
  return '等待中'
}

const formatJson = (value: Record<string, unknown>): string =>
  JSON.stringify(value, null, 2)

const loadAdminData = async () => {
  const apiKey = getSessionApiKey()
  if (!apiKey) return

  isLoading.value = true
  errorMessage.value = ''
  try {
    const user = await getCurrentUser(apiKey)
    currentUser.value = user
    if (user.role !== 'admin') {
      requestLogs.value = []
      toolCalls.value = []
      conversations.value = []
      return
    }

    const [logs, calls, records] = await Promise.all([
      getRequestLogs(apiKey),
      getToolCalls(apiKey),
      getAdminConversations(apiKey),
    ])
    requestLogs.value = logs
    toolCalls.value = calls
    conversations.value = records
  } catch {
    currentUser.value = undefined
    requestLogs.value = []
    toolCalls.value = []
    conversations.value = []
    errorMessage.value =
      '无法加载管理数据。请确认管理员 API Key 有效，且后端服务正在运行。'
  } finally {
    isLoading.value = false
  }
}

const openConversation = async (conversation: AdminConversation) => {
  const apiKey = getSessionApiKey()
  if (!apiKey) return

  selectedConversation.value = conversation
  messages.value = []
  messageDialogVisible.value = true
  isMessagesLoading.value = true
  try {
    messages.value = await getAdminMessages(
      apiKey,
      conversation.conversation_id,
    )
  } catch {
    errorMessage.value = '无法加载会话消息，请稍后重试。'
  } finally {
    isMessagesLoading.value = false
  }
}

onMounted(() => {
  void loadAdminData()
})
</script>

<template>
  <section class="admin-page">
    <div class="page-heading page-heading-with-action">
      <div>
        <h1>管理后台</h1>
        <p>查看经过服务端脱敏的请求审计、工具调用和会话记录。</p>
      </div>
      <el-button
        :loading="isLoading"
        :disabled="!hasApiKey"
        @click="loadAdminData"
      >
        <el-icon><RefreshRight /></el-icon>
        刷新
      </el-button>
    </div>

    <el-alert
      v-if="!hasApiKey"
      title="请先在“设置与 API Key”中保存管理员 API Key。"
      type="warning"
      show-icon
      :closable="false"
    />
    <el-alert
      v-else-if="errorMessage"
      class="admin-alert"
      :title="errorMessage"
      type="error"
      show-icon
      :closable="false"
    />
    <el-result
      v-else-if="currentUser && !isAdmin"
      icon="warning"
      title="需要管理员权限"
      sub-title="当前 API Key 不具备查看审计记录的权限。"
    >
      <template #icon
        ><el-icon :size="46"><Lock /></el-icon
      ></template>
    </el-result>

    <el-tabs v-else-if="isAdmin" class="admin-tabs">
      <el-tab-pane label="请求审计">
        <el-card shadow="never">
          <el-skeleton v-if="isLoading" :rows="6" animated />
          <el-empty
            v-else-if="!requestLogs.length"
            description="暂无请求审计记录。"
          />
          <el-table v-else :data="requestLogs" style="width: 100%">
            <el-table-column label="请求 ID" width="110">
              <template #default="scope">{{
                shortId(scope.row.request_id)
              }}</template>
            </el-table-column>
            <el-table-column
              label="请求内容"
              min-width="220"
              show-overflow-tooltip
            >
              <template #default="scope">{{ scope.row.query ?? '—' }}</template>
            </el-table-column>
            <el-table-column prop="intent" label="意图" width="130" />
            <el-table-column label="状态" width="90">
              <template #default="scope">
                <el-tag
                  :type="statusType(scope.row.status_code)"
                  effect="plain"
                >
                  {{ scope.row.status_code }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="耗时" width="90">
              <template #default="scope"
                >{{ scope.row.latency_ms }} ms</template
              >
            </el-table-column>
            <el-table-column label="时间" min-width="165">
              <template #default="scope">{{
                formatDate(scope.row.created_at)
              }}</template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-tab-pane>

      <el-tab-pane label="工具调用">
        <el-card shadow="never">
          <el-skeleton v-if="isLoading" :rows="6" animated />
          <el-empty
            v-else-if="!toolCalls.length"
            description="暂无工具调用记录。"
          />
          <el-collapse v-else class="audit-collapse">
            <el-collapse-item
              v-for="toolCall in toolCalls"
              :key="toolCall.tool_call_id"
              :name="toolCall.tool_call_id"
            >
              <template #title>
                <div class="tool-call-title">
                  <strong>{{ toolCall.tool_name }}</strong>
                  <el-tag
                    :type="toolStatusType(toolCall.status)"
                    effect="plain"
                  >
                    {{ toolStatusLabel(toolCall.status) }}
                  </el-tag>
                  <span>{{ formatDate(toolCall.created_at) }}</span>
                </div>
              </template>
              <div class="tool-call-details">
                <p><strong>会话：</strong>{{ toolCall.conversation_id }}</p>
                <p><strong>耗时：</strong>{{ toolCall.latency_ms }} ms</p>
                <p v-if="toolCall.error_message">
                  <strong>错误：</strong>{{ toolCall.error_message }}
                </p>
                <div class="json-columns">
                  <div>
                    <strong>输入（已脱敏）</strong>
                    <pre>{{ formatJson(toolCall.tool_input) }}</pre>
                  </div>
                  <div>
                    <strong>输出（已脱敏）</strong>
                    <pre>{{ formatJson(toolCall.tool_output) }}</pre>
                  </div>
                </div>
              </div>
            </el-collapse-item>
          </el-collapse>
        </el-card>
      </el-tab-pane>

      <el-tab-pane label="会话记录">
        <el-card shadow="never">
          <el-skeleton v-if="isLoading" :rows="6" animated />
          <el-empty
            v-else-if="!conversations.length"
            description="暂无会话记录。"
          />
          <el-table v-else :data="conversations" style="width: 100%">
            <el-table-column
              prop="title"
              label="会话标题"
              min-width="220"
              show-overflow-tooltip
            />
            <el-table-column label="用户 ID" min-width="150">
              <template #default="scope">{{
                shortId(scope.row.user_id)
              }}</template>
            </el-table-column>
            <el-table-column label="最后更新" min-width="165">
              <template #default="scope">{{
                formatDate(scope.row.updated_at)
              }}</template>
            </el-table-column>
            <el-table-column label="操作" width="110" fixed="right">
              <template #default="scope">
                <el-button
                  link
                  type="primary"
                  @click="openConversation(scope.row)"
                >
                  <el-icon><Tickets /></el-icon>
                  查看消息
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-tab-pane>
    </el-tabs>

    <el-dialog
      v-model="messageDialogVisible"
      title="会话消息（已脱敏）"
      width="min(760px, 94vw)"
    >
      <div v-if="selectedConversation" class="dialog-conversation-title">
        {{ selectedConversation.title }} ·
        {{ shortId(selectedConversation.conversation_id) }}
      </div>
      <el-skeleton v-if="isMessagesLoading" :rows="6" animated />
      <el-empty v-else-if="!messages.length" description="该会话暂无消息。" />
      <div v-else class="admin-message-list">
        <article
          v-for="(message, index) in messages"
          :key="`${message.created_at}-${index}`"
          class="admin-message-item"
        >
          <div class="admin-message-meta">
            <el-tag effect="plain">{{ message.role }}</el-tag>
            <span>{{ formatDate(message.created_at) }}</span>
          </div>
          <p>{{ message.content }}</p>
        </article>
      </div>
    </el-dialog>
  </section>
</template>
