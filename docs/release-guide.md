# 安装、升级与 TSMusicBot 适配

## 下载安装

在 [GitHub Releases](https://github.com/Slldyd2077/PowerfulTS/releases) 选择预构建包。`amd64` 对应 Intel / AMD x64，`arm64` 对应 Apple Silicon / ARM64 Linux / ARM64 NAS；ZIP 适合 Windows，tar.gz 适合 Linux / macOS。所有包都运行 Linux 容器，必须先安装 Docker Desktop 或 Docker Engine + Compose v2.20 以上。32 位 ARM / x86 不在发布矩阵内。

预构建包已包含前后端镜像，不需要 Git、Python、Node.js，导入后不需要访问镜像仓库。`docker-source` 是联网构建备用包，首次安装会下载基础镜像、Python 和前端依赖。音乐、Steam 等在线功能仍需网络。

1. 用 `SHA256SUMS` 校验下载文件。Windows 使用 `Get-FileHash 文件名 -Algorithm SHA256`；Linux 使用 `sha256sum -c SHA256SUMS`；macOS 使用 `shasum -a 256 文件名`。
2. 解压到固定目录，执行 `powerfults.ps1 init`（Windows 可用 `powershell -NoProfile -ExecutionPolicy Bypass -File .\powerfults.ps1 init`），或 `sh powerfults.sh init`。已有 `backend.env` 不会被覆盖。
3. 编辑 `backend.env`，填写 TS3 ServerQuery 地址、凭据和虚拟服务器 ID，以及 TSMusicBot 地址、账号、密码、默认 bot ID。不要上传这个文件。特殊字符请按 dotenv 语法加引号。
4. Windows 双击 `start.cmd`；Linux / macOS 执行 `sh start.sh`。脚本检查 Docker、CPU 架构，导入镜像并等待服务启动。浏览器打开 `http://localhost:8080`。
5. 先登录 TS3，用网页的 TS 在线验证码注册自己的账号。首个成功注册的账号自动成为管理员；完成初始化后再开放远程访问。

默认只绑定本机。服务器管理员可通过 SSH 转发访问远端的首次安装：`ssh -L 8080:127.0.0.1:8080 用户@服务器`，随后浏览器访问 localhost。NAS 可从 SSH 执行启动脚本或用 Container Manager / Container Station 导入镜像和 Compose 文件。

## 上游引擎

PowerfulTS 的安装包不捆绑 TS3 服务端或 TSMusicBot。需预先部署：

- TS3：开启 ServerQuery，配置读取频道 / 客户端以及所需频道写操作权限。限制 Query 端口访问范围。
- TSMusicBot：[专用 fork v1.12.2](https://github.com/Slldyd2077/teamspeak-music-bot/tree/2c1fc74fce812caaaa79b5e8566a7dd617c1e9ad)。核对提交 `2c1fc74fce812caaaa79b5e8566a7dd617c1e9ad`，使用该源码构建，不依赖分支名称永远不变。

2026-10-03 对照的 [原版上游](https://github.com/ZHANGTIANYAO1/teamspeak-music-bot/tree/87fca6d8b7b770e1e01f8891059c99d53705cc08) 已有 v1.14.0 更新记录，但其音乐 API 使用全局 provider。PowerfulTS 使用 fork 的 per-bot 音源、多实例、网页通话中继与语音闪避，不能直接替换为原版镜像。fork 的 `/api/health` 版本字段尚为 1.12.1，包版本为 1.12.2，因此应核对源码提交和接口，而非只看健康端点的版本字符串。

| 能力 | 需要的 fork 接口 / 约定 |
| --- | --- |
| WebUI 登录 | `POST /api/session/login`，session cookie；写请求 Origin 对应当前引擎 |
| 多平台音乐与平台账号 | `/api/music/*`、`/api/auth/*` 带 `botId` |
| 网页麦克风 | `POST /api/player/:botId/live` |
| 频道下行语音 | `/api/voice/downlink/:botId` WebSocket |
| 入场音效 | 引擎可访问 PowerfulTS 的回调 origin，并设置 `POWERFUL_TS_ORIGIN` |

本次适配包括每客户端 Origin、REST / WebSocket 的单次 401 续期、并发续期去重、默认 botId 回退和混合平台歌单按歌曲保留音源。网络超时不会自动重放入队等写请求，避免重复操作。

## 容器网络与远程访问

上游在宿主机时，安装包默认使用 `host.docker.internal`；Linux 通过 `host-gateway` 映射。上游在其他机器时改成其内网地址。`127.0.0.1` 在后端容器中指后端容器本身。

需要局域网访问时，在安装目录创建 `.env`（Compose 配置，和后端的 `backend.env` 分开）：

```dotenv
POWERFULTS_BIND=0.0.0.0
POWERFULTS_PORT=8080
```

之后执行 `restart`。公网请使用 HTTPS 反向代理，麦克风在非 localhost 场景也需要 HTTPS。后端端口默认仍只绑定本机，正常 API 通过面板 `/api` 代理。

网页通话和入场音效要求 TSMusicBot 主动拉取音频。在 `backend.env` 设置 `LIVE_AUDIO_PUBLIC_URL` 为 TSMusicBot 实际可访问的面板 origin，例如 `http://192.168.1.10:8080` 或 `https://ts.example.com`；在 TSMusicBot 设置完全相同、没有路径和末尾斜杠的 `POWERFUL_TS_ORIGIN`。上游容器访问 `host.docker.internal:8080` 时，面板需要绑定可从容器访问的地址；Linux 上游容器也要配置 host-gateway。

监控、频道和游客面板部分是公开功能，开放面板意味着访客能看到部分服务器活动。可选的 NapCat / Steam 配置留空即可。

## 维护与升级

- 停止：Windows 双击 `stop.cmd`，Linux / macOS 执行 `sh stop.sh`。不会删除 `data/`。
- 日志 / 状态：`powerfults.ps1 logs|status` 或 `sh powerfults.sh logs|status`。
- 修改配置：使用 `restart`，重新读取后端配置。
- 升级：停止旧版本，备份旧目录 `backend.env` 和 `data/`，解压新版到新目录，复制这两个项目后启动。Compose 默认项目名为 `powerfults`，同一 Docker 主机默认只运行一个实例。
- 回退：停止新版，恢复升级前的数据库与音效备份，再启动旧版；不要假设旧代码能读取已迁移的新数据库。

容器 healthy 和 `/health` 表示面板进程已完成本地初始化，**不表示 TS3、音乐平台或真实音频链路已经连通**。安装后必须验证 TS 身份注册、频道列表、点歌，以及需要使用的网页通话。查看日志时不要把账号、cookie、token 或完整配置公开发到 Issue。

## 发布维护者

所有版本文件同步为同一版本后，推送 `vX.Y.Z` tag。`.github/workflows/release.yml` 验证版本、测试、严格构建 amd64 / arm64 镜像，解压安装包启动验证后再上传 ZIP、tar.gz 与 `SHA256SUMS`。workflow_dispatch 只产 CI artifacts，tag 才发布 GitHub Release。版本号不一致、镜像构建或安装烟测失败时应修复后再发布。

本地打包：`python scripts/build_release.py --tag v0.13.2 --output .release` 产源码备用包；预构建包额外指定 `--images images.tar --arch amd64` 或 `arm64`，其中 images.tar 必须来自同时包含 `powerfults-backend:0.13.2` 与 `powerfults-frontend:0.13.2` 的 docker save。打包采用白名单，不包含工作区数据库、真实环境变量、venv 或缓存。
