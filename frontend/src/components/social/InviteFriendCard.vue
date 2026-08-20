<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { generateFriendInvitation } from '@/api/social'

const loading = ref(false)
const inviteUrl = ref('')
const expiresAt = ref('')

const formattedExpiry = computed(() => {
  if (!expiresAt.value) return ''
  const date = new Date(expiresAt.value)
  if (Number.isNaN(date.getTime())) return expiresAt.value
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
})

async function copyText(value: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(value)
    return true
  } catch {
    let input: HTMLTextAreaElement | null = null
    try {
      input = document.createElement('textarea')
      input.value = value
      input.setAttribute('readonly', '')
      input.style.position = 'fixed'
      input.style.opacity = '0'
      document.body.appendChild(input)
      input.select()
      return document.execCommand('copy')
    } catch {
      return false
    } finally {
      input?.remove()
    }
  }
}

async function generateAndCopy() {
  if (loading.value) return
  loading.value = true
  try {
    const result = await generateFriendInvitation()
    if (!result.success || !result.token) {
      throw new Error(result.error || '生成邀请链接失败')
    }

    const url = `${window.location.origin}/login#invite=${encodeURIComponent(result.token)}`
    inviteUrl.value = url
    expiresAt.value = result.expires_at
    const copied = await copyText(url)
    ElMessage.success(copied ? '邀请链接已生成并复制' : '邀请链接已生成，请手动复制')
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '生成邀请链接失败')
  } finally {
    loading.value = false
  }
}

async function copyExisting() {
  if (!inviteUrl.value) return
  const copied = await copyText(inviteUrl.value)
  if (copied) ElMessage.success('邀请链接已复制')
  else ElMessage.warning('无法自动复制，请长按链接手动复制')
}
</script>

<template>
  <section class="invite-card" aria-labelledby="invite-card-title">
    <div class="signal-rail" aria-hidden="true">
      <span v-for="index in 5" :key="index" class="signal-bar"></span>
    </div>

    <div class="invite-copy">
      <div class="invite-heading">
        <div>
          <h2 id="invite-card-title" class="invite-title">一键邀请好友</h2>
          <span class="invite-sub label-mono">SECURE LINK</span>
        </div>
        <span class="invite-status"><i></i> 单次授权</span>
      </div>

      <p class="invite-description">
        对方打开链接即可免 TS 验证码注册，填写 QQ 号后与你自动成为双向好友。
      </p>

      <div class="invite-rules" aria-label="邀请规则">
        <span>7 天有效</span>
        <span>仅可注册 1 次</span>
        <span>新链接会使旧链接失效</span>
      </div>

      <div v-if="inviteUrl" class="link-console">
        <div class="link-value mono" :title="inviteUrl">{{ inviteUrl }}</div>
        <button class="copy-button" type="button" @click="copyExisting">复制</button>
      </div>
      <p v-if="formattedExpiry" class="expiry label-mono">EXPIRES {{ formattedExpiry }}</p>

      <button
        class="generate-button"
        type="button"
        :disabled="loading"
        @click="generateAndCopy"
      >
        <span class="button-pip" aria-hidden="true"></span>
        {{ loading ? '正在签发…' : inviteUrl ? '重新生成并复制' : '生成并复制邀请链接' }}
      </button>
    </div>
  </section>
</template>

<style scoped>
.invite-card {
  position: relative;
  display: grid;
  grid-template-columns: 40px minmax(0, 1fr);
  overflow: hidden;
  margin-bottom: 16px;
  background:
    linear-gradient(135deg, rgba(var(--color-primary-rgb), 0.11), transparent 42%),
    var(--gradient-surface);
  border: 1px solid rgba(var(--color-primary-rgb), 0.3);
  border-radius: var(--radius-md);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.035);
}

.invite-card::after {
  content: '';
  position: absolute;
  inset: 0;
  pointer-events: none;
  background: repeating-linear-gradient(
    90deg,
    transparent 0,
    transparent 31px,
    rgba(82, 147, 226, 0.025) 32px
  );
}

.signal-rail {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: flex-end;
  justify-content: center;
  gap: 2px;
  padding: 18px 0;
  background: rgba(1, 30, 77, 0.26);
  border-right: 1px solid rgba(var(--color-primary-rgb), 0.18);
}

.signal-bar {
  width: 2px;
  height: 24%;
  min-height: 8px;
  max-height: 34px;
  border-radius: 2px;
  background: var(--color-primary);
  box-shadow: 0 0 7px rgba(var(--color-primary-rgb), 0.52);
  animation: signal 1.6s ease-in-out infinite alternate;
}

.signal-bar:nth-child(2) { animation-delay: -0.7s; }
.signal-bar:nth-child(3) { animation-delay: -1.1s; }
.signal-bar:nth-child(4) { animation-delay: -0.35s; }
.signal-bar:nth-child(5) { animation-delay: -0.9s; }

@keyframes signal {
  from { height: 18%; opacity: 0.4; }
  to { height: 72%; opacity: 1; }
}

.invite-copy {
  position: relative;
  z-index: 1;
  min-width: 0;
  padding: 16px 18px 18px;
}

.invite-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.invite-title {
  margin: 0;
  color: var(--text-primary);
  font-size: 0.98em;
  font-weight: 650;
}

.invite-sub {
  display: block;
  margin-top: 2px;
  color: var(--text-muted);
  font-size: 0.58em;
}

.invite-status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
  padding: 4px 8px;
  color: var(--text-secondary);
  font-size: 0.68em;
  border: 1px solid var(--border-default);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.025);
}

.invite-status i,
.button-pip {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--color-success);
  box-shadow: 0 0 8px rgba(34, 197, 94, 0.55);
}

.invite-description {
  margin: 12px 0 10px;
  color: var(--text-secondary);
  font-size: 0.78em;
  line-height: 1.6;
}

.invite-rules {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 14px;
}

.invite-rules span {
  padding: 3px 7px;
  color: var(--text-muted);
  font-size: 0.66em;
  border-left: 2px solid rgba(var(--color-primary-rgb), 0.55);
  background: rgba(255, 255, 255, 0.025);
}

.link-console {
  display: flex;
  min-width: 0;
  margin-bottom: 5px;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  background: rgba(1, 8, 20, 0.56);
}

.link-value {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  padding: 9px 10px;
  color: var(--text-secondary);
  font-size: 0.69em;
  text-overflow: ellipsis;
  white-space: nowrap;
  user-select: all;
}

.copy-button {
  padding: 0 13px;
  color: var(--color-primary);
  font: inherit;
  font-size: 0.72em;
  cursor: pointer;
  border: 0;
  border-left: 1px solid var(--border-default);
  background: rgba(var(--color-primary-rgb), 0.08);
}

.expiry {
  margin: 0 0 10px;
  color: var(--text-muted);
  font-size: 0.58em;
}

.generate-button {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 9px;
  width: 100%;
  min-height: 42px;
  color: var(--text-inverse);
  font-family: inherit;
  font-size: 0.82em;
  font-weight: 650;
  cursor: pointer;
  border: 0;
  border-radius: var(--radius-sm);
  background: var(--gradient-brand);
  box-shadow: 0 7px 22px rgba(17, 108, 224, 0.18);
  transition: transform 0.18s, filter 0.18s, opacity 0.18s;
}

.generate-button:hover:not(:disabled) {
  transform: translateY(-1px);
  filter: brightness(1.08);
}

.generate-button:disabled {
  opacity: 0.55;
  cursor: wait;
}

@media (max-width: 520px) {
  .invite-card { grid-template-columns: 30px minmax(0, 1fr); }
  .invite-copy { padding: 14px 13px 16px; }
  .invite-heading { align-items: center; }
  .invite-status { padding-inline: 7px; }
  .generate-button { min-height: 46px; }
  .copy-button { min-width: 58px; }
}

@media (prefers-reduced-motion: reduce) {
  .signal-bar { animation: none; }
}
</style>
