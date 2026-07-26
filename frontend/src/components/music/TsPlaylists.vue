<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useTsPlaylistStore } from '@/stores/ts_playlist'
import type { TsPlaylistSong } from '@/api/ts_playlist'

const ts = useTsPlaylistStore()
const { playlists, currentSongs, expandedId, loadingSongs } = storeToRefs(ts)

const coverInput = ref<HTMLInputElement | null>(null)
let coverTargetId: number | null = null

const PLATFORM_LABEL: Record<string, string> = {
  netease: '网易云',
  qq: 'QQ',
  bilibili: 'B站',
  kugou: '酷狗',
}

onMounted(() => ts.fetchPlaylists())

function readFileAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader()
    r.onload = () => (typeof r.result === 'string' ? resolve(r.result) : reject(new Error('读取失败')))
    r.onerror = () => reject(r.error)
    r.readAsDataURL(file)
  })
}

async function onCreate() {
  try {
    const res = await ElMessageBox.prompt('歌单名称', '新建 TS 歌单', {
      inputPattern: /\S/, inputErrorMessage: '名称不能为空',
    })
    const name = (res.value || '').trim().slice(0, 128)
    if (name) {
      await ts.createPlaylist(name)
      ElMessage.success('已创建')
    }
  } catch { /* 取消 */ }
}

async function onRename(id: number, cur: string) {
  try {
    const res = await ElMessageBox.prompt('歌单名称', '重命名', {
      inputValue: cur, inputPattern: /\S/, inputErrorMessage: '名称不能为空',
    })
    const name = (res.value || '').trim().slice(0, 128)
    if (name && name !== cur) {
      await ts.renamePlaylist(id, name)
      ElMessage.success('已改名')
    }
  } catch { /* */ }
}

async function onDelete(id: number, name: string) {
  try {
    await ElMessageBox.confirm(`确定删除歌单「${name}」？收藏的歌曲会一并移除。`, '删除', { type: 'warning' })
  } catch { return }
  await ts.deletePlaylist(id)
  ElMessage.success('已删除')
}

async function onPlayAll(id: number) {
  try {
    const res = await ts.playAll(id)
    if (res.enqueued === 0) ElMessage.warning('没有可播放的曲目（可能平台未登录或版权限制）')
    else ElMessage.success(`已加入 ${res.enqueued} 首`)
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '播放失败')
  }
}

function pickCover(id: number) {
  coverTargetId = id
  coverInput.value?.click()
}

async function onCoverPicked(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file || coverTargetId == null) return
  if (!/^image\/(png|jpe?g|webp)$/.test(file.type)) {
    ElMessage.error('仅支持 PNG/JPG/WebP'); coverTargetId = null; return
  }
  if (file.size > 200 * 1024) {
    ElMessage.error('封面需 ≤200KB'); coverTargetId = null; return
  }
  try {
    const dataUrl = await readFileAsDataUrl(file)
    await ts.uploadCover(coverTargetId, dataUrl)
    ElMessage.success('封面已更新')
  } catch {
    ElMessage.error('上传失败')
  } finally {
    coverTargetId = null
  }
}

async function onEditNote(song: TsPlaylistSong) {
  if (expandedId.value == null) return
  try {
    const res = await ElMessageBox.prompt('备注名（留空恢复原标题）', '修改备注', {
      inputValue: song.note || '', inputPlaceholder: song.originalName,
    })
    const note = (res.value || '').trim().slice(0, 255)
    await ts.updateSongNote(expandedId.value, song.platform, song.songId, note)
    ElMessage.success('已更新')
  } catch { /* */ }
}

async function onRemoveSong(song: TsPlaylistSong) {
  if (expandedId.value == null) return
  await ts.removeSong(expandedId.value, song.platform, song.songId)
}
</script>

<template>
  <div class="ts-playlists section">
    <input ref="coverInput" type="file" accept="image/png,image/jpeg,image/webp" hidden @change="onCoverPicked" />

    <div class="section-head">
      <span class="section-title">TS 歌单</span>
      <span class="section-sub label-mono">MIX</span>
      <button class="ts-create-btn" @click="onCreate">+ 新建</button>
    </div>

    <div v-if="playlists.length === 0" class="empty">
      还没有 TS 歌单。点「+ 新建」创建一个跨平台混合歌单，把搜索到或平台歌单里的歌收藏进来。
    </div>

    <div v-else class="pl-list">
      <div v-for="pl in playlists" :key="pl.id" class="pl-item">
        <div class="pl-row" @click="ts.toggleExpand(pl.id)">
          <div class="pl-cover" :title="'点击更换封面'" @click.stop="pickCover(pl.id)">
            <img v-if="pl.coverDataUrl" :src="pl.coverDataUrl" :alt="pl.name" />
            <span v-else class="pl-cover-fallback">♪</span>
          </div>
          <div class="pl-info">
            <span class="pl-name">{{ pl.name }}</span>
            <span class="pl-count">{{ pl.songCount || 0 }} 首</span>
          </div>
          <div class="pl-actions" @click.stop>
            <button class="mini primary" @click="onPlayAll(pl.id)">▶ 播放</button>
            <button class="mini" @click="onRename(pl.id, pl.name)">改名</button>
            <button class="mini danger" @click="onDelete(pl.id, pl.name)">删除</button>
            <svg class="pl-arrow" :class="{ open: expandedId === pl.id }" viewBox="0 0 16 16" width="14" height="14">
              <path d="M4 6l4 4 4-4" fill="none" stroke="currentColor" stroke-width="1.6" />
            </svg>
          </div>
        </div>

        <div v-if="expandedId === pl.id" class="pl-songs">
          <div v-if="loadingSongs[pl.id]" class="empty">加载中…</div>
          <div v-else-if="(currentSongs[pl.id] || []).length === 0" class="empty">
            空歌单——去搜索，或从下面平台歌单里点「收藏」加几首
          </div>
          <div v-else>
            <div
              v-for="s in currentSongs[pl.id]"
              :key="s.platform + ':' + s.songId"
              class="song-row"
            >
              <img v-if="s.coverUrl" :src="s.coverUrl" class="song-cover" :alt="s.name" loading="lazy" />
              <div v-else class="song-cover fallback"></div>
              <div class="song-meta">
                <span class="song-title">
                  {{ s.name }}
                  <span v-if="s.note" class="song-note-tag" :title="'原标题：' + s.originalName">备注</span>
                </span>
                <span class="song-sub">
                  <span class="platform-tag" :class="s.platform">{{ PLATFORM_LABEL[s.platform] || s.platform }}</span>
                  <span class="song-artist">{{ s.artist }}</span>
                </span>
              </div>
              <div class="song-ops">
                <button title="播放" @click="ts.playSong(s, false)">▶</button>
                <button title="加入队列" @click="ts.playSong(s, true)">＋</button>
                <button title="改备注" @click="onEditNote(s)">✎</button>
                <button title="移除" class="danger" @click="onRemoveSong(s)">✕</button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.section {
  margin-bottom: 18px;
}
.section-head {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 10px;
}
.section-title {
  font-size: 0.92em;
  font-weight: 600;
  color: var(--text-primary);
}
.section-sub {
  font-size: 0.58em;
  color: var(--text-muted);
}
.ts-create-btn {
  margin-left: auto;
  padding: 3px 12px;
  border: 1px solid var(--border-emphasis);
  border-radius: 8px;
  background: transparent;
  color: var(--color-primary);
  font-size: 0.72em;
  cursor: pointer;
}
.ts-create-btn:hover {
  background: rgba(var(--color-primary-rgb), 0.08);
}

.empty {
  text-align: center;
  color: var(--text-muted);
  padding: 18px;
  font-size: 0.78em;
  line-height: 1.5;
}

.pl-list {
  display: flex;
  flex-direction: column;
}
.pl-item {
  border-bottom: 1px solid var(--border-subtle);
}
.pl-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 4px;
  cursor: pointer;
}
.pl-row:hover {
  background: var(--surface-4);
}
.pl-cover {
  width: 40px;
  height: 40px;
  border-radius: 8px;
  flex-shrink: 0;
  overflow: hidden;
  border: 1px solid var(--border-default);
  display: grid;
  place-items: center;
  background: var(--surface-3);
}
.pl-cover img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.pl-cover-fallback {
  color: var(--text-muted);
  font-size: 1.1em;
}
.pl-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.pl-name {
  font-size: 0.86em;
  font-weight: 600;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.pl-count {
  font-size: 0.66em;
  color: var(--text-muted);
}
.pl-actions {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}
.mini {
  padding: 3px 9px;
  border: 1px solid var(--border-emphasis);
  border-radius: 7px;
  background: transparent;
  color: var(--text-secondary);
  font-size: 0.66em;
  cursor: pointer;
}
.mini:hover {
  color: var(--color-primary);
  border-color: var(--color-primary);
}
.mini.primary {
  color: var(--color-primary);
  border-color: var(--color-primary);
}
.mini.danger:hover {
  color: var(--color-danger);
  border-color: var(--color-danger);
}
.pl-arrow {
  color: var(--text-muted);
  transition: transform 0.2s;
  margin-left: 2px;
}
.pl-arrow.open {
  transform: rotate(180deg);
}

.pl-songs {
  padding: 2px 0 8px;
}
.song-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 8px 6px 12px;
  border-radius: 6px;
}
.song-row:hover {
  background: var(--surface-4);
}
.song-cover {
  width: 30px;
  height: 30px;
  border-radius: 6px;
  object-fit: cover;
  flex-shrink: 0;
  background: var(--surface-3);
}
.song-cover.fallback {
  border: 1px solid var(--border-default);
}
.song-meta {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.song-title {
  font-size: 0.82em;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.song-note-tag {
  display: inline-block;
  margin-left: 5px;
  padding: 0 4px;
  font-size: 0.7em;
  border-radius: 3px;
  background: rgba(var(--color-primary-rgb), 0.16);
  color: var(--color-primary);
  vertical-align: middle;
}
.song-sub {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.64em;
  color: var(--text-muted);
}
.song-artist {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.platform-tag {
  flex-shrink: 0;
  padding: 0 5px;
  border-radius: 3px;
  font-size: 0.82em;
  font-weight: 600;
  color: #fff;
}
.platform-tag.netease { background: #c20c0c; }
.platform-tag.qq { background: #31c27c; }
.platform-tag.bilibili { background: #fb7299; }
.platform-tag.kugou { background: #2ca2f9; }

.song-ops {
  display: flex;
  gap: 2px;
  flex-shrink: 0;
}
.song-ops button {
  width: 26px;
  height: 26px;
  border: 0;
  background: transparent;
  color: var(--text-muted);
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.8em;
}
.song-ops button:hover {
  background: var(--surface-3);
  color: var(--text-primary);
}
.song-ops button.danger:hover {
  color: var(--color-danger);
}
</style>
