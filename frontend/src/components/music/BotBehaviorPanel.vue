<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage } from 'element-plus'
import { useMusicStore } from '@/stores/music'
import type { BotProfile } from '@/api/music'

const music = useMusicStore()

// ── 全局行为：空闲下线 + 空频道自动暂停 ──
const idleInput = ref(0)
const globalBusy = ref(false)
const autoPauseBusy = ref(false)

// ── per-bot profile：6 开关 + 头像 ──
const profileBusy = ref<string | null>(null)
const avatarBusy = ref(false)
const avatarInput = ref<HTMLInputElement | null>(null)

// 二级行为面板：默认收起，腾出空间；点击头部展开
const expanded = ref(false)

// 开关定义：key → 中文说明
const SWITCHES: { key: keyof BotProfile; label: string; hint: string }[] = [
  { key: 'avatarEnabled', label: '头像随歌曲封面', hint: '关闭则显示下方固定头像' },
  { key: 'nicknameEnabled', label: '昵称随歌曲变化', hint: '♪ 歌名 - 歌手 - 默认昵称' },
  { key: 'descriptionEnabled', label: '描述显示当前歌曲', hint: '客户端描述栏' },
  { key: 'channelDescEnabled', label: '频道描述显示正在播放', hint: '所在频道的描述' },
  { key: 'awayStatusEnabled', label: '空闲显示离开状态', hint: '空闲时显示「等待播放」' },
  { key: 'nowPlayingMsgEnabled', label: '切歌发送正在播放', hint: '频道聊天发消息' },
]

// 头部一览：已开启的开关数（autoPause + per-bot 外观开关）
const activeCount = computed(() => {
  let n = music.botSettings.autoPauseOnEmpty ? 1 : 0
  if (music.followEnabled) n++
  const prof = music.activeBotProfile
  if (prof) for (const s of SWITCHES) if (prof[s.key]) n++
  return n
})

watch(() => music.botSettings.idleTimeoutMinutes, (v) => { idleInput.value = v ?? 0 }, { immediate: true })

// profile / avatar 由 store 在 activeBotId 就绪时统一拉取（fetchBots + setActiveBot），
// 组件不重复 watch activeBotId，避免双触发；此处仅在挂载时兜底首次加载。
onMounted(() => {
  void music.fetchBotSettings()
  if (music.activeBotId) {
    void music.fetchBotProfile()
    void music.refreshAvatar()
  }
})

// 释放 objectURL，防组件销毁后泄漏
onBeforeUnmount(() => {
  music.disposeAvatar()
})

async function saveGlobal() {
  const mins = Math.max(0, Math.floor(Number(idleInput.value) || 0))
  globalBusy.value = true
  try {
    await music.saveBotSettings({ idleTimeoutMinutes: mins })
    ElMessage.success('已保存')
  } catch {
    idleInput.value = music.botSettings.idleTimeoutMinutes ?? 0 // 回滚未保存的输入
    ElMessage.error('保存失败')
  } finally {
    globalBusy.value = false
  }
}

async function toggleAutoPause(val: boolean) {
  if (autoPauseBusy.value) return
  autoPauseBusy.value = true
  try {
    await music.saveBotSettings({ autoPauseOnEmpty: val })
  } catch {
    ElMessage.error('保存失败')
  } finally {
    autoPauseBusy.value = false
  }
}

const followBusy = ref(false)
async function toggleFollow(val: boolean) {
  if (followBusy.value) return
  followBusy.value = true
  try {
    await music.setFollow(val)
    ElMessage.success(val ? '已开启播放跟随' : '已关闭播放跟随')
  } catch {
    ElMessage.error('设置失败')
  } finally {
    followBusy.value = false
  }
}

async function toggleProfile(key: keyof BotProfile, val: boolean) {
  const prof = music.activeBotProfile
  if (!prof || profileBusy.value) return
  const old = prof[key]
  // 乐观更新：立即翻转，失败回滚（串行锁防止并发覆盖）
  music.activeBotProfile = { ...prof, [key]: val }
  profileBusy.value = key
  try {
    await music.saveBotProfile({ [key]: val } as Partial<BotProfile>)
  } catch {
    if (music.activeBotProfile) {
      music.activeBotProfile = { ...music.activeBotProfile, [key]: old }
    }
    ElMessage.error('更新失败')
  } finally {
    profileBusy.value = null
  }
}

function readFileAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => {
      if (typeof reader.result === 'string') resolve(reader.result)
      else reject(new Error('read failed'))
    }
    reader.onerror = () => reject(new Error('read failed'))
    reader.readAsDataURL(file)
  })
}

async function onPickAvatar(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = '' // 允许重复选同一文件
  if (!file) return
  if (!/^image\/(png|jpeg|webp)$/.test(file.type)) {
    ElMessage.error('仅支持 PNG / JPEG / WebP')
    return
  }
  if (file.size > 200 * 1024) {
    ElMessage.error('图片不能超过 200KB')
    return
  }
  avatarBusy.value = true
  try {
    const dataUrl = await readFileAsDataUrl(file)
    await music.uploadAvatar(dataUrl)
    ElMessage.success('固定头像已上传')
  } catch {
    ElMessage.error('上传失败')
  } finally {
    avatarBusy.value = false
  }
}

async function onRemoveAvatar() {
  if (!music.activeBotAvatarUrl) return
  avatarBusy.value = true
  try {
    await music.removeAvatar()
    ElMessage.success('已移除固定头像')
  } catch {
    ElMessage.error('移除失败')
  } finally {
    avatarBusy.value = false
  }
}
</script>

<template>
  <div class="behavior-panel">
    <!-- 二级面板：可折叠头部，点击展开/收起 -->
    <button
      type="button"
      class="behavior-head"
      :class="{ open: expanded }"
      :aria-expanded="expanded"
      aria-controls="bot-behavior-body"
      @click="expanded = !expanded"
    >
      <span class="bh-head-text">
        <span class="panel-title">机器人行为</span>
        <span class="panel-sub label-mono">BEHAVIOR</span>
      </span>
      <span class="bh-head-right">
        <span class="bh-summary mono">{{ activeCount ? activeCount + ' 项已开启' : '未开启' }}</span>
        <svg class="bh-chev" :class="{ open: expanded }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9l6 6 6-6" /></svg>
      </span>
    </button>

    <div id="bot-behavior-body" class="bh-body" :class="{ open: expanded }">
      <div class="bh-body-inner" :inert="!expanded">

    <!-- 全局行为 -->
    <section class="bh-section">
      <div class="bh-section-title">空闲与暂停（全局，所有 Bot 生效）</div>

      <div class="field-row field-row--inline">
        <div class="field-text">
          <span class="field-label">无人自动下线</span>
          <span class="field-hint">频道无人超过该时长，Bot 自动断开（0=关闭）</span>
        </div>
        <div class="idle-input-wrap">
          <input v-model.number="idleInput" class="idle-input" type="number" min="0" step="1" />
          <span class="idle-unit">分钟</span>
        </div>
      </div>

      <button
        type="button"
        role="switch"
        :aria-checked="music.botSettings.autoPauseOnEmpty"
        class="switch-row"
        :class="{ on: music.botSettings.autoPauseOnEmpty, busy: autoPauseBusy }"
        :disabled="autoPauseBusy"
        @click="toggleAutoPause(!music.botSettings.autoPauseOnEmpty)"
      >
        <span class="field-text">
          <span class="field-label">无人自动暂停</span>
          <span class="field-hint">频道没人时暂停播放，有人回来自动继续</span>
        </span>
        <span class="switch-track"><span class="switch-knob"></span></span>
      </button>
      <p class="warn-line">依赖 TS 服务器 clientlist 命令，部分服务器可能不生效。</p>

      <button
        type="button"
        role="switch"
        :aria-checked="music.followEnabled"
        class="switch-row"
        :class="{ on: music.followEnabled, busy: followBusy }"
        :disabled="followBusy"
        @click="toggleFollow(!music.followEnabled)"
      >
        <span class="field-text">
          <span class="field-label">播放时跟随到我的频道</span>
          <span class="field-hint">点歌/播放时，Bot 自动移动到你当前所在的 TS 频道</span>
        </span>
        <span class="switch-track"><span class="switch-knob"></span></span>
      </button>

      <div class="create-actions">
        <button class="submit-btn" :disabled="globalBusy" @click="saveGlobal">{{ globalBusy ? '保存中…' : '保存下线时长' }}</button>
      </div>
    </section>

    <!-- per-bot 外观（仅当前 active bot） -->
    <section v-if="music.activeBot" class="bh-section">
      <div class="bh-section-title">外观与显示 · {{ music.activeBot.name }}</div>

      <button
        v-for="s in SWITCHES"
        :key="s.key"
        type="button"
        role="switch"
        :aria-checked="!!(music.activeBotProfile && music.activeBotProfile[s.key])"
        class="switch-row"
        :class="{ on: !!(music.activeBotProfile && music.activeBotProfile[s.key]), busy: profileBusy === s.key }"
        :disabled="profileBusy !== null || !music.activeBotProfile"
        @click="music.activeBotProfile && toggleProfile(s.key, !music.activeBotProfile[s.key])"
      >
        <span class="field-text">
          <span class="field-label">{{ s.label }}</span>
          <span class="field-hint">{{ s.hint }}</span>
        </span>
        <span class="switch-track"><span class="switch-knob"></span></span>
      </button>

      <!-- 固定头像管理：当 avatarEnabled 关闭时显示此固定头像 -->
      <div class="avatar-block">
        <div class="field-label">固定头像</div>
        <span class="field-hint">关闭「头像随歌曲封面」时显示此头像（≤200KB，PNG/JPEG/WebP）</span>
        <div class="avatar-row">
          <div class="avatar-preview" :class="{ empty: !music.activeBotAvatarUrl }">
            <img v-if="music.activeBotAvatarUrl" :src="music.activeBotAvatarUrl" alt="固定头像" />
            <span v-else class="avatar-placeholder">{{ music.avatarLoading ? '…' : '无' }}</span>
          </div>
          <div class="avatar-actions">
            <button class="mini-btn" :disabled="avatarBusy" @click="avatarInput?.click()">
              {{ avatarBusy ? '…' : (music.activeBotAvatarUrl ? '更换' : '上传') }}
            </button>
            <button
              v-if="music.activeBotAvatarUrl"
              class="mini-btn mini-btn--ghost mini-btn--danger"
              :disabled="avatarBusy"
              @click="onRemoveAvatar"
            >移除</button>
          </div>
        </div>
        <input ref="avatarInput" type="file" accept="image/png,image/jpeg,image/webp" hidden @change="onPickAvatar" />
      </div>
    </section>
      </div>
    </div>
  </div>
</template>

<style scoped>
.behavior-panel {
  border-top: 1px solid var(--border-subtle);
  padding-top: 12px;
  margin-top: 12px;
  min-width: 0;
  max-width: 100%;
}
.panel-header { margin-bottom: 10px; }
.panel-title-group { display: flex; align-items: baseline; gap: 8px; }
.panel-title { font-size: 0.8em; font-weight: 600; color: var(--text-secondary); margin: 0; }
.panel-sub { font-size: 0.66em; color: var(--text-muted); }

/* ── 二级面板：可折叠头部 ── */
.behavior-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  width: 100%;
  padding: 8px 12px;
  margin-bottom: 2px;
  background: var(--surface-3);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  color: var(--text-secondary);
  font-family: inherit;
  text-align: left;
  cursor: pointer;
  transition: border-color 0.18s var(--ease-out-expo), color 0.18s;
}
.behavior-head:hover { border-color: var(--border-emphasis); color: var(--text-primary); }
.behavior-head:focus-visible { outline: none; border-color: var(--color-primary); box-shadow: var(--glow-primary); }
.behavior-head.open {
  border-color: rgba(var(--color-primary-rgb), 0.45);
  color: var(--color-primary);
}
.bh-head-text { display: flex; align-items: baseline; gap: 8px; min-width: 0; }
.bh-head-right { display: flex; align-items: center; gap: 9px; flex-shrink: 0; }
.bh-summary { font-size: 0.62em; color: var(--text-muted); white-space: nowrap; }
.bh-chev {
  width: 14px; height: 14px; color: var(--text-muted);
  transition: transform 0.22s var(--ease-out-expo), color 0.18s;
}
.behavior-head.open .bh-chev { transform: rotate(180deg); color: var(--color-primary); }

/* 折叠体：grid-template-rows 0fr→1fr 平滑展开（无需已知高度，现代写法） */
.bh-body {
  display: grid;
  grid-template-rows: 0fr;
  transition: grid-template-rows 0.28s var(--ease-out-expo);
}
.bh-body.open { grid-template-rows: 1fr; }
.bh-body-inner {
  overflow: hidden;
  min-height: 0;
  padding-top: 10px;
}

.bh-section {
  background: var(--surface-3);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  padding: 10px;
  margin-bottom: 8px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.bh-section-title { font-size: 0.68em; font-weight: 600; color: var(--color-primary); }

.field-row { display: flex; align-items: center; gap: 8px; }
.field-row--inline { justify-content: space-between; }
.field-text { display: flex; flex-direction: column; gap: 1px; min-width: 0; flex: 1; }
.field-label { font-size: 0.74em; color: var(--text-secondary); }
.field-hint { font-size: 0.62em; color: var(--text-muted); }

/* 单行开关（复用 follow-toggle 视觉语言） */
.switch-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 7px 10px;
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: border-color 0.18s var(--ease-out-expo);
  user-select: none;
  font-family: inherit;
  text-align: left;
  width: 100%;
}
.switch-row:hover:not(:disabled) { border-color: var(--border-emphasis); }
.switch-row:disabled { opacity: 0.55; cursor: default; }
.switch-row.busy { opacity: 0.6; cursor: default; }
.switch-track {
  width: 30px; height: 16px; border-radius: 999px;
  background: var(--surface-4);
  border: 1px solid var(--border-emphasis);
  position: relative; flex-shrink: 0;
  transition: background 0.18s var(--ease-out-expo), border-color 0.18s;
}
.switch-knob {
  position: absolute; top: 1px; left: 1px;
  width: 12px; height: 12px; border-radius: 50%;
  background: var(--text-muted);
  transition: transform 0.18s var(--ease-out-expo), background 0.18s;
}
.switch-row.on .switch-track {
  background: rgba(var(--color-primary-rgb), 0.25);
  border-color: var(--color-primary);
}
.switch-row.on .switch-knob {
  transform: translateX(14px);
  background: var(--color-primary);
}

.idle-input-wrap { display: flex; align-items: center; gap: 4px; flex-shrink: 0; }
.idle-input {
  width: 56px;
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: 4px;
  padding: 4px 7px;
  color: var(--text-primary);
  font-size: 0.74em;
  font-family: inherit;
  outline: none;
  text-align: center;
}
.idle-input:focus { border-color: var(--color-primary); }
.idle-unit { font-size: 0.66em; color: var(--text-muted); }

.warn-line { font-size: 0.6em; color: var(--text-muted); margin: -2px 0 0; line-height: 1.4; }

.create-actions { display: flex; justify-content: flex-end; gap: 7px; }
.submit-btn {
  padding: 4px 14px;
  border: 0;
  border-radius: 6px;
  background: var(--gradient-brand);
  color: var(--text-inverse);
  font-size: 0.72em;
  font-weight: 600;
  cursor: pointer;
}
.submit-btn:disabled { opacity: 0.5; cursor: default; }

.mini-btn {
  padding: 3px 9px;
  border: 1px solid var(--color-primary);
  border-radius: 10px;
  background: transparent;
  color: var(--color-primary);
  font-size: 0.66em;
  cursor: pointer;
  transition: all 0.15s;
}
.mini-btn:hover:not(:disabled) { background: var(--color-primary); color: #fff; }
.mini-btn:disabled { opacity: 0.5; cursor: default; }
.mini-btn--ghost { border-color: var(--border-emphasis); color: var(--text-secondary); }
.mini-btn--ghost:hover:not(:disabled) { background: var(--surface-4); color: var(--text-primary); }
.mini-btn--danger { border-color: var(--color-danger); color: var(--color-danger); }
.mini-btn--danger:hover:not(:disabled) { background: var(--color-danger); color: #fff; }

.avatar-block { display: flex; flex-direction: column; gap: 4px; padding-top: 4px; border-top: 1px dashed var(--border-subtle); margin-top: 2px; }
.avatar-row { display: flex; align-items: center; gap: 10px; margin-top: 2px; }
.avatar-preview {
  width: 48px; height: 48px; border-radius: var(--radius-sm);
  border: 1px solid var(--border-default);
  background: var(--bg-card);
  overflow: hidden; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
}
.avatar-preview img { width: 100%; height: 100%; object-fit: cover; }
.avatar-preview.empty { border-style: dashed; }
.avatar-placeholder { font-size: 0.64em; color: var(--text-muted); }
.avatar-actions { display: flex; gap: 5px; }

@media (max-width: 768px) {
  .mini-btn { padding: 5px 10px; }
  .field-row--inline { flex-wrap: wrap; }
  .behavior-head { padding: 10px; }
  .bh-summary { display: none; }
  .switch-row { min-height: 48px; }
  .create-actions .submit-btn { width: 100%; min-height: 42px; }
}
</style>
