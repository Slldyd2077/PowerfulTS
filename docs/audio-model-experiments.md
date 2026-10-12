# 人声模型本机试验（2026-10-11）

这两种模型已完成离线推理，并加入通话页面。DeepFilter 已改为持续状态流式处理；
SpEx+ 与组合仍为分段实验模式。
默认仍为低延迟本地 RNNoise 人声增强。

## 通话页面备选模式

- **DeepFilterNet3**：48 kHz，持续 WebSocket，20 ms PCM16LE 二进制帧。
  使用官方 v0.5.6 Windows LADSPA 实时运行时，保留 STFT、归一化、卷积、GRU、
  深度滤波和合成状态；每路独立进程，断线销毁状态。浏览器播放预缓冲 40 ms。
- **SpEx+ 目标提取**：2 秒一段，需先在页面上传 2–15 秒清晰独立参考录音；
  有效带宽约 4 kHz（模型输入输出 8 kHz，再重采样到 48 kHz 接入原有上传）。
- **组合**：SpEx+ 先提取指定说话人，再用 DeepFilterNet3 抑制残余噪声。
  同样为 2 秒分段，无法恢复 SpEx+ 丢失的高频。

参考录音存储在当前浏览器 localStorage，可在页面删除；每次通话首次上传，之后
复用模型进程内的有限缓存（最多 32 份，进程重启后清空）。不同账号的缓存键隔离。
普通通话音频分段不落盘。页面删除参考会清掉浏览器数据并切回本地人声增强；
已上传的参考由进程缓存淘汰或重启清除，不是立即删除服务器内存。

DeepFilter 经 `/api/voice-processing/stream`，首帧提交登录令牌，令牌不放 URL。
服务器最多四路、每账号一路。浏览器在途音频最多 300 ms，输出缓存最多 100 ms；
超限关闭并重新初始化。重试间隔逐步增加至 30 秒，连续收到两秒模型音频后重置退避；
繁忙时每 10 秒重试，登录失效停止重试。
DeepFilter 启动、缓冲耗尽或中断时自动使用常驻的本地 RNNoise 人声增强旁路。
模型恢复到实际播放音频后自动切回，使用短交叉淡化。同一条输出轨道保持有效，
不重建 MediaRecorder、不重连麦克风上行。页面显示正在使用旁路；本地增强不具备
SpEx+ 的目标说话人隔离效果。旁路自身初始化失败时会使用现有浏览器基础降噪回退。
SpEx+/组合继续保持处理失败时暂停的行为，不自动放宽目标说话人提取。
目标提取经登录鉴权的 `/api/voice-processing/pcm`。
分段模型服务监听 127.0.0.1:18186，流式服务监听 127.0.0.1:18187，Docker 后端通过 host.docker.internal 访问。
`start-all.ps1` 会在环境已安装时启动该服务。无需向公网开放模型服务端口。

DeepFilter 每路双向 PCM 净流量合计 1.536 Mbps，四路约 6.144 Mbps（另加协议、
Opus 通话、音乐和其他业务流量）。24 Mbps 线路通常有余量，仍需实际公网验收。
DeepFilter 模型忙或连接失败时页面显示旁路状态，普通通话继续发送本地处理音频。
SpEx+/组合请求失败时暂停输出，可切回本地人声增强。SpEx+/组合分段边界仍可能产生音质变化。

## 流式运行时与验证

在安装包根目录运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File source/scripts/audio-lab/install-stream-runtime.ps1
.\start-all.cmd
data/audio-lab/.venv/Scripts/python.exe source/scripts/audio-lab/test_stream.py
```

安装脚本固定官方 v0.5.6 DLL，并校验 SHA256。原生插件没有停止内部线程的接口，
因此每路使用独立子进程；连接结束杀掉进程，确保回收线程和模型内存。
Windows 使用 1 ms 计时精度避免 15.6 ms 默认睡眠误触发插件动态增缓冲，
代价是通话期间略高的 CPU 唤醒频率。每路启动含加载和预热，首次开启需稍等。

本机四路、20 ms 帧短测：有声流处理往返中位数 6.9–7.1 ms，p95 9.7–10.6 ms。
这个时间不含采集攒帧、模型算法延迟、浏览器 40 ms 播放缓冲、公网往返和原有
Opus/TS 中继，不能当作用户之间端到端延迟。原生插件仍可能因负载动态增加缓冲。
测试覆盖静音隔离、独立会话能量、重连清空、非法帧、Docker 鉴权桥接、重复会话限制，
浏览器用真实模型验证二进制流、强制断线恢复和资源释放。
旁路新增浏览器验证：首次模型不可用、通话中强制断开、真实 DeepFilter 恢复、
旁路有声输出、连续录音输出轨道不变、挂断后无请求及采集轨道所有权。
该机制只能处理模型链路故障；网页整体网络中断、TS 机器人断线或浏览器后台冻结
仍依赖通话链路的重连机制。常驻旁路会增加客户端 CPU 和电量消耗。

通话主区域仅保留加入/静音/挂断、音量、模式与单一状态；设备和高级参数、参考录音、
一起看、入场音效和帮助按需展开。手机宽度 390 px 已完成浏览器布局检查。

## 启动与试听

运行安装包根目录的 `start-audio-lab.cmd`，打开 http://127.0.0.1:18186 。
试验页面提供公开音频的处理前后对比，以及自己的录音上传。
服务只监听本机，不经 Sakura 公网发布；输入、参考录音和输出在本机 `data/audio-lab/samples`。

DeepFilterNet3 输入最长 30 秒。SpEx+ 另外需要 2–15 秒同一说话人的独立清晰参考语音；
尽量与待处理音频使用不同句子，参考语音中不要混入其他人。

## 初次验证结果

Windows CPU，PyTorch 2.5.1+cpu，4 个推理线程；公开语音截取 2.01 秒。

| 模型 | 试验 | 输入 SI-SDR | 输出 SI-SDR | 热身后的处理时间 |
| --- | --- | --- | --- | --- |
| DeepFilterNet3 | 语音 + 白噪声 | 5.99 dB | 17.40 dB | 0.234 秒 |
| SpEx+ | 两位说话人等 RMS 混合，参考指定第一位 | -0.04 dB | 17.32 dB | 0.556 秒 |
| SpEx+ | 同一混合，另一段参考指定第二位 | — | 16.94 dB | 未单独计时 |

SI-SDR 是对已知干净目标的信号失真指标，不是听感评分。
初次导出的 SpEx+ WAV 曾因漏做幅度归一化而严重削波，试听文件不可用。
现已修复：去除 DC，用整体线性增益恢复电平，RMS 不超过输入或 0.08，峰值不超过 0.95；
保存时也用整体衰减兜底，不再逐样本硬截断。重新导出的两个 WAV 削波率均为 0%，
峰值分别为 0.548 和 0.410，保存后 SI-SDR 仍为 17.32 / 16.94 dB。
`report.json` 新增 `saved_wav` 指标，并以落盘文件复测，避免仅检查模型浮点输出。
这只是短英文样本与合成噪声测试；不能据此断言中文、键盘、房间混响、目标缺席或所有设备表现。
CPU 推理速度快于音频长度也不代表端到端低延迟。

## 接入判断

DeepFilterNet3 保留 48 kHz 全带宽。网页实时模式已使用原生持续状态运行时；
离线试听和组合方案仍使用 Python `enhance()` 整段处理。
现有上行是 MediaRecorder WebM/Opus → HTTP 中继，不能把模型简单塞在字节转发中；
需要先解码 PCM、持续模型推理、重新编码，还需隔离每个用户的模型状态。

SpEx+ 的公开权重是非因果模型，输入输出 8 kHz（有效带宽约 4 kHz），
依赖整段统计与未来上下文。当前用途是录音试听与高延迟分段通话试验，不是流式低延迟模型。
实时上线需要另选因果/流式目标提取模型，并设计每位用户的参考录音和失败回退。
本机 RTX 4060 可用于后续加速，但本次实际测量仅使用 CPU。

## 复现

在安装包根目录创建独立 Python 3.11 环境并安装依赖：

```powershell
uv venv --python 3.11 data/audio-lab/.venv
uv pip install --python data/audio-lab/.venv/Scripts/python.exe -r source/scripts/audio-lab/requirements.txt
data/audio-lab/.venv/Scripts/python.exe source/scripts/audio-lab/experiment.py demo
```

处理自己的录音：

```powershell
data/audio-lab/.venv/Scripts/python.exe source/scripts/audio-lab/experiment.py deepfilter --input noisy.wav --output enhanced.wav
data/audio-lab/.venv/Scripts/python.exe source/scripts/audio-lab/experiment.py spex --input mixed.wav --reference reference.wav --output extracted.wav
```

报告位于 `data/audio-lab/report.json`，`samples` 保存 WAV 对比结果。
网页重复试验会覆盖 `custom-*` 文件；模型不向第三方推理服务发送录音。

## 上游与来源

- [DeepFilterNet](https://github.com/Rikorose/DeepFilterNet)：Python 包 0.5.6，模型 DeepFilterNet3。
  MIT / Apache-2.0 双许可证。
- [ClearerVoice-Studio SpEx+](https://github.com/modelscope/ClearerVoice-Studio/tree/6b3774dc79c46ae8bed2a4fa5f706f0ac8c75c61/train/target_speaker_extraction)：
  使用上游独立模型文件，文件头保留 MIT 许可证声明。
- [SpEx+ 权重](https://huggingface.co/alibabasglab/log_wsj0-2mix_speech_SpEx-plus_2spk/tree/2b99a144297ac4d074bb9dcc4ce9734a7e8924fd)：
  固定 revision，使用 `last_best_checkpoint.pt`。正式分发前需核对模型卡和权重许可。
- [SpeechBrain 测试样本](https://github.com/speechbrain/speechbrain/tree/develop/tests/samples/ASR)：
  `spk1_snt1/2` 与 `spk2_snt1/2`，使用不同句子作参考；不是用户的声音样本。

模型权重和 Python 推理环境保存在本机试验目录，不包含在生产前端镜像中。

新增验证：64 项前端单元测试；浏览器实际采集 → 本机模型 → PCM 输出（三个模式均通过）；
处理流资源释放；参考录音上传/删除、无参考禁用目标模式；鉴权代理拒绝未登录与无效参考；
三个模式通过 Docker 后端访问本机模型。没有代替真实安卓和多成员公网通话验收。
