本次音频功能已同步至引擎 GitHub 仓库：生产兼容源码 `9ea0a2e`，通用定制实现 `165e897`。更新到这两个提交无需重新应用补丁；版本选择与回归检查见[升级指南](../../docs/release-guide.md#上游引擎)。

# Issue #15：昵称长度校验与 identity 保存修复

另有基于历史提交 `453d2d1` 的[逐曲响度均衡补丁](../../docs/track-loudness-normalization.md)：机器人输出端统一不同歌曲的整体响度，同一首使用固定增益，保留曲内动态。

2026-10-10 的现有生产环境采用另外的兼容移植构建，保留原 TS 连接层，见[部署记录与生产兼容补丁](../../docs/audio-deployment-2026-10-10.md)。请根据源代码基线选择补丁，不能叠加两份响度补丁。

用户已确认这次连接失败的原因是昵称长度。PowerfulTS 的注册、发送验证码和加入
通话入口现已校验昵称需为 3–30 个 Unicode 字符；前端同步提示并禁止提交不合规
昵称。TS 非 SDK 客户端的限制见
[TeamSpeak 官方定义](https://github.com/teamspeak/ts3client-pluginsdk/blob/master/include/teamspeak/public_rare_definitions.h)。
已有不合规账号会立即得到长度提示，需要调整账号昵称及对应引擎 bot 的 nickname
配置；不会再等到连接超时才发现问题。

PowerfulTS 的前端等待时间、后端总连接时限和列表查询保护也已在本仓库修复。
identity 的生成与保存属于独立的 TSMusicBot 引擎，更新 PowerfulTS 镜像不会更新引擎。
本目录提供引擎补丁及其回归测试，基于定制分支 `merge/upstream-v1.12` 的固定提交
`2c1fc74fce812caaaa79b5e8566a7dd617c1e9ad`。

## 原因与验证边界

邀请注册原先允许 1–64 个字符，通话 bot 直接使用账号昵称登录 TS。Issue 中失败的
「1」「2」「5」只有 1 个字符，「雪凌」只有 2 个字符，均小于最低 3 个字符；成功
样本均至少 3 个字符。邀请注册绕过了真实 TS 客户端注册时已有的昵称限制，因此
PowerfulTS 的注册校验缺失是这次问题的入口。此结论依据用户确认和代码检查。

`issue-15-nickname.patch` 让引擎在 TS 连接入口也校验 3–30 个字符，连接前明确报错。
字符数按 Unicode 码点计算，不按 UTF-8 字节数或 JavaScript UTF-16 单元数计算。
回归测试覆盖过短、过长、中文和 emoji。

指定提交的 `src/bot/manager.ts` 在创建实例时没有写入 identity，手动启动和自动启动
都只在连接成功后保存。握手失败会留下 NULL，下次手动启动重新生成 UID，无法保留
该身份的服务器权限。成功启动后，旧记录上的 `autoStart=false` 还会覆盖刚写入的 true。

补丁在创建、加载旧记录和启动连接前持久化 identity，保留已有私钥及安全等级 offset；
成功后从最新记录写入 `autoStart`。已有 NULL 记录会在加载或启动时自动补齐。
测试覆盖失败后重试使用同一身份、成功后的自动启动标记和旧记录自动修复。

`@honeybbq/teamspeak-client` 0.2.2 的 `generateIdentity(8)` 已生成至少 8 级身份，
导出字符串也保留 offset。这里 identity 为 NULL 是失败后未落库的结果，不能证明
安全等级导致失败。`issue-15-identity.patch` 修复的是另一个已确认的身份生命周期
缺陷，不能替代昵称校验。
本地回归测试没有连接 issue 报告者的 TS 服务器。

## Issue #15 修复所在的通用分支

通用分支已同步原版主干 v1.15.2；最新音频实现为
[`165e897`](https://github.com/Slldyd2077/teamspeak-music-bot/commit/165e8975ac3dcf1ca24b83c8b000c9f623112010)。
该提交已包含本目录的两项修复，不需要额外应用补丁。现有生产服务器使用保留原连接层的兼容提交，版本选择见[升级指南](../../docs/release-guide.md#上游引擎)。下面的 Issue #15 补丁仅面向旧基线，不能未经连接验证就叠加到生产兼容引擎。

## 核对用户运行的引擎

检查实际用于构建引擎的 checkout，而不是只看 PowerfulTS 的版本：

```sh
git remote get-url origin
git branch --show-current
git rev-parse HEAD
```

应来自 `Slldyd2077/teamspeak-music-bot` 的定制分支，并核对构建提交。原版上游
`ZHANGTIANYAO1/teamspeak-music-bot` 不包含完整的 PowerfulTS 网页通话适配。
旧镜像或构建自其他分支的镜像也可能不兼容。`/api/health` 的版本字符串不足以核对：
指定提交的 health 版本为 1.12.1，package 版本为 1.12.2。

仅检查源码目录不能证明运行中的容器已更新。检查实际引擎容器的 image ID、镜像
构建记录或 revision label；确认下述补丁进入构建后，重新创建该容器。应同时具备
`/api/player/:botId/live` 和 `/api/voice/downlink/:botId` 定制接口。

## 应用补丁

在基于固定提交的引擎源码目录执行，把示例补丁路径换成实际路径：

```sh
git apply --check /path/to/PowerfulTS/deploy/tsmusicbot/issue-15-identity.patch
git apply /path/to/PowerfulTS/deploy/tsmusicbot/issue-15-identity.patch
git apply --check /path/to/PowerfulTS/deploy/tsmusicbot/issue-15-nickname.patch
git apply /path/to/PowerfulTS/deploy/tsmusicbot/issue-15-nickname.patch
npm ci
npx vitest run src/bot/manager-identity.test.ts src/ts-protocol/client-nickname.test.ts
npx tsc --noEmit
```

按原部署方式重新构建并重建 TSMusicBot 容器，保留其 data 卷；PowerfulTS 也需要
重新构建前后端。无需删除账号、VoiceBot 归属记录或已有 identity。
更新后验证失败重试及容器重启时 identity 不变，再测试原先无法加入通话的账号。
