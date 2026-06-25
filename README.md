<p align="center">
  <img src="assets/logo.svg" alt="PowerfulTS — TS3 Monitoring Dashboard" width="480" />
</p>

<p align="center">
  <strong>TS3 服务器监控面板</strong> · 独立前后端架构 · 原生 TS3 直连 + TSMusicBot 音乐引擎
</p>

<p align="center">
  <a href="https://vuejs.org/" target="_blank"><img alt="Vue" src="https://img.shields.io/badge/Vue-3.5-42b883?logo=vuedotjs&logoColor=white"></a>
  <a href="https://vite.dev/" target="_blank"><img alt="Vite" src="https://img.shields.io/badge/Vite-8-646CFF?logo=vite&logoColor=white"></a>
  <a href="https://fastapi.tiangolo.com/" target="_blank"><img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-0.115+-05998B?logo=fastapi&logoColor=white"></a>
  <a href="https://www.python.org/" target="_blank"><img alt="Python" src="https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white"></a>
  <img alt="Docker" src="https://img.shields.io/badge/Docker-一键部署-2496ED?logo=docker&logoColor=white">
  <img alt="TS3" src="https://img.shields.io/badge/TS3-支持-2580C3?logo=teamspeak&logoColor=white">
  <img alt="TS6" src="https://img.shields.io/badge/TS6-支持-2580C3?logo=teamspeak&logoColor=white">
  <img alt="License" src="https://img.shields.io/badge/License-MIT-blue?logo=mit&logoColor=white">
</p>

---

## 📖 简介

**PowerfulTS** 是一个面向 TeamSpeak（TS3 / TS6）服务器的实时监控与多媒体面板，采用**前后端分离**架构。
后端原生直连 TS3 ServerQuery 提供监控数据，并将音乐与点播能力委托给 TSMusicBot 多平台引擎，
让一个 Web 面板即可聚合呈现服务器的在线状态、用户、频道与多媒体能力。

> 💡 **跨平台**：提供完整 Docker 化方案，Linux / Windows / macOS / NAS（群晖、威联通等）均可一键部署。

---

## ✨ 功能特性

| 模块 | 状态 | 能力 |
|------|:----:|------|
| 👤 账户 | ✅ | 登录 / 注册（QQ + TS 昵称绑定 + 验证码） |
| 📊 实时监控 | ✅ | 服务器概览 · 5 秒轮询刷新 |
| 👥 在线用户 | ✅ | 昵称 · 游戏 · 所在频道 · 在线时长 |
| 🎮 游戏统计 | ✅ | 各游戏实时人数分布 |
| 📡 频道列表 | ✅ | 频道树浏览 |
| 🎵 音乐中心 | ✅ | 搜索 · 点歌 · 队列 · 音量 · 播放模式（网易云 / QQ） |
| 🎬 Bilibili | ✅ | 番剧 / 视频浏览与点播（TSMusicBot 多平台） |
| 🔐 平台账号 | ✅ | 网易云 / QQ 扫码登录（解锁 VIP / 个人歌单） |
| 🤝 社交 | ✅ | 好友添加 / 删除 / 在线状态 |

---

## 🧱 技术栈

| 层 | 技术 |
|----|------|
| **前端** | Vue 3 · Vite 8 · Element Plus · Pinia · Vue Router · TypeScript · Axios |
| **后端** | FastAPI · Uvicorn · httpx · SQLAlchemy (async) · aiosqlite · python-dotenv |
| **数据层** | SQLite（默认零依赖文件库，可切 PostgreSQL/MySQL） |
| **部署** | Docker · Docker Compose（跨平台一键部署） |
| **运行时** | Node.js ≥ 18 · Python ≥ 3.11（仅手动部署需要；Docker 已内置） |

---

## 🏗️ 系统架构

PowerfulTS 后端原生直连 TS3 ServerQuery，同时代理 TSMusicBot 的多媒体能力；对前端只暴露 `/api/*` 一个入口。

```
                          ┌──▶ TS3 ServerQuery (:10011)   监控 · 用户 · 频道 · 好友 · 认证（原生直连）
浏览器  ▶  Vue 3 SPA (:5173)  ▶  FastAPI (:9090)  ──┤
          (Vite 代理 /api)     原生数据层 + 代理网关   └──▶ TSMusicBot (:3000)            音乐搜索 · 点歌 · 播放控制 · B 站点播
                                                                 （网易云 / QQ / B 站 多平台 · TS3/TS6 双协议）
```

- `/api/stats`、`/api/channels` → 原生 TS3 ServerQuery（监控 / 频道，直读）
- `/api/auth/*`、`/api/friends/*` → 原生 TS3 ServerQuery + SQLite（认证 / 好友 / 账户）
- `/api/music/*` → TSMusicBot 音乐引擎（搜索 / 播放控制 / 平台账号登录）
- `/api/bili/*` → Bilibili 浏览与点播（点播由 TSMusicBot 多平台引擎驱动）+ 图片代理

> 监控、认证、社交等模块已由原生 TS3 ServerQuery 直连 + SQLite 数据层实现，不再依赖外部桥接服务。

---

## 📁 项目结构

```
PowerfulTS/
├── assets/                      # 项目 LOGO
├── backend/                     # FastAPI 后端 — 原生 TS3 直连 + 代理网关
│   ├── app/
│   │   ├── core/config.py           # 配置：从环境变量读取 TSMusicBot / TS3 凭据
│   │   ├── routers/                 # music / bilibili / monitor / auth / friends 路由
│   │   ├── services/                # TSMusicBot / 网易云 / TS3 监控 客户端
│   │   └── main.py                  # 应用入口（原生数据层 + TS3 监控 + 多媒体代理）
│   ├── Dockerfile               # 后端镜像
│   ├── .dockerignore
│   ├── .env.example             # 配置模板（复制为 .env 填写）
│   └── requirements.txt
├── frontend/                    # Vue 3 前端
│   ├── src/
│   ├── Dockerfile               # 多阶段构建（node 编译 → nginx 托管）
│   ├── nginx.conf               # 静态托管 + /api 反向代理
│   ├── .dockerignore
│   └── vite.config.ts
├── docker-compose.yml           # 一键编排（backend + frontend）
└── README.md
```

---

## 🚀 快速开始

### 方式一：Docker 一键部署（推荐）

适用于 Linux 服务器、Windows、macOS、NAS 等所有支持 Docker 的平台。**无需本地安装 Python / Node.js。**

#### 1. 前提条件

- 已安装 [Docker](https://docs.docker.com/get-docker/) 与 [Docker Compose](https://docs.docker.com/compose/install/)（Docker Desktop 自带）
- 上游服务已就绪（见 [🔌 接入上游服务](#-接入上游服务)）：
  - **TSMusicBot**（音乐 / 点播引擎，默认 :3000）
  - **TS3 服务端**（开启 ServerQuery，默认 :10011）

#### 2. 配置环境变量

```bash
cd backend
cp .env.example .env          # Windows PowerShell: copy .env.example .env
```

编辑 `backend/.env`，填入 TSMusicBot 与 TS3 凭据（**关键：容器内地址需特殊配置，见下方说明**）：

```ini
# TSMusicBot 音乐引擎
TSMUSIC_URL=http://host.docker.internal:3000   # ← 容器访问宿主机服务，见下方「容器网络地址」
TSMUSIC_USER=你的TSMusicBot账号
TSMUSIC_PASSWORD=你的TSMusicBot密码
TSMUSIC_BOT_ID=你的bot实例id

# TS3 ServerQuery
TS3_HOST=host.docker.internal                  # ← 同上
TS3_QUERY_PORT=10011
TS3_QUERY_USER=你的ServerQuery账号
TS3_QUERY_PASSWORD=你的ServerQuery密码
TS3_SID=1

# CORS（生产部署改为实际访问域名/端口）
CORS_ORIGINS=http://localhost:8080
```

> **🐳 容器网络地址说明**（Docker 部署必读）
>
> 容器内的 `127.0.0.1` 指向容器自身，**不是宿主机**。因此当 TSMusicBot / TS3 运行在宿主机时：
> - **Windows / macOS（Docker Desktop）**：用 `host.docker.internal`（如上例）。
> - **Linux**：`host.docker.internal` 默认不可用，需改用**宿主机内网 IP**（如 `192.168.1.100`），或在 `docker-compose.yml` 的 backend 服务加 `extra_hosts: ["host.docker.internal:host-gateway"]`。
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

### 方式二：手动部署（开发 / 无 Docker 环境）

#### 1. 前提条件

- Node.js ≥ 18、pnpm
- Python ≥ 3.11、[uv](https://docs.astral.sh/uv/)（推荐）或 pip
- 上游服务运行中：TSMusicBot（:3000）、TS3 服务端（ServerQuery :10011）

#### 2. 后端

```bash
cd backend
cp .env.example .env          # 编辑 .env 填入 TSMusicBot / TS3 凭据
uv sync                       # 安装依赖（或 pip install -r requirements.txt）
uv run uvicorn app.main:app --host 0.0.0.0 --port 9090 --reload
```

启动后访问 `http://localhost:9090/health` 应返回 `{"status":"ok","mode":"native-transition", ...}`。

#### 3. 前端

```bash
cd frontend
pnpm install
pnpm dev                      # 开发模式 → http://localhost:5173
```

Vite 已配置 `/api` 代理到后端 :9090，开发时直接访问 `http://localhost:5173`。

#### 4. 生产构建

```bash
cd frontend
pnpm build                    # 输出到 dist/，可用任意静态服务器（nginx）托管并反代 /api → :9090
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
| `TS3_HOST` | ✅ | TS3 服务端地址（容器内用 `host.docker.internal`） | `127.0.0.1` |
| `TS3_QUERY_PORT` | ✅ | ServerQuery 端口 | `10011` |
| `TS3_QUERY_USER` | ✅ | ServerQuery 账号 | — |
| `TS3_QUERY_PASSWORD` | ✅ | ServerQuery 密码 | — |
| `TS3_SID` | ✅ | 虚拟服务器 ID | `1` |
| `DATABASE_URL` | — | 数据库连接串（可切 PostgreSQL/MySQL） | `sqlite+aiosqlite:///./data/powerfults.db` |
| `CORS_ORIGINS` | — | 允许的前端来源（逗号分隔，生产改实际域名） | `http://localhost:5173` |
| `NETEASE_API_URL` | — | 网易云 API（可选，TSMusicBot 已内置） | `http://127.0.0.1:3000` |

**获取 TSMusicBot 凭据：** 在 TSMusicBot WebUI（默认 `http://localhost:3000`）登录所用的账号密码与 bot 实例 id，填入 `TSMUSIC_*`；后端会自动登录并代理其音乐 API，用户只与 PowerfulTS 交互。

**获取 TS3 ServerQuery 凭据：** 在 TS3 服务端创建 ServerQuery 账号（监控需 `clientlist` / `channellist` 读权限）。

---

## 🔌 接入上游服务

PowerfulTS 本身不含 TS3 服务端与音乐引擎，需接入两个上游：

### TSMusicBot（音乐 / 点播引擎）

- 项目：[ZHANGTIANYAO1/teamspeak-music-bot](https://github.com/ZHANGTIANYAO1/teamspeak-music-bot) —— TS3/TS6 多平台音乐机器人（网易云 / QQ / B 站）
- 自行部署后，将 `TSMUSIC_URL` 指向其地址，并填入账号密码与 bot id
- 它同时提供音乐搜索、播放控制与 **B 站点播**（PowerfulTS 的 `/api/bili/*` 即委托其 `platform=bilibili` 能力）

### TS3 服务端（监控 / 认证数据源）

- 开启 **ServerQuery**（默认 :10011），创建专用账号填入 `TS3_QUERY_*`
- PowerfulTS 通过 ServerQuery 长连接轮询在线用户 / 频道 / 游戏状态

> 两者均可运行在宿主机、独立容器或同一 compose 网络中，按 [容器网络地址说明](#方式一docker-一键部署推荐) 配置连接地址即可。

---

## 🎮 功能使用指南

| 功能 | 入口 | 说明 |
|------|------|------|
| 📊 监控 | 首页 Dashboard | 服务器概览、在线用户、游戏统计、频道树，每 5 秒自动刷新 |
| 🎵 音乐 | 音乐中心 | 搜索（默认网易云，可切 QQ/B 站）、播放/暂停/上下首/进度/音量/播放模式/清空队列 |
| 🎬 B站点播 | Bilibili | 搜索 B 站视频，点击播放（音频由 TSMusicBot 拉取） |
| 🔐 平台账号 | 音乐中心 → 账号 | 网易云 / QQ 扫码登录，解锁 VIP 曲库与个人歌单 |
| 🤝 社交 | 好友 | 添加 / 删除好友，查看好友在线状态 |
| 👤 账户 | 登录 / 注册 | QQ + TS 昵称绑定，ServerQuery 私聊下发验证码完成实名 |

> 音乐、点播、社交等功能**需登录后使用**；浏览器会自动在请求头注入会话 Token。

---

## 🌐 跨平台部署

| 平台 | 说明 |
|------|------|
| **Linux 服务器** | 安装 Docker + Compose 插件，按 Docker 教程部署；TSMusicBot/TS3 用宿主内网 IP 或 `host-gateway` |
| **Windows / macOS** | 安装 [Docker Desktop](https://www.docker.com/products/docker-desktop/)，上游地址用 `host.docker.internal` |
| **NAS（群晖 / 威联通等）** | 通过 Container Manager / Container Station 部署 compose，或在 SSH 下用 `docker compose`；注意 NAS 防火墙放行端口 |
| **反向代理 / HTTPS** | 将 nginx（frontend 容器）置于 Caddy / Traefik / Nginx 之后，并在 `CORS_ORIGINS` 填入最终访问域名 |

---

## 🛡️ 安全说明

- 所有凭据通过环境变量注入，源码中**无任何硬编码秘钥**；`.env` 已被 `.gitignore` 忽略。
- 统一鉴权：`X-Session-Token` 由 `get_current_account` 真实校验，无效会话一律 401。
- CORS 默认收敛为白名单（`CORS_ORIGINS`），生产部署请改为实际域名。
- B 站图片代理 `/api/bili/pic` 限制为 B 站 CDN 域名白名单，防止 SSRF。
- 数据持久化于 Docker volume `powerfults-data`，`docker compose down` 不会丢失（`-v` 才删除）。

---

## 🗺️ 路线图

- [x] 账户 / 监控 / 音乐 / Bilibili / 社交（核心功能）
- [x] 原生 TS3 ServerQuery 直连（监控 / 认证 / 好友）
- [x] 音乐与点播引擎迁移至 TSMusicBot（网易云 / QQ / B 站 多平台）
- [x] Docker 化跨平台一键部署

---

## ❓ 常见问题（FAQ）

**Q：访问 `localhost:8080` 打不开 / 502？**
检查容器状态 `docker compose ps` 与日志 `docker compose logs -f`。502 多为后端未就绪或上游 TSMusicBot/TS3 不可达。

**Q：音乐搜索 / B站点播无结果？**
确认 `TSMUSIC_*` 配置正确、TSMusicBot 在线，且容器能访问其地址（容器内勿用 `127.0.0.1`，用 `host.docker.internal` 或宿主 IP）。

**Q：监控无数据 / 在线用户为空？**
检查 `TS3_QUERY_*` 凭据是否正确、ServerQuery 是否开启、容器到 TS3 的 :10011 是否可达。

**Q：登录后提示跨域 / CORS 错误？**
将实际访问地址加入 `CORS_ORIGINS`（逗号分隔），如 `http://localhost:8080,https://ts.example.com`，重启后端。

**Q：端口 8080 / 9090 被占用？**
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
