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
