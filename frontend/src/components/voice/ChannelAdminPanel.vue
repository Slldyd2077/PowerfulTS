<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import axios from 'axios'
import api from '@/api/client'

type Channel = { cid: number; pid: number; name: string; hasPassword: boolean; isDefault: boolean }
type Member = { clid: number; cid: number; nickname: string }
type Bot = { id: string; name: string; status: string; ownerNickname: string }
const channels = ref<Channel[]>([])
const members = ref<Member[]>([])
const bots = ref<Bot[]>([])
const busy = ref(false)
const error = ref('')
const selectedBot = ref('')
const selectedMember = ref<number>()
const targetChannel = ref<number>()
const botPassword = ref('')
const replaceBotPassword = ref(false)
const dialog = ref(false)
const editing = ref<Channel | null>(null)
const name = ref('')
const parent = ref(0)
const password = ref('')
const replacePassword = ref(false)
const selectedMemberInfo = computed(() => members.value.find((member) => member.clid === selectedMember.value))
const channelName = (cid: number) => channels.value.find((channel) => channel.cid === cid)?.name || `频道 #${cid}`

function message(e: unknown) {
  return axios.isAxiosError(e) ? e.response?.data?.detail || '频道操作失败，请检查服务连接' : e instanceof Error ? e.message : '操作失败'
}
async function refresh() {
  const [overview, list] = await Promise.all([api.get('/admin/channels'), api.get('/admin/channels/bots')])
  channels.value = overview.data.channels
  members.value = overview.data.members
  bots.value = list.data.bots
}
async function perform(action: () => Promise<unknown>) {
  if (busy.value) return
  busy.value = true
  error.value = ''
  try { await action(); await refresh() }
  catch (e) { error.value = message(e) }
  finally { busy.value = false }
}
function edit(channel: Channel | null) {
  editing.value = channel
  name.value = channel?.name || ''
  parent.value = 0
  password.value = ''
  replacePassword.value = !channel
  dialog.value = true
}
async function save() {
  await perform(async () => {
    const data = { name: name.value.trim(), ...(replacePassword.value ? { password: password.value } : {}) }
    if (editing.value) await api.put(`/admin/channels/${editing.value.cid}`, data)
    else await api.post('/admin/channels', { ...data, parentId: parent.value })
    dialog.value = false
    ElMessage.success('频道已保存')
  })
}
async function remove(channel: Channel) {
  try { await ElMessageBox.confirm(`删除空频道「${channel.name}」？此操作不可恢复。`, '删除频道', { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }) }
  catch { return }
  await perform(async () => { await api.delete(`/admin/channels/${channel.cid}`); ElMessage.success('频道已删除') })
}
async function botChannel(saveDefault: boolean) {
  if (!selectedBot.value || !targetChannel.value) return
  await perform(async () => {
    const { data } = await api.put(`/admin/channels/bots/${selectedBot.value}`, {
      cid: targetChannel.value, saveDefault, ...(replaceBotPassword.value ? { password: botPassword.value } : {}),
    })
    ElMessage.success(data.detail)
  })
}
async function moveMember() {
  if (!selectedMember.value || !targetChannel.value) return
  await perform(async () => {
    await api.post(`/admin/channels/members/${selectedMember.value}/move`, { cid: targetChannel.value })
    ElMessage.success('成员已移动')
  })
}
async function kickMember() {
  if (!selectedMember.value) return
  const member = selectedMemberInfo.value
  if (!member) return
  try {
    await ElMessageBox.confirm(`将「${member.nickname}」移出 TeamSpeak 服务器？对方可以重新加入。`, '移除成员', {
      type: 'warning', confirmButtonText: '移除', cancelButtonText: '取消',
    })
  } catch { return }
  await perform(async () => {
    await api.post(`/admin/channels/members/${member.clid}/kick`, { reason: '由管理员从频道管理面板移除' })
    selectedMember.value = undefined
    ElMessage.success('成员已移除')
  })
}
onMounted(() => { void perform(async () => {}) })
</script>

<template>
  <section id="channel-management" class="channel-admin">
    <header><div><h2>频道管理</h2><p>管理员 · 管理服务器频道与所有成员的音乐机器人</p></div><button :disabled="busy" @click="perform(async () => {})">刷新</button></header>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <div class="section-head"><h3>服务器频道</h3><button :disabled="busy" @click="edit(null)">新建频道</button></div>
    <ul class="channels">
      <li v-for="channel in channels" :key="channel.cid">
        <span>{{ channel.name }} <small>#{{ channel.cid }}{{ channel.isDefault ? ' · 默认' : '' }}{{ channel.hasPassword ? ' · 有密码' : '' }}</small></span>
        <div><button :disabled="busy" @click="edit(channel)">编辑</button><button class="danger" :disabled="busy || channel.isDefault" @click="remove(channel)">删除</button></div>
      </li>
    </ul>
    <p v-if="!channels.length && !busy">暂无频道，或 ServerQuery 未连接。</p>
    <h3>移动与默认频道</h3>
    <label>目标频道<el-select v-model="targetChannel" aria-label="管理目标频道" :disabled="busy" placeholder="选择频道"><el-option v-for="c in channels" :key="c.cid" :value="c.cid" :label="`${c.name} · #${c.cid}`" /></el-select></label>
    <label>音乐机器人<el-select v-model="selectedBot" aria-label="管理音乐机器人" :disabled="busy" placeholder="选择任一成员的机器人"><el-option v-for="b in bots" :key="b.id" :value="b.id" :label="`${b.name} · ${b.ownerNickname} · ${b.status === 'connected' ? '在线' : '离线'}`" /></el-select></label>
    <label class="check"><input v-model="replaceBotPassword" type="checkbox" :disabled="busy">更新机器人保存的频道密码</label>
    <label v-if="replaceBotPassword">频道密码<input v-model="botPassword" type="password" :disabled="busy" placeholder="留空表示无密码"></label>
    <div class="actions"><button :disabled="busy || !selectedBot || !targetChannel" @click="botChannel(false)">立即移动机器人</button><button :disabled="busy || !selectedBot || !targetChannel" @click="botChannel(true)">保存默认频道</button></div>
    <p>立即移动需要机器人在线；保存默认频道在下次重连生效。播放跟随开启时，机器人可能随点歌者再次移动。</p>
    <h3>在线成员</h3>
    <label>选择成员<el-select v-model="selectedMember" aria-label="管理在线成员" :disabled="busy" placeholder="选择成员"><el-option v-for="m in members" :key="m.clid" :value="m.clid" :label="`${m.nickname} · ${channelName(m.cid)}`" /></el-select></label>
    <p v-if="selectedMemberInfo" class="member-location">当前频道：{{ channelName(selectedMemberInfo.cid) }} · 客户端 #{{ selectedMemberInfo.clid }}</p>
    <div class="actions">
      <button :disabled="busy || !selectedMember || !targetChannel" @click="moveMember">移动成员到目标频道</button>
      <button class="danger" :disabled="busy || !selectedMember" @click="kickMember">移除成员</button>
    </div>
    <p>移除会让成员立即断开 TeamSpeak 连接，但不会删除账号或封禁；对方可重新登录。</p>
    <el-dialog v-model="dialog" :title="editing ? '编辑频道' : '新建频道'" width="min(440px, 92vw)" append-to-body :close-on-click-modal="!busy" :show-close="!busy">
      <div class="channel-form">
        <label>频道名称<input v-model="name" maxlength="40" :disabled="busy"></label>
        <label v-if="!editing">父频道<el-select v-model="parent" :disabled="busy"><el-option :value="0" label="顶层频道" /><el-option v-for="c in channels" :key="c.cid" :value="c.cid" :label="c.name" /></el-select></label>
        <label v-if="editing" class="check"><input v-model="replacePassword" type="checkbox" :disabled="busy">修改频道密码</label>
        <label v-if="replacePassword">频道密码<input v-model="password" type="password" maxlength="128" :disabled="busy" placeholder="留空表示移除密码"></label>
        <p v-if="error" class="error" role="alert">{{ error }}</p>
      </div>
      <template #footer><button :disabled="busy" @click="dialog = false">取消</button><button :disabled="busy || !name.trim()" @click="save">保存</button></template>
    </el-dialog>
  </section>
</template>

<style scoped>
.channel-admin { padding: 20px; border: 1px solid var(--border-subtle); border-radius: var(--radius-lg); background: var(--bg-card); min-width: 0; display: grid; gap: 14px; }
header, .section-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
h2, h3 { margin: 0; color: var(--text-primary); font-size: 15px; }
h3 { font-size: 13px; margin-top: 8px; }
p, small { margin: 0; color: var(--text-muted); font-size: 12px; line-height: 1.6; }
.member-location { color: var(--text-secondary); }
header p { margin-top: 5px; }
label { display: grid; gap: 7px; color: var(--text-secondary); font-size: 12px; min-width: 0; }
.check { display: flex; align-items: center; gap: 8px; }
button { border: 1px solid var(--border-subtle); border-radius: 8px; padding: 8px 12px; background: var(--bg-elevated); color: var(--text-secondary); cursor: pointer; font-size: 12px; }
button:disabled { opacity: .45; cursor: default; }
.danger, .error { color: var(--color-danger); }
.channels { list-style: none; margin: 0; padding: 0; max-height: 320px; overflow: auto; }
.channels li { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 10px 0; border-bottom: 1px solid var(--border-subtle); font-size: 13px; color: var(--text-secondary); }
.channels li > span { min-width: 0; overflow-wrap: anywhere; }
.channels li > div, .actions { display: flex; gap: 8px; flex-wrap: wrap; }
.channels li > div { flex-shrink: 0; }
input:not([type=checkbox]) { min-width: 0; width: 100%; box-sizing: border-box; border: 1px solid var(--border-subtle); border-radius: 8px; padding: 10px; background: var(--bg-elevated); color: var(--text-primary); }
.channel-form { display: grid; gap: 16px; }
:deep(.el-select) { width: 100%; min-width: 0; }
</style>
