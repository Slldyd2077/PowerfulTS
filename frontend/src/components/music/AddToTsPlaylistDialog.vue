<script setup lang="ts">
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useTsPlaylistStore } from '@/stores/ts_playlist'
import type { Song } from '@/api/music'

const props = defineProps<{ visible: boolean; song: Song | null }>()
const emit = defineEmits<{ (e: 'update:visible', v: boolean): void }>()

const ts = useTsPlaylistStore()
const selectedId = ref<number | null>(null)
const newPlaylistName = ref('')
const submitting = ref(false)

watch(
  () => props.visible,
  async (open) => {
    if (!open) return
    selectedId.value = null
    newPlaylistName.value = ''
    await ts.fetchPlaylists()
    if (ts.playlists.length) selectedId.value = ts.playlists[0].id
  },
)

async function onConfirm() {
  if (!props.song) return
  const newName = newPlaylistName.value.trim()
  submitting.value = true
  try {
    let pid = selectedId.value
    if (newName) {
      const p = await ts.createPlaylist(newName)
      pid = p.id
    }
    if (pid == null) {
      ElMessage.warning('请选择一个歌单，或填写新歌单名称')
      return
    }
    await ts.addSong(pid, props.song)
    ElMessage.success('已收藏到 TS 歌单')
    emit('update:visible', false)
  } catch (e: unknown) {
    const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
    ElMessage.error(typeof detail === 'string' ? detail : '收藏失败')
  } finally {
    submitting.value = false
  }
}

function close() {
  emit('update:visible', false)
}
</script>

<template>
  <div v-if="props.visible" class="dlg-overlay" @click.self="close">
    <div class="dlg-box">
      <div class="dlg-head">
        <span>收藏到 TS 歌单</span>
        <button class="dlg-close" @click="close">×</button>
      </div>
      <div class="dlg-body">
        <p class="dlg-song">{{ props.song?.name }} · {{ props.song?.artist }}</p>
        <div class="dlg-list">
          <label
            v-for="pl in ts.playlists"
            :key="pl.id"
            class="dlg-item"
            :class="{ active: selectedId === pl.id }"
          >
            <input type="radio" :value="pl.id" v-model="selectedId" />
            <span class="dlg-item-name">{{ pl.name }}</span>
            <span class="dlg-item-count">{{ pl.songCount || 0 }}</span>
          </label>
          <div v-if="ts.playlists.length === 0" class="dlg-empty">还没有歌单，在下面新建一个</div>
        </div>
        <input
          class="dlg-new"
          v-model.trim="newPlaylistName"
          placeholder="或新建歌单（填写名称）"
          maxlength="128"
        />
      </div>
      <div class="dlg-foot">
        <button class="dlg-btn" @click="close">取消</button>
        <button class="dlg-btn primary" :disabled="submitting" @click="onConfirm">收藏</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.dlg-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  display: grid;
  place-items: center;
  z-index: 1000;
}
.dlg-box {
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  width: 420px;
  max-width: calc(100vw - 24px);
  max-height: 80vh;
  display: flex;
  flex-direction: column;
}
.dlg-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  border-bottom: 1px solid var(--border-subtle);
  font-weight: 600;
  color: var(--text-primary);
}
.dlg-close {
  border: 0;
  background: transparent;
  color: var(--text-muted);
  font-size: 1.3em;
  cursor: pointer;
  border-radius: 6px;
}
.dlg-close:hover {
  background: var(--surface-4);
}
.dlg-body {
  padding: 14px 16px;
  overflow-y: auto;
}
.dlg-song {
  margin: 0 0 12px;
  font-size: 0.8em;
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.dlg-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 12px;
}
.dlg-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  cursor: pointer;
  font-size: 0.82em;
}
.dlg-item:hover {
  background: var(--surface-4);
}
.dlg-item.active {
  border-color: var(--color-primary);
  background: rgba(var(--color-primary-rgb), 0.08);
}
.dlg-item input {
  accent-color: var(--color-primary);
}
.dlg-item-name {
  flex: 1;
  color: var(--text-primary);
}
.dlg-item-count {
  font-size: 0.8em;
  color: var(--text-muted);
}
.dlg-empty {
  text-align: center;
  color: var(--text-muted);
  padding: 16px;
  font-size: 0.8em;
}
.dlg-new {
  width: 100%;
  padding: 8px 10px;
  border: 1px solid var(--border-emphasis);
  border-radius: 8px;
  background: transparent;
  color: var(--text-primary);
  font-size: 0.82em;
  box-sizing: border-box;
}
.dlg-new:focus {
  outline: none;
  border-color: var(--color-primary);
}
.dlg-foot {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 12px 16px;
  border-top: 1px solid var(--border-subtle);
}
.dlg-btn {
  padding: 6px 16px;
  border: 1px solid var(--border-emphasis);
  border-radius: 8px;
  background: transparent;
  color: var(--text-secondary);
  font-size: 0.8em;
  cursor: pointer;
}
.dlg-btn.primary {
  background: var(--color-primary);
  border-color: var(--color-primary);
  color: var(--text-inverse);
}
.dlg-btn:disabled {
  opacity: 0.5;
}
</style>
