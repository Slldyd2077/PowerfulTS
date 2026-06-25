<script setup lang="ts">
import MusicSearch from '@/components/music/MusicSearch.vue'
import MusicPlayer from '@/components/music/MusicPlayer.vue'
import PlatformAccounts from '@/components/music/PlatformAccounts.vue'
</script>

<template>
  <div class="music-view">
    <div class="page-header">
      <div class="page-title-group">
        <h1 class="page-title">音乐控制</h1>
        <span class="page-sub label-mono">MUSIC · TSMUSICBOT</span>
      </div>
    </div>

    <div class="music-grid">
      <div class="music-main">
        <MusicSearch />
      </div>

      <div class="music-side">
        <MusicPlayer />
        <PlatformAccounts />
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

.page-title-group { display: flex; flex-direction: column; gap: 4px; }
.page-title { font-size: 1.4em; font-weight: 700; color: var(--text-primary); margin: 0; letter-spacing: -0.02em; line-height: 1.1; }
.page-sub { font-size: 0.62em; color: var(--text-muted); }

.music-grid {
  display: grid;
  grid-template-columns: 1fr 384px;
  gap: 20px;
  align-items: start;
}

.music-main { min-width: 0; }
.music-side { position: sticky; top: 0; }

@media (max-width: 1100px) {
  .music-grid { grid-template-columns: 1fr; }
  .music-side { position: static; }
}
</style>
