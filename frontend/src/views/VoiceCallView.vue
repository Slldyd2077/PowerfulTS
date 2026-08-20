<script setup lang="ts">
import { ref } from 'vue'
import ChannelVoice from '@/components/voice/ChannelVoice.vue'
import ChannelBrowser from '@/components/voice/ChannelBrowser.vue'
import EntrySoundPanel from '@/components/voice/EntrySoundPanel.vue'

const browser = ref<InstanceType<typeof ChannelBrowser> | null>(null)

// 加入/挂断会立刻改变「你在哪个频道」，不等 5 秒轮询。
function onSessionChange() {
  void browser.value?.refresh()
}
</script>

<template>
  <div class="voice-view">
    <div class="page-header">
      <div class="page-title-group">
        <h1 class="page-title">网页通话</h1>
        <span class="page-sub label-mono">VOICE · WEB CALL</span>
      </div>
    </div>

    <div class="voice-body">
      <div class="voice-column">
        <ChannelVoice @session-change="onSessionChange" />
        <EntrySoundPanel />

        <section class="voice-guide">
          <h2>怎么用</h2>
          <ol>
            <li><b>加入通话</b> —— 你会以自己的昵称出现在频道里，一个按钮同时开始收听和麦克风；进去之后可以随时点「静音」只听不说。</li>
            <li><b>选频道</b> —— 在右边点一个频道就能过去，你听到的也随之切换；带 🔒 的频道会让你输密码。</li>
            <li><b>挂断</b> —— 立刻离开服务器，不会占着频道位置。</li>
          </ol>
          <p class="tip">
            <span>建议戴耳机</span>
            外放时麦克风会把频道声音再送回频道形成回声；同一台设备也不要让 TS 客户端和网页同时待在这个频道。
          </p>
          <p class="tip">
            <span>通话中会带标记</span>
            频道里的人看到你的昵称前有 <code>&lt;WEB通讯&gt;</code>，表示你是从网页接入的。挂断后自动消失。
          </p>
        </section>
      </div>

      <div class="voice-column">
        <ChannelBrowser ref="browser" />
      </div>
    </div>
  </div>
</template>

<style scoped>
.voice-view {
  display: flex;
  flex-direction: column;
  gap: 20px;
  height: 100%;
  width: 100%;
  min-width: 0;
  max-width: 100%;
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

/* 两栏只在真正放得下的时候才拆：窄屏塞两栏会让频道树和设备下拉都挤成一团。 */
.voice-body {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 20px;
  align-items: start;
  width: 100%;
  min-width: 0;
}
.voice-column {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 20px;
}

@media (min-width: 1080px) {
  .voice-body { grid-template-columns: minmax(0, 1.05fr) minmax(0, 1fr); }
}
@media (min-width: 1600px) {
  .voice-body { gap: 24px; }
  .voice-column { gap: 24px; }
}

.voice-guide {
  padding: 18px 20px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  background: var(--bg-card);
  box-shadow: var(--shadow-card);
}
.voice-guide h2 { margin: 0 0 6px; color: var(--text-primary); font-size: 0.98em; letter-spacing: -0.015em; }
.voice-guide ol { margin: 0; padding-left: 18px; color: var(--text-secondary); font-size: 0.74em; line-height: 1.85; }
.voice-guide ol b { color: var(--text-primary); }
.tip {
  margin: 14px 0 0;
  padding-top: 12px;
  border-top: 1px solid var(--border-subtle);
  color: var(--text-muted);
  font-size: 0.7em;
  line-height: 1.6;
}
.tip span { margin-right: 8px; color: var(--color-accent); font-weight: 650; }
.tip + .tip { margin-top: 8px; padding-top: 0; border-top: 0; }
.tip code { padding: 1px 5px; border-radius: 4px; background: var(--bg-elevated); color: var(--text-secondary); font-size: 0.94em; }

@media (max-width: 768px) {
  .voice-view { gap: 14px; height: auto; overflow: visible; }
  .voice-body, .voice-column { gap: 14px; }
  .voice-guide { padding: 16px; }
  .page-title { font-size: clamp(1.1em, 4vw, 1.4em); }
  .page-header { padding-bottom: 12px; }
}
</style>
