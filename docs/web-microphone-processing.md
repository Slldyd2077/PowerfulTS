# 网页麦克风音频增强

网页通话的“麦克风音频增强”设置默认使用 RNNoise 智能降噪，开启回声消除、自动增益和键盘与停顿噪声抑制。设置保存在当前浏览器的 `voice_microphone_processing_v1`，不跨设备同步。

## 算法与链路

```text
麦克风 getUserMedia
  → 浏览器回声消除 / 自动增益
  → RNNoise 0.2（48 kHz 单声道，AudioWorklet + WASM）
  → RNNoise 人声概率门限（可选）
  → 麦克风音量
  → MediaStreamDestination
  → MediaRecorder
  → 原有 WebSocket 上行 / PowerfulTS / TSMusicBot / TeamSpeak
```

算法来自 [Xiph RNNoise](https://github.com/xiph/rnnoise)，使用 [Jitsi 的同步 WASM 构建](https://github.com/jitsi/rnnoise-wasm)，固定 npm 包 `@jitsi/rnnoise-wasm@0.2.1`。同步构建包含 RNNoise 0.2 模型，可在 AudioWorklet 中直接初始化。生产构建保留 ES 模块格式，避免默认 Worker 打包引入 AudioWorklet 中不存在的 `self.location`。

RNNoise 帧长为 480 样本，处理器把浏览器渲染块连续组装成 10 ms 帧，并将模型输出交给录音器。适配队列增加固定 10 ms 缓冲，模型自身另有处理延迟；这不代表通话端到端延迟。模型独立于界面主线程运行，不需要 SharedArrayBuffer 或跨源隔离。

键盘抑制利用模型返回的人声概率控制平滑门限。默认门限 60%，支持 10%–90%；开门约 5 ms、关门约 40 ms，保留约 250 ms 的人声尾音。调低门限可保留轻声，调高可加强停顿噪声抑制。此功能不能保证移除与人声重叠的所有键盘声，也不能区分自己与旁人的说话声。

回声消除和自动增益使用浏览器实现，实际支持状态通过采集音轨的 `getSettings()` 显示。RNNoise 负责噪声抑制，不替代回声消除。外放回声效果依赖浏览器、音频设备及播放路由，仍建议戴耳机。

## 模式与失败处理

- **RNNoise 智能降噪**：默认模式。采集先保留浏览器基础降噪，模型就绪后才尝试关闭基础降噪，保留采集端回声消除和自动增益参数。
- **浏览器基础降噪**：省电模式。100% 麦克风音量时直接使用原始采集流。
- **关闭降噪**：关闭背景噪声处理；回声消除和自动增益仍由各自开关决定。

模型、音频线程或 WASM 不可用时回退到原始采集流，显示提示；手动网页增益可能同时不可用。音频线程启动和模型加载有时限，避免手机浏览器在未解锁 AudioContext 时一直卡在连接中。运行中模型失败会在现有录音链路里切回采集流并恢复基础降噪；浏览器拒绝恢复时显示重新开启麦克风的提示。

模式、回声消除和自动增益变化会重新取得麦克风并重建上行。键盘抑制及人声门限通过消息即时更新，不重建录音器。静音、挂断、页面卸载和连接重建均释放 WASM 状态、处理图、输出音轨；加载模型时挂断会取消初始化，不向用户报麦克风故障。

处理在用户设备本机执行，算法及模型由本网站提供，不发送到第三方降噪服务；通话音频仍经项目原有后端和 TeamSpeak 发送。

## 验证

在 `frontend` 目录运行 `pnpm test:unit` 和 `pnpm build`。浏览器测试使用 Playwright，需安装 Chromium（`pnpm exec playwright install chromium`）或用 `VOICE_TEST_BROWSER` 指定本机浏览器可执行文件。

完成生产构建后，分别启动以下两个本地服务，再运行浏览器测试：

```text
pnpm exec vite --host 127.0.0.1 --port 18184 --strictPort
pnpm exec vite preview --host 127.0.0.1 --port 18185 --strictPort
pnpm test:voice-browser
```

`VOICE_TEST_ORIGIN` 默认 `http://127.0.0.1:18184`；`VOICE_TEST_APP_ORIGIN` 默认 `http://127.0.0.1:18185`，可分别覆盖。测试使用本地模拟 API/WebSocket、浏览器模拟麦克风和合成噪声，不连接真实 TeamSpeak、不向真实频道发送。

测试检查生产 WASM 初始化、连续 PCM、背景噪声减弱、人声门限、处理流录制、资源释放、加载失败降级、设置持久化、通话中切换模式和手机布局。合成音频验证不代表真实设备的音质评分；仍需用机械键盘、风扇、轻声讲话及扬声器外放进行真实 TeamSpeak 通话试听，Safari / iOS 也需要实机验收。

第三方许可随前端发布，位于 `public/third-party/rnnoise/`：Jitsi 包采用 Apache-2.0，RNNoise 采用 BSD-3-Clause。

## VAD、手机中断恢复与蓝牙（2026-10-11）

RNNoise 智能模式默认启用独立的 VAD 人声检测，即使关闭键盘抑制仍可按人声概率开门，沿用平滑开关和 250 ms 尾音。面板显示“检测到人声 / 等待人声”。浏览器基础降噪或关闭降噪不使用神经 VAD；机器人始终按解码 PCM 活动抑制静音传输，属于能量门限，不能等同于神经人声识别。

引擎 `WebVoiceTransmitGate` 只在网页麦克风桥的 realtime 模式生效：检测到活动才发送 TS Opus 包，再保留最多 10 个 20 ms 尾音包。录音器仍持续发送完整容器数据，不能丢弃 WebM/MP4 的静音块，否则 FFmpeg 可能无法解码。音乐及电脑音频分享的发送链路保持连续。音乐 bot 通过已有的 `voiceActivity` 和语音桥分类识别人声包，停止收到后按原有时间恢复音乐音量；该机制仍要求开启“语音避让”。

手机修复包括：点击时提前创建并解锁麦克风 AudioContext；resume / 解码器 / worklet 初始化有超时；获取麦克风后再恢复播放线程；首块验证期不重复拆除正常录音器；连续 10 秒没有录音块、系统 mute、网络积压会进入恢复而非永久显示 live。显式“恢复声音与麦克风”重新采集音轨，保留已解锁的新处理线程。WebCodecs 运行失败会切到 WASM，已关闭通话的解码回调不会进入新通话。

“只收听（不开麦克风）”不会调用 getUserMedia，也不会开启上传。静音释放全部采集音轨。Android 开启处理后的麦克风可能触发浏览器的系统通话模式及蓝牙 SCO/HFP 路由，网页无法控制其他应用的输出；只收听可避免主动进入这一采集模式。代码依据见 [Chromium Android AudioManager](https://chromium.googlesource.com/chromium/src/media/+/master/audio/android/audio_manager_android.cc) 和 [Android Chrome 输出选择限制](https://issues.chromium.org/issues/444576985)。

已加入的通话在后台也允许重连，取消项目原有的“必须前台”限制。但这只是恢复策略，不能阻止 Android 厂商省电策略、浏览器冻结页面或系统暂停麦克风；纯网页不能承诺锁屏后持续双向通话。MediaRecorder 的 timeslice 也可能因 Android 锁屏而延迟，见 [MDN 录音块事件](https://developer.mozilla.org/en-US/docs/Web/API/MediaRecorder/dataavailable_event)。若被暂停，回到页面点击恢复；蓝牙物理路由、Android 真机锁屏及通话中断仍需实机验收。网页 PWA 安装不等同于原生后台录音服务。

验证：70 项前端单元测试、生产构建、真实 Edge 的 RNNoise/WASM/录音与通话链路通过。通话浏览器测试没有关闭自动播放限制，检查生成的 Opus 音频解码后的实际波形、只收听不采集、播放/采集线程暂停后的手势恢复、导航保活、设备失效、静音重入及登出释放。引擎测试覆盖发送门限到音乐 bot 避让/恢复的联动；这些自动化测试不连接真实 TS，也不能代表 Android 蓝牙实机结果。
