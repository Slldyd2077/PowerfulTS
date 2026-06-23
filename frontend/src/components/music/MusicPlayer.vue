<script setup lang="ts">
import { onMounted } from 'vue'
import { useMusicStore } from '@/stores/music'
import { ElMessage } from 'element-plus'

const music = useMusicStore()

onMounted(() => music.fetchVolume())

async function handleVolumeChange(val: number) {
  try {
    await music.updateVolume(val)
  } catch {
    ElMessage.error('设置音量失败')
  }
}

async function handlePause() {
  try {
    await music.pause()
  } catch {
    ElMessage.error('操作失败')
  }
}

async function handleSkip() {
  try {
    await music.skip()
    ElMessage.success('已跳过当前歌曲')
  } catch {
    ElMessage.error('跳过失败')
  }
}

async function handleStop() {
  try {
    await music.stop()
    ElMessage.success('已停止播放')
  } catch {
    ElMessage.error('停止失败')
  }
}
</script>

<template>
  <div class="player">
    <!-- 音量 -->
    <div class="volume-section">
      <div class="volume-header">
        <span>🔊 音量</span>
        <span class="volume-value">{{ music.volume }}%</span>
      </div>
      <el-slider
        v-model="music.volume"
        :min="0"
        :max="100"
        :show-tooltip="false"
        @change="handleVolumeChange"
      />
    </div>

    <!-- 控制按钮 -->
    <div class="controls">
      <el-button @click="handlePause" :type="music.playing ? 'warning' : 'success'" plain>
        {{ music.playing ? '⏸ 暂停' : '▶ 恢复' }}
      </el-button>
      <el-button @click="handleSkip" plain>⏭ 跳过</el-button>
      <el-button @click="handleStop" type="danger" plain>⏹ 停止</el-button>
    </div>
  </div>
</template>

<style scoped>
.player {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--border-radius);
  padding: 20px;
  margin-top: 16px;
}

.volume-section {
  margin-bottom: 16px;
}

.volume-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.volume-value {
  font-weight: 700;
  color: var(--color-primary);
}

.controls {
  display: flex;
  gap: 8px;
}
</style>
