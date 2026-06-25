<script setup lang="ts">
import { computed } from 'vue'
import { useMonitorStore } from '@/stores/monitor'
import CountUp from '@/components/monitor/CountUp.vue'
import { vSpotlight } from '@/directives/spotlight'

const monitor = useMonitorStore()

const online = computed(() => monitor.stats?.online_users ?? 0)
const gaming = computed(() => monitor.stats?.gaming_users ?? 0)
const total = computed(() => monitor.stats?.total_users ?? 0)
const uptime = computed(() => formatTime(monitor.stats?.running_time ?? 0))

/** 游戏中占在线人数比例，真实派生值 */
const gamingRatio = computed(() => {
  if (!online.value) return 0
  return Math.min(100, Math.round((gaming.value / online.value) * 100))
})

/** 与上一个采样点相比的在线人数变化（真实，非编造） */
const onlineDelta = computed(() => {
  const h = monitor.onlineHistory
  if (h.length < 2) return 0
  return h[h.length - 1] - h[h.length - 2]
})

/* ── sparkline：从真实采样历史生成 SVG 路径 ── */
const SPARK_W = 140
const SPARK_H = 30

const spark = computed(() => {
  const data = monitor.onlineHistory
  if (!data || data.length < 2) {
    return { line: '', area: '' }
  }
  const max = Math.max(...data)
  const min = Math.min(...data)
  const range = max - min || 1
  const step = SPARK_W / (data.length - 1)
  const pts = data.map((v, i) => {
    const x = i * step
    const y = SPARK_H - 2 - ((v - min) / range) * (SPARK_H - 4)
    return { x: +x.toFixed(1), y: +y.toFixed(1) }
  })
  const line = pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x},${p.y}`).join(' ')
  const area = `${line} L${SPARK_W},${SPARK_H} L0,${SPARK_H} Z`
  return { line, area }
})

function formatTime(seconds: number): string {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  if (h > 24) return `${Math.floor(h / 24)}d ${h % 24}h`
  return `${h}h ${m}m`
}
</script>

<template>
  <div class="stats-row">
    <!-- 主指标：在线人数（真实 sparkline） -->
    <div v-spotlight class="stat-card stat-hero animate-in animate-delay-1">
      <div class="stat-head">
        <span class="stat-label label-mono">在线人数</span>
        <span class="stat-live">
          <span class="live-dot"></span>LIVE
        </span>
      </div>
      <div class="stat-value mono"><CountUp :value="online" /></div>
      <div class="stat-spark">
        <svg :viewBox="`0 0 ${SPARK_W} ${SPARK_H}`" preserveAspectRatio="none">
          <defs>
            <linearGradient id="spark-fill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stop-color="rgba(45,212,191,0.28)" />
              <stop offset="100%" stop-color="rgba(45,212,191,0)" />
            </linearGradient>
          </defs>
          <path v-if="spark.area" :d="spark.area" fill="url(#spark-fill)" />
          <path
            v-if="spark.line"
            :d="spark.line"
            fill="none"
            stroke="var(--color-primary)"
            stroke-width="1.5"
            stroke-linecap="round"
            stroke-linejoin="round"
            vector-effect="non-scaling-stroke"
          />
        </svg>
      </div>
      <div class="stat-foot">
        <span class="foot-cadence mono">↻ 5s</span>
        <span
          class="foot-delta mono"
          :class="{ up: onlineDelta > 0, down: onlineDelta < 0 }"
        >
          <template v-if="onlineDelta > 0">▲ {{ onlineDelta }}</template>
          <template v-else-if="onlineDelta < 0">▼ {{ Math.abs(onlineDelta) }}</template>
          <template v-else>— 0</template>
        </span>
      </div>
    </div>

    <!-- 游戏中（翡翠绿 · 活跃态） -->
    <div v-spotlight class="stat-card animate-in animate-delay-2">
      <div class="stat-head">
        <span class="stat-label label-mono">游戏中</span>
        <span class="stat-dot stat-dot--emerald"></span>
      </div>
      <div class="stat-value mono stat-value--emerald"><CountUp :value="gaming" /></div>
      <div class="bar-track">
        <div class="bar-fill bar-fill--emerald" :style="{ width: gamingRatio + '%' }" />
      </div>
      <div class="stat-foot">
        <span class="foot-cadence mono">占在线 {{ gamingRatio }}%</span>
      </div>
    </div>

    <!-- 累计用户（中性） -->
    <div v-spotlight class="stat-card animate-in animate-delay-3">
      <div class="stat-head">
        <span class="stat-label label-mono">累计用户</span>
      </div>
      <div class="stat-value mono"><CountUp :value="total" /></div>
      <div class="stat-rule"></div>
      <div class="stat-foot">
        <span class="foot-cadence mono">注册总数</span>
      </div>
    </div>

    <!-- 运行时长（中性） -->
    <div v-spotlight class="stat-card animate-in animate-delay-4">
      <div class="stat-head">
        <span class="stat-label label-mono">运行时长</span>
      </div>
      <div class="stat-value mono">{{ uptime }}</div>
      <div class="stat-rule"></div>
      <div class="stat-foot">
        <span class="foot-cadence mono">自启动</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.stats-row {
  display: grid;
  grid-template-columns: 1.35fr 1fr 1fr 1fr;
  gap: 12px;
}

@media (max-width: 1100px) {
  .stats-row {
    grid-template-columns: repeat(2, 1fr);
  }
}

.stat-card {
  position: relative;
  background: var(--gradient-surface);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  padding: 16px 16px 14px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  overflow: hidden;
  transition: border-color 0.2s var(--ease-out-expo), background 0.2s;
}

.stat-card:hover {
  border-color: var(--border-emphasis);
}

/* 内容层抬到聚光之上 */
.stat-card > * {
  position: relative;
  z-index: 1;
}

/* 光标聚光：跟随鼠标的极淡 teal 高光（仅 hover 显现） */
.stat-card::before {
  content: '';
  position: absolute;
  inset: 0;
  background: radial-gradient(
    170px circle at var(--mx, 50%) var(--my, 50%),
    rgba(45, 212, 191, 0.1),
    transparent 62%
  );
  opacity: 0;
  transition: opacity 0.3s;
  pointer-events: none;
  z-index: 0;
}
.stat-card:hover::before {
  opacity: 1;
}

/* 主卡：顶部 1px teal 信号线（唯一强调位置） */
.stat-hero {
  border-top: 1px solid var(--color-primary);
  background:
    linear-gradient(180deg, rgba(45, 212, 191, 0.05), rgba(45, 212, 191, 0) 60%),
    var(--gradient-surface);
}

.stat-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 16px;
}

.stat-label {
  font-size: 0.68em;
  color: var(--text-muted);
}

.stat-live {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.62em;
  font-weight: 600;
  letter-spacing: 0.12em;
  color: var(--color-primary);
}

.live-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--color-primary);
  animation: pulse-glow 1.8s ease-in-out infinite;
}

.stat-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
}
.stat-dot--emerald {
  background: var(--color-secondary);
}

.stat-value {
  font-size: 1.9em;
  font-weight: 700;
  color: var(--text-primary);
  line-height: 1;
  letter-spacing: -0.01em;
}

.stat-value--emerald {
  color: var(--color-secondary);
}

.stat-spark {
  position: relative;
  height: 30px;
  width: 100%;
  margin: 2px 0;
}
.stat-spark svg {
  width: 100%;
  height: 100%;
  display: block;
}

.bar-track {
  height: 3px;
  width: 100%;
  background: rgba(255, 255, 255, 0.05);
  border-radius: 2px;
  overflow: hidden;
  margin: 2px 0;
}
.bar-fill {
  height: 100%;
  border-radius: 2px;
  transition: width 0.6s var(--ease-out-expo);
}
.bar-fill--emerald {
  background: var(--color-secondary);
}

/* 中性卡的基线发丝线 */
.stat-rule {
  height: 1px;
  width: 100%;
  background: var(--border-subtle);
  margin: 2px 0;
}

.stat-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: auto;
  min-height: 14px;
}

.foot-cadence {
  font-size: 0.66em;
  color: var(--text-muted);
  letter-spacing: 0.04em;
}

.foot-delta {
  font-size: 0.66em;
  font-weight: 600;
  color: var(--text-muted);
}
.foot-delta.up {
  color: var(--color-secondary);
}
.foot-delta.down {
  color: var(--color-danger);
}
</style>
