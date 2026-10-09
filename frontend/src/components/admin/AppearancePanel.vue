<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useThemeStore } from '@/stores/theme'
import {
  deleteBackground,
  putAppearance,
  uploadBackground,
  type BackgroundKind,
} from '@/api/theme'

const MAX_BYTES = 10 * 1024 * 1024

const theme = useThemeStore()
const busy = ref<BackgroundKind | null>(null)
const dragging = ref<BackgroundKind | null>(null)
const dim = ref(theme.config.dim)
const blur = ref(theme.config.blur)
const savingLook = ref(false)

watch(
  () => [theme.config.dim, theme.config.blur] as const,
  ([d, b]) => {
    dim.value = d
    blur.value = b
  },
)

interface Slot {
  kind: BackgroundKind
  title: string
  hint: string
  spec: string
}

const slots: Slot[] = [
  { kind: 'desktop', title: '电脑端', hint: '横向大图，建议 16:9', spec: '推荐 2560×1440 · 最大 2560 宽' },
  { kind: 'mobile', title: '手机端', hint: '竖向大图，建议 9:19.5', spec: '推荐 1170×2532 · 最大 2532 高' },
]

const info = (kind: BackgroundKind) => theme.config[kind]
const fileInputs = ref<Partial<Record<BackgroundKind, HTMLInputElement>>>({})

function errorText(e: unknown, fallback: string): string {
  const detail = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  return typeof detail === 'string' ? detail : fallback
}

async function handleFile(kind: BackgroundKind, file: File | undefined) {
  if (!file) return
  if (!file.type.startsWith('image/')) {
    ElMessage.error('请选择图片文件')
    return
  }
  if (file.size > MAX_BYTES) {
    ElMessage.error('图片不能超过 10 MiB')
    return
  }
  busy.value = kind
  try {
    theme.setConfig(await uploadBackground(kind, file))
    ElMessage.success('背景已更新，主题色已根据图片自动提取')
  } catch (e) {
    ElMessage.error(errorText(e, '上传失败'))
  } finally {
    busy.value = null
  }
}

function onPick(kind: BackgroundKind, event: Event) {
  const input = event.target as HTMLInputElement
  handleFile(kind, input.files?.[0])
  input.value = ''
}

function onDrop(kind: BackgroundKind, event: DragEvent) {
  dragging.value = null
  handleFile(kind, event.dataTransfer?.files?.[0])
}

async function remove(kind: BackgroundKind) {
  busy.value = kind
  try {
    theme.setConfig(await deleteBackground(kind))
    ElMessage.success('已移除背景')
  } catch (e) {
    ElMessage.error(errorText(e, '移除失败'))
  } finally {
    busy.value = null
  }
}

const lookDirty = computed(() => dim.value !== theme.config.dim || blur.value !== theme.config.blur)

async function saveLook() {
  savingLook.value = true
  try {
    theme.setConfig(await putAppearance(dim.value, blur.value))
    ElMessage.success('显示效果已保存')
  } catch (e) {
    ElMessage.error(errorText(e, '保存失败'))
  } finally {
    savingLook.value = false
  }
}

// 滑动时即时预览（未保存前只改本地 store，不写缓存）
watch([dim, blur], ([d, b]) => {
  theme.config = { ...theme.config, dim: d, blur: b }
})
</script>

<template>
  <section class="appearance">
    <header class="ap-head">
      <div>
        <h3 class="ap-title">外观 · 自定义背景</h3>
        <p class="ap-desc">
          分别为电脑和手机上传背景图。主题色会根据图片内容<b>自动提取</b>，并同步到按钮、高亮、边框与文字色调。
        </p>
      </div>
    </header>

    <div class="slots">
      <div v-for="slot in slots" :key="slot.kind" class="slot" :class="`slot--${slot.kind}`">
        <div class="slot-top">
          <span class="slot-title">{{ slot.title }}</span>
          <span v-if="info(slot.kind)" class="swatch" :title="`提取的主题色 ${info(slot.kind)!.color}`">
            <i :style="{ background: info(slot.kind)!.color }"></i>
            <code>{{ info(slot.kind)!.color }}</code>
          </span>
        </div>

        <div
          class="drop"
          :class="{ 'drop--over': dragging === slot.kind, 'drop--busy': busy === slot.kind }"
          role="button"
          tabindex="0"
          :aria-label="`上传${slot.title}背景`"
          @click="fileInputs[slot.kind]?.click()"
          @keydown.enter.prevent="fileInputs[slot.kind]?.click()"
          @dragover.prevent="dragging = slot.kind"
          @dragleave="dragging = null"
          @drop.prevent="onDrop(slot.kind, $event)"
        >
          <img v-if="info(slot.kind)" :src="info(slot.kind)!.url" class="drop-img" alt="" />
          <div class="drop-empty" :class="{ 'drop-empty--over': !!info(slot.kind) }">
            <svg viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
              <path d="M12 16V4m0 0-4 4m4-4 4 4" />
              <path d="M4 15v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3" />
            </svg>
            <span>{{ busy === slot.kind ? '处理中…' : info(slot.kind) ? '点击或拖入以替换' : '点击或拖入图片' }}</span>
          </div>
          <span v-if="busy === slot.kind" class="drop-bar"></span>
        </div>
        <input
          :ref="(el) => { if (el) fileInputs[slot.kind] = el as HTMLInputElement }"
          type="file"
          accept="image/jpeg,image/png,image/webp,image/gif,image/bmp"
          hidden
          @change="onPick(slot.kind, $event)"
        />

        <div class="slot-foot">
          <span class="slot-hint">{{ slot.hint }}<br />{{ slot.spec }}</span>
          <button v-if="info(slot.kind)" class="ghost-btn" :disabled="busy === slot.kind" @click="remove(slot.kind)">
            移除
          </button>
        </div>
      </div>
    </div>

    <div class="look">
      <label class="look-row">
        <span class="look-label">背景暗度<em>{{ dim }}%</em></span>
        <input v-model.number="dim" type="range" min="0" max="85" step="1" />
      </label>
      <label class="look-row">
        <span class="look-label">背景模糊<em>{{ blur }}px</em></span>
        <input v-model.number="blur" type="range" min="0" max="24" step="1" />
      </label>
      <button class="save-btn" :disabled="!lookDirty || savingLook" @click="saveLook">
        {{ savingLook ? '保存中…' : '保存效果' }}
      </button>
    </div>
    <p class="ap-note">未设置某一端时，该端会使用另一端的图片；两端都未设置则恢复默认深海蓝主题。</p>
  </section>
</template>

<style scoped>
.appearance {
  position: relative;
  padding: 20px;
  margin-bottom: 22px;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  background:
    radial-gradient(120% 80% at 0% 0%, rgba(var(--color-primary-rgb), 0.12), transparent 60%),
    var(--gradient-surface);
  overflow: hidden;
}

.ap-title {
  font-size: 1.05em;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 4px;
}
.ap-desc {
  font-size: 0.82em;
  color: var(--text-secondary);
  line-height: 1.6;
  margin: 0 0 16px;
}
.ap-desc b {
  color: var(--color-primary);
  font-weight: 600;
}

.slots {
  display: grid;
  grid-template-columns: minmax(0, 1.7fr) minmax(0, 1fr);
  gap: 18px;
  align-items: start;
}

.slot-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.slot-title {
  font-weight: 600;
  font-size: 0.9em;
  color: var(--text-primary);
}
.swatch {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 0.72em;
  color: var(--text-secondary);
  animation: swatch-pop 0.5s var(--ease-spring);
}
.swatch i {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  box-shadow: 0 0 0 2px rgba(255, 255, 255, 0.18), 0 0 14px rgba(var(--color-primary-rgb), 0.5);
}
@keyframes swatch-pop {
  from { transform: scale(0.6); opacity: 0; }
}

.drop {
  position: relative;
  border-radius: var(--radius-md);
  border: 1.5px dashed var(--border-emphasis);
  background: rgba(var(--surface-0-rgb), 0.5);
  overflow: hidden;
  cursor: pointer;
  display: grid;
  place-items: center;
  transition: border-color 0.25s, transform 0.4s var(--ease-out-expo), box-shadow 0.4s;
}
.slot--desktop .drop { aspect-ratio: 16 / 9; }
.slot--mobile .drop { aspect-ratio: 9 / 16; max-width: 190px; margin-inline: auto; border-radius: 22px; }
.drop:hover,
.drop:focus-visible,
.drop--over {
  border-color: var(--color-primary);
  box-shadow: 0 12px 30px -16px rgba(var(--color-primary-rgb), 0.6);
  transform: translateY(-2px);
  outline: none;
}
.drop-img {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.drop-empty {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  font-size: 0.8em;
  color: var(--text-secondary);
  transition: opacity 0.25s, transform 0.3s var(--ease-out-expo);
}
.drop-empty svg { color: var(--color-primary); animation: float 3.4s ease-in-out infinite; }
/* 已有图片时，提示文字只在悬停时浮现 */
.drop-empty--over {
  opacity: 0;
  padding: 10px 14px;
  border-radius: 999px;
  background: rgba(var(--surface-0-rgb), 0.72);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
}
.drop:hover .drop-empty--over,
.drop:focus-visible .drop-empty--over,
.drop--over .drop-empty--over { opacity: 1; }
.drop--busy { pointer-events: none; }
.drop-bar {
  position: absolute;
  left: 0;
  bottom: 0;
  height: 3px;
  width: 40%;
  background: var(--gradient-brand);
  animation: bar-slide 1.1s var(--ease-soft) infinite;
}
@keyframes bar-slide {
  from { transform: translateX(-100%); }
  to { transform: translateX(260%); }
}

.slot-foot {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  gap: 10px;
  margin-top: 8px;
}
.slot-hint {
  font-size: 0.72em;
  color: var(--text-muted);
  line-height: 1.55;
}
.ghost-btn,
.save-btn {
  font: inherit;
  font-size: 0.8em;
  cursor: pointer;
  border-radius: 999px;
  padding: 6px 14px;
  transition: transform 0.28s var(--ease-spring), background 0.2s, border-color 0.2s, opacity 0.2s;
}
.ghost-btn {
  color: var(--color-danger);
  background: rgba(var(--color-danger-rgb), 0.08);
  border: 1px solid rgba(var(--color-danger-rgb), 0.3);
}
.ghost-btn:hover:not(:disabled) { background: rgba(var(--color-danger-rgb), 0.16); }
.save-btn {
  color: var(--text-inverse);
  background: var(--gradient-brand);
  border: none;
  font-weight: 600;
  padding: 8px 20px;
}
.save-btn:hover:not(:disabled),
.ghost-btn:hover:not(:disabled) { transform: translateY(-1px); }
.save-btn:active:not(:disabled),
.ghost-btn:active:not(:disabled) { transform: scale(0.95); }
.save-btn:disabled,
.ghost-btn:disabled { opacity: 0.4; cursor: not-allowed; }

.look {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: 18px 28px;
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid var(--border-subtle);
}
.look-row { flex: 1 1 200px; display: flex; flex-direction: column; gap: 8px; }
.look-label {
  display: flex;
  justify-content: space-between;
  font-size: 0.8em;
  color: var(--text-secondary);
}
.look-label em {
  font-style: normal;
  font-family: var(--font-mono);
  color: var(--color-primary);
}
.look input[type='range'] {
  width: 100%;
  accent-color: var(--color-primary);
  height: 22px;
}
.ap-note {
  margin: 12px 0 0;
  font-size: 0.72em;
  color: var(--text-muted);
}

@media (max-width: 768px) {
  .appearance { padding: 16px 14px; }
  .slots { grid-template-columns: 1fr; }
  .slot--mobile .drop { max-width: 160px; }
  .save-btn { min-height: 42px; }
  .ghost-btn { min-height: 36px; }
}
</style>
