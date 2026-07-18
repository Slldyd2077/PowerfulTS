<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getSteamAuthUrl, unbindSteam, type SteamMeResponse } from '@/api/steam'

const props = defineProps<{ me: SteamMeResponse | null }>()
const emit = defineEmits<{ (e: 'refresh'): void }>()

// 记录绑定弹窗引用，用于校验 postMessage 来源（仅接受自己打开的弹窗回传，防伪造）
let bindWin: Window | null = null

/** 发起 Steam OpenID 绑定。
 * 弹窗必须在用户手势内同步打开（否则浏览器拦截），故先开空白窗，拿到 URL 后再跳转。 */
async function startBind() {
  const win = window.open('', 'steam_bind', 'width=980,height=720')
  if (!win) {
    ElMessage.error('Steam 登录弹窗被拦截，请允许本站弹窗后重试')
    return
  }
  bindWin = win
  win.document.write('<p style="font-family:sans-serif;text-align:center;padding:40px">正在跳转到 Steam…</p>')
  try {
    const { url } = await getSteamAuthUrl()
    win.location.href = url
  } catch {
    win.close()
    bindWin = null
    ElMessage.error('获取 Steam 登录地址失败')
  }
}

/** 解绑前二次确认 */
async function onUnbind() {
  try {
    await ElMessageBox.confirm(
      '确定解绑当前 Steam 账号？解绑后 Steam 在线状态、游戏库与共同游戏将不再显示。',
      '解绑 Steam',
      { type: 'warning' },
    )
  } catch {
    return // 用户取消
  }
  try {
    const res = await unbindSteam()
    if (!res.success) throw new Error('解绑失败')
    ElMessage.success('已解绑 Steam')
    emit('refresh')
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '解绑失败')
  }
}

/** 监听 Steam 回调弹窗的 postMessage（绑定结果回传）。
 * 仅接受我们自己打开的弹窗回传的消息（e.source 为窗口引用，不受 dev 跨端口 origin 影响）。 */
function onMessage(e: MessageEvent) {
  if (e.source !== bindWin) return
  bindWin = null
  if (!e.data || e.data.type !== 'steam_bound') return
  if (e.data.success) {
    ElMessage.success('Steam 绑定成功')
    emit('refresh')
  } else {
    ElMessage.error('Steam 绑定未完成，请重试')
  }
}

onMounted(() => window.addEventListener('message', onMessage))
onUnmounted(() => window.removeEventListener('message', onMessage))
</script>

<template>
  <div class="steam-binding panel">
    <!-- 未绑定 -->
    <template v-if="!props.me?.bound">
      <div class="bind-empty">
        <div class="bind-icon">S</div>
        <div class="bind-text">
          <span class="bind-title">尚未绑定 Steam</span>
          <span class="bind-sub">绑定后可查看自己与好友的 Steam 在线状态、共同游戏与游戏时长</span>
        </div>
        <button class="bind-btn" @click="startBind">绑定 Steam</button>
      </div>
    </template>

    <!-- 已绑定 -->
    <template v-else>
      <div class="bound-row">
        <img
          v-if="props.me.avatar_url"
          :src="props.me.avatar_url"
          class="bound-avatar"
          :alt="props.me.persona || ''"
        />
        <div v-else class="bound-avatar bound-avatar--fallback">
          {{ (props.me.persona || 'S').charAt(0).toUpperCase() }}
        </div>
        <div class="bound-info">
          <span class="bound-persona">{{ props.me.persona || 'Steam 用户' }}</span>
          <a
            v-if="props.me.profile_url"
            :href="props.me.profile_url"
            target="_blank"
            rel="noopener"
            class="bound-profile mono"
          >
            Steam 主页 ↗
          </a>
        </div>
        <button class="unbind-btn" @click="onUnbind">解绑</button>
      </div>
    </template>
  </div>
</template>

<style scoped>
.panel {
  background: var(--gradient-surface);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  padding: 16px;
}

.bind-empty {
  display: flex;
  align-items: center;
  gap: 14px;
}
.bind-icon {
  width: 44px;
  height: 44px;
  flex-shrink: 0;
  border-radius: 10px;
  display: grid;
  place-items: center;
  background: linear-gradient(135deg, #1b2838, #66c0f4 130%);
  color: #fff;
  font-family: 'JetBrains Mono', monospace;
  font-weight: 800;
  font-size: 1.2em;
}
.bind-text {
  display: flex;
  flex-direction: column;
  gap: 3px;
  flex: 1;
  min-width: 0;
}
.bind-title {
  font-weight: 600;
  font-size: 0.92em;
  color: var(--text-primary);
}
.bind-sub {
  font-size: 0.7em;
  color: var(--text-muted);
  line-height: 1.4;
}
.bind-btn {
  padding: 7px 18px;
  flex-shrink: 0;
  border: 0;
  border-radius: 10px;
  background: linear-gradient(135deg, #1b2838, #2a475e);
  color: #fff;
  font-size: 0.82em;
  font-weight: 600;
  cursor: pointer;
  transition: transform 0.15s, box-shadow 0.15s;
}
.bind-btn:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
}

.bound-row {
  display: flex;
  align-items: center;
  gap: 12px;
}
.bound-avatar {
  width: 44px;
  height: 44px;
  border-radius: 10px;
  object-fit: cover;
  flex-shrink: 0;
  border: 1px solid var(--border-default);
}
.bound-avatar--fallback {
  display: grid;
  place-items: center;
  background: linear-gradient(135deg, #1b2838, #66c0f4 130%);
  color: #fff;
  font-weight: 700;
}
.bound-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1;
  min-width: 0;
}
.bound-persona {
  font-weight: 600;
  font-size: 0.95em;
  color: var(--text-primary);
}
.bound-profile {
  font-size: 0.68em;
  color: #66c0f4;
  text-decoration: none;
}
.bound-profile:hover {
  text-decoration: underline;
}
.unbind-btn {
  padding: 5px 14px;
  flex-shrink: 0;
  border: 1px solid var(--border-emphasis);
  border-radius: 9px;
  background: transparent;
  color: var(--text-secondary);
  font-size: 0.74em;
  cursor: pointer;
  transition: all 0.15s;
}
.unbind-btn:hover {
  border-color: var(--color-danger);
  color: var(--color-danger);
}

@media (max-width: 768px) {
  .bind-empty {
    flex-wrap: wrap;
  }
  .bind-text {
    flex-basis: calc(100% - 58px);
  }
  .bind-btn {
    flex: 1;
    min-height: 42px;
  }
}
</style>
