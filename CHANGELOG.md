## v0.8.0 (2026-07-13)

### Feat

- **Bot 分级共享**：共享时可选择仅提供 VIP 播放权限，或同时共享平台歌单；接受方可在自己的歌单与获授权的好友歌单之间切换。
- **好友申请即时状态**：主动发出的好友申请立即出现在好友列表并标记「已申请」，支持撤回。
- **好友通知可靠投递**：好友申请与接受通知按 QQ → 在线 TS → 留存待上线补发的优先级投递，避免重复通知和离线丢失。
- **逐好友上线提醒**：上线提醒从账号级总开关改为每位好友独立设置，首次升级自动继承原设置。

### Fix

- **多 Bot 音质隔离**：音质读取和设置携带 Bot ID，并将 QQ/酷狗音质值转换为平台原生格式，避免错误回退到低音质。
- 修复好友申请请求模型与 ORM 模型名称冲突，并补充回归测试。

## v0.7.1 (2026-07-06)

### Feat

- **好友互关标记**：好友列表显示「互关」/「单向」标签（对方是否也加了你为好友）
- **编辑 Bot 配置**：Bot 列表加「编辑」按钮，可改 Bot 名称/昵称/服务器地址/端口/默认频道/密码（连接类参数需先停止 Bot 再改才生效）

## v0.7.0 (2026-07-06)

### Feat

- **RBAC 权限控制**：`require_admin`/`AdminDep` 依赖（管理端点仅 admin）；首个注册用户自动 admin
- **管理后台**：`/admin` 系统设置页（admin 专属），网页配置 NapCat/TSMusicBot/TS3/CORS/Netease；NapCat/TSMusicBot/Netease 改后热重载（不重启），TS3/CORS 标记需重启；敏感项脱敏 `****`
- **NapCat 连接状态检测**：管理页一键检测 NapCat 连接 + 登录态（显示 QQ 昵称或失败原因）

### Fix

- element-plus 弹窗（el-dialog / ElMessageBox / ElMessage / el-select 下拉）亮色 → 暗色（导入 `dark/css-vars.css` + `html.dark`）
- `music.py` `IntegrityError` 导入路径修正（`sqlalchemy` → `sqlalchemy.exc`）

## v0.6.0 (2026-07-05)

### Feat

- **好友共享 Bot 实例**：owner 可在 TS Bot 面板把带 VIP 平台账号的 bot 共享给好友（即时授权、持久）；好友播放器 bot 下拉出现「共享·{owner}」选项，点播时用 owner 的 VIP 账号播放自己歌单的 VIP 曲目。接受方可播放/点播/队列/读 VIP 曲库 + start/stop bot；不可 delete/改配置/改平台账号（仅 owner）。
- 新增 BotShare 模型；`_owned_bot_id` 放宽（owned OR shared）覆盖播放/启停，新增 `_strict_owned_bot_id` 守住管理操作；list_bots 含共享 bot（标 shared+ownerNickname）。

## v0.5.0 (2026-07-04)

### Feat

- **播放队列长按拖动调序**：长按队列项（约 0.5s）触发放大拖动，上下拖动重排、其他项自动让位，松手生效，影响实际播放顺序；正在播放的项被拖动后继续播原歌（currentIndex 同步 shift）。需 TSMusicBot fork 配合（PlayQueue 新增 `move` + `/queue/:from/move` 端点）。

## v0.4.0 (2026-07-04)

### Feat

- **B 站收藏夹**：我的音乐 → B 站 tab 登录后展示收藏夹列表，点开看视频、单首点播、整单入队，自动过滤失效视频（需 TSMusicBot fork 配合：上游 BiliBiliProvider 新增 `getUserPlaylists` / `getPlaylistSongs`，用 B 站 v3 收藏夹 API）
- **扫码登录自动确认**：平台账号扫码后自动检测确认、关闭弹窗并刷新登录态（轮询 `qrcode/status`）；二维码过期自动提示重新获取

### Fix

- 扫码登录后弹窗不自动关闭：PowerfulTS 之前只查 `auth/status`，未调 fork 的 `qrcode/status` 触发 cookie 持久化，导致 fork 不知扫码完成、cookie 不存、窗口永不关

## v0.3.2 (2026-06-28)

### Fix

- 注册密码长度校验 + 还原登录页游客入口

## v0.3.1 (2026-06-28)

### Feat

- 播放跟随 + 应用设置 KV + 版本一致性校验
- 全站移动端响应式适配 + 好友上线QQ通知 + 开屏音乐后端
- 我的音乐/Bot管理 + 播放队列修复 + README 早期测试声明
- TSMusicBot 接管音乐/点播 + Docker 跨平台部署 + 安全加固
- 导航重构 + 网易云账号/歌单 + B站缩略图 + 音乐迁移 TSMusicBot
- 网易云音乐音源接入 (PowerfulTS 自研, 不依赖 TS3AudioBot 插件)
- **backend**: P1b 原生好友关系 + 修复断层
- **backend**: P1a 原生 TS 身份认证 + 安全加固
- **backend**: P0 原生化地基 — SQLite 数据层 + TS3 直连监控
- 网页标签 favicon 与登录页接入项目 LOGO

### Fix

- 播放队列点击切歌 + 频谱/歌单/按钮交互修复 + UI 调整
- **backend**: get_online_uid 返回 client_data 的 key uid
- **backend**: TS3 ServerQuery 客户端修复 + 认证发码打通
