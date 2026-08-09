# 网页端 TeamSpeak 频道双向语音：实现与校验记录

> 校验日期：2026-07-28
> 对照源码：PowerfulTS `dev@11ea88f`、本地 TSMusicBot `0.3.3@9df519f`

## 1. 目标与当前结论

用户无需同时打开 TeamSpeak 桌面客户端，即可在 PowerfulTS 网页中：

- 收听当前机器人所在频道的语音；
- 允许浏览器麦克风后向频道发言；
- 多人同时说话时在浏览器端混音；
- 在断线后自动重新取得一次性凭证并重连。

实现链路如下：

```text
TeamSpeak ──Opus/UDP──> TSMusicBot ──登录态 WebSocket──> PowerfulTS
                                                              │
                                     一次性票据 WebSocket      │
浏览器 <───────────────────────────────────────────────────────┘
  ├─ 下行：WebCodecs AudioDecoder -> AudioWorklet 混音 -> 扬声器
  └─ 上行：getUserMedia -> MediaRecorder -> 既有 LiveAudioRelay -> TSMusicBot
```

## 2. 原施工文档逐项校验

| 原结论 | 校验结果 | 采用的修正 |
|---|---|---|
| TSMusicBot 是 Node.js/TypeScript 的 `teamspeak-music-bot`，不是 TS3AudioBot | 正确 | 已对照本地 `E:\\TSMusicBot` 的 `package.json` 与源码 |
| 底层使用 `@honeybbq/teamspeak-client` | 正确 | 装的是 `0.2.2`（npm 上最新为 `0.2.3`，没有 0.3.x —— `0.3.3` 是 TSMusicBot 自己的版本号，别混），由 `src/ts-protocol/client.ts` 包装。入站语音在其 `dist/index.mjs` 里确有分发：包类型 0/1 且长度 > 5 时按 `[voiceId:u16][clientId:u16][codec:u8][opus…]` 拆出后回调 `voiceData` |
| 接收事件是 `client.on("voice")` | **错误** | 实际事件是 `client.on("voiceData")`；TSMusicBot 再向上发出 `voiceFrame` |
| 回调给出 `clientId`、`codec`、原始 Opus `data` | 正确，但仅对 Opus codec 4/5 可直接交给 WebCodecs | 导出端明确过滤其他旧 codec |
| 下行可经 TSMusicBot -> FastAPI -> 浏览器 | 正确 | 已实现两段 WebSocket 中继 |
| PowerfulTS 已有“麦克风上行” | **错误** | 原 `LiveAudioShare.vue` 采集的是屏幕/系统音频；本次另加 `getUserMedia` 麦克风上行 |
| 原始 Opus 必须固定丢弃 312 个 pre-skip 样本 | **错误** | 312 并非原始 TeamSpeak Opus 包的固定字段；未手动丢样本。Ogg Opus 的 pre-skip 属于 `OpusHead` 元数据 |
| TeamSpeak Opus 包固定 20 ms | **不可靠** | RFC 6716 允许多种帧长；从 TOC 解析包时长，异常时才回退 960 样本 |
| WebCodecs 时间戳可 `+= 960` | **错误** | `EncodedAudioChunk.timestamp` 单位是微秒；按 `durationSamples * 1_000_000 / 48000` 递增 |
| 通过 Safari 品牌判断启用 wasm | **不可靠** | 运行时调用 `AudioDecoder.isConfigSupported()`；当前实现对不支持原始 Opus 的浏览器给出明确错误，尚未引入 wasm |
| 延迟通常 50–150 ms | 只能作为估计，不能当验收事实 | 当前抖动启动缓冲为 40 ms，总排队上限 250 ms；端到端延迟必须在真实 TS 环境测量 |
| 断线需要重连 | 正确 | 浏览器指数退避，并为每次连接重新申请一次性票据 |
| Spike/MVP/生产三种混音方案 | 方向正确 | 当前采用浏览器端 per-client 解码与 AudioWorklet 混音（原方案 B） |

## 3. 已落地协议

### 3.1 TSMusicBot 下行端点

```text
WS /api/voice/downlink/{botId}
Cookie: session=<TSMusicBot 登录会话>
```

服务端复用现有会话校验，接受注册账号或受限的两小时 guest 会话，拒绝无效会话和不存在的 bot。每条 WebSocket 二进制消息对应一个完整 Opus 包：

```text
[version:u8][codec:u8][clientId:u16be][durationSamples:u16be][opus:remaining]
```

- `version`：当前为 `1`；
- `codec`：只发送 `4`（Opus Voice）或 `5`（Opus Music）；
- `clientId`：TeamSpeak 说话人的 client id；
- `durationSamples`：从 RFC 6716 TOC 解析的 48 kHz 样本数；
- `opus`：原始 Opus packet，不是 Ogg 容器。

### 3.2 PowerfulTS 浏览器端点

浏览器 WebSocket API 无法设置自定义 `X-Session-Token` 请求头，因此不把登录 token 放进 URL，而是分两步：

```text
POST /api/music/voice/start?botId={botId}
Authorization: PowerfulTS 现有会话（X-Session-Token）

WS /api/music/voice/{ticket}/stream
```

票据使用 32 字节随机能力值，30 秒过期且只能原子消费一次。权限在签发票据时通过 `OwnedBotId` 校验，重连必须申请新票据。

浏览器端点先 `accept()` 再去连 TSMusicBot，所以 WS 一打开只代表「PowerfulTS 收下了」，上游是否可用要看随后的关闭码。关闭码是前端唯一能拿到的诊断信息，因此分档给（见 `voice_close_for`）：

| code | 含义 | 前端处理 |
|---|---|---|
| 4404 | 票据不存在/已用掉/过期 | 重新申请票据 |
| 4502 | TSMusicBot 没有 `/api/voice/downlink`（版本过旧） | 停止重试并提示 |
| 4503 | 连不上 TSMusicBot（没起来 / 地址不通 / 登录没成功） | 有限次退避重连 |
| 1011 | 流中途出错 | 有限次退避重连 |

### 3.2.1 频道浏览与切换

```text
GET  /api/music/voice/channels?botId=   → 频道树 + 各频道在场成员 + botCid
POST /api/music/voice/channel?botId=    → {cid, password}
```

频道树/成员直接读 `ts3_monitor` 的 3 秒快照，不额外开 ServerQuery 连接；`channellist -flags`
额外带回 `channel_flag_password`，前端据此决定要不要弹密码框。

**动作之后要强制同步快照。** 3 秒快照对后台轮询够用，但加入通话 / 切频道 / 挂断之后
前端马上就会去读一次，那时快照还是动作之前的状态 —— 表现为「点了没反应，过一会儿才更新」，
而且前端乐观设置的当前频道会被这一拍旧数据覆盖，看起来像被弹回原频道。
所以监控提供 `request_refresh()` / `wait_for_refresh(token)`：前者唤醒轮询线程立刻跑一轮，
后者等到**本次请求之后才开始**的那一轮跑完（令牌用「已开始的轮询数」，正在飞的那一轮
读的是动作之前的状态，不算数）。三个 voice 端点和 `?fresh=1`（用户手动点刷新）走这条路，
上限 2 秒，超时就退回原来的行为，不把动作本身拖失败。

两个容易踩错的点：

- **bot 用 clid 定位，不用昵称。** 昵称会随「正在播放的歌」和 `<WEB通讯>` 标记变化，
  按昵称匹配会在这两种情况下失效。clid 由 TSMusicBot 的 `GET /api/bot/:id` 返回
  （`BotStatus.clientId`），每次重连都会变，所以不缓存。
- **切频道走 bot 自己的 TS 客户端，不走 ServerQuery `clientmove`。**
  SQ 管理账号通常持有 `b_channel_join_ignore_password`，那条路会把频道密码整个绕过去
  ——实测用错误密码也能把 bot 移进加密频道。改由 TSMusicBot 的
  `POST /api/bot/:id/channel` 用 bot 身份 `clientMove`，密码才由服务端正常校验，
  错误密码回 TS error 781 → 前端显示「频道密码不正确」。

### 3.2.2 `<WEB通讯>` 昵称标记

`setupVoiceDownlink` 按 bot 统计监听器数量，0→1 时 `BotInstance.setWebVoiceActive(true)`，
1→0 时置回，由 `BotProfileManager` 在昵称前加 `<WEB通讯> `。两个要点：

- 标记是状态提示不是装饰，所以 **`nicknameEnabled` 关着也要生效**；清除时必须
  `forceNickname`，否则关掉标记后没人再写昵称，bot 会一直挂着 `<WEB通讯>`。
- 标记占掉 30 字节上限里的 12 字节，基础昵称要在**剩余预算内**构建而不是拼完再截断，
  否则会把标记本身截半。`truncateUtf8` 原本在预算 < 3 字节时仍返回 3 字节省略号，
  会超限，已一并修掉。
- **PowerfulTS 侧要把标记剥掉再做身份匹配。** 昵称是好友上线提醒、好友在线状态、
  Steam 当前游戏这些功能的身份键，全是按账号昵称精确匹配的；带着标记去比一律失配
  —— 曾表现为「从网页加入通话后好友收不到 QQ 上线提醒」。`ts3_monitor` 因此在快照里
  存两份：`nickname` 是 TS 里的原样（展示用，别人看到的就是带标记的），
  `identity` 是 `strip_web_voice_marker()` 之后的账号昵称（匹配用），上线事件带的是后者。
  例外是 ServerQuery 私聊（验证码、补发的好友提醒）**仍按原样昵称精确匹配**：
  私聊发给网页身份等于发给一台机器人，用户在浏览器里根本看不到，
  认成「已送达」会把待发通知白白清掉。
- 通话 bot 自带一个全新的 TS `unique_identifier`，别把它登记成「首次进服务器的新成员」，
  否则每个人第一次用网页通话都会给管理员刷一条新人提醒（`on_online(web_voice=True)` 跳过）。

**运行前提（这个功能最容易踩的坑）**：链路的三段是分开部署的，只改源码不重启不生效——

- PowerfulTS 后端进程必须重启，否则 `POST /api/music/voice/start` 返回 **404**（前端已把这个 404 翻译成「请重启或重新部署后端」，不再是 axios 那句 `Request failed with status code 404`）；
- TSMusicBot 跑的是 `dist/`（容器里是构建期 `COPY` 进去的），改完 `src/` 要 `npm run build`，容器还得重新 build，否则升级被拒 → 4503/4502。

### 3.3 浏览器解码与混音

- 先以 `AudioDecoder.isConfigSupported({ codec: "opus", sampleRate: 48000, numberOfChannels: 2 })` 做能力检测；
- 每个 `clientId` 独立维护解码器和微秒时间戳，避免不同说话人的时间线互相干扰；
- 解码后的 planar PCM 传给 AudioWorklet；
- Worklet 以 40 ms 缓冲启动，多路累加后用饱和函数限幅，积压超过 250 ms 时丢弃旧音频；
- 10 秒无新包的解码器会关闭，WebSocket 断开时全部清理。

### 3.4 麦克风上行

网页使用：

```typescript
navigator.mediaDevices.getUserMedia({
  audio: {
    echoCancellation: true,
    noiseSuppression: true,
    autoGainControl: true,
    channelCount: 1,
  },
})
```

随后以 `MediaRecorder` 每 100 ms 发送一个 WebM/Opus（或浏览器可用格式）分片，复用既有 `/api/music/live/*` -> TSMusicBot `/api/player/:botId/live` 上行链路。`source=microphone` 仅用于正确标记会话用途。

注意：开启实时上行会占用机器人的播放器输入，和“共享电脑音频”一样会停止/替代当前播放；这不是独立的第二个 TeamSpeak 身份。

## 4. 文件清单

### `E:\TSMusicBot`

- `src/ts-protocol/client.ts`：订阅 `voiceData` 发出 `voiceFrame`；`joinChannelById` 让加入频道的错误往上抛（`joinChannel` 是聊天命令用的，吞异常）；
- `src/bot/instance.ts`：转发语音事件；`BotStatus.clientId`；`setWebVoiceActive` / `joinChannelById` 转发；
- `src/bot/profile.ts`：`<WEB通讯>` 昵称标记与字节预算；
- `src/web/api/bot.ts`：`POST /api/bot/:id/channel`（bot 身份加入频道，密码由服务端校验）；
- `src/web/voice-downlink.ts`：时长解析、二进制封包、订阅生命周期、按 bot 统计监听器数量；
- `src/web/voice-downlink.test.ts` / `src/bot/profile.test.ts`：协议、监听器计数、标记与昵称长度测试；
- `src/web/server.ts`：受会话保护的下行 WebSocket upgrade。

### `E:\PowerfulTS\backend`

- `app/services/voice_downlink.py`：短期一次性票据；
- `app/services/tsmusic_client.py`：携带 TSMusicBot Cookie 连接上游下行 WS；`TSMusicUnavailable` 标出「机器人没起来」（`_ensure_login` 对连接失败只记日志不抛，光看异常类型分不出来）；
- `app/routers/music.py`：票据签发、浏览器 WS 转发（含断开看门狗与关闭码分档）、麦克风 source；
- `app/services/ts3_monitor.py`：快照里补 `clid` 与频道密码标志，`get_voice_overview` 供频道选择器；
- `app/main.py`：初始化票据服务；
- `tests/test_voice_downlink.py`：票据单次消费/过期、关闭码分档、浏览器断开后上游随之关闭；
- `tests/test_voice_channels.py`：成员分组、按 clid 定位 bot、切频道错误分类。

### `E:\PowerfulTS\frontend`

- `src/api/voice.ts`：申请收听票据、频道总览与切频道，并把 HTTP 错误翻译成可照做的提示；
- `src/api/music.ts`：实时音频上行增加 `source`；
- `src/components/voice/ChannelVoice.vue`：「加入通话 / 挂断」单按钮（收听必成、麦克风尽力而为）+ 静音开关、有限次重连、状态 UI；
- `src/components/voice/ChannelBrowser.vue`：频道树 + 在场成员，点选切换，加锁频道弹密码框；
- `src/workers/voice-player-worklet.js`：抖动缓冲和多人混音；
- `src/views/VoiceCallView.vue`：独立的「网页通话」页（`/voice`），含机器人选择与用法说明；
- `src/router/index.ts`、`src/components/layout/SideNav.vue`、`MobileNav.vue`：`/voice` 路由与导航入口。

## 5. 安全与运行边界

- 浏览器不能直接连接 TSMusicBot；所有浏览器权限仍由 PowerfulTS 校验。
- TSMusicBot 下行由 PowerfulTS 的一次性票据代理；注册账号和受限 guest 会话均可申请，guest 不能借此访问音乐、好友、Steam 或管理接口。
- 一次性票据不会复用用户 token，也不能被第二条 WebSocket 重放。
- 单条上游包限制为 64 KiB。
- 建议使用耳机。AEC 只能降低扬声器回灌，无法保证在所有设备上完全消除回声；同一设备不要再让 TeamSpeak 桌面客户端进入同一频道。
- 当前不提供 wasm Opus fallback。不支持 WebCodecs 原始 Opus 的浏览器会被明确拒绝，而不是静默无声。
- TS6 行为尚未用真实服务器验证；当前代码基于本地 TSMusicBot/teamspeak-client 的同一 `voiceData` 接口。

## 6. 验收记录与待完成的实机项

已自动验证：

- TSMusicBot 新协议单元测试通过；
- TSMusicBot TypeScript 与 Web UI production build 通过；
- PowerfulTS 票据和既有 live audio 定向测试通过；
- PowerfulTS frontend production build 通过；
- 桌面与移动视口均完成浏览器渲染检查，未发现控制台错误或布局遮挡。

仍需连接真实 TeamSpeak 频道验收：

1. 单人讲话可持续收听，且不会出现周期性爆音；
2. 两人同时讲话时两路均可辨识；
3. 网页麦克风可被频道内其他用户听见；
4. 运行 1 小时无监听器泄漏或持续积累延迟；
5. 实测端到端延迟并据此调整 40 ms/250 ms 缓冲阈值；
6. 若要求 Safari 且 `isConfigSupported()` 返回 false，再独立加入并测试 wasm 解码器。

## 7. 规范依据

- [RFC 6716：Opus packet framing 与 TOC](https://www.rfc-editor.org/rfc/rfc6716)
- [RFC 7845：Ogg Opus 的 pre-skip / OpusHead](https://www.rfc-editor.org/rfc/rfc7845)
- [W3C WebCodecs：时间戳单位与 `isConfigSupported`](https://www.w3.org/TR/webcodecs/)
- [W3C Opus WebCodecs Registration：原始 Opus packet 与 codec string](https://www.w3.org/TR/webcodecs-opus-codec-registration/)
