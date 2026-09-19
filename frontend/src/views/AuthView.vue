<script setup lang="ts">
import { Lock, Message, User } from '@element-plus/icons-vue'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { computed, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { loginUser, registerUser } from '@/services/api'
import { saveSessionApiKey } from '@/services/session'

type AuthMode = 'login' | 'register'

const router = useRouter()
const route = useRoute()
const mode = ref<AuthMode>('login')
const formRef = ref<FormInstance>()
const submitting = ref(false)
const form = reactive({ name: '', email: '', password: '' })

const isRegister = computed(() => mode.value === 'register')
const title = computed(() => (isRegister.value ? '创建账户' : '登录账户'))

const rules = computed<FormRules>(() => ({
  name: [
    {
      required: true,
      message: '请输入姓名',
      trigger: 'blur',
    },
  ],
  email: [
    { required: true, message: '请输入邮箱', trigger: 'blur' },
    { type: 'email', message: '请输入有效的邮箱地址', trigger: 'blur' },
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 8, max: 128, message: '密码长度需为 8-128 位', trigger: 'blur' },
  ],
}))

const switchMode = (nextMode: AuthMode) => {
  mode.value = nextMode
  formRef.value?.clearValidate()
}

const handleModeChange = (value: string | number | boolean) => {
  if (value === 'login' || value === 'register') switchMode(value)
}

const submit = async () => {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return

  submitting.value = true
  try {
    const result = isRegister.value
      ? await registerUser(form.name, form.email, form.password)
      : await loginUser(form.email, form.password)
    saveSessionApiKey(result.api_key)
    ElMessage.success(isRegister.value ? '注册成功，已自动登录' : '登录成功')
    const redirect =
      typeof route.query.redirect === 'string' ? route.query.redirect : ''
    await router.push(
      redirect && redirect.startsWith('/') ? redirect : { name: 'chat' },
    )
  } catch (error) {
    ElMessage.error(
      error instanceof Error ? error.message : '操作失败，请稍后重试',
    )
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <section class="auth-page">
    <el-card class="auth-card" shadow="never">
      <div class="auth-heading">
        <div class="auth-mark">AI</div>
        <h1>{{ title }}</h1>
        <p>使用企业知识库客服账号访问自己的文档、对话和资料。</p>
      </div>

      <el-segmented
        v-model="mode"
        class="auth-mode"
        :options="[
          { label: '登录', value: 'login' },
          { label: '注册', value: 'register' },
        ]"
        @change="handleModeChange"
      />

      <el-form
        ref="formRef"
        class="auth-form"
        :model="form"
        :rules="rules"
        label-position="top"
        @submit.prevent="submit"
      >
        <el-form-item v-if="isRegister" label="姓名" prop="name">
          <el-input
            v-model="form.name"
            :prefix-icon="User"
            autocomplete="name"
          />
        </el-form-item>
        <el-form-item label="邮箱" prop="email">
          <el-input
            v-model="form.email"
            :prefix-icon="Message"
            type="email"
            autocomplete="email"
          />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input
            v-model="form.password"
            :prefix-icon="Lock"
            type="password"
            show-password
            autocomplete="current-password"
            @keyup.enter="submit"
          />
        </el-form-item>
        <el-button
          class="auth-submit"
          type="primary"
          :loading="submitting"
          native-type="submit"
        >
          {{ isRegister ? '注册并登录' : '登录' }}
        </el-button>
      </el-form>

      <p class="auth-switch">
        <template v-if="isRegister">
          已有账户？
          <el-button link type="primary" @click="switchMode('login')"
            >去登录</el-button
          >
        </template>
        <template v-else>
          还没有账户？
          <el-button link type="primary" @click="switchMode('register')"
            >去注册</el-button
          >
        </template>
      </p>
    </el-card>
  </section>
</template>
