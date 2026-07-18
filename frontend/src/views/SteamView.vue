<script setup lang="ts">
import { ref } from 'vue'
import { getSteamMe, type SteamMeResponse } from '@/api/steam'
import { usePolling } from '@/composables/usePolling'
import SteamBinding from '@/components/steam/SteamBinding.vue'
import MySteamProfile from '@/components/steam/MySteamProfile.vue'
import SteamFriends from '@/components/steam/SteamFriends.vue'
import SteamLeaderboard from '@/components/steam/SteamLeaderboard.vue'

const me = ref<SteamMeResponse | null>(null)

async function fetchMe() {
  try {
    me.value = await getSteamMe()
  } catch {
    /* 静默；未登录 401 由拦截器统一处理 */
  }
}

usePolling(fetchMe, 60000)
</script>

<template>
  <div class="steam-view">
    <div class="page-header">
      <div class="page-title-group">
        <h1 class="page-title">Steam</h1>
        <span class="page-sub label-mono">STEAM</span>
      </div>
    </div>

    <SteamBinding :me="me" @refresh="fetchMe" />

    <div class="steam-grid">
      <div class="grid-col">
        <MySteamProfile :me="me" />
        <SteamLeaderboard />
      </div>
      <div class="grid-col">
        <SteamFriends />
      </div>
    </div>
  </div>
</template>

<style scoped>
.steam-view {
  display: flex;
  flex-direction: column;
  gap: 18px;
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

.steam-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 18px;
  align-items: start;
}
.grid-col {
  display: flex;
  flex-direction: column;
  gap: 18px;
  min-width: 0;
}

@media (max-width: 900px) {
  .steam-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 768px) {
  .steam-view {
    gap: 14px;
    height: auto;
    overflow: visible;
  }
  .page-header {
    padding-bottom: 12px;
  }
  .page-title {
    font-size: clamp(1.1em, 4vw, 1.4em);
  }
}
</style>
