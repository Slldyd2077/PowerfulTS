# 网页端 TS 频道语音双向通话 — 施工文档

> **给实施 Agent**：本文档已做过完整可行性验证（2026-07-28）。所有技术选型、接口、坑点都有实证依据，**不要重新调研方向**，直接按本文实施。如遇本文未覆盖的细节，再针对性查证。

---

## 1. 目标

用户**不安装 TeamSpeak 客户端**，只用 PowerfulTS 网页端，就能和 TS 频道里的人双向语音通话：
- **上行**（网页麦克风 → 频道）：**已实现**（`LiveAudioShare.vue` + `live_audio.py` + TSMusicBot 的 `/api/player/:botId/live`）。
- **下行**（频道 → 网页扬声器）：**本文档要实现的**。

---

## 2. 已验证的技术基础（⚠️ 必读，避免走弯路）

### 2.1 TSMusicBot 的真实身份
**不是** Splamy 的 TS3AudioBot，**不是**基于 TSLib/C#。
是 [ZHANGTIANYAO1/teamspeak-music-bot](https://github.com/ZHANGTIANYAO1/teamspeak-music-bot) —— 独立的 **Node.js / TypeScript** 项目（PowerfulTS README 第 263、429 行有链接）。纯播放器（音源→FFmpeg→Opus→发频道），目前无下行能力，需要我们加。

### 2.2 底层 TS 协议库（下行的真正基础）
[HoneyBBQ/teamspeak-js](https://github.com/HoneyBBQ/teamspeak-js)（npm 包 `@honeybbq/teamspeak-client`）。
TypeScript clean-room 实现 TS3/5/6 完整客户端协议（ECDH+AES-EAX）。借鉴了 TSLib 的协议知识，但独立实现，**与 TSLib 无代码关系**。

### 2.3 下行接口（已实证 `client.ts:408-433`）
```typescript
client.on("voice", ({ clientId, codec, data }) => {
  // clientId: number  —— 说话人的 TS client id（已自动过滤 bot 自己：if(clientId===this.clid) return）
  // codec: number      —— 4 = Opus Voice, 5 = Opus Music
  // data: Uint8Array   —— 去掉 5 字节包头后的 Opus 编码帧（~20ms）
});
```
**包格式**：`[VId:u16][CId:u16][Codec:u8][Data:var]`，库解析后给出 `data`（纯 Opus 帧）。
**库不解码、不混音**，给的是 per-client 的原始 Opus 帧。
发送用 `client.sendVoice(data, codec)`（TSMusicBot 播放音乐已用此上行）。

### 2.4 结论
**全链路可行，全 TypeScript/JS 同栈**（TSMusicBot + teamspeak-js + PowerfulTS 后端 + 浏览器 WebCodecs）。没有"逆向协议/写 C#/等官方 web 客户端"的死结。

---

## 3. 整体架构

```
TS 服务器
   │ (其他人说话的语音包，UDP/Opus)
   ▼
┌──────────────────────────────────────┐
│ TSMusicBot (teamspeak-music-bot)     │  ← 在此新增 onVoice 订阅
│  client.on("voice", {clientId,       │
│     codec, data}) 收 per-client Opus │
│  → 混音(可选) → WebSocket 推出        │
└──────────────┬───────────────────────┘
               │ WebSocket: per-client 或混合后的 Opus 帧
               ▼
┌──────────────────────────────────────┐
│ PowerfulTS 后端 (FastAPI)            │  ← 镜像现有 LiveAudioRelay
│  services/voice_downlink.py          │
│  收 TSMusicBot 流 → asyncio.Queue    │
│  → WebSocket 推浏览器                │
└──────────────┬───────────────────────┘
               │ WebSocket: Opus 帧
               ▼
┌──────────────────────────────────────┐
│ 浏览器 (Vue3)                        │  ← 新增下行播放器
│  WebCodecs AudioDecoder 解 Opus→PCM  │
│  AudioWorklet 播放(混音如需)          │
└──────────────────────────────────────┘
```

**关键对称性**：上行链路（`LiveAudioShare.vue` + `live_audio.py` + `/api/music/live/*`）已经跑通，下行几乎是其镜像——复用同样的 WebSocket + Queue + StreamingResponse/WebSocket 模式，方向反过来。

---

## 4. 实施分块

### 4.1 TSMusicBot 侧（teamspeak-music-bot 项目，独立仓库）

**目标**：在 bot 连接上加 `on("voice")` 订阅，把频道语音导出给 PowerfulTS 后端。

**改动点**（在 teamspeak-music-bot 的 bot 连接逻辑里，找到创建 `Client` 的地方）：
```typescript
// 伪代码：bot 连接后
client.on("voice", ({ clientId, codec, data }) => {
  // 方案 A（推荐 MVP）：直接转发 per-client Opus 帧（不混音，后端/浏览器处理）
  voiceDownlinkWS.send(JSON.stringify({ clientId, codec }) + "\n" + Buffer.from(data));
  // 或用二进制帧：[clientId:u16][codec:u8][len:u16][opus data]
});

// 方案 B（生产，后端省事）：TSMusicBot 内混音
// 需要 opus 解码(@discordjs/opus 已在依赖里) → 多 client PCM 累加 → 重编码 Opus 或直推 PCM
```

**新增端点**：暴露一个 WebSocket（如 `/api/voice/downlink/:botId`）让 PowerfulTS 后端连接订阅；或反过来 TSMusicBot 主动推到 PowerfulTS 的一个 ingest 端点（参照现有上行 `/api/player/:botId/live` 的反向）。

**参考**：teamspeak-music-bot 现有的 `sendVoice`/播放管道（FFmpeg→Opus→sendVoice）就是上行的实现，下行的连接/Client 创建代码可复用。

### 4.2 PowerfulTS 后端（本仓库）

**目标**：接收 TSMusicBot 的 Opus 流，中继给浏览器。**几乎照抄 `backend/app/services/live_audio.py` 的 `LiveAudioRelay`，方向反过来。**

**新增文件**：
- `backend/app/services/voice_downlink.py` —— `VoiceDownlinkRelay`（镜像 `LiveAudioRelay`）：连 TSMusicBot 的下行 WS → `asyncio.Queue` → 给浏览器 WebSocket 拉取。
- `backend/app/routers/voice.py`（或并入 `music.py`）—— 端点：
  - `WS /api/music/voice/stream/{bot_id}` —— 浏览器订阅下行语音流。

**复用**：`deps.py` 的 `OwnedBotId`（权限，只有可访问该 bot 的用户能听）、`TsmusicDep`。

**关键**：TSMusicBot 连接配置（tsmusic_url/凭据）已在 `.env`，复用。

### 4.3 前端（本仓库）

**目标**：WebSocket 收 Opus 帧 → WebCodecs 解码 → 播放。

**新增**：`frontend/src/components/music/ChannelListen.vue`（或并入 `LiveAudioShare.vue` 做"双向"）。

**核心代码**（WebCodecs 解码 + AudioWorklet 播放）：
```typescript
const decoder = new AudioDecoder({
  output: async (frame: AudioData) => {
    // 把 PCM 帧喂给 AudioWorklet 播放
    workletPort.postMessage(frame, [/* transfer */]);
    frame.close();
  },
  error: (e) => console.error('decode error', e),
});
decoder.configure({
  codec: 'opus',            // ⚠️ 见 6.2 的 codec 映射坑
  sampleRate: 48000,
  numberOfChannels: 1,
});

ws.onmessage = (e) => {
  // e.data = per-client 或混合的 Opus 帧
  const chunk = new EncodedAudioChunk({
    type: 'key',            // Opus 每帧都是 keyframe
    timestamp: currentTs,   // 需递增（见 6.3）
    data: new Uint8Array(e.data),
  });
  decoder.decode(chunk);
};
```

**AudioWorklet**：一个 `voice-player-worklet.js`（收到 PCM → 灌扬声器，处理 underrun/缓冲）。多人混音若在浏览器做，Worklet 里多路累加。

---

## 5. 混音策略（多人同时说话）

TS 服务器**按说话人分别发包**（onVoice 是 per-client 的，不混合）。两人同时说话 → 两个 clientId 的 Opus 帧。

| 方案 | 在哪混 | 优点 | 缺点 | 推荐场景 |
|---|---|---|---|---|
| **A. 后端混（TSMusicBot 或 PowerfulTS）** | 解码各 client Opus→PCM，累加，推单路 | 浏览器简单（单路播放）、省带宽 | 后端要解码（CPU） | **生产推荐** |
| **B. 浏览器混** | 转发 per-client 帧，浏览器多路解码+AudioWorklet 累加 | 后端零处理 | 浏览器 CPU、带宽×人数 | MVP / 人少 |
| **C. 不混（单人）** | 只转发当前说话人 | 最简单 | 抢话会断续 | **Spike 验证用** |

**Spike 用 C，MVP 用 B，生产用 A**（A 可在 TSMusicBot 内用已有的 `@discordjs/opus` 解码混音）。

---

## 6. 关键工程要点（已查证的坑）

### 6.1 Opus pre-skip（必处理）
Opus 流开头有 **312 个样本（@48kHz，约 6.5ms）的预延迟**，必须跳过，否则开头有杂音/延迟错位。WebCodecs 不自动处理。在第一个解码帧后丢弃前 312 样本。

### 6.2 codec 映射
teamspeak-js 的 `codec` 字段（4=Opus Voice / 5=Opus Music）。WebCodecs 的 `AudioDecoderConfig.codec` 用字符串 `'opus'`。两者不冲突（都 Opus），但要注意 TS 的 Opus 帧边界是 20ms，喂 `EncodedAudioChunk` 时 `timestamp` 要按 20ms 递增（`timestamp += 960` @48k）。

### 6.3 timestamp / 帧边界
WebCodecs 要求每个 `EncodedAudioChunk` 有递增 `timestamp`（微秒）。Opus 20ms 帧 → timestamp 步进 `20000`（μs）或 sample 步进 `960`（按 sampleRate 算）。乱序/倒退会解码失败。

### 6.4 Safari 兜底
WebCodecs `AudioDecoder` 的 Opus 支持在 Safari 滞后。**兜底**：检测 `typeof AudioDecoder === 'undefined'` 时用 `opus-wasm` / `@codesandbox/opus-decoder` 解码。Chrome/Edge/Firefox 已支持。

### 6.5 回声消除（⚠️ 重要）
`onVoice` 已过滤 bot 自己（`clientId === clid`）。但如果**网页用户同时用 TS 桌面客户端进了同一频道**，会形成：频道→bot→网页扬声器，和 网页用户 TS 客户端→频道→bot，形成回环啸叫。
- **方案 1（推荐，简单）**：网页语音模式下，要求用户**不要同时用 TS 桌面客户端进同频道**（纯网页模式，bot 代听代说）。
- **方案 2（复杂）**：浏览器端 WebRTC AEC（`echoCancellation:true` 的 getUserMedia 约束 + 回声参考）。成本高，MVP 不做。

### 6.6 延迟
WebSocket + 浏览器音频栈注定比原生 TS（UDP+内核混音）多 **50-150ms**。日常聊天完全可接受，电竞级不行。优化手段：AudioWorklet（不在主线程）、合适的缓冲深度（太小 underrun，太大延迟）。

### 6.7 断线重连
teamspeak-js 的 Client 断线后需重连（`on("disconnected")`）。下行中继的 WebSocket 也要处理断线（浏览器自动重连 + 后端 Queue 缓冲）。

---

## 7. 文件清单

### TSMusicBot（teamspeak-music-bot，独立仓库）
- bot 连接逻辑：加 `client.on("voice", ...)` 订阅
- 新增：下行导出端点（WebSocket 或 HTTP ingest）

### PowerfulTS 后端（本仓库 `backend/`）
- 新增 `app/services/voice_downlink.py`（镜像 `live_audio.py`）
- 新增 `app/routers/voice.py`（或并入 `music.py`）：`WS /api/music/voice/stream/{bot_id}`
- `app/main.py`：注册 router + lifespan 挂下行中继
- `app/core/config.py` + `.env`：如需 TSMusicBot 下行端点地址

### PowerfulTS 前端（本仓库 `frontend/`）
- 新增 `src/api/voice.ts`
- 新增 `src/components/music/ChannelListen.vue`（或扩展 `LiveAudioShare.vue`）
- 新增 `src/workers/voice-player-worklet.js`（AudioWorklet）
- 可能新增 `opus-wasm` 依赖（Safari 兜底）

---

## 8. 分阶段实施

### 阶段 0：Spike（1 周）—— 验证链路通
**目标**：一个人在频道说话，网页能听到。
- TSMusicBot：加 `onVoice` → 转发单 client Opus 帧（方案 C 不混音）→ 新 WS 端点
- 后端：镜像 `LiveAudioRelay` 收发
- 前端：WebCodecs 解码单路 + AudioWorklet 播放（处理 pre-skip）
- **验收**：网页能实时听到频道里一个人说话，延迟 < 300ms。

### 阶段 1：MVP（+1-2 周）—— 多人可用
- 多人混音（方案 B 浏览器混，或 A 后端混）
- Safari 兜底（opus-wasm）
- 断线重连
- 上行+下行整合到一个 UI（双向通话）

### 阶段 2：生产（+1-2 周）
- 后端混音（方案 A，TSMusicBot 用 @discordjs/opus 混）
- 回声处理（方案 1 纯网页模式约束，或 AEC）
- 延迟调优、稳定性、多 bot 场景

**总工作量**：原型（阶段0+1）2-3 周，生产级（含阶段2）1.5-2 个月。

---

## 9. 验证标准

- **Spike 通过**：网页登录 → 进入某 bot 的频道语音下行 → 频道里一人说话 → 网页扬声器实时出声（< 300ms 延迟，无持续杂音）。
- **MVP 通过**：两人同时说话都能听到、不破音；Chrome + Safari 都行。
- **生产通过**：稳定运行 1 小时无断线累积延迟；回声可控；多人频道正常。

---

## 10. 风险与降级

| 风险 | 应对 |
|---|---|
| teamspeak-js 的 onVoice 在 TS6（新版协议）下行为不一致 | TS3 已实证；TS6 需在 Spike 专门验证（teamspeak-js 声称兼容 3/5/6） |
| Opus 帧边界/timestamp 导致解码失败 | 严格按 20ms/960sample 递增；先在单人静态文件上验证解码 |
| TSMusicBot 改动需 fork/PR 上游 | 先用插件/补丁方式（如果 teamspeak-music-bot 支持），最小侵入 |
| 浏览器 AudioWorklet 兼容性 | AudioWorklet 现代浏览器都支持；老路 fallback 用 ScriptProcessorNode（已废弃但能用） |
| 上游 teamspeak-music-bot 维护节奏 | 本功能改动局部（onVoice 订阅 + 一个端点），不依赖上游大改 |

---

## 11. 参考（已查证）

- **底层库**：[HoneyBBQ/teamspeak-js](https://github.com/HoneyBBQ/teamspeak-js) —— `on("voice")` 在 `src/client.ts:408-433`，`VoiceData` 在 `src/types.ts`
- **TSMusicBot**：[ZHANGTIANYAO1/teamspeak-music-bot](https://github.com/ZHANGTIANYAO1/teamspeak-music-bot) —— bot 连接 + sendVoice 管道可参考
- **上行实现（镜像参考）**：`backend/app/services/live_audio.py`（`LiveAudioRelay`）、`backend/app/routers/music.py` 的 `/api/music/live/*`（232-337 行）、`frontend/src/components/music/LiveAudioShare.vue`
- **WebCodecs**：[MDN AudioDecoder](https://developer.mozilla.org/en-US/docs/Web/API/WebCodecs_API)、[W3C spec](https://www.w3.org/TR/webcodecs/)（Opus pre-skip、EncodedAudioChunk）
- **协议背景**：[ReSpeak/tsdeclarations](https://github.com/ReSpeak/tsdeclarations/blob/master/ts3protocol.md)（TS3 语音协议，仅供理解，不需要自己实现）

---

## 附：实施前的快速核对

实施 Agent 动手前，先确认这几点（5 分钟，避免返工）：
1. 你的 TSMusicBot 版本 ≥ 支持 teamspeak-js 的 `on("voice")`（检查 `node_modules/@honeybbq/teamspeak-client` 的 `client.ts` 有 `#handleVoicePacket`）。
2. TS 服务器是 TS3 还是 TS6（TS6 需额外验证 onVoice 行为）。
3. 浏览器目标（Chrome/Firefox 直接 WebCodecs；要支持 Safari 就准备 opus-wasm）。
4. 是否接受"网页语音时不同时开 TS 桌面客户端"（回声方案 1）。
