<p align="center">
  <img src="assets/banner.png" alt="PowerfulTS — TeamSpeak 管理面板" width="800" />
</p>

<p align="center">
  <strong>TeamSpeak 服务器管理面板</strong> · 独立前后端架构 · 原生 TS 直连 + TSMusicBot 音乐引擎
</p>

<p align="center">
  <a href="https://vuejs.org/" target="_blank"><img alt="Vue" src="https://img.shields.io/badge/Vue-3.5-42b883?logo=vuedotjs&logoColor=white"></a>
  <a href="https://vite.dev/" target="_blank"><img alt="Vite" src="https://img.shields.io/badge/Vite-8-646CFF?logo=vite&logoColor=white"></a>
  <a href="https://fastapi.tiangolo.com/" target="_blank"><img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-0.115+-05998B?logo=fastapi&logoColor=white"></a>
  <a href="https://www.python.org/" target="_blank"><img alt="Python" src="https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white"></a>
  <img alt="Docker" src="https://img.shields.io/badge/Docker-一键部署-2496ED?logo=docker&logoColor=white">
  <img alt="TS3" src="https://img.shields.io/badge/TS3-支持-2580C3?logo=teamspeak&logoColor=white">
  <img alt="TS6 SSH Query" src="https://img.shields.io/badge/TS6-SSH_Query-2580C3?logo=teamspeak&logoColor=white">
  <a href="https://github.com/sealdong/napcat-dotnet" target="_blank"><img alt="NapCat" src="https://img.shields.io/badge/NapCat-QQ通知-12B1E9?logo=tencentqq&logoColor=white"></a>
  <img alt="License" src="https://img.shields.io/badge/License-MIT-blue?logo=mit&logoColor=white">
</p>

---

## 🎬 宣传视频

https://github.com/user-attachments/assets/3761cb43-a68d-4768-b6d0-dd5860de7902

[▶ 在 Bilibili 观看高清版宣传视频与部署教程](https://www.bilibili.com/video/BV1f3He6EEZS/)

---

## 📖 简介

**PowerfulTS** 是一个面向 TeamSpeak（TS3 / TS6）服务器的 Web 管理面板，采用**前后端分离**架构。
后端通过 raw TCP 或 SSH 原生直连 TS3 / TS6 ServerQuery 提供服务器数据，并将音乐与点播能力委托给 TSMusicBot 多平台引擎，
让一个 Web 面板即可聚合呈现服务器的在线状态、用户、频道与多媒体能力。

其中**网页通话**让成员不装 TeamSpeak 客户端也能直接在浏览器里收听频道并发言。

> 🍴 **TSMusicBot 专用分支**：本项目的音乐引擎与网页通话中继依赖 [TSMusicBot](https://github.com/Slldyd2077/teamspeak-music-bot) 的专用定制分支 [`merge/upstream-v1.12`](https://github.com/Slldyd2077/teamspeak-music-bot/tree/merge/upstream-v1.12)——per-bot 多实例架构、双向 Opus 语音中继、语音闪避（含网页通话触发）等接口仅存在于该分支。**部署时必须使用该分支构建的 TSMusicBot**（v1.12.1+），上游 [ZHANGTIANYAO1/teamspeak-music-bot](https://github.com/ZHANGTIANYAO1/teamspeak-music-bot) 的原版不支持这些能力。

> 💡 **跨平台 Release**：从 [Releases](https://github.com/Slldyd2077/PowerfulTS/releases) 下载 x64 或 ARM64 安装包，解压、配置后启动。预构建包无需 Git / Python / Node.js，需要 Docker Engine 与 Compose v2；支持 Windows、macOS、Linux 和支持 Docker 的 NAS。详见 [安装与升级指南](docs/release-guide.md)。

> **NAS 直接拉取镜像**：也可使用 [NAS Compose 模板](docs/nas.md)，无需下载源码或安装包。首次镜像发布完成并公开后即可匿名拉取。

> **TS6 服务端接入（v1.0.0 起）**：使用 `TS3_QUERY_TRANSPORT=ssh` 连接 TS6 的 SSH ServerQuery（通常 TCP 10022），并配置可信主机公钥。`TS3_*` 名称为兼容旧配置保留，TS6 同样使用这些变量。请升级到 v1.0.0 或更新版本的源码 / 安装包；旧 v0.13.2 不包含 SSH。[TS6 配置与验证范围](docs/ts6-server.md)。

> ⚠️ **早期测试版本**：本项目目前处于**早期开发与测试阶段**，功能仍在快速迭代中，存在诸多 Bug。如遇问题，欢迎[提交 Issue](https://github.com/Slldyd2077/PowerfulTS/issues) 反馈。

---

## ✨ 功能特性

| 模块 | 状态 | 能力 |
|------|:----:|------|
| 👤 账户 | ✅ | 登录 / 注册（QQ + TS 昵称绑定 + 验证码） |
| 🎙️ **网页通话** | ✅ | **不装 TS 客户端，直接在网页收听频道并发言**：以自己的昵称接入、浏览并切换频道（支持频道密码）、按人调节音量、麦克风增益与输入输出设备选择 |
| 🖥️ 一起看 / 屏幕共享 | ✅ | 每个网页通话频道一个画面，首位分享者为房主、支持转交；视频同步默认等待缓冲并允许成员暂停，网页视频通过配套扩展同步进度，屏幕 / 窗口使用 WebRTC 共享 |
| 👥 在线用户 | ✅ | 昵称 · 游戏 · 所在频道 · 在线时长 · 各游戏人数分布 |
| 📡 频道列表 | ✅ | 频道树浏览 · 各频道在场成员 |
| 🎵 音乐中心 | ✅ | 搜索 · 点歌 · 队列 · 音量 · 播放模式 · 语音闪避（有人说话自动压低音乐）（网易云 / QQ / 酷狗 / B 站） |
| 📡 电脑音频直播 | ✅ | 用户主动选择应用/屏幕并授权后，通过音乐机器人实时共享音频 |
| 🔐 平台账号 | ✅ | 网易云 / QQ / 酷狗 / Bilibili 扫码登录（解锁 VIP 曲库、个人歌单、番剧与视频点播） |
| 🎮 Steam | ✅ | OpenID 绑定 · 好友在线状态 · 共同游戏 · 游戏时长排行；TS 在线列表优先显示 Steam 当前游戏 |
| 📱 QQ通知 | ✅ | 通过 NapCat/OneBot 实现QQ好友上线通知（需配置 NapCat） |
| 🤝 社交 | ✅ | 好友添加 / 删除 / 在线状态 · 好友申请接受 / 拒绝 |
| 📱 移动端 | ✅ | 手机 / 平板自适应（抽屉导航 · 响应式布局 · 触屏长按操作） |

> 音乐、点播、社交等功能**需注册账号后使用**；游客会获得两小时临时身份，仅可浏览管理面板和使用网页通话。浏览器会自动在请求头注入会话 Token。

---

## 📸 界面预览

> 以下截图取自一台本地搭建的 **演示 TS3 服务器**（频道与在线成员均为演示数据），并非任何真实服务器的用户信息。

### 服务器监控

在线人数、游戏分布、在线用户列表与频道树，每 5 秒自动刷新。

<p align="center">
  <img src="assets/screenshots/dashboard.png" alt="服务器监控 — 在线用户 · 游戏分布 · 频道树" width="900" />
</p>

### 音乐控制

多平台搜索（网易云 / QQ / 酷狗 / B 站）、播放队列、音量与播放模式，右侧管理多个 TS Bot 实例。

<p align="center">
  <img src="assets/screenshots/music.png" alt="音乐控制 — 搜索 · 点歌 · 队列 · 播放器" width="900" />
</p>

### 网页通话

不装 TeamSpeak 客户端，直接在浏览器收听频道并发言；右侧可浏览频道与在场成员，带 🔒 的频道需要密码。

<p align="center">
  <img src="assets/screenshots/voice.png" alt="网页通话 — 频道浏览 · 设备与增益设置" width="900" />
</p>

### 登录页

左侧音频频谱随开屏背景音乐律动，支持以游客身份浏览管理面板；进入游客模式时会由服务端分配随机临时昵称，也可直接使用网页通话。

<p align="center">
  <img src="assets/screenshots/login.png" alt="登录页 — 音频频谱开屏" width="900" />
</p>

### 移动端

手机 / 平板自适应：底部标签栏导航、单栏布局、触摸友好的操作按钮。

<p align="center">
  <img src="assets/screenshots/mobile-dashboard.png" alt="移动端 — 服务器监控" width="260" />
  <img src="assets/screenshots/mobile-music.png" alt="移动端 — 音乐控制" width="260" />
  <img src="assets/screenshots/mobile-voice.png" alt="移动端 — 网页通话" width="260" />
</p>

---

## 🧱 技术栈

| 层 | 技术 |
|----|------|
| **前端** | Vue 3 · Vite 8 · Element Plus · Pinia · Vue Router · TypeScript · Axios |
| **后端** | FastAPI · Uvicorn · httpx · SQLAlchemy (async) · aiosqlite · python-dotenv |
| **数据层** | SQLite（默认零依赖文件库，可切 PostgreSQL/MySQL） |
| **部署** | Docker · Docker Compose（跨平台一键部署） |
| **运行时** | Node.js ≥ 22.12 · Python ≥ 3.11（仅手动部署需要；Docker 已内置） |

---

## 🏗️ 系统架构

PowerfulTS 后端原生直连 TS3 / TS6 ServerQuery，同时代理 TSMusicBot 的多媒体能力；对前端只暴露 `/api/*` 一个入口。Query 管理连接与机器人 UDP 语音连接分别配置。

```
                          ┌──▶ TS3 / TS6 ServerQuery     监控 · 用户 · 频道 · 好友 · 认证（原生直连）
                          │    raw TCP :10011 / SSH :10022
浏览器  ▶  Vue 3 SPA (:5173)  ▶  FastAPI (:8001)  ──┤
          (Vite 代理 /api)     原生数据层 + 代理网关   └──▶ TSMusicBot (:3000)            音乐搜索 · 点歌 · 播放控制 · B 站点播
                                                                 （网易云 / QQ / B 站 多平台 · UDP 语音通常 :9987）
```

- `/api/stats`、`/api/channels` → 原生 TS3 / TS6 ServerQuery（概览 / 频道，直读）
- `/api/auth/*`、`/api/friends/*` → 原生 TS3 / TS6 ServerQuery + SQLite（认证 / 好友 / 账户）
- `/api/music/*` → TSMusicBot 音乐引擎（搜索 / 播放控制 / 平台账号登录）
- `/api/music/voice/*` → 网页通话（浏览器 ⇄ TSMusicBot 的双向 Opus 中继 + 频道浏览/切换）
- `/api/steam/*` → Steam OpenID 绑定与好友 / 游戏数据
- `/api/bili/*` → Bilibili 浏览与点播（点播由 TSMusicBot 多平台引擎驱动）+ 图片代理

> 监控、认证、社交等模块使用 ServerQuery 直连 + SQLite 数据层；TS6 SSH 接入无需部署额外 Query 代理。TS6 的音乐播放与网页双向语音仍需在目标服务器验收，不能仅凭 Query 连通判定通过。

---

## 📁 项目结构

```
PowerfulTS/
├── assets/                      # 项目 LOGO、banner 与界面截图（screenshots/）
├── backend/                     # FastAPI 后端 — 原生 TS3 / TS6 Query 直连 + 代理网关
│   ├── app/
│   │   ├── core/config.py           # 配置：TSMusicBot / TS3、TS6 共用的 TS3_* 凭据
│   │   ├── models/                  # SQLAlchemy 模型（账号 / bot 归属 / 歌单 …）
│   │   ├── routers/                 # music(含 voice) / bilibili / monitor / auth / friends / steam / admin
│   │   ├── services/                # TSMusicBot 客户端 · TS 监控 · 语音中继 · 通话 bot · Steam …
│   │   └── main.py                  # 应用入口（原生数据层 + TS 监控 + 多媒体代理）
│   ├── tests/                   # 后端测试
│   ├── Dockerfile               # 后端镜像
│   ├── .env.example             # 配置模板（复制为 .env 填写）
│   └── requirements.txt
├── frontend/                    # Vue 3 前端
│   ├── src/
│   │   ├── components/voice/        # 网页通话面板与频道浏览器
│   │   ├── workers/                 # AudioWorklet：抖动缓冲 + 多人混音 + 每人增益
│   │   └── views/                   # 各页面
│   ├── Dockerfile               # 多阶段构建（node 编译 → nginx 托管）
│   ├── nginx.conf               # 静态托管 + /api 反向代理
│   └── vite.config.ts
├── docs/                        # 设计与校验文档
├── docker-compose.yml           # 从源码构建（backend + frontend）
├── docker-compose.nas.yml       # NAS 直接拉取镜像，无需源码 / .env
├── .github/workflows/docker-publish.yml # GHCR 多架构镜像发布
└── README.md
```

---

## 🚀 快速开始

### 方式一：下载 Release（推荐）

1. 安装并启动 Docker Desktop（Windows / macOS），或 Docker Engine + Compose v2（Linux / NAS）。Windows 必须使用 Linux containers。
2. 从 [Releases](https://github.com/Slldyd2077/PowerfulTS/releases) 下载对应 CPU 的预构建包；普通 Intel / AMD 选 `amd64`，Apple Silicon / ARM64 NAS 选 `arm64`。Windows 优先 ZIP，Linux / macOS 优先 tar.gz。
3. 解压到固定目录，Windows 双击 `start.cmd`，Linux / macOS 执行 `sh powerfults.sh start`。首次运行生成配置后会停止，按提示编辑 `backend.env` 填入 TS3 / TS6 ServerQuery 与 TSMusicBot 凭据，再次运行启动。TS6 SSH 接入需先按 [TS6 指南](docs/ts6-server.md) 准备可信主机公钥，并使用包含 SSH 适配的版本。
4. 打开 `http://localhost:8080`。先通过 TS 身份验证码注册自己的管理员账号，再按安装指南开启局域网 / 公网访问。

`data/` 与 `backend.env` 必须保留。预构建包包含镜像，可用 `docker load` 离线导入；TSMusicBot、TS3 或 TS6 服务端需另外部署。源码包首次启动需要联网构建。[详细安装、升级与排错](docs/release-guide.md)。

### 方式二：NAS / 服务器直接拉取镜像

在 NAS 的 Compose 项目中粘贴 [`docker-compose.nas.yml`](docker-compose.nas.yml)，直接修改其中的 TeamSpeak / TSMusicBot 地址与账号密码后部署。无需下载源码、编译镜像或准备 `.env` 文件。默认访问 `http://NAS的IP:8080`，数据保存在项目的 `data` 目录。

支持 x86_64 / ARM64，TeamSpeak 与专用分支的 TSMusicBot 需已部署。**首次使用前，维护者需完成 GHCR 镜像发布并设为 Public**；完整步骤、服务地址配置、更新与备份见 [NAS 安装说明](docs/nas.md)。

通过 SSH 启动（先修改配置并创建 `data` 目录）：

```bash
docker compose -f docker-compose.nas.yml up -d
```

### 方式三：从源码构建 Docker 镜像

适用于 Linux 服务器、Windows、macOS、NAS 等所有支持 Docker 的平台。**无需本地安装 Python / Node.js。**

#### 1. 前提条件

- 已安装 [Docker](https://docs.docker.com/get-docker/) 与 [Docker Compose](https://docs.docker.com/compose/install/)（Docker Desktop 自带）
- 上游服务已就绪（见 [🔌 接入上游服务](#-接入上游服务)）：
  - **TSMusicBot**（音乐 / 点播引擎，默认 :3000；须使用 [专用分支 `merge/upstream-v1.12`](https://github.com/Slldyd2077/teamspeak-music-bot/tree/merge/upstream-v1.12) 构建，v1.12.1+）
  - **TS3 或 TS6 服务端**（TS3 raw Query 通常 TCP :10011；TS6 开启 SSH Query，通常 TCP :10022；机器人语音通常 UDP :9987）

#### 2. 配置环境变量

```bash
cd backend
cp .env.example .env          # Windows PowerShell: copy .env.example .env
```

编辑 `backend/.env`，填入 TSMusicBot 与 TS3 / TS6 凭据（**关键：容器内地址需特殊配置，见下方说明**）：

```ini
# TSMusicBot 音乐引擎
TSMUSIC_URL=http://host.docker.internal:3000   # ← 容器访问宿主机服务，见下方「容器网络地址」
TSMUSIC_USER=你的TSMusicBot账号
TSMUSIC_PASSWORD=你的TSMusicBot密码
TSMUSIC_BOT_ID=你的bot实例id

# TeamSpeak ServerQuery（下例为 TS3 raw TCP）
TS3_HOST=host.docker.internal                  # ← 同上
TS3_QUERY_TRANSPORT=raw
TS3_QUERY_PORT=10011
TS3_QUERY_USER=你的ServerQuery账号
TS3_QUERY_PASSWORD=你的ServerQuery密码
TS3_SID=1

# CORS（生产部署改为实际访问域名/端口）
CORS_ORIGINS=http://localhost:8080
```

TS6 改为 `TS3_QUERY_TRANSPORT=ssh`、`TS3_QUERY_PORT=10022`、`TS3_QUERY_SSH_KNOWN_HOSTS=/app/data/known_hosts`，并先完成[主机公钥核验](docs/ts6-server.md#核验-ssh-主机公钥)。只改 transport 不会覆盖 `.env` 里显式填写的旧端口。源码 Compose 使用命名数据卷，公钥文件放入该卷的 `/app/data/known_hosts`；Release 使用安装目录的 `data/known_hosts`。

> **🐳 容器网络地址说明**（Docker 部署必读）
>
> 容器内的 `127.0.0.1` 指向容器自身，**不是宿主机**。因此当 TSMusicBot / TS3 / TS6 运行在宿主机时：
> - **Windows / macOS（Docker Desktop）**：用 `host.docker.internal`（如上例）。
> - **Linux**：本项目 Compose 已添加 `host.docker.internal:host-gateway` 映射；也可使用**宿主机内网 IP**（如 `192.168.1.100`）。
> - 若 TSMusicBot 也用 Docker 且在同一 compose 网络，则用服务名（如 `http://tsmusic:3000`）。

#### 3. 启动

```bash
docker compose up -d --build
```

#### 4. 访问

打开 `http://localhost:8080`（默认端口）即可使用面板。

#### 5. 常用命令

```bash
docker compose logs -f          # 查看实时日志
docker compose restart          # 重启
docker compose down             # 停止并移除容器（数据保留）
docker compose down -v          # 停止并删除数据（⚠️ 清空 SQLite）
docker compose up -d --build    # 代码更新后重新构建并启动
```

#### 6. 修改端口

面板默认 `8080`。若被占用，编辑 `docker-compose.yml`：

```yaml
frontend:
  ports:
    - "3000:80"                 # 改为 3000:80 → 访问 http://localhost:3000
```

---

### 方式四：手动部署（开发 / 无 Docker 环境）

#### 1. 前提条件

- Node.js ≥ 22.12、pnpm 10.27.0
- Python ≥ 3.11、[uv](https://docs.astral.sh/uv/)（推荐）或 pip
- 上游服务运行中：TSMusicBot（:3000）、TS3 或 TS6 服务端（raw Query TCP :10011 / SSH Query TCP :10022）

#### 2. 后端

```bash
cd backend
cp .env.example .env          # 编辑 .env 填入 TSMusicBot / TS3、TS6 凭据
uv sync                       # 安装依赖（或 pip install -r requirements.txt）
uv run uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

启动后访问 `http://localhost:8001/health` 应返回 `{"status":"ok","mode":"native-transition", ...}`。

#### 3. 前端

```bash
cd frontend
pnpm install
pnpm dev                      # 开发模式 → http://localhost:5173
```

Vite 已配置 `/api` 代理到后端 :8001，开发时直接访问 `http://localhost:5173`。

#### 4. 生产构建

```bash
cd frontend
pnpm build                    # 输出到 dist/，可用任意静态服务器（nginx）托管并反代 /api → :8001
```

---

## ⚙️ 环境变量详解

后端通过 `backend/.env` 读取配置（**含凭据，已被 `.gitignore` 忽略，切勿提交**）。从 `.env.example` 复制后填写：

| 变量 | 必填 | 说明 | 默认值 |
|------|:----:|------|--------|
| `TSMUSIC_URL` | ✅ | TSMusicBot 地址（容器内用 `host.docker.internal`） | `http://127.0.0.1:3000` |
| `TSMUSIC_USER` | ✅ | TSMusicBot WebUI 登录账号 | — |
| `TSMUSIC_PASSWORD` | ✅ | TSMusicBot WebUI 登录密码 | — |
| `TSMUSIC_BOT_ID` | ✅ | 默认操作的 bot 实例 id | — |
| `LIVE_AUDIO_PUBLIC_URL` | — | TSMusicBot 可访问的 PowerfulTS 后端地址；跨 Docker 网络时配置 | 从当前请求推断 |
| `TS3_HOST` | ✅ | TS3 / TS6 服务端地址（容器内用 `host.docker.internal`） | `127.0.0.1` |
| `TS3_QUERY_TRANSPORT` | — | `raw` 或 `ssh`；TS6 使用 SSH Query | `raw` |
| `TS3_QUERY_PORT` | — | ServerQuery TCP 端口；显式值优先于 transport 默认值 | raw `10011` / ssh `10022` |
| `TS3_QUERY_SSH_KNOWN_HOSTS` | SSH 时需可信公钥 | known_hosts 文件路径；也读取运行用户的系统 known_hosts，拒绝未知或变更的主机公钥 | 留空；Docker 推荐 `/app/data/known_hosts` |
| `TS3_QUERY_USER` | ✅ | ServerQuery 账号 | — |
| `TS3_QUERY_PASSWORD` | ✅ | ServerQuery 密码 | — |
| `TS3_SID` | ✅ | 虚拟服务器 ID | `1` |
| `DATABASE_URL` | — | 数据库连接串（可切 PostgreSQL/MySQL） | `sqlite+aiosqlite:///./data/powerfults.db` |
| `CORS_ORIGINS` | — | 允许的前端来源（逗号分隔，生产改实际域名） | `http://localhost:5173` |
| `NETEASE_API_URL` | — | 网易云 API（可选，TSMusicBot 已内置） | `http://127.0.0.1:3000` |

**获取 TSMusicBot 凭据：** 在 TSMusicBot WebUI（默认 `http://localhost:3000`）登录所用的账号密码与 bot 实例 id，填入 `TSMUSIC_*`；后端会自动登录并代理其音乐 API，用户只与 PowerfulTS 交互。

**获取 ServerQuery 凭据：** 在 TS3 / TS6 服务端创建专用 Query 账号（监控需 `clientlist` / `channellist` 读权限，注册验证码需私聊权限）。TS6 要开启 SSH Query 并核验主机公钥，详见 [TS6 指南](docs/ts6-server.md)。配置变量的 `TS3_` 前缀不限制服务端版本。

---

## 🔌 接入上游服务

PowerfulTS 本身不含 TeamSpeak 服务端与音乐引擎，需接入两个上游：

### TSMusicBot（音乐 / 点播引擎）

- 项目：[ZHANGTIANYAO1/teamspeak-music-bot](https://github.com/ZHANGTIANYAO1/teamspeak-music-bot) —— TS3/TS6 多平台音乐机器人（网易云 / QQ / B 站）
- 自行部署后，将 `TSMUSIC_URL` 指向其地址，并填入账号密码与 bot id
- 它同时提供音乐搜索、播放控制与 **B 站点播**（PowerfulTS 的 `/api/bili/*` 即委托其 `platform=bilibili` 能力）

### TS3 / TS6 服务端（监控 / 认证数据源）

- TS3：开启 raw **ServerQuery**（通常 TCP :10011），使用 `TS3_QUERY_TRANSPORT=raw`；也可连接已开启的 SSH Query
- TS6：开启 **SSH ServerQuery**（官方配置默认关闭，通常 TCP :10022），使用 `TS3_QUERY_TRANSPORT=ssh` 并准备可信主机公钥；配置示例与官方来源见 [TS6 指南](docs/ts6-server.md)
- 创建专用账号填入 `TS3_QUERY_USER` / `TS3_QUERY_PASSWORD`，并用 `TS3_SID` 选择虚拟服务器
- PowerfulTS 通过 ServerQuery 长连接轮询在线用户 / 频道 / 游戏状态
- TSMusicBot 连接相同虚拟服务器的 **UDP 语音端口**（通常 :9987），其 bot 配置中的 port 不可填 Query 的 10022

> 两者均可运行在宿主机、独立容器或同一 compose 网络中，按 [容器网络地址说明](docs/release-guide.md#容器网络与远程访问) 或 [NAS 服务地址与回调说明](docs/nas.md#服务地址与回调)配置连接地址即可。

---

## 📱 移动端适配

面板支持手机 / 平板访问，采用渐进式响应式布局，**桌面端（≥1100px）体验完全不变**：

- **抽屉式导航**：窄屏下侧边栏收起为抽屉，顶栏汉堡按钮唤出；点击菜单跳转后自动收起。
- **三级响应式断点**：`1100px`（平板：多栏→单栏）/ `768px`（移动端主断点）/ `480px`（小屏精简），由 `useBreakpoint` 组合式函数统一管理。
- **触屏优化**：操作按钮在触屏设备常显；好友列表支持**长按删除**（桌面端仍为右键删除）；关键按钮触摸目标 ≥44px。
- **可访问性**：允许双指缩放（遵循 WCAG），仅禁用双击缩放以避免误触。

> 手机访问直接用浏览器打开面板地址即可。

---

## 🎙️ 网页通话

不安装 TeamSpeak 客户端，直接在浏览器里收听频道并发言。注册成员点「加入通话」后，PowerfulTS 会以**自己的昵称**开一个专属通话身份进入服务器；游客则使用服务端随机分配的 `游客-XXXXXX` 临时昵称。挂断即离开，游客身份对应的临时通话实例会直接删除——它和音乐机器人相互独立，不会出现在音乐控制的实例列表里，也不影响点歌。

| 能力 | 说明 |
|------|------|
| 收听 + 发言 | 一个按钮同时开启，进去后可随时静音只听不说 |
| 频道浏览 / 切换 | 看到每个频道里有谁，点一下就过去；加锁频道会提示输密码 |
| 每人独立音量 | 频道里每个人一条滑条（0–200%，可静音），按昵称记住，下次进来仍然有效 |
| 设备与增益 | 麦克风增益、输入设备、播放设备（支持 `setSinkId` 的浏览器）均可选择 |
| 通话标记 | 通话期间频道里的人会看到你的昵称前带 `<WEB通讯>`，挂断后自动恢复 |

**运行要求**

- 浏览器需支持 **WebCodecs `AudioDecoder`**（Chrome / Edge 等 Chromium 内核）；不支持时会明确报错而不是静默失灵。
- 生产环境需 HTTPS（localhost 开发环境除外），否则拿不到麦克风权限。
- TSMusicBot 需要带 `/api/voice/downlink/:botId` 下行接口与 `POST /api/player/:botId/live` 实时流入口。**改完 TSMusicBot 源码要重新 build 镜像并重建容器**，否则跑的还是旧代码。
- 若 TSMusicBot 无法通过浏览器所用域名反连 PowerfulTS，把 `LIVE_AUDIO_PUBLIC_URL` 设为它能访问的面板地址（例如 `http://host.docker.internal:8080`），面板需绑定上游可访问的地址；在 TSMusicBot 设置同值 `POWERFUL_TS_ORIGIN`。
- **建议戴耳机**；同一台设备不要让 TS 客户端和网页同时待在同一频道，否则会形成回声。

> 实现细节与协议见 [`docs/web-voice-downlink-spec.md`](docs/web-voice-downlink-spec.md)。

**延迟诊断**：已加入通话的账号可调用 `GET /api/music/voice/diagnostics`。响应只返回当前账号
通话 bot 的中继队列驻留、TSMusicBot decoded-PCM 与首个有声 TS 发送指标；不会返回 botId、
上行 capability/sessionId 或当前歌曲等无关状态。该接口供 S-Live 做非阻塞首响归因，不参与音频热路径。

---

## 📡 电脑音频实时共享

音乐控制的「共享电脑音频」只会在用户点击按钮后调用浏览器的屏幕共享选择器。选择网易云等应用窗口并勾选「共享音频」后，浏览器才会将音频实时发送给当前音乐机器人；停止系统共享、切换机器人或离开页面都会自动断开。

- 生产环境需要 HTTPS（localhost 开发环境除外），建议使用最新版 Chrome / Edge。
- 优先选择单个应用窗口。共享整个屏幕可能把 TeamSpeak 的声音再次录入，造成回声。
- TSMusicBot 需要包含 `POST /api/player/:botId/live` 实时流入口。
- 如果 TSMusicBot 无法通过浏览器访问的域名反向连接 PowerfulTS，可将 `LIVE_AUDIO_PUBLIC_URL` 设置为它能访问的面板地址，例如 `http://host.docker.internal:8080`，并按[语音回连说明](docs/release-guide.md#容器网络与远程访问)配置监听地址和 `POWERFUL_TS_ORIGIN`。

---

## 🖥️ 一起看与屏幕共享

在「网页通话」加入频道后，点击「一起看 · 屏幕共享」中的「加入共享房间」。同频道的网页成员会看到已有内容，每个频道只允许一个画面；父子频道互不影响。首位发起者成为房主，可以将权限转交给同频道已加入共享的成员。

- **同步观看**：每人自行加载视频，只发送播放进度、暂停、倍速和就绪状态。MP4 / WebM 等直链可以直接播放；B 站、腾讯视频、爱奇艺等使用通话页提供的 Chrome / Edge 扩展连接视频标签页。每人需要自己的账号与播放权限；各平台播放器、广告及嵌入方式的兼容性仍需实站验证。
- **等待成员**：点播默认等待所有观看者加载完成，房主可关闭。掉线后保留 20 秒等待重新加入；主动退出或切频道会立即移出。选择「这是直播」或屏幕共享时不等待缓冲。
- **成员暂停**：默认允许成员暂停整个房间，房主可关闭；继续播放由房主控制。转交同步观看保留进度，转交屏幕共享需要新房主重新选择并授权窗口。
- **屏幕共享**：使用 WebRTC 传输用户选择的屏幕、窗口或标签页及可捕获的音频。生产环境需要 HTTPS；跨网络连接失败时配置 `SCREEN_SHARE_ICE_SERVERS` 的 TURN 中继。当前使用分享者向观看者逐一发送的模式，每个房间最多 9 人。

完整安装、部署要求和验证范围见 [一起看与屏幕共享说明](docs/watch-room.md)。

---

## 🎼 开屏背景音乐（可选）

登录页左侧的音频频谱会随**真实音频**律动，开屏可随机播放本地背景音乐。

### 添加音乐

把音频文件（`.mp3` / `.wav` / `.ogg` / `.m4a` / `.flac` / `.aac`）放入 `backend/data/intro-music/` 目录即可——**无需重启、无需维护清单**，后端自动扫描，开屏随机选一首播放，播完自动换下一首。

> ⚠️ **版权与隐私**：`backend/data/intro-music/` 内的音频文件已被 `.gitignore` 忽略（仅保留 `.gitkeep` 与 `README.md` 占位），**不会上传到 GitHub**。请使用你拥有合法使用权的音频，切勿提交受版权保护的内容。

### 浏览器自动播放策略

- 开屏先尝试有声播放；若被浏览器拦截，则**静音播放**（频谱随之贴底静止）并在左下角显示 🔇 按钮，点击即可开声。
- 左下角按钮支持**悬停展开音量滑块**：频谱高度随音量**等比例**变化——默认 40% 为基准，往上拖更高、往下更矮，**静音或拖到 0 时频谱贴底不动**；音量自动记忆，下次进入恢复。
- 频谱在**首次与页面交互**（动鼠标 / 点击 / 按键）后才会切换为真实音频律动——这是 `AudioContext` 的浏览器限制。

### Docker 部署挂载音乐

Docker 镜像不含你的本地音乐，需把宿主机目录挂载进容器（在 `docker-compose.yml` 的 `backend` 服务添加 volume）：

```yaml
backend:
  volumes:
    - ./backend/data/intro-music:/app/data/intro-music
```

---

## 🌐 跨平台部署

| 平台 | 说明 |
|------|------|
| **Linux 服务器** | 安装 Docker + Compose 插件，按 Docker 教程部署；TSMusicBot/TS3/TS6 用宿主内网 IP 或 `host-gateway` |
| **Windows / macOS** | 安装 [Docker Desktop](https://www.docker.com/products/docker-desktop/)，上游地址用 `host.docker.internal` |
| **NAS（群晖 / 威联通等）** | 使用 [`docker-compose.nas.yml`](docker-compose.nas.yml) 直接拉取镜像，参见 [NAS 安装说明](docs/nas.md)；支持 x86_64 / ARM64，注意 NAS 防火墙放行端口 |
| **反向代理 / HTTPS** | 将 nginx（frontend 容器）置于 Caddy / Traefik / Nginx 之后，并在 `CORS_ORIGINS` 填入最终访问域名 |

---

## 🛡️ 安全说明

- 所有凭据通过环境变量注入，源码中**无任何硬编码秘钥**；`.env` 已被 `.gitignore` 忽略。
- 统一鉴权：`X-Session-Token` 先校验真实会话，再按角色授权；普通接口拒绝 guest，只有网页通话接口接受两小时游客会话，无效会话一律 401。
- CORS 默认收敛为白名单（`CORS_ORIGINS`），生产部署请改为实际域名。
- SSH ServerQuery 校验可信主机公钥，拒绝未知或已变更的公钥；不自动信任 `ssh-keyscan` 的结果。raw TCP Query 只用于可信内网或已有安全隧道。
- B 站图片代理 `/api/bili/pic` 限制为 B 站 CDN 域名白名单，防止 SSRF。
- 网页通话的收听凭据是 32 字节一次性票据（30 秒过期、只能消费一次），不把登录 Token 放进 WebSocket URL。
- 切换频道由通话 bot 以**自己的 TS 客户端身份**执行，频道密码由服务端正常校验；刻意不走 ServerQuery `clientmove`——查询管理员通常持有 `b_channel_join_ignore_password`，那条路会直接绕过频道密码。
- 数据持久化于 Docker volume `powerfults-data`，`docker compose down` 不会丢失（`-v` 才删除）。

---

## 🗺️ 路线图

- [x] 账户 / 概览 / 音乐 / 平台账号 / 社交（核心功能）
- [x] 原生 TS3 / TS6 ServerQuery 直连（raw TCP / SSH；概览 / 认证 / 好友）
- [x] 音乐与点播引擎迁移至 TSMusicBot（网易云 / QQ / 酷狗 / B 站 多平台）
- [x] Steam 集成（OpenID 绑定 · 好友在线 · 共同游戏 · 时长排行）
- [x] Docker 化跨平台一键部署
- [x] 网页通话（浏览器直连频道语音，双向）
- [ ] 网页通话：多人同时接入的实机压测与延迟基线
- [ ] TS6：目标服务器上的音乐播放、频道密码和网页双向语音实机验收

---

## 🤝 参与贡献

本项目处于早期阶段，**非常欢迎并感谢社区的各类贡献** —— 反馈 Bug、提出建议、完善文档或提交代码，对项目都很有帮助。

- 🐛 **反馈问题 / 功能建议**：请[提交 Issue](https://github.com/Slldyd2077/PowerfulTS/issues/new)，尽量附上复现步骤、相关日志与运行环境信息。
- 🛠️ **提交代码（Pull Request）**：
  1. Fork 本仓库并克隆到本地
  2. 新建分支：`git checkout -b feat/你的功能` 或 `fix/问题描述`
  3. 提交改动，遵循 [Conventional Commits](https://www.conventionalcommits.org/) 规范（如 `feat:` / `fix:` / `docs:`）
  4. 推送分支并发起 Pull Request，描述改动内容与动机
- 💬 **交流讨论**：也欢迎在 Issue 区分享使用体验与改进想法。

> 首次贡献者同样欢迎 —— 哪怕只是修正一处文档错别字、补充一段说明，都是有价值的贡献 🎉

---

## ❓ 常见问题（FAQ）

**Q：访问 `localhost:8080` 打不开 / 502？**
检查容器状态 `docker compose ps` 与日志 `docker compose logs -f`。502 多为后端未就绪或上游 TSMusicBot / TeamSpeak 不可达。

**Q：音乐搜索 / B站点播无结果？**
确认 `TSMUSIC_*` 配置正确、TSMusicBot 在线，且容器能访问其地址（容器内勿用 `127.0.0.1`，用 `host.docker.internal` 或宿主 IP）。

**Q：监控无数据 / 在线用户为空？**
检查 `TS3_QUERY_*` 凭据、虚拟服务器 ID、Query transport 和 TCP 端口。TS3 raw 通常 :10011；TS6 SSH 通常 :10022，且服务端需显式开启 SSH Query。SSH 模式还要确认后端能读取 known_hosts 且其中记录与 `TS3_HOST` / 端口一致，详见 [TS6 排错](docs/ts6-server.md#排错)。

**Q：TS6 连接配置为什么还是 `TS3_*`？10022 可以用作音乐机器人的端口吗？**
`TS3_*` 为兼容旧配置保留，TS3 / TS6 共用。10022 是 SSH Query 管理端口；音乐机器人和网页通话连接 UDP 语音端口，通常为 9987。修改 Query transport 不需要向 TSMusicBot API 添加 `serverProtocol` 参数。

**Q：登录后提示跨域 / CORS 错误？**
将实际访问地址加入 `CORS_ORIGINS`（逗号分隔），如 `http://localhost:8080,https://ts.example.com`，重启后端。

**Q：端口 8080 / 8001 被占用？**
修改 `docker-compose.yml` 的 `ports` 映射（如 `"3000:80"`）。

**Q：如何升级到新版本？**
```bash
git pull
docker compose up -d --build
```

**Q：数据存在哪里？如何备份？**
SQLite 存于 Docker volume `powerfults-data`（容器内 `/app/data/powerfults.db`）。备份：`docker cp powerfults-backend:/app/data ./backup`。

---

## 📄 许可证

本项目基于 [**MIT License**](./LICENSE) 开源。

---

## 🙏 致谢

本项目站在巨人的肩膀上，感谢以下开源项目和开发者：

| 项目 | 说明 |
|------|------|
| [ZHANGTIANYAO1/teamspeak-music-bot](https://github.com/ZHANGTIANYAO1/teamspeak-music-bot) | TSMusicBot — TS3/TS6 多平台音乐机器人（网易云 / QQ / B 站），PowerfulTS 音乐与点播功能的核心引擎 |
| [yichen11818/NeteaseTSBot](https://github.com/yichen11818/NeteaseTSBot) | TS6 协议兼容参考（vendored tsproto 补丁） |
| [@honeybbq/teamspeak-client](https://github.com/honeybbq/teamspeak-client) | TS3 完整客户端协议实现，原生直连参考 |
| [YesPlayMusic](https://github.com/qier222/YesPlayMusic) | UI 设计灵感 |
| [NeteaseCloudMusicApi](https://github.com/Binaryify/NeteaseCloudMusicApi) | 网易云音乐 API 项目 |
| [QQMusicApi](https://github.com/jsososo/QQMusicApi) | QQ 音乐 API 项目 |
| [@sansenjian/qq-music-api](https://github.com/sansenjian/qq-music-api) | QQ 音乐 API 活跃维护版本 |
| [bilibili-API-collect](https://github.com/SocialSisterYi/bilibili-API-collect) | 哔哩哔哩 API 文档 |
