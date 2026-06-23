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
                ➕ 添加好友
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
  gap: 24px;
  height: 100%;
}

.dashboard-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 24px;
  min-width: 0;
  overflow-y: auto;
  padding-right: 4px;
}

.dashboard-panels {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 24px;
}

.dashboard-section {
  flex-shrink: 0;
}

.section-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 24px;
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
