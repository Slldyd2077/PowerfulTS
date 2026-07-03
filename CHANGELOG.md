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
