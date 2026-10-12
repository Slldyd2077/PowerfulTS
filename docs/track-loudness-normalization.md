# 音乐机器人逐曲响度均衡

均衡在 TSMusicBot 播放引擎中完成，再编码 Opus 发往 TeamSpeak；网页和原版客户端收到同一份处理后的音乐。先播放并后台分析，分析完成后用 5 秒平滑过渡到固定增益，之后不追随歌曲内部的轻声、渐强或高潮改变音量。

## 处理方式

1. 立即启动播放，同时由独立 FFmpeg 进程用 `ebur128=peak=true` 分析完整音源，仅读取综合响度和真峰值，分析输出发送到 null。
2. 默认目标为 −18 LUFS。固定增益取 `min(目标响度 − 输入响度, −1 − 输入真峰值, 12)` dB。峰值余量优先，最大提升为 12 dB；因此高动态歌曲可能无法完全达到目标。
3. 开始以 0 dB 播放，分析完成后在输出 PCM 上按分贝渐变 5 秒，再保持计算出的固定增益。渐变只随实际输出的音乐帧推进，暂停或缓冲不足不推进。无需重启 FFmpeg 解码器。
4. 歌曲增益与用户音量、语音闪避相乘，再叠加入场音效、编码发送。入场音效不使用歌曲增益；语音闪避仍可在人说话时暂时压低音乐。

分析使用的立体声采样格式与播放链路一致。算法以 [FFmpeg ebur128](https://www.ffmpeg.org/ffmpeg-filters.html#ebur128) / BS.1770 测量为基础；−18 LUFS 是项目选定的音乐目标，不宣称符合广播 EBU R128 的 −23 LUFS 交付规范。分析结束前及渐变期间尚未达到最终均衡值；后续有损编码或客户端处理仍可能改变峰值。

跳转进度或 B站 CDN 中断后续播时继续使用当前歌曲的固定增益，不重新分析片段。开关或目标变化只作用于下一首歌；暂停/恢复保持增益。全静音内容使用 0 dB，不放大底噪。麦克风、实时共享和没有完整音源的外部 PCM 流不应用此功能，包括 go-librespot 的连续 Spotify FIFO。

响度分析不再阻塞开播或歌曲结束后的队列前进；音源解析和首帧缓冲仍需要时间。网络音源通常读取两次，但不新增磁盘音频缓存。保留现有每个播放器最多 64 项、15 分钟的内存测量结果缓存，服务重启即失效。分析最长 60 秒，停止/切歌取消子进程；失败继续以原始增益播放，面板显示“本首响度分析失败”。跳转进度与 CDN 续播保留当前分析及渐变进度。

## 更新与使用

### 后台分析与 5 秒平滑过渡（2026-10-12，v1.1.5）

生产兼容引擎提交 `48577fe57984ca3522da092e614a30f2501b6455` 同时包含快速测量、后台开播、5 秒增益过渡和 PR #22 的 PCM 语音避让修复。直接从该提交构建，无需再叠加响度或语音避让补丁。保留原 TeamSpeak 连接实现，只新增语音活动事件的编码数据供人声阈值检测。

补丁迁移可使用 [track-loudness-background.patch](../deploy/tsmusicbot/track-loudness-background.patch)，基于 `5b19d35` 的音频文件，已包含快速测量；不要再叠加 fast-analysis 补丁。此补丁只迁移响度改动，完整 v1.1.5 引擎请使用上述固定提交。

本地 180 秒 WAV 本次复测：旧方式 12.03 秒，新方式 0.80 秒。生产服务器 FFmpeg 8.0.1 对 180 秒合成音频的无文件测试：旧方式 33.46 秒，新方式 2.77 秒，约快 12 倍。两组音源和机器不同，不能直接比较绝对速度，也不代表真实 CDN 下载耗时。

275 项引擎回归通过，包含真实播放先于分析完成、逐帧音量连续性、正负增益、暂停/跳转保持过渡、EOF 不等待分析、切歌取消、静音、HTTP 整曲分析、配置/API 和 PCM 语音避让。TypeScript 检查及编译通过；前端浏览器检查后台分析时仍显示播放状态。

### 减少开播分析耗时（2026-10-11，历史单项验证）

新增增量补丁 [track-loudness-fast-analysis.patch](../deploy/tsmusicbot/track-loudness-fast-analysis.patch)，基于生产兼容提交 `9ea0a2e7600333cf6caf72eae3a4bc5a0e1248a6`。把预分析的 `loudnorm` 换成只测量的 `ebur128=peak=true`，仍扫描完整音源、统一为 48 kHz 立体声，并保留 BS.1770 综合响度门限和过采样真峰值测量。旧流程为获取输入统计，还计算并丢弃动态均衡后的 192 kHz 输出；新流程去掉这部分开销。播放时的固定增益公式、峰值余量、最大提升、缓存和切歌取消保持不变。

本地 Windows FFmpeg 对同一段 180 秒立体声 WAV 的对比：旧分析 4.29 秒，新分析 0.53 秒，约快 8 倍。这是本地计算基准，不代表线上加载也快 8 倍；首次播放仍需完整下载和解码，播放阶段仍重新读取音源，网络带宽、CDN 和音源解析可能成为瓶颈。现有缓存按完整 URL 保存 15 分钟，签名 URL 改变时可能无法复用。进一步降低首播等待可以提前分析下一首，或缓存下载的音源，但此次没有引入这些生命周期和存储改动。

两种测量器的分块与统计实现有所差异，变化明显的短音频可能获得不同的综合响度和固定增益，不能承诺逐项读数完全相同。回归测试检查稳态音源在 44.1/48/96 kHz 下与旧测量接近，并直接验证新算法保留轻声/高潮比例、平衡不同母带、捕捉采样点之间的峰值、静音不放大、HTTP 在 EOF 结束及缓存命中不重复下载。低于测量门限或过短且没有有效综合读数的非静音内容按分析失败处理。

本地验证：兼容引擎上述五组测试 261 项通过，TypeScript 检查和后端引擎编译通过；PowerfulTS 前端生产构建及歌单浏览器测试通过，确认队列处理中显示进度、完成后隐藏、中断后保留错误提示。这些检查没有连接真实 TeamSpeak，也未测量线上 CDN 耗时。

在对应的引擎源码目录应用并验证：

```sh
git rev-parse HEAD
git apply --check /path/to/PowerfulTS/deploy/tsmusicbot/track-loudness-fast-analysis.patch
git apply /path/to/PowerfulTS/deploy/tsmusicbot/track-loudness-fast-analysis.patch
npx vitest run src/audio/track-loudness.test.ts src/audio/player.test.ts src/data/config.test.ts src/web/api/bot.test.ts src/bot/instance.test.ts
npx tsc --noEmit
npm run build
```

这是已包含原响度功能之后的增量补丁；不要用它代替初次功能补丁。重建并部署外部 TSMusicBot 后才会加速实际播放，只更新 PowerfulTS 前端不会改变引擎分析速度。

HTTP 音源的预分析会移除播放链路的 `reconnect_at_eof` 参数：整首音频读完后必须结束分析并取得统计 JSON，不能在文件末尾不断重连。播放阶段的 CDN 重连参数保持不变。回归测试包含本地 HTTP 服务提供的完整音频，检查只读取一次并正常结束。

引擎仓库已保存完整实现：现有生产服务器使用[兼容提交 `9ea0a2e`](https://github.com/Slldyd2077/teamspeak-music-bot/tree/9ea0a2e7600333cf6caf72eae3a4bc5a0e1248a6)（分支 `codex/audio-production-compatible`）；通用定制分支使用[提交 `165e897`](https://github.com/Slldyd2077/teamspeak-music-bot/tree/165e8975ac3dcf1ca24b83c8b000c9f623112010)。这两个提交均直接包含功能，构建时无需应用补丁。兼容提交的 `src/` 已逐文件核对为实际上线源码；升级分支选择与检查见[发布指南](release-guide.md#上游引擎)。

### 旧基线的补丁迁移

以下补丁留作历史迁移及回退参考。2026-10-10 已在现有网站上线。线上采用保留原 TS 连接层的兼容移植构建，使用[生产兼容补丁](../deploy/tsmusicbot/track-loudness-production-compatible.patch)，其源代码基线校验值见[基线清单](../deploy/tsmusicbot/track-loudness-production-baseline.json)。这份补丁只用于清单对应的实际生产基线；含 CRLF 的旧文件应先核对校验值，再用 `git apply --check --ignore-space-change` 验证。固定提交 `453d2d1` 则使用下文的通用补丁，不能混用两份。

PowerfulTS 不捆绑 TSMusicBot，引擎需要单独更新。补丁基于专用 fork 的固定提交 `453d2d124b9995034fe9cd46ebf2cad597382d42`，文件为 [track-loudness.patch](../deploy/tsmusicbot/track-loudness.patch)。在该引擎源码目录执行：

```sh
git rev-parse HEAD
git apply --check /path/to/PowerfulTS/deploy/tsmusicbot/track-loudness.patch
git apply /path/to/PowerfulTS/deploy/tsmusicbot/track-loudness.patch
npm ci
npx vitest run src/audio/track-loudness.test.ts src/audio/player.test.ts src/data/config.test.ts src/web/api/bot.test.ts src/bot/instance.test.ts
npx tsc --noEmit
npm run build
```

然后按原部署方式重建 TSMusicBot 并重建 PowerfulTS 前后端，保留原数据卷。安装包或 PowerfulTS 镜像升级不会自动升级外部引擎。

在“音乐控制 → 机器人行为 → 逐曲响度均衡”开启。默认关闭；开关按引擎保存，对该引擎的所有机器人音乐输出生效。旧引擎没有支持字段时按钮禁用，直接请求启用也返回 409，不会假装已经生效。

引擎配置为 `loudnessNormalization: { enabled: false, targetLufs: -18 }`，目标允许 −24 到 −14 LUFS。设置接口是 `GET/POST /api/bot/settings`；PowerfulTS 代理为 `GET/PUT /api/music/bot-settings`。播放状态提供 `analyzing`、`applied`、`failed`、`disabled` 或 `unavailable` 及本首固定增益，播放器显示实际状态。

## 验证边界

真实 FFmpeg 测试生成两首具有轻声段和高潮段的音频：原始整体相差约 14 dB；逐曲处理后高潮段相差小于 0.2 dB，每首歌内轻声/高潮原有的约 12 dB 比例保持不变。另有测试覆盖峰值余量、静音、固定增益、跳转、设置变化、取消分析、失败回退、入场音效期间的队列保护、配置持久化和旧引擎拒绝。

浏览器验证检查面板启用、下首生效提示、固定增益状态、刷新持久化、分析失败状态和手机布局。运行 `pnpm test:music-browser` 前，先构建前端并在端口 18185 启动 `vite preview`；浏览器参数同[麦克风增强测试说明](web-microphone-processing.md)。

上述自动化测试不连接真实 TeamSpeak；实际部署的服务、HTTP 分析与公网浏览器验收另见[部署记录](audio-deployment-2026-10-10.md)。上线后仍应试听不同母带响度的歌曲、同一首的轻声/高潮、拖动进度和语音闪避，确认实际客户端效果。
