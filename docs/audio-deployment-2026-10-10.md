# 2026-10-10 音频功能部署记录

已部署至 `https://tsqq.top`，网页/API 版本为 1.1.2。部署批次为 `audio-20261010-01`。

## 上线内容

- 网页麦克风默认使用 RNNoise 智能降噪，提供键盘抑制、人声门限、浏览器回声消除和自动增益开关、实际支持状态及失败降级。
- 机器人音乐输出启用逐曲响度均衡，默认目标 −18 LUFS。整首固定增益，保留曲内动态；设置改动在下一首生效。
- 现有 TS 身份、平台登录、配置和数据目录保留；部署后无需用户再次手动开启全局音乐均衡。

## 运行构建

现有服务器的 TS 连接层与通用补丁的固定基线有差异。最终构建把响度均衡移植到生产源代码快照上，保留原 `ts-protocol/client.ts` 及其运行模块。源码基线、补丁和运行产物 SHA256 已记录：

- [生产兼容补丁](../deploy/tsmusicbot/track-loudness-production-compatible.patch)
- [生产源代码基线清单](../deploy/tsmusicbot/track-loudness-production-baseline.json)
- 服务器 `/opt/powerfults-releases/audio-20261010-01/SHA256SUMS`

## GitHub 源码留存与后续更新

- 生产引擎：[提交 `9ea0a2e`](https://github.com/Slldyd2077/teamspeak-music-bot/commit/9ea0a2e7600333cf6caf72eae3a4bc5a0e1248a6)，维护分支 `codex/audio-production-compatible`。生产源代码快照与历史提交 `2c1fc74fce812caaaa79b5e8566a7dd617c1e9ad` 的全部 `src/` 文件一致；新兼容提交的全部 `src/` 与最终部署源码一致（忽略 CRLF/LF 行尾差异）。
- 通用引擎：[提交 `165e897`](https://github.com/Slldyd2077/teamspeak-music-bot/commit/165e8975ac3dcf1ca24b83c8b000c9f623112010)，已进入原推荐分支 `merge/upstream-v1.12`，317 项针对性测试及 TypeScript 检查通过。
- 网页 RNNoise、后端接口与状态显示、回归测试、补丁和部署说明保存在 PowerfulTS `main`。生产代码已入 Git，服务器私有配置、数据库、队列和身份不提交。

后续构建直接使用相应固定提交，无需再次应用补丁。现有服务器沿用兼容分支；切换通用分支需重新验收 TS 连接层。同步上游时保留固定增益和配置接口，并运行引擎响度回归测试。不要用原版上游镜像覆盖此定制引擎。

临时断开调用追踪已经从最终源码和运行文件移除。通用引擎补丁仍面向 `453d2d1`，独立保留在 `track-loudness.patch`，不能与生产兼容补丁叠加应用。

## 验收证据

- 兼容引擎 257 项针对性测试通过，包括真实 FFmpeg 文件处理、HTTP 整曲分析、曲内比例保留、固定增益和配置/API 测试；TypeScript 编译通过。
- 后端完整测试 364 项通过，前端 63 项单元测试和生产构建通过。
- Linux 服务器上的真实 HTTP 音频分析在 EOF 正常结束，只读取一次音源，取得有效综合响度和固定增益。
- 公网浏览器确认部署的 RNNoise 文件与构建产物 SHA256 一致，WASM 初始化、真实音频处理及处理后音频录制通过。
- 公网页面验收涵盖音频增强控件、逐曲均衡开关、固定增益状态、旧引擎禁用提示、设置持久化和手机布局。页面交互使用模拟 API；服务器接口能力和启用状态另用真实认证请求确认。
- `tsmusicbot`、`powerfults-api` 均为 active，新 OpenAPI 包含 `LoudnessNormalizationRequest`，真实引擎设置返回 supported=true、enabled=true、targetLufs=-18。

这些验证不代表真实设备的主观音质评分，也没有向频道注入测试音频。

## 排障与恢复记录

早期切换因 TS 重连验证未通过而自动回退，服务代码、配置和数据库恢复成功。观察到 SDK 握手停留在 `initivexpand2`，并出现启动请求重建旧实例的调用。完整根因未确认；最终保留生产连接层，按引擎先启动并确认连接、再启动网页 API 的顺序切换，采用有界显式重连。最终连接及原有队列、暂停状态验收通过。

另外修正了确定的 HTTP 预分析问题：播放参数中的 `reconnect_at_eof` 会让分析阶段无法及时结束，导致统计结果没有返回；现在仅在预分析中去掉该参数，并增加 HTTP 回归测试。曲内仍不使用动态增益。

部署验证时保留了原 24 个机器人记录及已有非空 TS 身份，并恢复了原队列和暂停状态。后续访问日志记录到正常认证的 `DELETE /api/music/bots/...` 请求（200），用户删除了一个音乐机器人，数量变为 23；没有逆转或重建该用户操作。

## 备份与回退

备份保存在服务器 `/opt/backups/powerfults-audio-20261010-01/`，权限受限，含代码/前端快照、配置、在线 SQLite 备份和切换前一致性数据库备份。原运行队列快照也仅保存在此私有目录，未提交账号、密码、session 或 identity 到仓库。

部署脚本及日志位于 `/opt/powerfults-releases/audio-20261010-01/`。回退需先停止网页 API 和机器人服务，再还原代码、配置和相应一致性数据库快照，恢复文件属主后启动；不要把旧快照覆盖到运行中的 SQLite/WAL 数据库上，也不要逆转部署后用户的合法修改。
