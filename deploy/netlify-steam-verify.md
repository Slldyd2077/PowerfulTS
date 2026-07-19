# Steam OpenID 验签反代 — Netlify Edge Function（国内可用、免费）

国内服务器（阿里云等）访问 `steamcommunity.com` 被 GFW 阻断，且 `*.workers.dev` 也被墙。
实测 `*.netlify.app` 在国内 ECS 可达（0.6s、泛解析），故用 Netlify Edge Function 做反代。

> 逻辑与 `deploy/cloudflare-worker/steam-verify/` 完全一致，只是换了运行时（Deno Edge Function）。
> 只有「服务器验签」走这里；用户浏览器打开 Steam 授权页不经此。

## 部署（免费，约 3 分钟）

1. 登 https://app.netlify.com → **Add new site** → **Import an existing project**
2. 连 GitHub → 选 `Slldyd2077/PowerfulTS` 仓库
3. 构建配置：Netlify 会自动读仓库根的 `netlify.toml`（build 空、publish 空，只部署 Edge Function）。
   Site name 取个名，如 `powerfults-steam-verify` → **Deploy**
4. 部署完成后拿到站点域名：`https://powerfults-steam-verify.netlify.app`
5. Edge Function 完整 URL = `https://<site>.netlify.app/steam-verify`

## 接入后端

把上一步的完整 URL 填入生产 `backend/.env`（或管理后台「系统设置 → Steam OpenID 验签端点」热重载）：

```
STEAM_OPENID_VERIFY_ENDPOINT=https://powerfults-steam-verify.netlify.app/steam-verify
```

重启 backend（或经 admin 热重载）即可。

## 验证（在服务器上）

```bash
# 期望非 000/非超时（Steam 对空 POST 通常返回 400），说明 Netlify 链路通
curl -sS -o /dev/null -w "%{http_code} %{time_total}s\n" -X POST https://<site>.netlify.app/steam-verify --max-time 15
```

## 备注

- Netlify Edge Functions 免费额度：125k 次/月、100h 执行时长，绑定的实际验签量极小，远够用。
- 后续给仓库 push 代码，Netlify 会自动重新部署该 Edge Function。
- 若哪天 `*.netlify.app` 也被墙，可换 `*.zeabur.app`（实测也可达，但免费额度是计时 credit）。
