<p align="center">
  <img src="assets/logo.svg" alt="PowerfulTS — TS3 Monitoring Dashboard" width="480" />
</p>

<p align="center">
  <strong>TS3 服务器监控面板</strong> · 独立前后端架构 · 从 S-QC-Bot 项目解耦重构
</p>

<p align="center">
  <a href="https://vuejs.org/" target="_blank"><img alt="Vue" src="https://img.shields.io/badge/Vue-3.5-42b883?logo=vuedotjs&logoColor=white"></a>
  <a href="https://vite.dev/" target="_blank"><img alt="Vite" src="https://img.shields.io/badge/Vite-8-646CFF?logo=vite&logoColor=white"></a>
  <a href="https://fastapi.tiangolo.com/" target="_blank"><img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-0.115+-05998B?logo=fastapi&logoColor=white"></a>
  <a href="https://www.python.org/" target="_blank"><img alt="Python" src="https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white"></a>
  <img alt="License" src="https://img.shields.io/badge/License-MIT-blue?logo=mit&logoColor=white">
</p>

---

## 📖 简介

**PowerfulTS** 是一个面向 TeamSpeak 3 服务器的实时监控面板，采用**前后端分离 + 双桥接代理**架构。
后端作为网关，将前端请求按路径分流到三个上游服务：S-QC-Bot（监控）、TS3AudioBot（音乐）、Bilibili（点播），
让一个 Web 面板即可聚合呈现 TS3 服务器的在线状态、用户、频道与多媒体能力。

---

## ✨ 功能特性

| 模块 | 状态 | 能力 |
|------|:----:|------|
| 👤 账户 | ✅ | 登录 / 注册（QQ + TS 昵称绑定 + 验证码） |
| 📊 实时监控 | ✅ | 服务器概览 · 5 秒轮询刷新 |
| 👥 在线用户 | ✅ | 昵称 · 游戏 · 所在频道 · 在线时长 |
| 🎮 游戏统计 | ✅ | 各游戏实时人数分布 |
| 📡 频道列表 | ✅ | 频道树浏览 |
| 🎵 音乐中心 | ✅ | 搜索 · 点歌 · 队列 · 音量控制 |
| 🎬 Bilibili | ✅ | 番剧 / 视频浏览与播放 |
| 🤝 社交 | ✅ | 好友添加 / 删除 / 在线状态 |
| 🏷️ 频道租赁 | 🔄 | 规划中 |
| 🧍 VRM 虚拟形象 | 🔄 | 规划中 |
| 🛠️ 管理员后台 | 🔄 | 规划中 |

---

## 🧱 技术栈

| 层 | 技术 |
|----|------|
| **前端** | Vue 3 · Vite 8 · Element Plus · Pinia · Vue Router · TypeScript · Axios |
| **后端** | FastAPI · Uvicorn · httpx · python-dotenv |
| **包管理** | pnpm（前端） / uv + pip（后端） |
| **运行时** | Node.js ≥ 18 · Python ≥ 3.11 |

---

## 🏗️ 系统架构

PowerfulTS 后端是一个**双桥接代理网关**：对前端只暴露 `/api/*` 一个入口，再按子路径转发到不同上游。

```
                          ┌──▶ S-QC-Bot (:8080)      监控 · 用户 · 频道 · 好友 · 账户
                          │      (TS3 ServerQuery + Redis)
浏览器  ▶  Vue 3 SPA (:5173)  ▶  FastAPI (:9090)  ──┼──▶ TS3AudioBot (:58913)   音乐搜索 · 点歌 · 音量
          (Vite 代理 /api)        双桥接网关          │      (BASIC auth, REST)
                                                  └──▶ Bilibili API           番剧/视频浏览与播放
```

- `/api/music/*` → TS3AudioBot 音乐引擎
- `/api/bilibili/*` → Bilibili 浏览与点播（后端自取音频流，不依赖插件）
- `/api/*`（其余）→ S-QC-Bot（监控/用户/频道，透传）

> 后端初期采用桥接代理模式，所有监控数据透传自 S-QC-Bot；后续可平滑切换为直连 TS3 ServerQuery + Redis。

---

## 📁 项目结构

```
PowerfulTS/
├── assets/                      # 项目 LOGO
│   ├── logo.svg                 # 横版组合（含文字）
│   └── logo-mark.svg            # 纯图标（favicon / 头像）
├── backend/                     # FastAPI 后端 — 双桥接代理
│   └── app/
│       ├── core/config.py           # 配置：从环境变量读取上游地址与凭据
│       ├── routers/                 # music / bilibili 具体路由
│       ├── services/                # TS3AudioBot / Bilibili 客户端
│       └── main.py                  # 应用入口 + 通用 /api 透传代理
│   ├── .env.example             # 配置模板（复制为 .env 填写）
│   └── requirements.txt
├── frontend/                    # Vue 3 前端
│   └── src/
│       ├── api/                 # 类型化 Axios 请求层
│       ├── stores/              # Pinia 状态管理
│       ├── views/               # 页面（Dashboard / Login / 404）
│       ├── components/          # monitor / music / social / bilibili / layout
│       ├── composables/         # 轮询 / 主题切换
│       └── router/
│   └── vite.config.ts           # /api → :9090 开发代理
└── README.md
```

---

## 🚀 快速开始

### 1. 前提条件

- Node.js ≥ 18、pnpm
- Python ≥ 3.11、[uv](https://docs.astral.sh/uv/)（推荐）或 pip
- **上游服务正在运行：**
  - S-QC-Bot：`python src/bot_main_v2.py`（默认 :8080）
  - TS3AudioBot（可选，提供音乐能力，默认 :58913）

### 2. 后端

```bash
cd backend
cp .env.example .env          # 复制配置模板
# 编辑 .env 填入 TS3AudioBot 凭据（见下方「环境配置」）

uv sync                       # 安装依赖（或 pip install -r requirements.txt）
uv run uvicorn app.main:app --host 0.0.0.0 --port 9090 --reload
```

启动后访问 `http://localhost:9090/health` 应返回 `{"status":"ok","mode":"dual-bridge", ...}`。

### 3. 前端

```bash
cd frontend
pnpm install
pnpm dev                      # → http://localhost:5173
```

Vite 已配置 `/api` 代理到后端 :9090，开发时直接访问 `http://localhost:5173` 即可。

### 4. 生产构建

```bash
cd frontend
pnpm build                    # 输出到 dist/
```

---

## ⚙️ 环境配置

后端通过 `backend/.env` 读取配置（**该文件含凭据，已被 `.gitignore` 忽略，切勿提交**）。从 `.env.example` 复制后填写：

```ini
# 通道 1: S-QC-Bot（监控/用户/频道）
SQC_BOT_URL=http://127.0.0.1:8080

# 通道 2: TS3AudioBot（音乐引擎）
TS3AB_URL=http://127.0.0.1:58913
TS3AB_BOT_UID=<填入>          # BASIC 认证用户名
TS3AB_API_TOKEN=<填入>        # BASIC 认证密码
TS3AB_DEFAULT_BOT_ID=0
```

**获取 TS3AudioBot 凭据：** 在 TS3 客户端私聊 bot 发送 `!api token`，bot 回复形如
`uA0U7t4PBxdJ5TLnarsOHQh4/tY=:abcdef1234567890...` —— 冒号前填 `TS3AB_BOT_UID`，冒号后填 `TS3AB_API_TOKEN`。

---

## 🛡️ 安全说明

- 所有凭据通过环境变量注入，源码中**无任何硬编码秘钥**。
- `.env` / `.env.*` 已被 `.gitignore` 忽略，仅 `.env.example`（占位模板）入库。
- `.venv/`、`node_modules/`、临时工作目录均不纳入版本控制。

---

## 🗺️ 路线图

- [x] 账户 / 监控 / 音乐 / Bilibili / 社交（核心功能）
- [ ] 频道租赁管理
- [ ] VRM 虚拟形象
- [ ] 管理员后台

---

## 📄 许可证

本项目基于 [**MIT License**](./LICENSE) 开源。

---

## 🙏 致谢

本项目站在巨人的肩膀上，感谢以下开源项目和开发者：

| 项目 | 说明 |
|------|------|
| [ZHANGTIANYAO1/teamspeak-music-bot](https://github.com/ZHANGTIANYAO1/teamspeak-music-bot) | TS3/TS6 音乐机器人 — 网易云/QQ/B站，YesPlayMusic 风格 WebUI，PowerfulTS 音乐功能的后端引擎 |
| [yichen11818/NeteaseTSBot](https://github.com/yichen11818/NeteaseTSBot) | TS6 协议兼容参考（vendored tsproto 补丁） |
| [Splamy/TS3AudioBot](https://github.com/Splamy/TS3AudioBot) | 优秀的 TeamSpeak 音频机器人框架 |
| [TS3AudioBot-BiliBiliPlugin](https://github.com/HuxiaoRoar/TS3AudioBot-bilibili) | 提供插件开发参考 |
| [TS3AudioBot-NetEaseCloudmusic-plugin](https://github.com/ZHANGTIANYAO1/TS3AudioBot-NetEaseCloudmusic-plugin) | 提供插件开发参考和懒加载设计参考 |
| [TS3AudioBot-CloudMusic-plugin](https://github.com/577fkj/TS3AudioBot-CloudMusic-plugin) | 提供插件开发参考 |
| [TS3AudioBot-Plugin-Netease-QQ](https://github.com/HuxiaoRoar/TS3AudioBot-Plugin-Netease-QQ) | 提供插件开发参考 |
| [YesPlayMusic](https://github.com/qier222/YesPlayMusic) | UI 设计灵感 |
| [NeteaseCloudMusicApi](https://github.com/Binaryify/NeteaseCloudMusicApi) | 网易云音乐 API 项目 |
| [QQMusicApi](https://github.com/jsososo/QQMusicApi) | QQ 音乐 API 项目 |
| [@sansenjian/qq-music-api](https://github.com/sansenjian/qq-music-api) | QQ 音乐 API 活跃维护版本 |
| [@honeybbq/teamspeak-client](https://github.com/honeybbq/teamspeak-client) | TS3 完整客户端协议实现 |
| [bilibili-API-collect](https://github.com/SocialSisterYi/bilibili-API-collect) | 哔哩哔哩 API 文档 |
