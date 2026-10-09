# PowerfulTS Docker 便捷安装包

支持 Windows、Linux、macOS 的 x64 / ARM64 主机，运行 Linux 容器。安装包中的 PowerfulTS 前后端已构建，无需安装 Git、Node.js 或 Python；TS3 或 TS6 服务端和 TSMusicBot 需自行安装和配置。

TS6 SSH Query 从 v1.0.0 起支持，旧 v0.13.2 安装包不包含此能力。配置变量仍使用兼容旧安装的 `TS3_*` 名称。[TS6 接入、主机公钥核验与验证范围](https://github.com/Slldyd2077/PowerfulTS/blob/v1.0.0/docs/ts6-server.md)。

音乐引擎需使用 [PowerfulTS 指定的 TSMusicBot 定制 fork v1.12.2](https://github.com/Slldyd2077/teamspeak-music-bot/tree/2c1fc74fce812caaaa79b5e8566a7dd617c1e9ad)，固定提交 `2c1fc74fce812caaaa79b5e8566a7dd617c1e9ad`。请按 [安装与适配说明](https://github.com/Slldyd2077/PowerfulTS/blob/main/docs/release-guide.md#上游引擎) 核对接口；原版上游不包含网页双向语音中继等定制接口。

## 选择安装包

- Intel / AMD x64：`docker-amd64.zip`（Windows）或 `docker-amd64.tar.gz`（Linux/macOS）。
- Apple Silicon / ARM64：`docker-arm64.zip`（Windows ARM）或 `docker-arm64.tar.gz`（Linux/macOS）。
- `docker-source` 包是源码构建备用包，需要联网下载依赖并在 Docker 内构建，不含预构建镜像。

安装 Docker Desktop（Windows/macOS）或 Docker Engine + Compose 插件（Linux）。Docker Compose 需 v2.20 以上，Windows Docker Desktop 切换到 Linux 容器。Windows ARM 的 Docker Desktop 支持取决于其当前版本，请优先确认 Docker 能运行 ARM64 Linux 容器。预构建包导入镜像后无需访问镜像仓库；音乐和第三方功能仍需要网络。

## 安装和启动

1. 核对发布页 `SHA256SUMS` 中的 SHA-256 校验值，解压到长期保存的目录（Windows 支持空格路径）。
2. Windows：PowerShell 执行 `powershell -NoProfile -ExecutionPolicy Bypass -File .\powerfults.ps1 init`；Linux/macOS：执行 `sh powerfults.sh init`。将生成 `backend.env`，已有文件不会被覆盖。
3. 编辑 `backend.env`：填写 `TS3_QUERY_USER` / `TS3_QUERY_PASSWORD`，以及 `TSMUSIC_USER` / `TSMUSIC_PASSWORD` / `TSMUSIC_BOT_ID`。TS3 raw Query 通常 TCP 10011；TS6 开启服务端 SSH Query 后，设置 `TS3_QUERY_TRANSPORT=ssh`、`TS3_QUERY_PORT=10022`、`TS3_QUERY_SSH_KNOWN_HOSTS=/app/data/known_hosts`，按 TS6 指南核验公钥并保存至安装目录 `data/known_hosts`。上游在宿主机上时使用默认 `host.docker.internal`；上游在其他机器上时改为其实际地址。机器人语音端口通常 UDP 9987，与 Query 端口分开。
4. Windows 双击 `start.cmd`；Linux/macOS 执行 `sh start.sh`。脚本自动导入镜像并等待前后端健康，成功后访问 <http://localhost:8080>。未配置上游时面板仍可启动，但登录、音乐和监控需上游连接正常。直接首次运行 `start` 也会生成配置并退出，填写后再运行即可。

`start.cmd` 仅对本次 PowerShell 进程使用 `ExecutionPolicy Bypass`，不修改系统策略。

## 停止、日志与升级

- 停止：Windows 双击 `stop.cmd`；Linux/macOS 执行 `sh stop.sh`。停止保留所有数据。
- 日志：Windows `powershell -NoProfile -ExecutionPolicy Bypass -File .\powerfults.ps1 logs`；Linux/macOS `sh powerfults.sh logs`。
- 修改配置后：Windows 执行同一 PowerShell 命令并使用 `restart`；Linux/macOS `sh powerfults.sh restart`。
- 数据保存在本目录 `data/`（数据库、上传音效等），配置在 `backend.env`。备份请先停止，然后同时备份两者。
- 升级：先停止旧版本并备份，解压新版本到新目录，再复制旧版本 `backend.env` 和 `data/`，最后启动新版本。旧版本可能无法读取新版本迁移后的数据库，回退时恢复备份。
- 所有安装包共用 Docker Compose 项目名 `powerfults`，一台 Docker 主机默认只运行一个实例。

## 远程访问和语音回连

默认面板和后端只绑定本机，避免意外公开面板。需要局域网访问时，可在安装目录创建 `.env`：

```dotenv
POWERFULTS_BIND=0.0.0.0
POWERFULTS_PORT=8080
# 后端默认仍只绑定本机，通常通过面板端口代理 /api 即可。
```

之后 `restart`。对公网开放时请先配置 HTTPS 反向代理。网页麦克风在非 localhost 场景需要 HTTPS。

TSMusicBot 需要主动拉取 PowerfulTS 的语音/音效，`LIVE_AUDIO_PUBLIC_URL` 必须是它实际能访问的面板或后端地址，且其进程 `POWERFUL_TS_ORIGIN` 需完全相同（不带路径）。例如同宿主机 TSMusicBot 容器需要 `http://host.docker.internal:8080`，此时面板需绑定可从容器访问的地址；Linux 上游容器也需配置 `host.docker.internal:host-gateway`。远程上游需使用局域网地址或 HTTPS 域名。不要把容器内的 `127.0.0.1` 当作宿主机地址。

安装包不会自动部署 TSMusicBot、TS3 或 TS6，也不会替用户创建上游账号。容器健康只确认面板初始化成功；还需验证 Query 数据、验证码注册、音乐及需要使用的网页双向语音。
