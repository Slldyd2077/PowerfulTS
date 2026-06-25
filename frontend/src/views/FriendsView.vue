<script setup lang="ts">
import { ref } from 'vue'
import FriendsList from '@/components/social/FriendsList.vue'
import AddFriendDialog from '@/components/social/AddFriendDialog.vue'

const showAddFriend = ref(false)
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
      <FriendsList />
      <div class="add-friend-wrapper">
        <el-button type="primary" plain @click="showAddFriend = true" class="add-friend-btn">
          添加好友
        </el-button>
      </div>
    </div>

    <AddFriendDialog v-model:visible="showAddFriend" />
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
</style>
