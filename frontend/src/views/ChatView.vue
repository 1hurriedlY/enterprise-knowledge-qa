<script setup lang="ts">
import {
  ChatDotRound,
  CircleCheck,
  Plus,
  Promotion,
} from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { computed, nextTick, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import {
  type ChatResponse,
  type ConversationMessage,
  type SourceCitation,
  type ToolCallSummary,
  createConversation,
  getConversationMessages,
  sendChat,
} from '@/services/chat'
import { getCurrentUser, type CurrentUserResponse } from '@/services/documents'
import {
  clearCurrentConversation,
  getCurrentConversation,
  getSessionApiKey,
  saveCurrentConversation,
} from '@/services/session'

interface DisplayMessage extends ConversationMessage {
  metadata?: Pick<
    ChatResponse,
    'need_human' | 'rewritten_query' | 'tool_calls' | 'latency_ms'
  >
}

const MAX_QUERY_LENGTH = 4_000
const router = useRouter()
const currentUser = ref<CurrentUserResponse>()
const conversationId = ref<string>()
const messages = ref<DisplayMessage[]>([])
const query = ref('')
const isLoading = ref(false)
const isSending = ref(false)
const errorMessage = ref('')
const messagePanel = ref<HTMLElement>()

const hasApiKey = computed(() => Boolean(getSessionApiKey()))
const canSend = computed(
  () => Boolean(currentUser.value && query.value.trim()) && !isSending.value,
)

const toolLabels: Record<ToolCallSummary['tool_name'], string> = {
  query_order: '订单查询',
  query_logistics: '物流查询',
  transfer_to_human: '人工服务工单',
}

const toolTagType = (
  status: ToolCallSummary['status'],
): 'info' | 'success' | 'danger' | 'warning' => {
  if (status === 'success') return 'success'
  if (status === 'failed') return 'danger'
  if (status === 'timeout') return 'warning'
  return 'info'
}

const formatDate = (value: string): string => {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return new Intl.DateTimeFormat('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

const scrollToLatest = async () => {
  await nextTick()
  if (messagePanel.value) {
    messagePanel.value.scrollTop = messagePanel.value.scrollHeight
  }
}

const loadHistory = async (apiKey: string, savedConversationId: string) => {
  isLoading.value = true
  try {
    messages.value = (
      await getConversationMessages(apiKey, savedConversationId)
    ).filter((message) => message.role !== 'tool')
    conversationId.value = savedConversationId
    await scrollToLatest()
  } catch {
    clearCurrentConversation()
    conversationId.value = undefined
    messages.value = []
    errorMessage.value = '无法恢复此前的会话，请开始新的咨询。'
  } finally {
    isLoading.value = false
  }
}

const initializeChat = async () => {
  const apiKey = getSessionApiKey()
  if (!apiKey) return

  isLoading.value = true
  errorMessage.value = ''
  try {
    const user = await getCurrentUser(apiKey)
    currentUser.value = user
    const savedConversationId = getCurrentConversation(user.user_id)
    if (savedConversationId) {
      await loadHistory(apiKey, savedConversationId)
    }
  } catch {
    currentUser.value = undefined
    errorMessage.value =
      '无法识别当前身份。请确认 API Key 有效，且后端服务正在运行。'
  } finally {
    isLoading.value = false
  }
}

const createConversationForQuery = async (
  apiKey: string,
  userId: string,
  value: string,
): Promise<string> => {
  const title = value.replace(/\s+/g, ' ').slice(0, 80) || '新咨询'
  const conversation = await createConversation(apiKey, userId, title)
  saveCurrentConversation(conversation.conversation_id, userId)
  conversationId.value = conversation.conversation_id
  return conversation.conversation_id
}

const submitQuery = async () => {
  const apiKey = getSessionApiKey()
  const user = currentUser.value
  const value = query.value.trim()
  if (!apiKey || !user || !value || isSending.value) return

  if (value.length > MAX_QUERY_LENGTH) {
    ElMessage.error(`单次提问不能超过 ${MAX_QUERY_LENGTH} 个字符。`)
    return
  }

  isSending.value = true
  errorMessage.value = ''
  query.value = ''
  const optimisticMessage: DisplayMessage = {
    role: 'user',
    content: value,
    sources: [],
    created_at: new Date().toISOString(),
  }
  messages.value.push(optimisticMessage)
  await scrollToLatest()

  try {
    const activeConversationId =
      conversationId.value ??
      (await createConversationForQuery(apiKey, user.user_id, value))
    const response = await sendChat(
      apiKey,
      user.user_id,
      activeConversationId,
      value,
    )
    messages.value.push({
      role: 'assistant',
      content: response.answer,
      sources: response.sources,
      created_at: new Date().toISOString(),
      metadata: {
        need_human: response.need_human,
        rewritten_query: response.rewritten_query,
        tool_calls: response.tool_calls,
        latency_ms: response.latency_ms,
      },
    })
    await scrollToLatest()
  } catch {
    messages.value = messages.value.filter(
      (message) => message !== optimisticMessage,
    )
    query.value = value
    errorMessage.value = '暂时无法处理本次咨询，请稍后重试或转接人工客服。'
  } finally {
    isSending.value = false
  }
}

const startNewConversation = () => {
  clearCurrentConversation()
  conversationId.value = undefined
  messages.value = []
  errorMessage.value = ''
  ElMessage.success('已开始新的会话。')
}

const sourceLabel = (source: SourceCitation): string =>
  source.heading_path
    ? `${source.filename} · ${source.heading_path}`
    : source.filename

onMounted(() => {
  void initializeChat()
})
</script>

<template>
  <section class="chat-page">
    <div class="page-heading page-heading-with-action">
      <div>
        <h1>智能对话</h1>
        <p>基于您的知识文档进行回答，也可查询订单、物流或申请人工服务。</p>
      </div>
      <el-button :disabled="!hasApiKey" @click="startNewConversation">
        <el-icon><Plus /></el-icon>
        新对话
      </el-button>
    </div>

    <el-alert
      v-if="!hasApiKey"
      title="请先在“设置与 API Key”中保存并验证 API Key，再开始咨询。"
      type="warning"
      show-icon
      :closable="false"
    >
      <template #default>
        <el-button
          link
          type="primary"
          @click="router.push({ name: 'settings' })"
        >
          前往设置
        </el-button>
      </template>
    </el-alert>

    <template v-else>
      <el-alert
        v-if="errorMessage"
        class="chat-error"
        :title="errorMessage"
        type="error"
        show-icon
        :closable="false"
      />
      <el-card class="chat-card" shadow="never">
        <div ref="messagePanel" class="message-panel">
          <el-skeleton v-if="isLoading" :rows="5" animated />
          <div v-else-if="!messages.length" class="welcome-panel">
            <el-icon :size="42"><ChatDotRound /></el-icon>
            <h2>你好，我是企业知识库客服</h2>
            <p>你可以询问业务政策、订单状态、物流进度，或申请转人工服务。</p>
            <div class="suggested-questions">
              <el-button text @click="query = '如何申请退款？'"
                >如何申请退款？</el-button
              >
              <el-button text @click="query = '我的订单 12345 发货了吗？'">
                我的订单 12345 发货了吗？
              </el-button>
              <el-button text @click="query = '我要转人工客服'"
                >我要转人工客服</el-button
              >
            </div>
          </div>

          <article
            v-for="(message, index) in messages"
            :key="`${message.created_at}-${index}`"
            class="message-row"
            :class="`message-${message.role}`"
          >
            <div class="message-avatar">
              <el-icon v-if="message.role === 'assistant'"
                ><CircleCheck
              /></el-icon>
              <el-icon v-else><ChatDotRound /></el-icon>
            </div>
            <div class="message-content">
              <div class="message-meta">
                <strong>{{
                  message.role === 'assistant' ? '智能客服' : '您'
                }}</strong>
                <time>{{ formatDate(message.created_at) }}</time>
              </div>
              <div class="message-bubble">{{ message.content }}</div>

              <div v-if="message.metadata" class="response-metadata">
                <el-tag
                  v-if="message.metadata.need_human"
                  type="warning"
                  effect="plain"
                >
                  建议人工服务
                </el-tag>
                <el-tag
                  v-for="toolCall in message.metadata.tool_calls"
                  :key="toolCall.tool_call_id"
                  :type="toolTagType(toolCall.status)"
                  effect="plain"
                >
                  {{ toolLabels[toolCall.tool_name] }} ·
                  {{ toolCall.status === 'success' ? '已完成' : '未完成' }}
                </el-tag>
                <span v-if="message.metadata.latency_ms">
                  响应 {{ message.metadata.latency_ms }} ms
                </span>
              </div>

              <el-collapse
                v-if="message.sources.length"
                class="source-collapse"
              >
                <el-collapse-item
                  :title="`引用来源（${message.sources.length}）`"
                  :name="`sources-${index}`"
                >
                  <div
                    v-for="(source, sourceIndex) in message.sources"
                    :key="source.chunk_id"
                    class="source-item"
                  >
                    <strong
                      >[{{ sourceIndex + 1 }}] {{ sourceLabel(source) }}</strong
                    >
                    <span>匹配度 {{ Math.round(source.score * 100) }}%</span>
                    <p>{{ source.content }}</p>
                  </div>
                </el-collapse-item>
              </el-collapse>
            </div>
          </article>
        </div>

        <div class="chat-composer">
          <el-input
            v-model="query"
            type="textarea"
            :rows="3"
            resize="none"
            maxlength="4000"
            show-word-limit
            placeholder="请输入您的问题，例如：如何申请退款？"
            :disabled="isLoading || isSending"
            @keydown.ctrl.enter.prevent="submitQuery"
          />
          <div class="composer-actions">
            <span>按 Ctrl + Enter 发送</span>
            <el-button
              type="primary"
              :loading="isSending"
              :disabled="!canSend"
              @click="submitQuery"
            >
              <el-icon><Promotion /></el-icon>
              发送
            </el-button>
          </div>
        </div>
      </el-card>
    </template>
  </section>
</template>
