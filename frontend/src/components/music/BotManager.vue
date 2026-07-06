<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useMusicStore } from '@/stores/music'
import type { BotInfo, BotCreate } from '@/api/music'
import { shareBot, unshareBot, getMyShares, updateBot, getBotConfig, type MyShare } from '@/api/music'
import { getFriends, type Friend } from '@/api/social'
import BotBehaviorPanel from './BotBehaviorPanel.vue'

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

// active 实例下拉开关（自建，避免原生 <select> 弹层古老）
const botMenuOpen = ref(false)
async function chooseBot(id: string) {
  botMenuOpen.value = false
  try {
    await music.setActiveBot(id)
  } catch {
    ElMessage.error('切换 Bot 失败')
  }
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

// ── 共享管理 ──
const showShare = ref(false)
const shareTarget = ref<BotInfo | null>(null)
const friends = ref<Friend[]>([])
const selectedFriend = ref<string>('') // ts_nickname
const myShares = ref<MyShare[]>([])

async function onShare(b: BotInfo) {
  shareTarget.value = b
  selectedFriend.value = ''
  try {
    const res = await getFriends()
    friends.value = res.friends
  } catch {
    friends.value = []
  }
  showShare.value = true
}
async function confirmShare() {
  if (!shareTarget.value || !selectedFriend.value) return
  try {
    await shareBot(shareTarget.value.id, selectedFriend.value)
    ElMessage.success(`已共享给 ${selectedFriend.value}`)
    showShare.value = false
    await fetchMyShares()
  } catch (e: unknown) {
    ElMessage.error(e instanceof Error ? e.message : '共享失败')
  }
}
async function onUnshare(botId: string, friendAccountId: number, nickname: string) {
  try {
    await unshareBot(botId, friendAccountId)
    ElMessage.success(`已撤销对 ${nickname} 的共享`)
    await fetchMyShares()
  } catch {
    ElMessage.error('撤销失败')
  }
}
async function fetchMyShares() {
  try {
    const res = await getMyShares()
    myShares.value = res.shares
  } catch {
    myShares.value = []
  }
}

// ── 编辑 bot 配置 ──
const showEdit = ref(false)
const editTarget = ref<BotInfo | null>(null)
const editForm = ref<BotCreate>({ name: '', nickname: '', serverAddress: '', serverPort: 9987, defaultChannel: '', channelPassword: '', serverPassword: '' })
const editBusy = ref(false)

async function onEdit(b: BotInfo) {
  editTarget.value = b
  showEdit.value = true
  editBusy.value = true
  try {
    const cfg = await getBotConfig(b.id)
    editForm.value = {
      name: cfg.name || b.name,
      nickname: cfg.nickname || '',
      serverAddress: cfg.serverAddress || '',
      serverPort: cfg.serverPort || 9987,
      defaultChannel: cfg.defaultChannel || '',
      channelPassword: '',
      serverPassword: '',
    }
  } catch {
    editForm.value = { name: b.name, nickname: '', serverAddress: '', serverPort: 9987, defaultChannel: '', channelPassword: '', serverPassword: '' }
  } finally {
    editBusy.value = false
  }
}

async function submitEdit() {
  if (!editTarget.value) return
  editBusy.value = true
  try {
    await updateBot(editTarget.value.id, editForm.value)
    ElMessage.success('已更新，连接类参数需重启 bot 生效')
    showEdit.value = false
    await music.fetchBots()
  } catch (e: unknown) {
    ElMessage.error(e instanceof Error ? e.message : '更新失败')
  } finally {
    editBusy.value = false
  }
}

// bot 名查（共享列表展示用）
const botNameById = computed(() => {
  const m: Record<string, string> = {}
  for (const b of bots.value) m[b.id] = b.name
  return m
})

onMounted(() => {
  music.fetchBots()
  music.fetchFollowSetting()
  fetchMyShares()
})
</script>

<template>
  <div class="bot-manager">
    <div class="panel-header">
      <div class="panel-title-group">
        <h2 class="panel-title">TS Bot</h2>
        <span class="panel-sub label-mono">INSTANCES</span>
      </div>
    </div>

    <!-- active 选择器（自建下拉，避免原生 <select> 弹层古老） -->
    <div v-if="hasBots" class="active-select">
      <button
        type="button"
        class="bot-trigger"
        :class="{ open: botMenuOpen }"
        aria-haspopup="listbox"
        :aria-expanded="botMenuOpen"
        @click="botMenuOpen = !botMenuOpen"
        @keydown.esc="botMenuOpen = false"
      >
        <span class="status-dot" :class="music.activeBot?.status === 'connected' ? 'dot-on' : 'dot-off'"></span>
        <span class="bot-trigger-text">
          {{ music.activeBot?.name || '选择 Bot' }}
          <span class="bot-trigger-status">· {{ statusText(music.activeBot?.status || '') }}</span>
        </span>
        <svg class="bot-chev" :class="{ open: botMenuOpen }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9l6 6 6-6" /></svg>
      </button>

      <transition name="bot-menu">
        <div v-if="botMenuOpen" class="bot-menu" role="listbox">
          <button
            v-for="b in bots"
            :key="b.id"
            type="button"
            class="bot-option"
            :class="{ active: b.id === music.activeBotId }"
            role="option"
            :aria-selected="b.id === music.activeBotId"
            @click="chooseBot(b.id)"
          >
            <span class="bot-dot" :class="b.status === 'connected' ? 'dot-on' : 'dot-off'"></span>
            <span class="bot-option-name">
              {{ b.name }}
              <span v-if="b.shared" class="shared-tag">共享·{{ b.ownerNickname }}</span>
            </span>
            <span class="bot-option-status">{{ statusText(b.status) }}{{ b.playing ? ' · 播放中' : '' }}</span>
            <svg v-if="b.id === music.activeBotId" class="bot-check" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M5 13l4 4L19 7" /></svg>
          </button>
        </div>
      </transition>

      <!-- 透明遮罩：点击外部收起 -->
      <div v-if="botMenuOpen" class="bot-backdrop" @click="botMenuOpen = false"></div>
    </div>

    <!-- 列表 -->
    <div v-if="hasBots" class="bot-list">
      <div v-for="b in bots" :key="b.id" class="bot-row" :class="{ active: b.id === music.activeBotId }">
        <span class="bot-dot" :class="b.status === 'connected' ? 'dot-on' : 'dot-off'"></span>
        <div class="bot-info">
          <span class="bot-name">
            {{ b.name }}
            <span v-if="b.default" class="default-tag">默认</span>
            <span v-if="b.shared" class="shared-tag">共享·{{ b.ownerNickname }}</span>
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
          <button v-if="!b.shared" class="mini-btn mini-btn--ghost" :disabled="!!busy[b.id]" @click="onEdit(b)">编辑</button>
          <button v-if="!b.shared" class="mini-btn mini-btn--ghost" :disabled="!!busy[b.id]" @click="onShare(b)">共享</button>
          <button v-if="!b.shared" class="mini-btn mini-btn--ghost mini-btn--danger" :disabled="!!busy[b.id]" @click="onDelete(b)">删</button>
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

    <!-- 我的共享（owner 管理：撤销） -->
    <div v-if="myShares.length" class="my-shares">
      <div class="shares-title">我的共享</div>
      <div v-for="s in myShares" :key="s.botId" class="share-group">
        <span class="share-bot">{{ botNameById[s.botId] || s.botId.slice(0, 8) }}</span>
        <span v-for="t in s.sharedTo" :key="t.accountId" class="share-chip">
          {{ t.nickname }}
          <button class="chip-x" title="撤销共享" @click="onUnshare(s.botId, t.accountId, t.nickname)">×</button>
        </span>
      </div>
    </div>

    <!-- 共享给好友（dialog） -->
    <el-dialog v-model="showShare" :title="`共享「${shareTarget?.name}」给好友`" width="340" append-to-body>
      <div v-if="!friends.length" class="no-friends">还没有好友，先去「好友」页添加</div>
      <div v-else class="friend-pick">
        <label
          v-for="f in friends"
          :key="f.ts_nickname"
          class="friend-opt"
          :class="{ on: selectedFriend === f.ts_nickname }"
        >
          <input type="radio" :value="f.ts_nickname" v-model="selectedFriend" />
          <span>{{ f.ts_nickname }}</span>
          <span class="friend-dot" :class="f.online_status === 'online' ? 'dot-on' : 'dot-off'"></span>
        </label>
      </div>
      <template #footer>
        <button class="mini-btn mini-btn--ghost" @click="showShare = false">取消</button>
        <button class="submit-btn" :disabled="!selectedFriend" @click="confirmShare">共享</button>
      </template>
    </el-dialog>

    <!-- 编辑 bot 配置 -->
    <el-dialog v-model="showEdit" :title="`编辑「${editTarget?.name}」`" width="360" append-to-body>
      <div class="create-form" style="margin-top:0">
        <div class="field"><label>Bot 名称</label><input v-model="editForm.name" /></div>
        <div class="field"><label>TS 昵称</label><input v-model="editForm.nickname" /></div>
        <div class="field"><label>TS 服务器地址</label><input v-model="editForm.serverAddress" placeholder="host.docker.internal" /></div>
        <div class="field"><label>端口</label><input v-model.number="editForm.serverPort" type="number" /></div>
        <div class="field"><label>默认频道</label><input v-model="editForm.defaultChannel" placeholder="留空进根频道" /></div>
        <div class="field"><label>频道密码</label><input v-model="editForm.channelPassword" type="password" placeholder="留空不改" /></div>
        <div class="field"><label>服务器密码</label><input v-model="editForm.serverPassword" type="password" placeholder="留空不改" /></div>
        <p class="warn-line" style="font-size:0.62em;color:var(--text-muted);margin:0">连接类参数（地址/端口/昵称/频道）需先停止 bot 再改才生效</p>
      </div>
      <template #footer>
        <button class="mini-btn mini-btn--ghost" @click="showEdit = false">取消</button>
        <button class="submit-btn" :disabled="editBusy" @click="submitEdit">{{ editBusy ? '保存中…' : '保存' }}</button>
      </template>
    </el-dialog>

    <!-- 机器人行为设置（空闲下线 / 头像 / 昵称等） -->
    <BotBehaviorPanel v-if="hasBots" />
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

.active-select { position: relative; display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }

/* 触发器 */
.bot-trigger {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  background: var(--surface-3);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  padding: 6px 9px;
  color: var(--text-primary);
  font-size: 0.78em;
  font-family: inherit;
  cursor: pointer;
  transition: border-color 0.18s var(--ease-out-expo), box-shadow 0.18s;
}
.bot-trigger:hover { border-color: var(--border-emphasis); }
.bot-trigger.open { border-color: var(--color-primary); box-shadow: var(--glow-primary); }
.bot-trigger-text { flex: 1; min-width: 0; text-align: left; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.bot-trigger-status { color: var(--text-muted); }
.bot-chev { width: 14px; height: 14px; flex-shrink: 0; color: var(--text-muted); transition: transform 0.18s var(--ease-out-expo), color 0.18s; }
.bot-chev.open { transform: rotate(180deg); color: var(--color-primary); }

/* 弹层 */
.bot-menu {
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  right: 0;
  z-index: 50;
  display: flex;
  flex-direction: column;
  background: var(--surface-2);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-lg);
  padding: 4px;
}
.bot-option {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 8px;
  border: 0;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-secondary);
  font-size: 0.76em;
  font-family: inherit;
  text-align: left;
  cursor: pointer;
  transition: background 0.14s, color 0.14s;
}
.bot-option:hover { background: var(--surface-4); color: var(--text-primary); }
.bot-option.active { background: rgba(45, 212, 191, 0.12); color: var(--color-primary); }
.bot-option-name { font-weight: 600; }
.bot-option-status { margin-left: auto; color: var(--text-muted); font-size: 0.92em; }
.bot-option.active .bot-option-status { color: var(--color-primary); opacity: 0.8; }
.bot-check { width: 14px; height: 14px; flex-shrink: 0; }

/* 点击外部收起的透明遮罩（在弹层之下） */
.bot-backdrop { position: fixed; inset: 0; z-index: 40; }

/* 弹层进出过渡 */
.bot-menu-enter-from { opacity: 0; transform: translateY(-4px); }
.bot-menu-enter-active,
.bot-menu-leave-active { transition: opacity 0.15s var(--ease-out-expo), transform 0.15s var(--ease-out-expo); }
.bot-menu-leave-to { opacity: 0; transform: translateY(-4px); }

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
.shared-tag {
  font-size: 0.78em;
  color: var(--color-accent, #60a5fa);
  border: 1px solid var(--color-accent, #60a5fa);
  border-radius: 3px;
  padding: 0 4px;
  font-weight: 500;
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

/* 我的共享 */
.my-shares { margin-top: 10px; padding-top: 8px; border-top: 1px solid var(--border-subtle); }
.shares-title { font-size: 0.66em; color: var(--text-muted); margin-bottom: 5px; }
.share-group { display: flex; align-items: center; flex-wrap: wrap; gap: 5px; padding: 3px 0; }
.share-bot { font-size: 0.72em; font-weight: 600; color: var(--text-secondary); min-width: 60px; }
.share-chip {
  display: inline-flex; align-items: center; gap: 4px;
  font-size: 0.68em; color: var(--text-secondary);
  background: var(--surface-4); border: 1px solid var(--border-default);
  border-radius: 999px; padding: 1px 4px 1px 8px;
}
.chip-x {
  width: 16px; height: 16px; border: 0; border-radius: 50%;
  background: transparent; color: var(--text-muted); cursor: pointer; font-size: 1.1em; line-height: 1;
}
.chip-x:hover { color: var(--color-danger); }

/* 好友选择 dialog */
.no-friends { text-align: center; color: var(--text-muted); padding: 16px; font-size: 0.8em; }
.friend-pick { display: flex; flex-direction: column; gap: 4px; max-height: 260px; overflow-y: auto; }
.friend-opt {
  display: flex; align-items: center; gap: 8px;
  padding: 6px 8px; border-radius: var(--radius-sm); cursor: pointer;
  font-size: 0.82em; color: var(--text-secondary);
}
.friend-opt:hover { background: var(--surface-4); }
.friend-opt.on { background: rgba(45, 212, 191, 0.12); color: var(--color-primary); }
.friend-opt input { accent-color: var(--color-primary); }
.friend-dot { width: 7px; height: 7px; border-radius: 50%; margin-left: auto; }

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

/* 移动端：加大按钮触摸区、列表行允许折行 */
@media (max-width: 768px) {
  .mini-btn { padding: 5px 10px; }
  .bot-row { flex-wrap: wrap; }
}
</style>
