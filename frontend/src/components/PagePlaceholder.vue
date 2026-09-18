<script setup lang="ts">
defineProps<{
  title: string
  description: string
  nextStep: string
}>()
</script>

<template>
  <el-card shadow="never" class="placeholder-card">
    <h1>{{ title }}</h1>
    <p>{{ description }}</p>
    <el-divider />
    <p class="next-step">下一步：{{ nextStep }}</p>
  </el-card>
</template>
