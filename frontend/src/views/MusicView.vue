<script setup lang="ts">
import MusicSearch from '@/components/music/MusicSearch.vue'
import BiliSearch from '@/components/bilibili/BiliSearch.vue'
import MusicPlayer from '@/components/music/MusicPlayer.vue'
import RadioControl from '@/components/music/RadioControl.vue'
import NeteaseAccount from '@/components/music/NeteaseAccount.vue'
</script>

<template>
  <div class="music-view">
    <div class="page-header">
      <div class="page-title-group">
        <h1 class="page-title">音乐控制</h1>
        <span class="page-sub label-mono">MUSIC · NETEASE / BILIBILI</span>
      </div>
    </div>

    <div class="music-grid">
      <div class="music-main">
        <MusicSearch />
        <BiliSearch />
        <MusicPlayer />
        <RadioControl />
      </div>

      <div class="music-side">
        <NeteaseAccount />
      </div>
    </div>
  </div>
</template>

<style scoped>
.music-view {
  display: flex;
  flex-direction: column;
  gap: 20px;
  height: 100%;
  overflow-y: auto;
}

.page-header {
  display: flex;
  align-items: flex-end;
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

.music-grid {
  display: grid;
  grid-template-columns: 1fr 320px;
  gap: 20px;
  align-items: start;
}

.music-main {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-width: 0;
}

.music-side {
  position: sticky;
  top: 0;
}

.placeholder {
  background: var(--gradient-surface);
  border: 1px dashed var(--border-default);
  border-radius: var(--radius-md);
  padding: 40px 24px;
  text-align: center;
}

.placeholder-icon {
  font-size: 2.4em;
  display: block;
  margin-bottom: 12px;
  opacity: 0.7;
}

.placeholder-title {
  font-size: 1em;
  font-weight: 600;
  color: var(--text-secondary);
  margin: 0 0 8px;
}

.placeholder-desc {
  font-size: 0.82em;
  color: var(--text-muted);
  line-height: 1.6;
  margin: 0 0 16px;
}

.placeholder-hint {
  font-size: 0.6em;
  color: var(--color-primary);
  letter-spacing: 0.1em;
}

@media (max-width: 1100px) {
  .music-grid {
    grid-template-columns: 1fr;
  }
  .music-side {
    position: static;
  }
}
</style>
