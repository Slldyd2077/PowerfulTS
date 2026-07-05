<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { getAdminSettings, putAdminSettings, checkNapcatStatus, type SettingItem, type NapcatStatus } from '@/api/admin'

const auth = useAuthStore()
const loading = ref(false)
const saving = ref(false)
const settings = ref<Record<string, SettingItem>>({})
const form = reactive<Record<string, string>>({})

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

onMounted(load)
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
</style>
