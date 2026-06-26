<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useMusicStore } from '@/stores/music'
import type { BotInfo, BotCreate } from '@/api/music'

const music = useMusicStore()

const bots = computed(() => music.bots)
const hasBots = computed(() => bots.value.length > 0)

const showCreate = ref(false)
const creating = ref(false)
const form = ref<BotCreate>({
  name: '',
  nickname: 'PowerfulTS',
  serverAddress: 'host.docker.internal',
  serverPort: 9987,
  defaultChannel: '',
  channelPassword: '',
  serverPassword: '',
})
const errors = ref<Record<string, string>>({})

// 每行启停/删除 loading
const busy = ref<Record<string, 'start' | 'stop' | 'delete' | undefined>>({})

function statusText(s: string): string {
  return s === 'connected' ? '已连接' : '离线'
}

function resetForm() {
  form.value = {
    name: '', nickname: 'PowerfulTS', serverAddress: 'host.docker.internal',
    serverPort: 9987, defaultChannel: '', channelPassword: '', serverPassword: '',
  }
}

async function submitCreate() {
  errors.value = {}
  if (!form.value.name.trim()) errors.value.name = '必填'
  if (!form.value.nickname.trim()) errors.value.nickname = '必填'
  if (!form.value.serverAddress.trim()) errors.value.serverAddress = '必填'
  if (Object.keys(errors.value).length) return
  creating.value = true
  try {
    // 创建后不自动 start（start 是异步 TS 连接，语义分离更清晰）
    const created = await music.createBot({ ...form.value })
    ElMessage.success(`Bot「${created.name}」已创建，请在列表点「启动」连接 TS`)
    showCreate.value = false
    resetForm()
    await music.setActiveBot(created.id)
  } catch (e: unknown) {
    ElMessage.error(e instanceof Error ? e.message : '创建失败，请检查 TSMusicBot 是否在线')
  } finally {
    creating.value = false
  }
}

async function onStart(b: BotInfo) {
  busy.value[b.id] = 'start'
  try {
    await music.startBot(b.id)
    ElMessage.success(`${b.name} 连接请求已发送`)
  } catch {
    ElMessage.error(`${b.name} 连接失败：请检查 TS 地址/端口/密码`)
  } finally {
    busy.value[b.id] = undefined
  }
}

async function onStop(b: BotInfo) {
  busy.value[b.id] = 'stop'
  try {
    await music.stopBot(b.id)
  } finally {
    busy.value[b.id] = undefined
  }
}

async function onDelete(b: BotInfo) {
  try {
    await ElMessageBox.confirm(`确定删除「${b.name}」？此操作不可恢复。`, '删除 Bot', {
      type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消',
    })
  } catch {
    return // 用户取消
  }
  busy.value[b.id] = 'delete'
  try {
    await music.deleteBot(b.id)
    ElMessage.success(`已删除 ${b.name}`)
  } finally {
    busy.value[b.id] = undefined
  }
}

onMounted(() => music.fetchBots())
</script>

<template>
  <div class="bot-manager">
    <div class="panel-header">
      <div class="panel-title-group">
        <h2 class="panel-title">TS Bot</h2>
        <span class="panel-sub label-mono">INSTANCES</span>
      </div>
    </div>

    <!-- active 选择器 -->
    <div v-if="hasBots" class="active-select">
      <span class="status-dot" :class="music.activeBot?.status === 'connected' ? 'dot-on' : 'dot-off'"></span>
      <select
        class="bot-select"
        :value="music.activeBotId"
        @change="music.setActiveBot(($event.target as HTMLSelectElement).value)"
      >
        <option v-for="b in bots" :key="b.id" :value="b.id">{{ b.name }} · {{ statusText(b.status) }}</option>
      </select>
    </div>

    <!-- 列表 -->
    <div v-if="hasBots" class="bot-list">
      <div v-for="b in bots" :key="b.id" class="bot-row" :class="{ active: b.id === music.activeBotId }">
        <span class="bot-dot" :class="b.status === 'connected' ? 'dot-on' : 'dot-off'"></span>
        <div class="bot-info">
          <span class="bot-name">
            {{ b.name }}
            <span v-if="b.default" class="default-tag">默认</span>
          </span>
          <span class="bot-status">{{ statusText(b.status) }}{{ b.playing ? ' · 播放中' : '' }}</span>
        </div>
        <div class="bot-actions">
          <button v-if="b.status !== 'connected'" class="mini-btn" :disabled="!!busy[b.id]" @click="onStart(b)">
            {{ busy[b.id] === 'start' ? '…' : '启动' }}
          </button>
          <button v-else class="mini-btn mini-btn--ghost" :disabled="!!busy[b.id]" @click="onStop(b)">
            {{ busy[b.id] === 'stop' ? '…' : '停止' }}
          </button>
          <button class="mini-btn mini-btn--ghost mini-btn--danger" :disabled="!!busy[b.id]" @click="onDelete(b)">删</button>
        </div>
      </div>
    </div>

    <!-- 空态 -->
    <div v-else class="bot-empty">
      <p>还没有 Bot 实例</p>
    </div>

    <!-- 新建 -->
    <button v-if="hasBots && !showCreate" class="add-btn" @click="showCreate = true">+ 新建 Bot</button>
    <button v-else-if="!hasBots && !showCreate" class="add-btn" @click="showCreate = true">+ 新建第一个 Bot</button>

    <div v-if="showCreate" class="create-form">
      <div class="field">
        <label>Bot 名称 *</label>
        <input v-model="form.name" :class="{ err: errors.name }" />
      </div>
      <div class="field">
        <label>TS 昵称 *</label>
        <input v-model="form.nickname" :class="{ err: errors.nickname }" />
      </div>
      <div class="field">
        <label>TS 服务器地址 *</label>
        <input v-model="form.serverAddress" :class="{ err: errors.serverAddress }" placeholder="host.docker.internal" />
      </div>
      <div class="field">
        <label>端口</label>
        <input v-model.number="form.serverPort" type="number" />
      </div>
      <div class="field">
        <label>默认频道</label>
        <input v-model="form.defaultChannel" placeholder="留空进服务器根频道" />
      </div>
      <div class="field">
        <label>频道密码</label>
        <input v-model="form.channelPassword" type="password" />
      </div>
      <div class="field">
        <label>服务器密码</label>
        <input v-model="form.serverPassword" type="password" />
      </div>
      <div class="create-actions">
        <button class="mini-btn mini-btn--ghost" @click="showCreate = false">取消</button>
        <button class="submit-btn" :disabled="creating" @click="submitCreate">{{ creating ? '创建中…' : '创建' }}</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.bot-manager {
  border-top: 1px solid var(--border-subtle);
  padding-top: 12px;
}
.panel-header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 10px;
}
.panel-title-group { display: flex; align-items: baseline; gap: 8px; }
.panel-title { font-size: 0.8em; font-weight: 600; color: var(--text-secondary); margin: 0; }
.panel-sub { font-size: 0.66em; color: var(--text-muted); }

.active-select { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
.bot-select {
  flex: 1;
  min-width: 0;
  background: var(--surface-3);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  padding: 5px 8px;
  color: var(--text-primary);
  font-size: 0.78em;
  font-family: inherit;
  outline: none;
}
.bot-select:focus { border-color: var(--color-primary); }

.status-dot,
.bot-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.dot-on { background: var(--color-success); }
.dot-off { background: var(--text-muted); }

.bot-list { display: flex; flex-direction: column; gap: 4px; }
.bot-row {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 6px 4px;
  border-radius: var(--radius-sm);
}
.bot-row:hover { background: var(--surface-4); }
.bot-row.active { background: var(--surface-4); }
.bot-info { display: flex; flex-direction: column; gap: 1px; flex: 1; min-width: 0; }
.bot-name { font-size: 0.78em; font-weight: 600; color: var(--text-primary); display: flex; align-items: center; gap: 5px; }
.default-tag {
  font-size: 0.8em;
  color: var(--color-primary);
  border: 1px solid var(--color-primary);
  border-radius: 3px;
  padding: 0 4px;
}
.bot-status { font-size: 0.64em; color: var(--text-muted); }
.bot-actions { display: flex; gap: 4px; flex-shrink: 0; }

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

.bot-empty { text-align: center; color: var(--text-muted); padding: 18px 10px; font-size: 0.78em; }

.add-btn {
  width: 100%;
  margin-top: 8px;
  padding: 6px;
  border: 1px dashed var(--border-emphasis);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-secondary);
  font-size: 0.72em;
  cursor: pointer;
  transition: all 0.15s;
}
.add-btn:hover { border-color: var(--color-primary); color: var(--color-primary); }

.create-form {
  margin-top: 8px;
  padding: 10px;
  background: var(--surface-3);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  display: flex;
  flex-direction: column;
  gap: 7px;
}
.field { display: flex; flex-direction: column; gap: 2px; }
.field label { font-size: 0.64em; color: var(--text-muted); }
.field input {
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: 4px;
  padding: 4px 7px;
  color: var(--text-primary);
  font-size: 0.74em;
  font-family: inherit;
  outline: none;
}
.field input:focus { border-color: var(--color-primary); }
.field input.err { border-color: var(--color-danger); }
.create-actions { display: flex; justify-content: flex-end; gap: 7px; margin-top: 3px; }
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
</style>
