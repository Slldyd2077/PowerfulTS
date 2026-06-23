<script setup lang="ts">
import { ref } from 'vue'
import { useMusicStore } from '@/stores/music'
import { ElMessage } from 'element-plus'

const music = useMusicStore()
const loading = ref(false)

async function handleCall() {
  loading.value = true
  try {
    await music.callRadio()
    ElMessage.success('已呼叫强基计划到你的频道')
  } catch (e: unknown) {
    ElMessage.error(e instanceof Error ? e.message : '呼叫失败')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="radio-control">
    <el-button
      type="danger"
      size="large"
      :loading="loading"
      @click="handleCall"
      class="radio-btn"
    >
      📻 呼叫强基计划
    </el-button>
    <p class="radio-hint">将音乐电台呼叫到你当前所在的 TS3 频道</p>
  </div>
</template>

<style scoped>
.radio-control {
  margin-top: 16px;
  text-align: center;
}

.radio-btn {
  width: 100%;
}

.radio-hint {
  margin-top: 8px;
  font-size: 0.8em;
  color: var(--text-muted);
}
</style>
