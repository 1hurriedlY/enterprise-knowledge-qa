<script setup lang="ts">
import {
  Delete,
  FolderOpened,
  RefreshRight,
  UploadFilled,
} from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import {
  type CurrentUserResponse,
  type DocumentListItem,
  type DocumentStatus,
  deleteDocument,
  getCurrentUser,
  listDocuments,
  uploadDocument,
} from '@/services/documents'
import { getSessionApiKey } from '@/services/session'

const MAX_FILE_SIZE = 10 * 1024 * 1024
const ALLOWED_EXTENSIONS = ['.md', '.txt', '.pdf']

const router = useRouter()
const fileInput = ref<HTMLInputElement>()
const selectedFile = ref<File>()
const documents = ref<DocumentListItem[]>([])
const currentUser = ref<CurrentUserResponse>()
const isLoading = ref(false)
const isUploading = ref(false)
const deletingId = ref<string>()
const errorMessage = ref('')

const hasApiKey = computed(() => Boolean(getSessionApiKey()))
const canUpload = computed(() =>
  Boolean(selectedFile.value && currentUser.value && !isUploading.value),
)

const statusLabels: Record<DocumentStatus, string> = {
  pending: '等待处理',
  processing: '处理中',
  completed: '已完成',
  failed: '处理失败',
  deleted: '已删除',
}

const statusTypes: Record<
  DocumentStatus,
  'info' | 'warning' | 'success' | 'danger'
> = {
  pending: 'info',
  processing: 'warning',
  completed: 'success',
  failed: 'danger',
  deleted: 'info',
}

const getStatusLabel = (status: DocumentStatus): string => statusLabels[status]

const getStatusType = (
  status: DocumentStatus,
): 'info' | 'warning' | 'success' | 'danger' => statusTypes[status]

const formatDate = (value: string): string => {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('zh-CN', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date)
}

const loadDocuments = async () => {
  const apiKey = getSessionApiKey()
  if (!apiKey) return

  isLoading.value = true
  errorMessage.value = ''
  try {
    const [user, items] = await Promise.all([
      getCurrentUser(apiKey),
      listDocuments(apiKey),
    ])
    currentUser.value = user
    documents.value = items
  } catch {
    currentUser.value = undefined
    documents.value = []
    errorMessage.value =
      '无法加载文档。请确认 API Key 有效，且后端服务正在运行。'
  } finally {
    isLoading.value = false
  }
}

const validateFile = (file: File): boolean => {
  const extension = `.${file.name.split('.').pop()?.toLowerCase() ?? ''}`
  if (!ALLOWED_EXTENSIONS.includes(extension)) {
    ElMessage.error('仅支持 PDF、Markdown 或 TXT 文件。')
    return false
  }
  if (file.size > MAX_FILE_SIZE) {
    ElMessage.error('单个文件不能超过 10 MB。')
    return false
  }
  return true
}

const selectFile = (event: Event) => {
  const input = event.target as HTMLInputElement
  const [file] = Array.from(input.files ?? [])
  if (!file) return
  selectedFile.value = validateFile(file) ? file : undefined
}

const dropFile = (event: DragEvent) => {
  const [file] = Array.from(event.dataTransfer?.files ?? [])
  if (!file) return
  selectedFile.value = validateFile(file) ? file : undefined
}

const openFilePicker = () => fileInput.value?.click()

const submitUpload = async () => {
  const apiKey = getSessionApiKey()
  const file = selectedFile.value
  if (!apiKey || !file || !currentUser.value) return

  isUploading.value = true
  errorMessage.value = ''
  try {
    await uploadDocument(apiKey, currentUser.value.user_id, file)
    selectedFile.value = undefined
    if (fileInput.value) fileInput.value.value = ''
    ElMessage.success('文档已提交入库，正在异步处理。')
    await loadDocuments()
  } catch {
    errorMessage.value = '上传失败。请检查文件格式和大小后重试。'
  } finally {
    isUploading.value = false
  }
}

const removeDocument = async (document: DocumentListItem) => {
  const apiKey = getSessionApiKey()
  if (!apiKey) return

  try {
    await ElMessageBox.confirm(
      `删除“${document.filename}”后将同时移除对应向量，且无法恢复。`,
      '确认删除文档',
      {
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        confirmButtonClass: 'el-button--danger',
        type: 'warning',
      },
    )
  } catch {
    return
  }

  deletingId.value = document.document_id
  errorMessage.value = ''
  try {
    await deleteDocument(apiKey, document.document_id)
    documents.value = documents.value.filter(
      (item) => item.document_id !== document.document_id,
    )
    ElMessage.success('文档及其向量已删除。')
  } catch {
    errorMessage.value =
      '删除失败。文档可能已不存在或暂时无法删除，请刷新后重试。'
  } finally {
    deletingId.value = undefined
  }
}

onMounted(() => {
  void loadDocuments()
})
</script>

<template>
  <section class="documents-page">
    <div class="page-heading page-heading-with-action">
      <div>
        <h1>知识文档</h1>
        <p>
          上传 PDF、Markdown 或 TXT 文档。系统会异步解析、切片并写入知识库。
        </p>
      </div>
      <el-button :loading="isLoading" @click="loadDocuments">
        <el-icon><RefreshRight /></el-icon>
        刷新
      </el-button>
    </div>

    <el-alert
      v-if="!hasApiKey"
      title="请先在“设置与 API Key”中保存并验证 API Key，再管理您的知识文档。"
      type="warning"
      show-icon
      :closable="false"
    >
      <template #default>
        <el-button
          link
          type="primary"
          @click="router.push({ name: 'settings' })"
          >前往设置</el-button
        >
      </template>
    </el-alert>
    <el-alert
      v-else-if="errorMessage"
      :title="errorMessage"
      type="error"
      show-icon
      :closable="false"
    />

    <el-row v-if="hasApiKey" :gutter="20" class="documents-layout">
      <el-col :xs="24" :lg="8">
        <el-card shadow="never">
          <template #header>
            <span class="card-title">上传文档</span>
          </template>
          <input
            ref="fileInput"
            class="file-input"
            type="file"
            accept=".md,.txt,.pdf"
            @change="selectFile"
          />
          <div
            class="upload-dropzone"
            role="button"
            tabindex="0"
            @click="openFilePicker"
            @keydown.enter="openFilePicker"
            @keydown.space.prevent="openFilePicker"
            @dragover.prevent
            @drop.prevent="dropFile"
          >
            <el-icon class="upload-icon"><UploadFilled /></el-icon>
            <div>点击选择文件，或将文件拖到这里</div>
            <div class="el-upload__tip">
              支持 .md、.txt、.pdf，单个文件不超过 10 MB
            </div>
          </div>
          <div v-if="selectedFile" class="selected-file">
            <strong>{{ selectedFile.name }}</strong>
            <span>{{ (selectedFile.size / 1024 / 1024).toFixed(2) }} MB</span>
          </div>
          <el-button
            class="upload-submit"
            type="primary"
            :disabled="!canUpload"
            :loading="isUploading"
            @click="submitUpload"
          >
            提交入库
          </el-button>
        </el-card>
      </el-col>

      <el-col :xs="24" :lg="16" class="documents-list-column">
        <el-card shadow="never">
          <template #header>
            <div class="card-header">
              <span>我的文档</span>
              <span v-if="currentUser" class="muted-text">{{
                currentUser.email
              }}</span>
            </div>
          </template>
          <el-skeleton v-if="isLoading" :rows="5" animated />
          <el-empty
            v-else-if="!documents.length"
            description="还没有文档，上传第一份资料开始构建知识库。"
          >
            <el-icon :size="36"><FolderOpened /></el-icon>
          </el-empty>
          <el-table v-else :data="documents" style="width: 100%">
            <el-table-column
              prop="filename"
              label="文件名"
              min-width="180"
              show-overflow-tooltip
            />
            <el-table-column label="状态" width="110">
              <template #default="scope">
                <el-tag :type="getStatusType(scope.row.status)" effect="plain">
                  {{ getStatusLabel(scope.row.status) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="chunk_count" label="切片数" width="90" />
            <el-table-column label="上传时间" min-width="150">
              <template #default="scope">{{
                formatDate(scope.row.created_at)
              }}</template>
            </el-table-column>
            <el-table-column label="操作" width="90" fixed="right">
              <template #default="scope">
                <el-button
                  type="danger"
                  link
                  :loading="deletingId === scope.row.document_id"
                  @click="removeDocument(scope.row)"
                >
                  <el-icon><Delete /></el-icon>
                  删除
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>
  </section>
</template>
