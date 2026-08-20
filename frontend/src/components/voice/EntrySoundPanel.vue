<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { isAxiosError } from 'axios'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  deleteEntrySound,
  getEntrySound,
  uploadEntrySound,
  type EntrySoundMetadata,
} from '@/api/entrySound'
import { useAuthStore } from '@/stores/auth'

const MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024
const MAX_DURATION_SECONDS = 7
const AUDIO_EXTENSIONS = new Set([
  'aac', 'flac', 'm4a', 'mp3', 'mp4', 'oga', 'ogg', 'wav', 'wave',
])
const AUDIO_MIME_TYPES = new Set([
  'application/ogg',
  'audio/aac',
  'audio/flac',
  'audio/mp3',
  'audio/mp4',
  'audio/mpeg',
  'audio/ogg',
  'audio/vnd.wave',
  'audio/wav',
  'audio/wave',
  'audio/x-aac',
  'audio/x-flac',
  'audio/x-m4a',
  'audio/x-wav',
])
const ACCEPTED_AUDIO_TYPES = [
  '.mp3', '.wav', '.wave', '.ogg', '.oga', '.m4a', '.mp4', '.aac', '.flac',
  ...AUDIO_MIME_TYPES,
].join(',')

type BusyState = 'idle' | 'loading' | 'validating' | 'uploading' | 'deleting'

const auth = useAuthStore()
const fileInput = ref<HTMLInputElement | null>(null)
const metadata = ref<EntrySoundMetadata>({ configured: false })
const selectedFile = ref<File | null>(null)
const selectedDurationMs = ref(0)
const previewUrl = ref('')
const previewName = ref('')
const busyState = ref<BusyState>('idle')
const uploadProgress = ref(0)
const errorMessage = ref('')
const isDragging = ref(false)
const isRegistered = computed(() => auth.isLoggedIn && !auth.isGuest && auth.role !== 'guest')
const registeredSessionKey = computed(() => isRegistered.value ? auth.token || '' : '')
const isBusy = computed(() => busyState.value !== 'idle')
const uploadButtonLabel = computed(() => {
  if (busyState.value === 'uploading') {
    return uploadProgress.value >= 100 ? '正在保存…' : `正在上传 ${uploadProgress.value}%`
  }
  return metadata.value.configured ? '替换为此音效' : '上传此音效'
})

let selectionVersion = 0
let requestGeneration = 0
let metadataController: AbortController | null = null
let uploadController: AbortController | null = null

function formatBytes(bytes?: number): string {
  if (bytes === undefined) return '—'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KiB`
  return `${(bytes / (1024 * 1024)).toFixed(2)} MiB`
}

function formatDuration(durationMs?: number): string {
  if (durationMs === undefined) return '—'
  const seconds = durationMs / 1000
  return `${Number.isInteger(seconds) ? seconds.toFixed(0) : seconds.toFixed(1)} 秒`
}

function apiErrorText(error: unknown, fallback: string): string {
  if (isAxiosError(error)) {
    const body = error.response?.data as { detail?: string; error?: string; message?: string } | undefined
    return body?.detail || body?.error || body?.message || (!error.response ? '无法连接 PowerfulTS 后端' : fallback)
  }
  return error instanceof Error ? error.message : fallback
}

function clearPreview() {
  selectionVersion += 1
  selectedFile.value = null
  selectedDurationMs.value = 0
  previewName.value = ''
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
  previewUrl.value = ''
  if (fileInput.value) fileInput.value.value = ''
}

function fileExtension(filename: string): string {
  return filename.toLowerCase().match(/\.([^.]+)$/)?.[1] || ''
}

function validateFileBasics(file: File): string {
  if (file.size === 0) return '音频文件不能为空。'
  if (file.size > MAX_FILE_SIZE_BYTES) return '文件超过 10 MiB，请压缩或裁剪后再上传。'

  const extension = fileExtension(file.name)
  const mimeType = file.type.toLowerCase().split(';', 1)[0]
  if (!AUDIO_EXTENSIONS.has(extension)) {
    return '不支持该文件扩展名，请选择 MP3、WAV、OGG、M4A、AAC 或 FLAC 音频。'
  }
  if (mimeType && !AUDIO_MIME_TYPES.has(mimeType)) {
    return '文件类型与支持的音频格式不匹配。'
  }
  return ''
}

function readAudioDuration(url: string): Promise<number> {
  return new Promise((resolve, reject) => {
    const audio = document.createElement('audio')
    const timeout = window.setTimeout(() => finish(new Error('读取音频时长超时，请换一个文件重试。')), 10_000)

    function cleanup() {
      window.clearTimeout(timeout)
      audio.removeEventListener('loadedmetadata', onLoadedMetadata)
      audio.removeEventListener('error', onError)
      audio.removeAttribute('src')
    }

    function finish(error?: Error, duration?: number) {
      cleanup()
      if (error) reject(error)
      else resolve(duration || 0)
    }

    function onLoadedMetadata() {
      if (!Number.isFinite(audio.duration) || audio.duration <= 0) {
        finish(new Error('浏览器无法读取这个音频的时长，请转换为 MP3 或 WAV 后重试。'))
        return
      }
      finish(undefined, audio.duration)
    }

    function onError() {
      finish(new Error('浏览器无法解析这个音频，请确认文件没有损坏。'))
    }

    audio.preload = 'metadata'
    audio.addEventListener('loadedmetadata', onLoadedMetadata, { once: true })
    audio.addEventListener('error', onError, { once: true })
    audio.src = url
    audio.load()
  })
}

async function selectFile(file: File) {
  clearPreview()
  errorMessage.value = ''
  const basicError = validateFileBasics(file)
  if (basicError) {
    errorMessage.value = basicError
    return
  }

  const version = selectionVersion
  const objectUrl = URL.createObjectURL(file)
  busyState.value = 'validating'
  try {
    const durationSeconds = await readAudioDuration(objectUrl)
    if (version !== selectionVersion) {
      URL.revokeObjectURL(objectUrl)
      return
    }
    if (durationSeconds > MAX_DURATION_SECONDS) {
      URL.revokeObjectURL(objectUrl)
      errorMessage.value = `音频时长为 ${durationSeconds.toFixed(1)} 秒，不能超过 7 秒。`
      return
    }
    selectedFile.value = file
    selectedDurationMs.value = Math.round(durationSeconds * 1000)
    previewUrl.value = objectUrl
    previewName.value = file.name
  } catch (error) {
    URL.revokeObjectURL(objectUrl)
    errorMessage.value = error instanceof Error ? error.message : '无法读取音频文件。'
  } finally {
    if (version === selectionVersion) busyState.value = 'idle'
  }
}

function onFilePicked(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (file) void selectFile(file)
}

function onDrop(event: DragEvent) {
  isDragging.value = false
  const files = event.dataTransfer?.files
  if (!files?.length) return
  if (files.length > 1) {
    errorMessage.value = '每次只能上传一个入场音效。'
    return
  }
  void selectFile(files[0])
}

async function loadMetadata() {
  const generation = ++requestGeneration
  metadataController?.abort()
  const controller = new AbortController()
  metadataController = controller
  busyState.value = 'loading'
  errorMessage.value = ''
  try {
    const result = await getEntrySound(controller.signal)
    if (generation === requestGeneration && isRegistered.value) metadata.value = result
  } catch (error) {
    if (!controller.signal.aborted && generation === requestGeneration) {
      errorMessage.value = apiErrorText(error, '读取入场音效配置失败。')
    }
  } finally {
    if (metadataController === controller) metadataController = null
    if (generation === requestGeneration) busyState.value = 'idle'
  }
}

async function uploadSelectedFile() {
  if (!selectedFile.value || isBusy.value) return
  busyState.value = 'uploading'
  uploadProgress.value = 0
  errorMessage.value = ''
  const generation = requestGeneration
  const controller = new AbortController()
  uploadController = controller
  try {
    const result = await uploadEntrySound(selectedFile.value, (progress) => {
      if (generation === requestGeneration) uploadProgress.value = progress
    }, controller.signal)
    if (generation !== requestGeneration || !isRegistered.value) return
    metadata.value = result
    selectedFile.value = null
    if (fileInput.value) fileInput.value.value = ''
    ElMessage.success('入场音效已保存，下次切换频道时生效')
  } catch (error) {
    if (!controller.signal.aborted && generation === requestGeneration) {
      errorMessage.value = apiErrorText(error, '上传入场音效失败。')
    }
  } finally {
    if (uploadController === controller) uploadController = null
    if (generation === requestGeneration) {
      uploadProgress.value = 0
      busyState.value = 'idle'
    }
  }
}

async function removeEntrySound() {
  if (isBusy.value) return
  try {
    await ElMessageBox.confirm(
      '删除后，下次切换频道将不再播放自定义入场音效。',
      '删除入场音效',
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }

  busyState.value = 'deleting'
  errorMessage.value = ''
  const generation = requestGeneration
  const controller = new AbortController()
  uploadController = controller
  try {
    await deleteEntrySound(controller.signal)
    if (generation !== requestGeneration || !isRegistered.value) return
    metadata.value = { configured: false }
    clearPreview()
    ElMessage.success('自定义入场音效已删除')
  } catch (error) {
    if (!controller.signal.aborted && generation === requestGeneration) {
      errorMessage.value = apiErrorText(error, '删除入场音效失败。')
    }
  } finally {
    if (uploadController === controller) uploadController = null
    if (generation === requestGeneration) busyState.value = 'idle'
  }
}

function invalidateRequests() {
  requestGeneration += 1
  metadataController?.abort()
  metadataController = null
  uploadController?.abort()
  uploadController = null
  uploadProgress.value = 0
  busyState.value = 'idle'
}

watch(registeredSessionKey, (sessionKey) => {
  invalidateRequests()
  if (sessionKey) void loadMetadata()
  else {
    metadata.value = { configured: false }
    clearPreview()
    errorMessage.value = ''
  }
}, { immediate: true })

onBeforeUnmount(() => {
  invalidateRequests()
  clearPreview()
})
</script>

<template>
  <section v-if="isRegistered" class="entry-sound-panel" aria-labelledby="entry-sound-title">
    <header class="panel-heading">
      <div class="sound-mark" aria-hidden="true">
        <span />
        <span />
        <span />
      </div>
      <div class="heading-copy">
        <div class="eyebrow">CHANNEL ENTRY · PERSONAL SOUND</div>
        <h2 id="entry-sound-title">自定义入场音效</h2>
        <p>上传后，你每次成功切换频道都会播放。音频不超过 7 秒，文件不超过 10 MiB。</p>
      </div>
      <span class="config-status" :class="{ configured: metadata.configured }">
        {{ busyState === 'loading' ? '读取中' : metadata.configured ? '已启用' : '未设置' }}
      </span>
    </header>

    <div v-if="metadata.configured" class="current-sound">
      <div class="current-icon" aria-hidden="true">♪</div>
      <div class="current-copy">
        <strong>{{ metadata.originalName || '自定义音效' }}</strong>
        <span>
          {{ formatDuration(metadata.durationMs) }} · {{ formatBytes(metadata.sizeBytes) }}
          <template v-if="metadata.mimeType"> · {{ metadata.mimeType }}</template>
        </span>
      </div>
      <button
        class="delete-button"
        type="button"
        :disabled="isBusy"
        aria-label="删除当前入场音效"
        @click="removeEntrySound"
      >
        {{ busyState === 'deleting' ? '删除中…' : '删除' }}
      </button>
    </div>

    <button
      class="drop-zone"
      :class="{ dragging: isDragging }"
      type="button"
      :disabled="isBusy"
      @click="fileInput?.click()"
      @dragenter.prevent="isDragging = true"
      @dragover.prevent="isDragging = true"
      @dragleave.prevent="isDragging = false"
      @drop.prevent="onDrop"
    >
      <span class="upload-icon" aria-hidden="true">↑</span>
      <span class="drop-copy">
        <strong>{{ metadata.configured ? '选择新音频替换' : '选择或拖入音频' }}</strong>
        <small>MP3 · WAV · OGG · M4A · AAC · FLAC</small>
      </span>
    </button>
    <input
      ref="fileInput"
      class="visually-hidden"
      type="file"
      :accept="ACCEPTED_AUDIO_TYPES"
      aria-label="选择入场音效文件"
      @change="onFilePicked"
    >
    <p v-if="busyState === 'validating'" class="validation-status" role="status" aria-live="polite">
      正在读取音频格式和时长…
    </p>

    <div v-if="previewUrl" class="preview-card">
      <div class="preview-heading">
        <div>
          <span class="preview-label">{{ selectedFile ? '上传前预览' : '本次上传预览' }}</span>
          <strong>{{ previewName }}</strong>
          <small>{{ formatDuration(selectedDurationMs) }}<template v-if="selectedFile"> · {{ formatBytes(selectedFile.size) }}</template></small>
        </div>
        <button
          type="button"
          class="clear-button"
          :disabled="isBusy"
          aria-label="清除本地预览"
          @click="clearPreview"
        >清除</button>
      </div>
      <audio :src="previewUrl" controls preload="metadata">当前浏览器不支持音频预览。</audio>
    </div>

    <div
      v-if="busyState === 'uploading'"
      class="upload-progress"
      role="progressbar"
      aria-label="入场音效上传进度"
      aria-valuemin="0"
      aria-valuemax="100"
      :aria-valuenow="uploadProgress"
    >
      <span :style="{ width: `${uploadProgress}%` }" />
    </div>

    <p v-if="errorMessage" class="entry-error" role="alert">
      <span>上传未完成</span>{{ errorMessage }}
    </p>

    <div v-if="selectedFile" class="panel-actions">
      <button class="upload-button" type="button" :disabled="isBusy" @click="uploadSelectedFile">
        {{ uploadButtonLabel }}
      </button>
      <span role="status" aria-live="polite">
        {{ busyState === 'validating' ? '正在读取音频时长…' : busyState === 'uploading' ? uploadButtonLabel : '确认预览无误后再上传' }}
      </span>
    </div>
  </section>

  <section v-else-if="auth.isGuest" class="entry-sound-unavailable" aria-label="自定义入场音效不可用">
    <span class="lock-mark" aria-hidden="true">◇</span>
    <div>
      <strong>自定义入场音效仅限正式账号</strong>
      <p>游客的临时通话身份不会保存个人音效；登录或注册后即可设置。</p>
    </div>
  </section>
</template>

<style scoped>
.entry-sound-panel,
.entry-sound-unavailable {
  position: relative;
  overflow: hidden;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  background:
    linear-gradient(145deg, rgba(var(--color-primary-rgb), .055), transparent 46%),
    var(--bg-card);
  box-shadow: var(--shadow-card);
}
.entry-sound-panel { display: flex; padding: 20px; flex-direction: column; gap: 14px; }
.entry-sound-panel::before {
  content: '';
  position: absolute;
  inset: 0 auto 0 0;
  width: 3px;
  background: var(--gradient-brand);
  opacity: .68;
}
.panel-heading { display: flex; align-items: flex-start; gap: 13px; }
.sound-mark {
  display: flex;
  width: 39px;
  height: 39px;
  flex: 0 0 39px;
  align-items: flex-end;
  justify-content: center;
  gap: 3px;
  padding-bottom: 10px;
  border: 1px solid rgba(var(--color-primary-rgb), .28);
  border-radius: 11px;
  background: rgba(var(--color-primary-rgb), .08);
}
.sound-mark span { width: 3px; height: 11px; border-radius: 3px; background: var(--color-primary); }
.sound-mark span:nth-child(2) { height: 20px; }
.heading-copy { min-width: 0; flex: 1; }
.eyebrow { margin: 2px 0 7px; color: var(--color-primary); font: 600 .61em/1 ui-monospace, Consolas, monospace; letter-spacing: .11em; }
h2 { margin: 0 0 5px; color: var(--text-primary); font-size: 1em; letter-spacing: -.015em; }
p { margin: 0; color: var(--text-secondary); font-size: .72em; line-height: 1.6; }
.config-status {
  flex: none;
  padding: 5px 8px;
  border: 1px solid var(--border-default);
  border-radius: 999px;
  color: var(--text-muted);
  background: var(--surface-2);
  font-size: .61em;
}
.config-status.configured { border-color: rgba(var(--color-success-rgb), .28); color: var(--color-success); }
.current-sound {
  display: flex;
  align-items: center;
  gap: 11px;
  padding: 11px 12px;
  border: 1px solid rgba(var(--color-success-rgb), .18);
  border-radius: var(--radius-md);
  background: rgba(var(--color-success-rgb), .045);
}
.current-icon {
  display: grid;
  width: 31px;
  height: 31px;
  flex: 0 0 31px;
  place-items: center;
  border-radius: 50%;
  color: var(--color-success);
  background: rgba(var(--color-success-rgb), .12);
  font-weight: 700;
}
.current-copy { display: flex; min-width: 0; flex: 1; flex-direction: column; gap: 2px; }
.current-copy strong { overflow: hidden; color: var(--text-primary); font-size: .73em; text-overflow: ellipsis; white-space: nowrap; }
.current-copy span { color: var(--text-muted); font-size: .61em; }
.delete-button,
.clear-button {
  flex: none;
  border: 0;
  color: var(--text-muted);
  background: transparent;
  font: inherit;
  font-size: .66em;
  cursor: pointer;
}
.delete-button:hover:not(:disabled) { color: var(--color-danger); }
.delete-button:disabled { opacity: .5; cursor: wait; }
.drop-zone {
  display: flex;
  width: 100%;
  min-height: 76px;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 13px 16px;
  border: 1px dashed var(--border-emphasis);
  border-radius: var(--radius-md);
  color: var(--text-secondary);
  background: rgba(var(--color-primary-rgb), .025);
  font: inherit;
  text-align: left;
  cursor: pointer;
  transition: border-color .18s, background .18s, transform .18s;
}
.drop-zone:hover:not(:disabled),
.drop-zone.dragging { border-color: rgba(var(--color-primary-rgb), .56); background: rgba(var(--color-primary-rgb), .075); transform: translateY(-1px); }
.drop-zone:focus-visible,
.upload-button:focus-visible,
.delete-button:focus-visible,
.clear-button:focus-visible { outline: 2px solid var(--color-primary); outline-offset: 2px; }
.drop-zone:disabled { opacity: .52; cursor: wait; }
.upload-icon { display: grid; width: 30px; height: 30px; flex: none; place-items: center; border-radius: 9px; color: var(--color-primary); background: rgba(var(--color-primary-rgb), .1); font-weight: 750; }
.drop-copy { display: flex; min-width: 0; flex-direction: column; gap: 3px; }
.drop-copy strong { color: var(--text-primary); font-size: .73em; }
.drop-copy small { color: var(--text-muted); font-size: .58em; letter-spacing: .035em; }
.visually-hidden {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  clip-path: inset(50%);
  white-space: nowrap;
}
.preview-card { padding: 11px 12px; border: 1px solid var(--border-subtle); border-radius: var(--radius-md); background: var(--surface-2); }
.preview-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; margin-bottom: 9px; }
.preview-heading > div { display: grid; min-width: 0; gap: 2px; }
.preview-label { color: var(--color-primary); font: 600 .58em/1.4 ui-monospace, Consolas, monospace; letter-spacing: .08em; }
.preview-heading strong { overflow: hidden; color: var(--text-primary); font-size: .7em; text-overflow: ellipsis; white-space: nowrap; }
.preview-heading small { color: var(--text-muted); font-size: .6em; }
.clear-button:hover { color: var(--text-primary); }
.clear-button:disabled { opacity: .5; cursor: wait; }
audio { display: block; width: 100%; height: 34px; color-scheme: dark; }
.upload-progress { height: 4px; overflow: hidden; border-radius: 999px; background: rgba(var(--color-primary-rgb), .1); }
.upload-progress span { display: block; height: 100%; border-radius: inherit; background: var(--gradient-brand); transition: width .15s ease; }
.entry-error { padding: 9px 11px; border: 1px solid rgba(var(--color-danger-rgb), .28); border-radius: var(--radius-sm); background: rgba(var(--color-danger-rgb), .065); }
.entry-error span { margin-right: 7px; color: var(--color-danger); font-weight: 700; }
.validation-status { color: var(--text-muted); text-align: center; }
.panel-actions { display: flex; align-items: center; gap: 12px; }
.upload-button {
  min-height: 38px;
  padding: 8px 15px;
  border: 1px solid rgba(var(--color-primary-rgb), .42);
  border-radius: var(--radius-sm);
  color: #fff;
  background: var(--gradient-brand);
  font: inherit;
  font-size: .72em;
  font-weight: 650;
  cursor: pointer;
}
.upload-button:disabled { opacity: .5; cursor: wait; }
.panel-actions span { color: var(--text-muted); font-size: .61em; }
.entry-sound-unavailable { display: flex; align-items: center; gap: 12px; padding: 14px 16px; }
.lock-mark { display: grid; width: 31px; height: 31px; flex: none; place-items: center; border: 1px solid var(--border-default); border-radius: 50%; color: var(--text-muted); }
.entry-sound-unavailable strong { color: var(--text-secondary); font-size: .72em; }
.entry-sound-unavailable p { margin-top: 2px; color: var(--text-muted); font-size: .65em; }
@media (max-width: 680px) {
  .entry-sound-panel { padding: 17px 15px; }
  .panel-heading { flex-wrap: wrap; }
  .config-status { margin-left: 52px; }
  .current-sound { align-items: flex-start; }
  .delete-button { min-height: 32px; }
  .drop-zone { min-height: 82px; padding: 14px 12px; }
  .panel-actions { align-items: stretch; flex-direction: column; }
  .upload-button { min-height: 44px; width: 100%; }
  .panel-actions span { text-align: center; }
}
</style>
