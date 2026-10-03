# TS6 服务端接入与验证范围

PowerfulTS 的原生数据层支持 raw TCP 与 SSH ServerQuery。TS6 使用 SSH Query，无需额外 Query 代理；音乐与网页通话仍交给指定的 TSMusicBot fork。`TS3_*` 配置和 `ts3_monitor` 模块名称为兼容旧安装保留，同样用于 TS6。

SSH 功能从 v1.0.0 起支持，请使用该版本或更新版本的源码 / 安装包。旧 v0.13.2 安装包不包含 SSH 客户端，不能只添加环境变量完成升级。

## 服务端准备

2026-10-03 对照 [TeamSpeak 官方 TS6 服务端仓库](https://github.com/teamspeak/teamspeak6-server) 与 [官方配置说明](https://github.com/teamspeak/teamspeak6-server/blob/main/CONFIG.md)。TS6 仍处于 Beta；部署时固定并核对具体版本，而非依赖 `latest` 永远保持相同行为。

在你已有的 TS6 配置中开启 SSH Query：

```dotenv
# 这些是 TS6 服务端变量，设置在 TS6 进程或容器中，不是 PowerfulTS 的 backend.env。
TSSERVER_QUERY_SSH_ENABLED=true
TSSERVER_QUERY_SSH_PORT=10022
```

官方配置示例默认关闭 SSH Query。准备专用 Query 账号与密码，授予频道 / 在线客户端读取、验证码私聊及使用功能所需权限。SSH 登录直接使用该 Query 账号密码；不要把操作系统 SSH 账号或 TS6 HTTP API key 填到这里。限制该 TCP 端口的访问来源，并核对服务端 Query 防洪策略。

| 连接 | 通常端口 | 用途 |
| --- | --- | --- |
| SSH ServerQuery | TCP 10022 | PowerfulTS 监控、认证、好友和频道管理 |
| TS3 raw ServerQuery | TCP 10011 | 兼容已有 TS3 配置；明文连接只用于可信内网或安全隧道 |
| TeamSpeak 语音 | UDP 9987 | TSMusicBot 音乐 bot、网页通话 bot；以虚拟服务器实际端口为准 |

SSH Query 10022 与宿主机管理 SSH 22 是不同服务。若 TS6 在 Docker 中运行，需发布或通过容器网络连通 SSH Query 和 UDP 语音端口；无需把 Query 对公网开放。

## PowerfulTS 配置

源码部署编辑 `backend/.env`；Release 编辑 `backend.env`：

```dotenv
TS3_HOST=ts.example.com
TS3_QUERY_TRANSPORT=ssh
TS3_QUERY_PORT=10022
TS3_QUERY_USER=专用Query账号
TS3_QUERY_PASSWORD="你的Query密码"
TS3_SID=1
TS3_QUERY_SSH_KNOWN_HOSTS=/app/data/known_hosts
```

仅当没有显式设置端口时，`raw` 默认 10011、`ssh` 默认 10022。从旧模板复制的配置通常已经含 `TS3_QUERY_PORT=10011`，切换时必须一并修改。改完配置后重启后端；源码 Docker 部署先重新构建镜像。

Docker 的 `TS3_HOST` 必须从后端容器可达。宿主机可用 `host.docker.internal`；同一 Docker 网络内可用 TS6 服务名；其他机器用其内网地址。容器中的 `127.0.0.1` 指容器自己。

## 核验 SSH 主机公钥

后端读取运行用户的系统 known_hosts 与 `TS3_QUERY_SSH_KNOWN_HOSTS` 指定文件，严格拒绝未知或已变更的主机公钥；不会自动接受首次连接的公钥。Docker 容器不会自动继承宿主机的 `~/.ssh/known_hosts`。

1. 从管理员已验证的服务器控制台或可信管理连接取得 **TS6 Query 服务**主机公钥的 SHA-256 指纹。官方配置中 SSH RSA key 文件为 `ssh_host_rsa_key`，以该服务器实际配置为准。在服务器上可执行 `ssh-keygen -y -f /实际路径/ssh_host_rsa_key | ssh-keygen -lf -`。它只提取公钥并计算指纹；不要复制或公开私钥，也不要误用宿主机 SSH 22 的 key。
2. 在安装端收集候选公钥，例如 `ssh-keyscan -p 10022 -t rsa ts.example.com`，并保存到临时文件 `known_hosts.pending`。`ssh-keyscan` **只能收集，不能证明服务器可信**。运行 `ssh-keygen -lf known_hosts.pending`，与步骤 1 的可信指纹逐项核对；不一致则停止并排查。
3. 核对通过后保存为 known_hosts。记录中的主机名必须与 `TS3_HOST` 完全一致，非默认 SSH 端口写为 `[ts.example.com]:10022`。如果安装端只能扫描服务器真实 IP，但容器使用 `host.docker.internal` 或 Docker 服务名，应在核对完成后把记录首字段改为 `[host.docker.internal]:10022` 或相应服务名，保留已核验的 key 类型和公钥内容。
4. Release 把文件放到安装目录 `data/known_hosts`，对应容器 `/app/data/known_hosts`。源码 Compose 使用命名数据卷：后端容器启动后可执行 `docker cp known_hosts powerfults-backend:/app/data/known_hosts`，再重启后端。手动运行时填本机真实文件路径，或使用该运行用户的系统 known_hosts。

文件内容为 OpenSSH known_hosts 的文本格式；Windows 保存时使用 ASCII 或 UTF-8 无 BOM，避免 PowerShell 默认 UTF-16。只保存公钥，不保存私钥或账号密码。备份安装目录时一并保留 known_hosts；若服务端重建或管理员轮换主机 key，先重新通过可信渠道核验，再更新记录。

## 音乐与网页通话配置

使用 [Release 指南指定的 TSMusicBot fork](release-guide.md#上游引擎)，在音乐 bot 中配置 TS6 的主机、**UDP 语音端口**、服务器连接密码和目标频道。PowerfulTS 的 `TS3_SID` 应指向同一个虚拟服务器。

网页通话实例沿用音乐 bot 的服务器连接配置，包括服务器连接密码；加入加密频道时仍需单独提供频道密码。指定 fork 已通过通用 TeamSpeak 客户端实现 TS6 连接能力，不需要向其 bot API 添加 `serverProtocol` 字段。Query 传输类型也不会改变 bot 的语音协议或端口。

公网网页麦克风需要 HTTPS；TSMusicBot 反向拉取音频的 `POWERFUL_TS_ORIGIN` 与面板的 `LIVE_AUDIO_PUBLIC_URL` 设置见 [语音回连说明](release-guide.md#容器网络与远程访问)。

## 兼容与验收矩阵

| 服务端 / 能力 | 接入方式 | 验证边界 |
| --- | --- | --- |
| TS3 监控 / 认证 / 好友 | raw TCP；保留已有默认配置 | 保留既有 Query 命令与调用方；SSH 改动须同时通过 raw 回归 |
| TS3 SSH Query | `ssh` + 可信 known_hosts | 使用同一 SSH 传输；本次未另起 TS3 SSH 服务端实测 |
| TS6 Query 登录与频道管理 | 原生 `ssh` + 可信 known_hosts | 官方 Docker `6.0.0-beta13.1` 实测版本读取、登录认证、`use sid`、中文与管道字符转义的频道创建 / 读取 / 编辑 / 删除通过 |
| TS6 监控与验证码私聊 | SSH Query + 现有数据层 | 同版本实测监控连接与轮询、频道树、`clientlist`、真实客户端 UID 识别通过；`ts3_auth.send_verify_code` 发出的私聊由客户端实际收到，尚未验收完整网页注册流程 |
| Docker 后端连接 TS6 | 容器网络 + 可信 known_hosts | 实际后端容器 `/health` 正常、`/api/stats` 为 `monitor_running=true` 和 `serverquery_transport=ssh`、`/api/channels` 可读通过 |
| TS6 客户端入服 | 指定 fork 的 `@honeybbq/teamspeak-client` + UDP | 同版本使用实际 SDK 客户端完成握手上线，Query 可识别该客户端；这只验证入服，不验证声音 |
| TS6 音乐与网页双向语音 | 指定 fork + UDP 语音 | 未播放音乐，未实测浏览器 PCM / Opus 上下行或物理扬声器；仍需真实播放与麦克风 / 扬声器验收 |

安装后依次确认频道与在线用户、验证码注册及需要的频道操作，再播放一首歌。网页通话需另测浏览器上行和下行、服务器密码、频道密码、切换频道、断线重连。Query 可读、容器 healthy 或 `/health` 正常均不能替代音乐和真实音频验收。

## 排错

- 连接被拒绝或超时：检查服务端 SSH Query 是否显式开启，TCP 端口映射、防火墙及容器地址是否正确。TS6 HTTP Query 与 SSH Query 是不同传输，不能把 10080 / 10443 用作 SSH 端口。
- unknown host / host key mismatch：检查 known_hosts 文件路径与读权限、`TS3_HOST` 对应记录及端口；公钥变更需管理员先核验，不能通过关闭校验处理。
- 认证失败：检查 Query 账号密码；这是 TS6 Query 服务的凭据，不是 SSH 22 的系统账号。
- 无频道 / 私聊失败：检查 `TS3_SID` 及 Query 账号权限、目标用户昵称和服务器防洪限制。
- 短时间连续 SSH 连接出现 banner EOF：本次官方 TS6 `6.0.0-beta13.1` 两次快速连接出现此现象，间隔约 3 秒后重连成功。检查服务器限速日志；必要时仅将可信后端的实际出口 IP 加入 `TSSERVER_QUERY_ALLOW_LIST` 指定的 Query allowlist 文件，不关闭暴力破解保护，也不对全网豁免。
- Query 正常但 bot 连不上：检查 TSMusicBot 使用的 UDP 语音端口、服务器连接密码和指定 fork；Query 10022 不用于音频。
- 网页无声音：单独检查 fork 双向语音接口、HTTPS、浏览器权限和音频回连地址，并对照 [语音实现与校验记录](web-voice-downlink-spec.md)。
