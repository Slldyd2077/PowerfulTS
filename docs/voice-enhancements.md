# 网页语音增强与频道管理

本次扩展保留默认的低延迟本地 RNNoise，增加可选 DeepFilterNet3 流式处理、SpEx+ 目标说话人提取及组合模式。DeepFilter 不可用时自动切到本地增强旁路，避免仅因模型中断而丢失麦克风输出。详见[模型原理与验证边界](audio-model-experiments.md)。

频道管理支持创建、编辑和删除空频道，移动在线成员，移除成员，以及管理所有成员音乐机器人的当前和默认频道。后台强制校验管理员权限；移除使用 TeamSpeak 服务器踢出操作，不删除账号、不封禁。详见[频道管理](channel-management.md)。

界面将辅助功能折叠，保留主要通话操作；使用实际 PCM 阈值突出显示说话成员，并记忆个人收听设置和设备偏好。手机设备选择与恢复能力取决于浏览器支持。

## 源码部署模型服务（Windows）

下列命令在仓库根目录执行，要求 Python 3.11 和 uv。模型服务是可选的；不安装时仍可使用本地 RNNoise。DeepFilter 的实时插件安装脚本针对 Windows x64。

```powershell
uv venv --python 3.11 data/audio-lab/.venv
uv pip install --python data/audio-lab/.venv/Scripts/python.exe -r scripts/audio-lab/requirements.txt
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/audio-lab/install-stream-runtime.ps1
```

分别在两个终端启动：

```powershell
data/audio-lab/.venv/Scripts/python.exe scripts/audio-lab/stream_server.py
data/audio-lab/.venv/Scripts/python.exe scripts/audio-lab/server.py
```

流式服务监听 127.0.0.1:18187，分段模型服务监听 127.0.0.1:18186。Docker 后端默认通过 host.docker.internal 访问。自定义地址可配置后端环境变量 VOICE_STREAM_WORKER_URL 和 VOICE_MODEL_WORKER_URL；Linux Docker 需配置 host-gateway 或使用合适的内部网络地址。不要公开这些本地工作服务。

源码部署默认将模型、录音和输出放在仓库 data/audio-lab；解压安装包的 source/ 布局沿用安装包 data/audio-lab。可通过 POWERFUL_TS_DATA_DIR 指定私有数据目录，安装脚本和 Python 工作服务需要使用同一设置。数据目录、环境凭据和模型权重不提交到仓库。

DeepFilterNet、ClearerVoice-Studio/SpEx+、模型权重和测试音频由各自上游发布，仓库不打包这些资产；使用和再分发前应核对各自的代码、权重与音频许可证。

## MusicBot 人声避让修复

避让逻辑属于独立的音乐引擎，升级 PowerfulTS 不会自动修复它。[引擎补丁](../deploy/tsmusicbot/voice-ducking-rms.patch)基于 453d2d124b9995034fe9cd46ebf2cad597382d42，将“收到包”改为解码 Opus 后检测实际 PCM，避免静音包持续触发。

阈值与页面说话状态一致：开始 RMS 0.0032、持续 RMS 0.002、保持 180 ms；不受个人播放增益影响。解码实现与网络时序不同可能产生少量显示时差。仅支持 Opus mono/stereo，其他编码不会触发。

```sh
git apply --check /path/to/PowerfulTS/deploy/tsmusicbot/voice-ducking-rms.patch
git apply /path/to/PowerfulTS/deploy/tsmusicbot/voice-ducking-rms.patch
```

在独立引擎项目完成构建和测试后再部署。已有其他补丁的构建须先核对基线，不能盲目叠加。[真实 Opus 验证脚本](../deploy/tsmusicbot/ducking-check.mjs)在 /app 布局的引擎容器中运行。

## 已知限制

- 手机后台、锁屏可能冻结网页或中断音频；当前恢复和旁路不能保证持续后台通话。
- iPad 加入失败仍需结合具体系统、浏览器和错误日志排查，本次未宣称解决。
- SpEx+ 与组合模式是约 2 秒分段的实验功能，要求参考录音，延迟明显高于流式 DeepFilter。
- DeepFilter 每人双向 PCM 净流量约 1.536 Mbps，额外占用服务器计算资源；当前限制最多四路、每账号一路。
- 普通声强阈值不能完全区分人声和同等强度的噪声。
