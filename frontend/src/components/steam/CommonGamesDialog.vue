<script setup lang="ts">
import { ref, watch } from 'vue'
import { getCommonGames, type CommonGame, type SteamFriend } from '@/api/steam'

const props = defineProps<{ visible: boolean; friend: SteamFriend | null }>()
const emit = defineEmits<{ (e: 'update:visible', v: boolean): void }>()

const games = ref<CommonGame[]>([])
const friendPersona = ref('')
const loading = ref(false)
const error = ref('')
let reqId = 0 // 请求竞态保护：打开 A→关闭→立刻打开 B 时丢弃过期响应

watch(
  () => props.visible,
  async (open) => {
    if (!open || !props.friend) return
    const myId = ++reqId
    loading.value = true
    error.value = ''
    games.value = []
    friendPersona.value = props.friend.persona || props.friend.ts_nickname
    try {
      const res = await getCommonGames(props.friend.account_id)
      if (myId !== reqId) return // 已被更新的请求取代，丢弃
      games.value = res.common_games || []
      friendPersona.value = res.friend_persona || props.friend.ts_nickname
    } catch (e) {
      if (myId !== reqId) return
      error.value = e instanceof Error ? e.message : '获取共同游戏失败'
    } finally {
      if (myId === reqId) loading.value = false
    }
  },
)

function close() {
  emit('update:visible', false)
}
</script>

<template>
  <div v-if="props.visible" class="cg-overlay" @click.self="close">
    <div class="cg-box">
      <div class="cg-header">
        <h3 class="cg-title">与「{{ friendPersona }}」的共同游戏</h3>
        <button class="cg-close" @click="close">×</button>
      </div>

      <div v-if="loading" class="cg-body no-data">加载中…</div>
      <div v-else-if="error" class="cg-body no-data">{{ error }}</div>
      <div v-else-if="games.length === 0" class="cg-body no-data">暂无共同游戏</div>

      <div v-else class="cg-body">
        <p class="cg-count">共 {{ games.length }} 款共同游戏</p>
        <div class="cg-list">
          <div v-for="g in games" :key="g.appid" class="cg-row">
            <img v-if="g.icon_url" :src="g.icon_url" class="cg-icon" :alt="g.name" loading="lazy" />
            <div v-else class="cg-icon cg-icon--fallback"></div>
            <span class="cg-name" :title="g.name">{{ g.name }}</span>
            <span class="cg-hours mono">
              <span class="me">我 {{ g.my_hours }}h</span>
              <span class="friend">Ta {{ g.friend_hours }}h</span>
            </span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.cg-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  display: grid;
  place-items: center;
  z-index: 1000;
}
.cg-box {
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  width: 520px;
  max-width: calc(100vw - 24px);
  max-height: 80vh;
  display: flex;
  flex-direction: column;
}
.cg-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 18px;
  border-bottom: 1px solid var(--border-subtle);
}
.cg-title {
  margin: 0;
  font-size: 0.98em;
  font-weight: 600;
  color: var(--text-primary);
}
.cg-close {
  width: 28px;
  height: 28px;
  border: 0;
  background: transparent;
  color: var(--text-muted);
  font-size: 1.4em;
  cursor: pointer;
  border-radius: 6px;
}
.cg-close:hover {
  background: var(--surface-4);
  color: var(--text-primary);
}
.cg-body {
  padding: 12px 18px 18px;
  overflow-y: auto;
}
.no-data {
  text-align: center;
  color: var(--text-muted);
  padding: 30px;
  font-size: 0.86em;
}
.cg-count {
  margin: 0 0 10px;
  font-size: 0.72em;
  color: var(--text-muted);
}
.cg-list {
  display: flex;
  flex-direction: column;
}
.cg-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 7px 2px;
  border-bottom: 1px solid var(--border-subtle);
}
.cg-row:last-child {
  border-bottom: none;
}
.cg-icon {
  width: 26px;
  height: 26px;
  border-radius: 5px;
  object-fit: cover;
  flex-shrink: 0;
  background: var(--surface-3);
}
.cg-icon--fallback {
  border: 1px solid var(--border-default);
}
.cg-name {
  flex: 1;
  min-width: 0;
  font-size: 0.84em;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.cg-hours {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  font-size: 0.66em;
}
.cg-hours .me {
  color: var(--color-primary);
  font-weight: 600;
}
.cg-hours .friend {
  color: var(--text-muted);
}

@media (max-width: 768px) {
  .cg-box {
    width: calc(100vw - 16px);
    max-height: 88vh;
  }
}
</style>
