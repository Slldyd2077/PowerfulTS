# NAS / 服务器直接拉取镜像安装

使用根目录的 [`docker-compose.nas.yml`](../docker-compose.nas.yml)，在 NAS 上直接拉取 PowerfulTS 前后端镜像，无需下载整个仓库、编译代码或准备 `.env` 文件。配置支持 `linux/amd64`（Intel / AMD）和 `linux/arm64`（64 位 ARM），Docker 会选择对应架构；不支持 32 位 ARM。

**发布前提：维护者先完成本文末尾的首次镜像发布，并把两个 GHCR 包设为 Public。发布成功前，模板里的镜像地址无法用于匿名安装。**

## 安装前准备

- NAS 已安装支持 Compose 的容器管理工具，例如群晖 Container Manager、威联通 Container Station 或 Dockge；也可通过 SSH 使用 Docker Compose。
- 已有 TeamSpeak 服务端，开启 ServerQuery 并准备查询账号。
- 已有 [PowerfulTS 专用 TSMusicBot 分支](https://github.com/Slldyd2077/teamspeak-music-bot/tree/merge/upstream-v1.12) 构建的音乐机器人（v1.12.1+），准备 WebUI 账号、密码与 bot 实例 ID。
- NAS 能访问 `ghcr.io` 拉取镜像，也能访问 TeamSpeak 与 TSMusicBot。

本模板安装 PowerfulTS 前后端。TeamSpeak、TSMusicBot、可选的 NapCat 由现有服务提供。

## 在 NAS 管理界面安装

1. 创建一个名为 `powerfults` 的 Compose 项目，为它选择一个独立的持久化目录。
2. 将 [`docker-compose.nas.yml`](../docker-compose.nas.yml) 的全部内容粘贴到项目的 YAML 编辑器，或下载该文件后导入。若工具要求文件名为 `compose.yaml` / `docker-compose.yml`，重命名即可。
3. 在 YAML 中修改下列参数，不需要另建 `.env` 文件：

   | 参数 | 填写内容 |
   |------|----------|
   | `TS3_HOST` | TeamSpeak 所在机器的 IP / 域名 |
   | `TS3_QUERY_PORT` / `TS3_SID` | 查询端口、虚拟服务器 ID，默认 `10011` / `1` |
   | `TS3_QUERY_USER` / `TS3_QUERY_PASSWORD` | ServerQuery 专用账号与密码 |
   | `TSMUSIC_URL` | 音乐机器人 WebUI 地址，例如 `http://192.168.1.100:3000` |
   | `TSMUSIC_USER` / `TSMUSIC_PASSWORD` / `TSMUSIC_BOT_ID` | WebUI 账号、密码和 bot 实例 ID |
   | `LIVE_AUDIO_PUBLIC_URL` | TSMusicBot 能访问的面板地址，例如 `http://NAS的IP:8080`，不带路径 |
   | `CORS_ORIGINS` | 浏览器访问面板的实际地址；多个来源用逗号分隔 |
   | frontend 的 `ports` | 默认 `8080:80`；若 8080 被占用，只改左侧端口 |

4. 在项目目录中创建 `data` 文件夹；若管理工具无法确定相对路径的位置，将 `./data:/app/data` 的左侧改成 NAS 上专用数据目录的绝对路径。
5. 点击部署 / 启动，等待镜像下载和后端健康检查通过后，访问 `http://NAS的IP:8080`（或你修改的端口）。

**密码中的 `$` 必须写成 `$$`**，否则 Compose 会尝试替换变量，即使使用 YAML 单引号也不能避免。所有账号密码均保留为字符串；含特殊字符时使用合法 YAML 引号。填过真实凭据的配置不要上传到公开仓库。

## 服务地址与回调

容器内的 `127.0.0.1` 指向容器自身。TeamSpeak / TSMusicBot 部署在 NAS 或其他设备时，用它们可达的局域网 IP 和已映射的端口；Linux NAS 无需依赖 `host.docker.internal`。

本模板只暴露前端入口 `8080`，API、WebSocket、音频回调由 Nginx 转发到后端，后端 `8001` 不必对外映射。`LIVE_AUDIO_PUBLIC_URL` 可以使用 `http://NAS的IP:8080`；启用入场音效时，在 **TSMusicBot** 的配置中设置完全相同的 `POWERFUL_TS_ORIGIN`（不带路径）。若修改入口端口，同步修改回调地址与 CORS 来源。

通过域名提供网页通话时，应配置 HTTPS 反向代理，支持 WebSocket 并传递 `X-Forwarded-Proto`；浏览器通过普通局域网 HTTP 地址访问时不能使用麦克风。Steam 绑定还需填写 `STEAM_API_KEY`、随机的 `STEAM_OPENID_STATE_SECRET` 和用户可访问的 `STEAM_OPENID_RETURN_URL`，其余参数见 [后端配置模板](../backend/.env.example)。

## 通过 SSH 安装

在 NAS 的项目目录里保存并编辑 `docker-compose.nas.yml`，创建 `data` 目录，然后运行：

```bash
mkdir -p data
docker compose -f docker-compose.nas.yml config --quiet
docker compose -f docker-compose.nas.yml up -d
docker compose -f docker-compose.nas.yml ps
```

查看日志：

```bash
docker compose -f docker-compose.nas.yml logs -f
```

## 更新、固定版本与备份

NAS 管理界面中重新拉取镜像并重建项目，或通过 SSH 执行：

```bash
docker compose -f docker-compose.nas.yml pull
docker compose -f docker-compose.nas.yml up -d
```

模板默认固定为 `1.1.3`。升级时可设置 `POWERFULTS_VERSION` 为已发布版本，或同时修改前后端的默认标签；两者应保持一致。使用 `latest` 会随主分支更新，也可以固定为同一个 `sha-完整提交哈希`。切换版本前备份数据；回退镜像不代表数据库可以自动回退。

数据保存在项目的 `data` 目录，包括 SQLite、入场音效和可选的开屏音乐。备份时先停止项目，再复制整个 `data` 目录与填好的 Compose 配置，完成后重新启动。删除项目时保留此目录即可保留数据。

使用本模板从原有源码 Compose 迁移时，原数据在 Docker 命名卷中，不会自动出现在新的 `./data` 目录。先停止原项目，通过 `docker cp powerfults-backend:/app/data/. ./data` 导出数据，再停止并移除原容器、启动新项目；复制前确认当前目录为新项目目录。不要让两套后端同时写同一份 SQLite 数据。

开屏音乐可以放进 `data/intro-music/`；不要把用户上传的入场音效目录改为公开静态目录。

## 常见问题

| 现象 | 排查方法 |
|------|----------|
| `denied` / `unauthorized` / `manifest unknown` | 确认维护者已发布两个镜像并设为 Public，所选标签确实存在 |
| `no matching manifest` | 确认 NAS 为 x86_64 或 ARM64，且该标签已发布对应架构 |
| 拉取超时 | 检查 NAS 到 GHCR 的网络；本模板无需登录即可拉取公开镜像 |
| 前端等待后端 / 后端 unhealthy | 查看后端日志，检查数据目录可写、配置的端口与 ID 为数字 |
| 页面正常但监控 / 音乐不可用 | 检查容器是否能访问上游 IP、映射端口及账号密码；健康检查只检查面板服务是否启动 |
| 网页麦克风不可用 | 使用 HTTPS 域名访问，并检查浏览器授权 |

## 维护者：首次发布镜像

仓库提供 [`.github/workflows/docker-publish.yml`](../.github/workflows/docker-publish.yml)。合入 `main` 后，前后端或工作流相关文件更新会触发构建；也可以在 GitHub Actions 中手动运行 **Publish Docker images**。发布 `vX.Y.Z` 标签会生成对应版本标签。手动在非默认分支运行只生成提交哈希标签，避免覆盖主分支的 `latest`。

工作流分别构建前后端的 `linux/amd64` / `linux/arm64` 镜像，使用仓库的 `GITHUB_TOKEN` 推送到 GHCR，无需另外配置 Docker Hub 密钥。流程参照 [Docker 多架构构建文档](https://docs.docker.com/build/ci/github-actions/multi-platform/)。

本仓库的发布地址为：

```text
ghcr.io/slldyd2077/powerfults-backend:latest
ghcr.io/slldyd2077/powerfults-frontend:latest
```

**首次发布后，分别进入两个包的 Package settings，将可见性改为 Public。** GHCR 新包默认私有，公开仓库并不会自动令镜像公开；只有公开包才能匿名拉取，见 [GitHub GHCR 文档](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry)。Fork 的工作流会发布到 Fork 所有者的命名空间，使用时相应修改 Compose 的两处镜像地址。

首次对外提供模板前，确认工作流两个任务均成功、两个镜像均包含所需架构，并在未登录 GHCR 的环境中分别拉取这两个镜像，再完成一次启动验证。
