<script setup lang="ts">
import { computed, ref } from 'vue'
import axios from 'axios'
import { ElMessage, ElMessageBox } from 'element-plus'
import { moveVoiceChannel, type VoiceChannel } from '@/api/voice'
import { useVoiceChannels } from '@/composables/useVoiceChannels'

// 频道数据和每人音量面板共用一份轮询（见 useVoiceChannels）。
const {
  channels, botCid, botOnline, monitorRunning, loading, loadError, currentChannel, refresh,
} = useVoiceChannels()

const switching = ref<number | null>(null)

const totalListeners = computed(() => currentChannel.value?.clients.length ?? 0)

function errorText(error: unknown, fallback: string): string {
  if (axios.isAxiosError(error)) {
    const detail = (error.response?.data as { detail?: string } | undefined)?.detail
    if (detail) return detail
    if (!error.response) return '连不上 PowerfulTS 后端'
  }
  return error instanceof Error ? error.message : fallback
}

async function switchTo(channel: VoiceChannel) {
  if (channel.cid === botCid.value || switching.value !== null) return
  if (!botOnline.value) {
    ElMessage.warning('请先点「加入通话」，之后才能切换频道')
    return
  }

  let password = ''
  if (channel.hasPassword) {
    try {
      const { value } = await ElMessageBox.prompt(
        `「${channel.name}」需要密码`,
        '加入频道',
        {
          confirmButtonText: '加入',
          cancelButtonText: '取消',
          inputType: 'password',
          inputPlaceholder: '频道密码',
        },
      )
      password = value || ''
    } catch {
      return // 用户取消
    }
  }

  switching.value = channel.cid
  try {
    await moveVoiceChannel(channel.cid, password)
    // 别等下一次轮询，先本地跳过去，切换手感才跟得上点击。
    botCid.value = channel.cid
    ElMessage.success(`已进入「${channel.name}」`)
    await refresh()
  } catch (error) {
    ElMessage.error(errorText(error, '切换频道失败'))
  } finally {
    switching.value = null
  }
}

// 加入/挂断后立刻刷新，不用等下一次轮询才更新「当前频道」。
defineExpose({ refresh })
</script>

<template>
  <section class="channel-browser">
    <div class="browser-head">
      <div>
        <h2>频道</h2>
        <p v-if="currentChannel">
          你在「<b>{{ currentChannel.name }}</b>」 · {{ totalListeners }} 人在场 · 点其他频道即可切换
        </p>
        <p v-else-if="!botOnline">加入通话后即可点击切换频道。</p>
        <p v-else>还没进入任何频道。</p>
      </div>
      <button class="refresh" type="button" :disabled="loading" @click="refresh">刷新</button>
    </div>

    <p v-if="loadError" class="browser-error" role="alert">{{ loadError }}</p>
    <p v-else-if="!monitorRunning" class="browser-error">
      TS 服务器监控未连接，频道成员可能不是最新的。
    </p>

    <p v-if="loading && !channels.length" class="hint">正在读取频道…</p>
    <p v-else-if="!channels.length" class="hint">没有可显示的频道。</p>

    <ul v-else class="channel-list">
      <li
        v-for="channel in channels"
        :key="channel.cid"
        class="channel"
        :class="{ current: channel.cid === botCid }"
      >
        <button
          class="channel-row"
          type="button"
          :style="{ paddingLeft: `${10 + channel.depth * 16}px` }"
          :disabled="switching !== null || channel.cid === botCid"
          @click="switchTo(channel)"
        >
          <span class="channel-name">
            <i class="marker" aria-hidden="true" />
            {{ channel.name }}
            <span v-if="channel.hasPassword" class="lock" title="需要密码">🔒</span>
          </span>
          <span class="channel-action">
            <template v-if="switching === channel.cid">切换中…</template>
            <template v-else-if="channel.cid === botCid">你在这里</template>
            <template v-else-if="channel.clients.length">{{ channel.clients.length }} 人</template>
          </span>
        </button>

        <ul v-if="channel.clients.length" class="member-list" :style="{ paddingLeft: `${26 + channel.depth * 16}px` }">
          <li v-for="client in channel.clients" :key="client.nickname" :class="{ bot: client.isBot }">
            <i class="dot" aria-hidden="true" />{{ client.nickname }}
            <span v-if="client.isBot" class="tag">机器人</span>
          </li>
        </ul>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.channel-browser {
  padding: 18px 20px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  background: var(--bg-card);
  box-shadow: var(--shadow-card);
}
.browser-head { display: flex; gap: 14px; align-items: flex-start; justify-content: space-between; margin-bottom: 14px; }
.browser-head h2 { margin: 0 0 6px; color: var(--text-primary); font-size: 0.98em; letter-spacing: -0.015em; }
.browser-head p { margin: 0; color: var(--text-secondary); font-size: 0.74em; line-height: 1.6; }
.browser-head b { color: var(--color-primary); }
.refresh {
  flex: none;
  padding: 6px 12px;
  border: 1px solid var(--border-subtle);
  border-radius: 999px;
  background: var(--bg-elevated);
  color: var(--text-muted);
  font-size: 0.66em;
  font-weight: 600;
  cursor: pointer;
}
.refresh:hover:not(:disabled) { color: var(--text-primary); border-color: rgba(var(--color-primary-rgb), 0.4); }
.refresh:disabled { opacity: 0.5; cursor: wait; }

.browser-error {
  margin: 0 0 12px;
  padding: 9px 11px;
  border: 1px solid rgba(var(--color-danger-rgb), 0.3);
  border-radius: var(--radius-sm);
  background: rgba(var(--color-danger-rgb), 0.07);
  color: var(--text-secondary);
  font-size: 0.7em;
  line-height: 1.6;
}
.hint { margin: 0; color: var(--text-muted); font-size: 0.72em; }

.channel-list, .member-list { margin: 0; padding: 0; list-style: none; }
/* 频道树可能有上百个频道，不封顶的话整页会被拉成几屏高。 */
.channel-list {
  max-height: min(62vh, 640px);
  margin-right: -6px;
  overflow-y: auto;
  padding-right: 6px;
  overscroll-behavior: contain;
}
.channel-list::-webkit-scrollbar { width: 8px; }
.channel-list::-webkit-scrollbar-thumb { border-radius: 4px; background: var(--border-default); }
.channel-list::-webkit-scrollbar-track { background: transparent; }
.channel { border-radius: var(--radius-sm); }
.channel + .channel { margin-top: 2px; }
.channel.current { background: rgba(var(--color-primary-rgb), 0.06); }

.channel-row {
  display: flex;
  width: 100%;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 8px 11px;
  border: 0;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-secondary);
  font-family: inherit;
  font-size: 0.76em;
  font-weight: 600;
  text-align: left;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}
.channel-row:hover:not(:disabled) { background: rgba(var(--color-primary-rgb), 0.08); color: var(--text-primary); }
.channel-row:disabled { cursor: default; }
.current .channel-row { color: var(--color-primary); }
.channel-name { display: inline-flex; min-width: 0; align-items: center; gap: 7px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.marker { width: 5px; height: 5px; flex: none; border-radius: 50%; background: var(--border-default); }
.current .marker { background: var(--color-primary); box-shadow: 0 0 0 3px rgba(var(--color-primary-rgb), 0.2); }
.lock { font-size: 0.85em; }
.channel-action { flex: none; color: var(--text-muted); font-size: 0.86em; font-weight: 500; }
.current .channel-action { color: var(--color-primary); }

.member-list { padding-bottom: 7px; }
.member-list li { display: flex; align-items: center; gap: 7px; padding: 2px 0; color: var(--text-muted); font-size: 0.7em; }
.member-list .dot { width: 4px; height: 4px; border-radius: 50%; background: var(--color-success); }
.member-list li.bot { color: var(--text-secondary); }
.tag {
  padding: 1px 6px;
  border-radius: 999px;
  background: rgba(var(--color-primary-rgb), 0.12);
  color: var(--color-primary);
  font-size: 0.86em;
  font-weight: 600;
}

@media (max-width: 680px) {
  .channel-browser { padding: 16px; }
  .browser-head { flex-direction: column; }
}
</style>
