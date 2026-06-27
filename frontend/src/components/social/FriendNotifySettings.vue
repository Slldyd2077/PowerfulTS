<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { getFriendSettings, updateFriendSettings } from '@/api/social'

const qq = ref('')
const notify = ref(false)
const loading = ref(false)
const savingQQ = ref(false)
const editingQQ = ref(false)

onMounted(load)

async function load() {
  loading.value = true
  try {
    const s = await getFriendSettings()
    qq.value = s.qq_number || ''
    notify.value = !!s.notify_friends_online
  } catch {
    // 静默
  } finally {
    loading.value = false
  }
}

async function saveQQ() {
  const v = qq.value.trim()
  if (v && !/^\d+$/.test(v)) {
    ElMessage.error('QQ 号必须为纯数字')
    return
  }
  savingQQ.value = true
  try {
    await updateFriendSettings({ qq_number: v })
    qq.value = v
    ElMessage.success(v ? 'QQ 号已绑定' : '已解绑 QQ')
    editingQQ.value = false
  } catch {
    ElMessage.error('保存失败')
  } finally {
    savingQQ.value = false
  }
}

function cancelEdit() {
  editingQQ.value = false
  void load() // 还原显示值
}

async function toggleNotify(val: boolean | string | number) {
  const on = !!val
  try {
    await updateFriendSettings({ notify_friends_online: on })
    ElMessage.success(on ? '已开启好友上线提醒' : '已关闭好友上线提醒')
  } catch {
    notify.value = !on // 回滚
    ElMessage.error('切换失败')
  }
}
</script>

<template>
  <div class="notify-card" v-loading="loading">
    <div class="nc-header">
      <span class="nc-title">好友上线提醒</span>
      <span class="nc-sub label-mono">QQ NOTIFY</span>
    </div>
    <p class="nc-hint">
      绑定 QQ 并开启后，当你的好友上线 TeamSpeak，会通过 NapCat 给你的 QQ 发私聊提醒。
    </p>

    <div class="nc-row">
      <div class="nc-label">QQ 号</div>
      <template v-if="!editingQQ">
        <span class="nc-value" :class="{ bound: qq }">{{ qq || '未绑定' }}</span>
        <button class="nc-btn" @click="editingQQ = true">{{ qq ? '修改' : '绑定' }}</button>
      </template>
      <template v-else>
        <input
          v-model="qq"
          class="nc-input"
          placeholder="输入 QQ 号（纯数字）"
          maxlength="16"
          inputmode="numeric"
        />
        <button class="nc-btn" :disabled="savingQQ" @click="saveQQ">{{ savingQQ ? '保存中…' : '保存' }}</button>
        <button class="nc-btn nc-btn--ghost" @click="cancelEdit">取消</button>
      </template>
    </div>

    <div class="nc-row">
      <div class="nc-label">上线提醒</div>
      <span class="nc-desc">{{ notify ? '已开启' : '未开启' }}</span>
      <el-switch
        v-model="notify"
        :disabled="!qq"
        class="nc-switch"
        @change="toggleNotify"
      />
    </div>
    <p v-if="!qq" class="nc-tip">先绑定 QQ 号才能开启提醒。</p>
  </div>
</template>

<style scoped>
.notify-card {
  margin-top: 16px;
  background: var(--gradient-surface);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  padding: 16px 18px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.nc-header {
  display: flex;
  align-items: baseline;
  gap: 8px;
}
.nc-title {
  font-size: 0.92em;
  font-weight: 600;
  color: var(--text-primary);
}
.nc-sub {
  font-size: 0.62em;
  color: var(--text-muted);
}
.nc-hint {
  margin: 0;
  font-size: 0.76em;
  color: var(--text-secondary);
  line-height: 1.5;
}
.nc-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 0;
}
.nc-label {
  font-size: 0.82em;
  font-weight: 600;
  color: var(--text-primary);
  width: 64px;
  flex-shrink: 0;
}
.nc-value {
  flex: 1;
  font-size: 0.82em;
  color: var(--text-muted);
}
.nc-value.bound {
  color: var(--text-primary);
}
.nc-desc {
  flex: 1;
  font-size: 0.78em;
  color: var(--text-muted);
}
.nc-input {
  flex: 1;
  min-width: 0;
  height: 32px;
  padding: 0 10px;
  background: var(--surface-3);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  color: var(--text-primary);
  font-size: 0.82em;
  font-family: inherit;
  outline: none;
  transition: border-color 0.15s;
}
.nc-input:focus {
  border-color: var(--color-primary);
}
.nc-btn {
  height: 30px;
  padding: 0 14px;
  flex-shrink: 0;
  border: 0;
  border-radius: var(--radius-sm);
  background: var(--gradient-brand);
  color: var(--text-inverse);
  font-size: 0.78em;
  font-weight: 600;
  cursor: pointer;
  transition: filter 0.15s, opacity 0.15s;
}
.nc-btn:hover:not(:disabled) {
  filter: brightness(1.08);
}
.nc-btn:disabled {
  opacity: 0.5;
  cursor: default;
}
.nc-btn--ghost {
  background: transparent;
  border: 1px solid var(--border-emphasis);
  color: var(--text-secondary);
}
.nc-btn--ghost:hover:not(:disabled) {
  filter: none;
  color: var(--text-primary);
  border-color: var(--text-secondary);
}
.nc-switch {
  flex-shrink: 0;
}
.nc-tip {
  margin: 0;
  font-size: 0.7em;
  color: var(--text-muted);
}

/* 移动端：表单行允许折行、加大输入框与按钮触摸区 */
@media (max-width: 768px) {
  .nc-row { flex-wrap: wrap; }
  .nc-input { height: 40px; }
  .nc-btn { height: 40px; }
}
</style>
