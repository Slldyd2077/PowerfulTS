<script setup lang="ts">
import { ref } from 'vue'
import { useMonitorStore } from '@/stores/monitor'
import { usePolling } from '@/composables/usePolling'
import StatsCards from '@/components/monitor/StatsCards.vue'
import OnlineUsers from '@/components/monitor/OnlineUsers.vue'
import GameStats from '@/components/monitor/GameStats.vue'
import ChannelSidebar from '@/components/monitor/ChannelSidebar.vue'
import MusicSearch from '@/components/music/MusicSearch.vue'
import BiliSearch from '@/components/bilibili/BiliSearch.vue'
import MusicPlayer from '@/components/music/MusicPlayer.vue'
import RadioControl from '@/components/music/RadioControl.vue'
import FriendsList from '@/components/social/FriendsList.vue'
import AddFriendDialog from '@/components/social/AddFriendDialog.vue'

const monitor = useMonitorStore()

// 5 秒轮询更新数据
usePolling(() => monitor.fetchStats(), 5000)

const showAddFriend = ref(false)

function onFriendAdded() {
  // FriendsList 内部会通过 usePolling 自动刷新，这里不需要额外操作
}
</script>

<template>
  <div class="dashboard">
    <div class="dashboard-main">
      <!-- 页头：遥测标题条 -->
      <div class="page-header">
        <div class="page-title-group">
          <h1 class="page-title">服务器监控</h1>
          <span class="page-sub label-mono">SERVER MONITOR · TS3</span>
        </div>
        <div class="page-meta">
          <span v-if="monitor.stats?.monitor_running === false" class="meta-off">
            <span class="meta-dot meta-dot--off"></span>监控未运行
          </span>
          <span v-else-if="monitor.lastUpdate !== '--'" class="meta-live">
            <span class="meta-dot"></span>实时 · {{ monitor.lastUpdate }}
          </span>
          <span v-else class="meta-idle">
            <span class="meta-dot meta-dot--idle"></span>等待数据
          </span>
        </div>
      </div>

      <!-- 统计卡片 -->
      <StatsCards />

      <!-- 在线用户 + 游戏统计 -->
      <div class="dashboard-panels">
        <OnlineUsers />
        <GameStats />
      </div>

      <!-- 音乐控制 -->
      <div class="dashboard-section">
        <div class="section-grid">
          <div>
            <MusicSearch />
            <BiliSearch />
            <MusicPlayer />
            <RadioControl />
          </div>

          <!-- 好友列表 -->
          <div>
            <FriendsList />
            <div class="add-friend-wrapper">
              <el-button type="primary" plain @click="showAddFriend = true" class="add-friend-btn">
                添加好友
              </el-button>
            </div>
            <AddFriendDialog v-model:visible="showAddFriend" @added="onFriendAdded" />
          </div>
        </div>
      </div>
    </div>

    <!-- 频道侧边栏 -->
    <ChannelSidebar class="dashboard-sidebar" />
  </div>
</template>

<style scoped>
.dashboard {
  display: flex;
  gap: 20px;
  height: 100%;
}

.dashboard-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 20px;
  min-width: 0;
  overflow-y: auto;
  padding-right: 4px;
}

/* ── 页头遥测条 ── */
.page-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  flex-shrink: 0;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--border-subtle);
}

.page-title-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.page-title {
  font-size: 1.4em;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
  letter-spacing: -0.02em;
  line-height: 1.1;
}

.page-sub {
  font-size: 0.62em;
  color: var(--text-muted);
}

.page-meta {
  display: flex;
  align-items: center;
  gap: 12px;
}

.meta-live,
.meta-off,
.meta-idle {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.7em;
  color: var(--text-secondary);
  letter-spacing: 0.04em;
}

.meta-live {
  color: var(--color-success);
}

.meta-off {
  color: var(--color-danger);
}

.meta-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--color-success);
  animation: pulse-glow 2s ease-in-out infinite;
}
.meta-dot--off {
  background: var(--color-danger);
  animation: none;
}
.meta-dot--idle {
  background: var(--text-muted);
  animation: none;
}

.dashboard-panels {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
}

.dashboard-section {
  flex-shrink: 0;
}

.section-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
}

.dashboard-sidebar {
  width: 300px;
  flex-shrink: 0;
}

.add-friend-wrapper {
  margin-top: 12px;
  text-align: center;
}

.add-friend-btn {
  width: 100%;
}

@media (max-width: 1100px) {
  .dashboard {
    flex-direction: column;
  }
  .dashboard-panels,
  .section-grid {
    grid-template-columns: 1fr;
  }
  .dashboard-sidebar {
    width: 100%;
  }
}
</style>
