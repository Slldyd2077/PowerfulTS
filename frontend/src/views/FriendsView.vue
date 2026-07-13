<script setup lang="ts">
import { ref } from 'vue'
import FriendsList from '@/components/social/FriendsList.vue'
import AddFriendDialog from '@/components/social/AddFriendDialog.vue'
import FriendNotifySettings from '@/components/social/FriendNotifySettings.vue'

const showAddFriend = ref(false)
const friendsListKey = ref(0)
function refreshFriends() {
  friendsListKey.value += 1
}
</script>

<template>
  <div class="friends-view">
    <div class="page-header">
      <div class="page-title-group">
        <h1 class="page-title">好友列表</h1>
        <span class="page-sub label-mono">FRIENDS</span>
      </div>
    </div>

    <div class="friends-content">
      <FriendsList :key="friendsListKey" />
      <div class="add-friend-wrapper">
        <el-button type="primary" plain @click="showAddFriend = true" class="add-friend-btn">
          添加好友
        </el-button>
      </div>
      <FriendNotifySettings />
    </div>

    <AddFriendDialog v-model:visible="showAddFriend" @added="refreshFriends" />
  </div>
</template>

<style scoped>
.friends-view {
  display: flex;
  flex-direction: column;
  gap: 20px;
  height: 100%;
  overflow-y: auto;
}

.page-header {
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

.friends-content {
  max-width: 520px;
}

.add-friend-wrapper {
  margin-top: 12px;
  text-align: center;
}

.add-friend-btn {
  width: 100%;
}

/* 移动端：间距收缩、标题流式缩放、添加好友按钮加大触摸区 */
@media (max-width: 768px) {
  .friends-view { gap: 14px; height: auto; overflow: visible; }
  .page-header { padding-bottom: 12px; }
  .page-title {
    font-size: clamp(1.1em, 4vw, 1.4em);
  }
  .add-friend-btn {
    min-height: 44px;
    font-size: 0.9em;
  }
}
</style>
