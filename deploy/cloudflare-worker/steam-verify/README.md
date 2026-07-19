# Steam OpenID 验签反代 Worker

国内服务器（阿里云等）访问 `steamcommunity.com` 被 GFW 阻断，而 Steam OpenID 绑定的
**服务器端验签**必须 POST 到 `https://steamcommunity.com/openid/login`。本 Worker 在
Cloudflare 边缘中转该请求，让国内服务器也能完成绑定验签。

> 只有「服务器验签」走 Worker。用户浏览器打开 Steam 授权页那一步不经 Worker（浏览器可达）。

## 部署（任选一种）

### 方式 A：Cloudflare Dashboard（推荐，免命令行）

1. 登录 https://dash.cloudflare.com → 左侧 **Workers & Pages** → **Create** → **Worker**
2. 取个名字（如 `powerfults-steam-verify`）→ **Deploy** → 再点 **Edit code**
3. 把本目录 `index.js` 的全部内容粘贴进去覆盖默认代码 → 右上角 **Deploy**
4. 部署后得到一个 URL，形如 `https://powerfults-steam-verify.<你的子域>.workers.dev`

### 方式 B：wrangler CLI

```bash
cd deploy/cloudflare-worker/steam-verify
npx wrangler login          # 浏览器授权一次
npx wrangler deploy
# 输出会给出 https://powerfults-steam-verify.<子域>.workers.dev
```

## 接入后端

把 Worker URL 填入生产 `backend/.env`（或管理后台「系统设置 → Steam OpenID 验签端点」热重载）：

```
STEAM_OPENID_VERIFY_ENDPOINT=https://powerfults-steam-verify.<你的子域>.workers.dev
```

填完重启 backend（或经 admin 热重载）即可。

## 国内可达性

- `*.workers.dev` 子域国内多数情况可达（Cloudflare 边缘节点），先直接用。
- 若个别地区不稳，可在 CF Dashboard → 该 Worker → **Settings → Triggers → Custom Domains**
  绑一个托管在 Cloudflare 的自定义域名（需要该域名已托管在 CF）。
- 不要把 Worker URL 配成 IP 或 `steamcommunity.com` 本身。

## 验证

部署后在服务器上 curl 一下确认可达：

```bash
curl -sS -o /dev/null -w "%{http_code}\n" -X POST https://<worker-url> --max-time 15
# 期望 400（Steam 返回的参数错误）或 200，只要不是 000/超时即可，说明 Worker 链路通
```
