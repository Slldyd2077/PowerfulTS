/**
 * PowerfulTS Steam OpenID 验签反代 (Cloudflare Worker)
 *
 * 背景：国内 ECS 访问 steamcommunity.com 被 GFW 阻断（TCP 连不上），
 * 而 Steam OpenID 绑定的【服务器端验签】（check_authentication）必须 POST 到
 * https://steamcommunity.com/openid/login。本 Worker 在 Cloudflare 边缘中转这个 POST，
 * 让国内服务器也能完成验签。
 *
 * 注意：只有「服务器验签」走本 Worker。用户浏览器发起授权（访问 Steam 登录页）不经过它
 * （浏览器可达 steamcommunity.com）。
 *
 * 部署后把 Worker URL 填入后端 .env 的 STEAM_OPENID_VERIFY_ENDPOINT。
 */
const TARGET = "https://steamcommunity.com/openid/login";

export default {
  async fetch(request) {
    // 只透传 POST（后端验签用）；其余方法返回 405，避免被滥用为通用代理
    if (request.method !== "POST") {
      return new Response("Method Not Allowed", { status: 405 });
    }
    let body;
    try {
      body = await request.text();
    } catch {
      return new Response("Bad Request", { status: 400 });
    }
    const resp = await fetch(TARGET, {
      method: "POST",
      headers: {
        "Content-Type": request.headers.get("Content-Type") || "application/x-www-form-urlencoded",
        "User-Agent": "PowerfulTS-SteamVerify/1.0",
      },
      body,
    });
    return new Response(resp.body, {
      status: resp.status,
      headers: { "Content-Type": resp.headers.get("Content-Type") || "text/plain; charset=utf-8" },
    });
  },
};
