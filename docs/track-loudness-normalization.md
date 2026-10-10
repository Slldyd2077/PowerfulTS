# 音乐机器人逐曲响度均衡

均衡在 TSMusicBot 播放引擎中完成，再编码 Opus 发往 TeamSpeak；网页和原版客户端收到同一份处理后的音乐。它调整不同歌曲的整体响度，同一首歌使用一个固定增益，不追随歌曲内部的轻声、渐强或高潮改变音量。

## 处理方式

1. 播放前，由 FFmpeg 分析完整音源。`loudnorm` 的分析输出发送到 null，仅读取 **输入**综合响度 `input_i` 和输入真峰值 `input_tp`。
2. 默认目标为 −18 LUFS。固定增益取 `min(目标响度 − 输入响度, −1 − 输入真峰值, 12)` dB。峰值余量优先，最大提升为 12 dB；因此高动态歌曲可能无法完全达到目标。
3. 真正播放时只使用常量 `volume=增益dB`。播放链路不使用动态 loudnorm、dynaudnorm、压缩器或自动增益，不压平高潮。
4. 之后才应用用户设置的机器人音量及既有语音闪避、叠加入场音效，再编码发送。语音闪避是独立功能：如果打开，仍会在人说话时暂时压低音乐。

分析使用的立体声采样格式与播放链路一致。算法以 [FFmpeg loudnorm](https://www.ffmpeg.org/ffmpeg-filters.html#loudnorm) / BS.1770 测量为基础；−18 LUFS 是项目选定的音乐目标，不宣称符合广播 EBU R128 的 −23 LUFS 交付规范。真峰值余量用于解码 PCM，后续有损编码或客户端处理仍可能改变峰值。

跳转进度或 B站 CDN 中断后续播时继续使用当前歌曲的固定增益，不重新分析片段。开关或目标变化只作用于下一首歌；暂停/恢复保持增益。全静音内容使用 0 dB，不放大底噪。麦克风、实时共享和没有完整音源的外部 PCM 流不应用此功能，包括 go-librespot 的连续 Spotify FIFO。

首次播放需分析完整音源，可能增加开播等待；网络音源通常读取两次。对完全相同的音源 URL 缓存测量结果 15 分钟，每个播放器最多 64 项。CDN URL 或音质变化可能需要重新分析。分析最长 60 秒，停止/切歌会取消子进程；失败则整首使用原始增益，面板明确显示“本首响度分析失败”。不会在歌曲开始后迟到地改变增益。

## 更新与使用

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
