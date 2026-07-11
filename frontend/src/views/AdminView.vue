<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import {
  getAdminSettings, putAdminSettings, checkNapcatStatus, getMemberNotifications, putMemberNotifications,
  getFriendMessageTemplates, getNotificationMessageTemplates,
  type SettingItem, type NapcatStatus, type MemberNotification, type MessageTemplates, type NotificationMessageTemplates,
} from '@/api/admin'

const auth = useAuthStore()
const loading = ref(false)
const saving = ref(false)
const settings = ref<Record<string, SettingItem>>({})
const form = reactive<Record<string, string>>({})
const memberNotifications = ref<MemberNotification[]>([])
const memberNotificationsLoading = ref(false)
const savingMemberId = ref<number | null>(null)
const napcatEnabled = ref(false)
const friendTemplates = ref<MessageTemplates | null>(null)
const notificationTemplates = ref<NotificationMessageTemplates | null>(null)
const templatesLoading = ref(false)
const savingTemplates = ref(false)

async function load() {
  loading.value = true
  try {
    const res = await getAdminSettings()
    settings.value = res.settings
    Object.keys(res.settings).forEach((k) => { form[k] = res.settings[k].value })
  } catch {
    ElMessage.error('加载设置失败')
  } finally {
    loading.value = false
  }
}

async function loadMemberNotifications() {
  memberNotificationsLoading.value = true
  try {
    const res = await getMemberNotifications()
    memberNotifications.value = res.members
    napcatEnabled.value = res.napcat_enabled
  } catch {
    ElMessage.error('加载成员通知设置失败')
  } finally {
    memberNotificationsLoading.value = false
  }
}

async function loadMessageTemplates() {
  templatesLoading.value = true
  try {
    const [friendRes, notificationRes] = await Promise.all([
      getFriendMessageTemplates(),
      getNotificationMessageTemplates()
    ])
    friendTemplates.value = friendRes
    notificationTemplates.value = notificationRes
  } catch {
    ElMessage.error('加载消息模板失败')
  } finally {
    templatesLoading.value = false
  }
}

async function saveMessageTemplates() {
  if (!friendTemplates.value || !notificationTemplates.value) return

  savingTemplates.value = true
  try {
    const items: Record<string, string> = {
      'friend_add_ts_message': friendTemplates.value.friend_add_ts_message,
      'friend_add_qq_message': friendTemplates.value.friend_add_qq_message,
      'friend_online_notice_message': friendTemplates.value.friend_online_notice_message,
      'friend_online_notice': notificationTemplates.value.friend_online_notice,
      'server_online_notice': notificationTemplates.value.server_online_notice,
      'server_first_join_notice': notificationTemplates.value.server_first_join_notice,
    }

    await putAdminSettings(items)
    ElMessage.success('消息模板已保存')
    await loadMessageTemplates()
  } catch (e: unknown) {
    ElMessage.error(e instanceof Error ? e.message : '保存消息模板失败')
  } finally {
    savingTemplates.value = false
  }
}

async function saveMemberNotifications(member: MemberNotification) {
  savingMemberId.value = member.id
  try {
    await putMemberNotifications(member.id, {
      notify_server_online: member.notify_server_online,
      notify_server_first_join: member.notify_server_first_join,
      notification_channel: member.notification_channel,
    })
    ElMessage.success(`已保存 ${member.ts_nickname} 的通知设置`)
  } catch (e: unknown) {
    ElMessage.error(e instanceof Error ? e.message : '保存成员通知设置失败')
    await loadMemberNotifications()
  } finally {
    savingMemberId.value = null
  }
}

async function save() {
  // 只提交改动的项；敏感项若值仍是 ****（未改）不提交
  const items: Record<string, string> = {}
  Object.keys(form).forEach((k) => {
    const orig = settings.value[k]?.value
    if (form[k] !== orig) items[k] = form[k]
  })
  if (!Object.keys(items).length) {
    ElMessage.info('没有改动')
    return
  }
  saving.value = true
  try {
    const res = await putAdminSettings(items)
    if (res.need_restart) {
      ElMessage.warning('已保存。TS3 / CORS 改动需重启后端才生效')
    } else if (res.reloaded.length) {
      ElMessage.success(`已保存并热重载: ${res.reloaded.join(', ')}`)
    } else {
      ElMessage.success('已保存')
    }
    await load()
  } catch (e: unknown) {
    ElMessage.error(e instanceof Error ? e.message : '保存失败')
  } finally {
    saving.value = false
  }
}

const napcatStatus = ref<NapcatStatus | null>(null)
const checkingNapcat = ref(false)
async function checkNapcat() {
  checkingNapcat.value = true
  try {
    napcatStatus.value = await checkNapcatStatus()
  } catch (e: unknown) {
    napcatStatus.value = { connected: false, error: e instanceof Error ? e.message : '检测失败' }
  } finally {
    checkingNapcat.value = false
  }
}

onMounted(() => {
  load()
  loadMemberNotifications()
  loadMessageTemplates()
})
</script>

<template>
  <div v-if="!auth.isAdmin" class="no-admin">
    <p>需要管理员权限才能访问此页面</p>
  </div>
  <div v-else class="admin-panel panel">
    <div class="panel-header">
      <div class="panel-title-group">
        <h2 class="panel-title">系统设置</h2>
        <span class="panel-sub label-mono">ADMIN</span>
      </div>
    </div>

    <!-- NapCat 连接状态检测 -->
    <div class="napcat-status-card" :class="{ ok: napcatStatus?.connected, fail: napcatStatus && !napcatStatus.connected }">
      <div class="ns-left">
        <span class="ns-dot"></span>
        <span class="ns-text">
          <template v-if="!napcatStatus">NapCat：未检测</template>
          <template v-else-if="napcatStatus.connected">NapCat：已连接（{{ napcatStatus.nickname || napcatStatus.user_id }}）</template>
          <template v-else>NapCat：未连接<span class="ns-error"> — {{ napcatStatus.error }}</span></template>
        </span>
      </div>
      <button class="ns-btn" :disabled="checkingNapcat" @click="checkNapcat">{{ checkingNapcat ? '检测中…' : '检测连接' }}</button>
    </div>

    <div v-if="loading" class="loading-row">加载中…</div>
    <div v-else class="settings-form">
      <!-- 消息模板设置 -->
      <section class="message-templates">
        <div class="templates-header">
          <h3>消息模板设置</h3>
          <p>自定义好友添加和成员上线通知的消息内容</p>
        </div>

        <div v-if="templatesLoading" class="member-loading">加载消息模板中…</div>
        <div v-else-if="friendTemplates && notificationTemplates" class="templates-content">
          <!-- 好友添加通知模板 -->
          <div class="template-group">
            <h4>好友添加通知</h4>
            <div class="field">
              <label>
                <span class="field-label">TS 通知消息</span>
                <span class="tag tag-variable">变量: {nickname}</span>
              </label>
              <textarea
                v-model="friendTemplates.friend_add_ts_message"
                class="template-textarea"
                rows="2"
                placeholder="输入TS通知消息模板"
              />
            </div>
            <div class="field">
              <label>
                <span class="field-label">QQ 通知消息</span>
                <span class="tag tag-variable">变量: {nickname}</span>
              </label>
              <textarea
                v-model="friendTemplates.friend_add_qq_message"
                class="template-textarea"
                rows="2"
                placeholder="输入QQ通知消息模板"
              />
            </div>
            <div class="field">
              <label>
                <span class="field-label">在线提醒消息</span>
                <span class="tag tag-variable">变量: {nickname}, {game}</span>
              </label>
              <textarea
                v-model="friendTemplates.friend_online_notice_message"
                class="template-textarea"
                rows="2"
                placeholder="输入在线提醒消息模板"
              />
            </div>
          </div>

          <!-- 成员上线通知模板 -->
          <div class="template-group">
            <h4>成员上线通知</h4>
            <div class="field">
              <label>
                <span class="field-label">好友上线通知</span>
                <span class="tag tag-variable">变量: {nick}</span>
              </label>
              <textarea
                v-model="notificationTemplates.friend_online_notice"
                class="template-textarea"
                rows="2"
                placeholder="输入好友上线通知模板"
              />
            </div>
            <div class="field">
              <label>
                <span class="field-label">成员上线通知</span>
                <span class="tag tag-variable">变量: {nick}</span>
              </label>
              <textarea
                v-model="notificationTemplates.server_online_notice"
                class="template-textarea"
                rows="2"
                placeholder="输入成员上线通知模板"
              />
            </div>
            <div class="field">
              <label>
                <span class="field-label">新成员首次加入通知</span>
                <span class="tag tag-variable">变量: {nick}</span>
              </label>
              <textarea
                v-model="notificationTemplates.server_first_join_notice"
                class="template-textarea"
                rows="2"
                placeholder="输入新成员首次加入通知模板"
              />
            </div>
          </div>

          <div class="template-actions">
            <button
              class="save-btn"
              :disabled="savingTemplates"
              @click="saveMessageTemplates"
            >
              {{ savingTemplates ? '保存中…' : '保存消息模板' }}
            </button>
          </div>
        </div>
      </section>

      <!-- 系统设置 -->
      <div v-for="(s, key) in settings" :key="key" class="field">
        <label>
          <span class="field-label">{{ s.label }}</span>
          <span v-if="s.sensitive" class="tag tag-secret" title="敏感信息，保存时留空则不改">敏感</span>
          <span v-if="s.restart" class="tag tag-restart" title="改动需重启后端生效">需重启</span>
          <span v-else-if="s.reload" class="tag tag-reload" title="保存后自动热重载">热重载</span>
        </label>
        <input
          :type="s.sensitive ? 'password' : 'text'"
          v-model="form[key as string]"
          :placeholder="s.is_set ? '' : '未设置（用 .env 默认）'"
        />
      </div>

      <section class="member-notifications">
        <div class="member-notifications-header">
          <div>
            <h3>成员通知</h3>
            <p>默认通过 TeamSpeak 私聊发送；NapCat 已启用时可改为 QQ。</p>
          </div>
          <span class="event-key"><i class="key-dot"></i>{{ napcatEnabled ? 'TS / QQ 可选' : 'TS 私聊' }}</span>
        </div>
        <div v-if="memberNotificationsLoading" class="member-loading">加载成员列表中…</div>
        <div v-else-if="!memberNotifications.length" class="member-loading">暂无成员</div>
        <div v-else class="member-notification-list">
          <article v-for="member in memberNotifications" :key="member.id" class="member-notification-row">
            <div class="member-identity">
              <span class="member-avatar">{{ member.ts_nickname.slice(0, 1).toUpperCase() }}</span>
              <div>
                <strong>{{ member.ts_nickname }}</strong>
                <small :class="{ muted: !member.qq_bound }">{{ member.qq_bound ? '已绑定 QQ，可选 QQ 通知' : '未绑定 QQ，使用 TS 私聊' }}</small>
              </div>
            </div>
            <label class="notice-channel">
              <span>通知渠道</span>
              <el-select v-model="member.notification_channel" size="small" :disabled="savingMemberId === member.id" @change="saveMemberNotifications(member)">
                <el-option label="TeamSpeak 私聊（默认）" value="ts" />
                <el-option label="QQ 私聊" value="qq" :disabled="!napcatEnabled || !member.qq_bound" />
              </el-select>
            </label>
            <label class="notice-toggle">
              <span>成员上线</span>
              <el-switch v-model="member.notify_server_online" :disabled="savingMemberId === member.id" @change="saveMemberNotifications(member)" />
            </label>
            <label class="notice-toggle">
              <span>新成员首次加入</span>
              <el-switch v-model="member.notify_server_first_join" :disabled="savingMemberId === member.id" @change="saveMemberNotifications(member)" />
            </label>
          </article>
        </div>
      </section>
      <div class="actions">
        <span class="hint">敏感项留空（****）= 不修改；其他项留空 = 清除覆盖回退 .env 默认</span>
        <button class="save-btn" :disabled="saving" @click="save">{{ saving ? '保存中…' : '保存设置' }}</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.no-admin { padding: 48px; text-align: center; color: var(--text-muted); font-size: 0.9em; }
.admin-panel { display: flex; flex-direction: column; gap: 4px; }
.panel-header {
  display: flex; align-items: baseline; justify-content: space-between;
  margin-bottom: 14px; padding-bottom: 12px; border-bottom: 1px solid var(--border-subtle);
}
.panel-title-group { display: flex; align-items: baseline; gap: 8px; }
.panel-title { font-size: 1em; font-weight: 600; color: var(--text-primary); margin: 0; }
.panel-sub { font-size: 0.66em; color: var(--text-muted); }
.loading-row { padding: 30px; text-align: center; color: var(--text-muted); font-size: 0.85em; }
.settings-form { display: flex; flex-direction: column; gap: 13px; }
.member-notifications { margin-top: 16px; padding: 18px; border: 1px solid var(--border-default); border-radius: 10px; background: linear-gradient(135deg, rgba(36, 170, 210, 0.08), transparent 45%), var(--surface-3); }
.member-notifications-header { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; margin-bottom: 14px; }
.member-notifications h3 { margin: 0 0 3px; font-size: .9em; color: var(--text-primary); }
.member-notifications p { margin: 0; font-size: .72em; color: var(--text-muted); }
.event-key { display: inline-flex; align-items: center; gap: 5px; white-space: nowrap; color: var(--text-secondary); font-size: .68em; }
.key-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--color-success); box-shadow: 0 0 8px var(--color-success); }
.member-notification-list { display: flex; flex-direction: column; }
.member-notification-row { display: grid; grid-template-columns: minmax(160px, 1fr) 185px 130px 160px; align-items: center; gap: 16px; padding: 11px 0; border-top: 1px solid var(--border-subtle); }
.member-identity { display: flex; align-items: center; gap: 9px; min-width: 0; }
.member-avatar { width: 28px; height: 28px; display: grid; place-items: center; flex-shrink: 0; border-radius: 50%; background: var(--gradient-brand); color: var(--text-inverse); font-size: .75em; font-weight: 700; }
.member-identity strong, .member-identity small { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.member-identity strong { color: var(--text-primary); font-size: .8em; }
.member-identity small { margin-top: 2px; color: var(--color-success); font-size: .66em; }
.member-identity small.muted { color: var(--text-muted); }
.notice-toggle { display: flex; align-items: center; justify-content: space-between; gap: 8px; color: var(--text-secondary); font-size: .72em; cursor: pointer; }
.notice-channel { display: flex; flex-direction: column; gap: 4px; color: var(--text-secondary); font-size: .72em; }
.member-loading { padding: 18px 0 4px; color: var(--text-muted); font-size: .75em; text-align: center; }
.field { display: flex; flex-direction: column; gap: 4px; }
.field label { display: flex; align-items: center; gap: 6px; }
.field-label { font-size: 0.74em; color: var(--text-secondary); }
.field input {
  background: var(--surface-3); border: 1px solid var(--border-default); border-radius: 6px;
  padding: 7px 10px; color: var(--text-primary); font-size: 0.82em;
  font-family: 'JetBrains Mono', monospace; outline: none;
  transition: border-color 0.15s;
}
.field input:focus { border-color: var(--color-primary); }
.tag { font-size: 0.7em; padding: 0 5px; border-radius: 3px; font-weight: 600; line-height: 1.6; }
.tag-secret { color: #f5a623; border: 1px solid rgba(245, 166, 35, 0.4); }
.tag-restart { color: var(--color-danger); border: 1px solid var(--color-danger); }
.tag-reload { color: var(--color-primary); border: 1px solid var(--color-primary); }
.actions { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-top: 8px; }
.hint { font-size: 0.64em; color: var(--text-muted); flex: 1; }
.save-btn {
  padding: 7px 22px; border: 0; border-radius: 6px;
  background: var(--gradient-brand); color: var(--text-inverse);
  font-size: 0.82em; font-weight: 600; cursor: pointer; flex-shrink: 0;
}
.save-btn:disabled { opacity: 0.5; cursor: default; }

.napcat-status-card {
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  padding: 10px 14px; border: 1px solid var(--border-default); border-radius: var(--radius-sm);
  background: var(--surface-3); margin-bottom: 14px;
}
.napcat-status-card.ok { border-color: var(--color-success); background: rgba(34, 197, 94, 0.06); }
.napcat-status-card.fail { border-color: var(--color-danger); background: rgba(248, 113, 113, 0.06); }
.ns-left { display: flex; align-items: center; gap: 10px; min-width: 0; }
.ns-dot { width: 9px; height: 9px; border-radius: 50%; background: var(--text-muted); flex-shrink: 0; }
.napcat-status-card.ok .ns-dot { background: var(--color-success); }
.napcat-status-card.fail .ns-dot { background: var(--color-danger); }
.ns-text { font-size: 0.8em; color: var(--text-secondary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ns-error { color: var(--color-danger); }
.ns-btn {
  padding: 4px 14px; border: 1px solid var(--border-emphasis); border-radius: 6px;
  background: transparent; color: var(--text-secondary); font-size: 0.74em; cursor: pointer; flex-shrink: 0;
}
.ns-btn:hover:not(:disabled) { color: var(--color-primary); border-color: var(--color-primary); }
.ns-btn:disabled { opacity: 0.5; cursor: default; }

.message-templates {
  padding: 18px;
  border: 1px solid var(--border-default);
  border-radius: 10px;
  background: linear-gradient(135deg, rgba(168, 85, 247, 0.08), transparent 45%), var(--surface-3);
  margin-bottom: 16px;
}

.templates-header {
  margin-bottom: 16px;
}

.templates-header h3 {
  margin: 0 0 4px;
  font-size: 0.9em;
  color: var(--text-primary);
}

.templates-header p {
  margin: 0;
  font-size: 0.72em;
  color: var(--text-muted);
}

.templates-content {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.template-group {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px;
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  background: var(--surface-2);
}

.template-group h4 {
  margin: 0;
  font-size: 0.82em;
  color: var(--text-primary);
  font-weight: 600;
}

.template-textarea {
  width: 100%;
  min-height: 60px;
  padding: 8px 10px;
  border: 1px solid var(--border-default);
  border-radius: 6px;
  background: var(--surface-3);
  color: var(--text-primary);
  font-size: 0.8em;
  font-family: 'JetBrains Mono', monospace;
  resize: vertical;
  outline: none;
  transition: border-color 0.15s;
}

.template-textarea:focus {
  border-color: var(--color-primary);
}

.template-actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 8px;
}

.tag-variable {
  font-size: 0.7em;
  padding: 0 5px;
  border-radius: 3px;
  font-weight: 600;
  line-height: 1.6;
  color: var(--color-primary);
  border: 1px solid var(--color-primary);
  background: rgba(64, 158, 255, 0.1);
}

@media (max-width: 768px) {
  .no-admin { padding: 32px 16px; }
  .admin-panel { gap: 8px; }
  .panel-header { margin-bottom: 10px; }
  .panel-title { font-size: 1.15em; }
  .napcat-status-card {
    align-items: stretch;
    flex-direction: column;
    padding: 12px;
  }
  .ns-left { align-items: flex-start; }
  .ns-dot { margin-top: 7px; }
  .ns-text { white-space: normal; overflow: visible; line-height: 1.55; }
  .ns-btn { width: 100%; min-height: 44px; font-size: 0.84em; }
  .settings-form { gap: 16px; }
  .message-templates { padding: 14px 12px; }
  .templates-header h3 { font-size: 1em; }
  .template-group { padding: 12px; }
  .template-textarea {
    min-height: 80px;
    font-size: 16px;
    padding: 10px 12px;
  }
  .template-actions {
    justify-content: stretch;
  }
  .template-actions .save-btn {
    width: 100%;
    min-height: 46px;
  }
  .member-notifications { padding: 14px 12px; }
  .member-notifications-header { flex-direction: column; }
  .member-notification-row { grid-template-columns: 1fr; gap: 10px; padding: 14px 0; }
  .notice-toggle { padding-left: 37px; }
  .field label { flex-wrap: wrap; }
  .field-label { font-size: 0.82em; }
  .field input {
    width: 100%;
    min-height: 44px;
    padding: 9px 11px;
    font-size: 16px;
  }
  .actions { flex-direction: column; align-items: stretch; gap: 12px; }
  .hint { line-height: 1.6; }
  .save-btn { width: 100%; min-height: 46px; }
}
</style>
