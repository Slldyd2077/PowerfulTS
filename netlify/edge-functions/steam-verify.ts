/**
 * PowerfulTS Steam OpenID 验签反代 (Netlify Edge Function, Deno 运行时)
 *
 * 背景：国内 ECS 访问 steamcommunity.com 被 GFW 阻断，而 Steam OpenID 绑定的
 * 【服务器端验签】（check_authentication）必须 POST 到
 * https://steamcommunity.com/openid/login。本 Edge Function 在 Netlify 边缘（境外）中转该 POST。
 *
 * 为什么用 Netlify 而非 CF Worker：*.workers.dev 在国内 ECS 也被墙，而 *.netlify.app 可达。
 *
 * 部署后 URL 形如 https://<site>.netlify.app/steam-verify，填入后端 STEAM_OPENID_VERIFY_ENDPOINT。
 * 只有「服务器验签」走这里；用户浏览器打开 Steam 授权页不经此。
 */
const TARGET = "https://steamcommunity.com/openid/login";

export default async (request: Request): Promise<Response> => {
  // 只透传 POST（后端验签用）；其余方法 405，避免被滥用为通用代理
  if (request.method !== "POST") {
    return new Response("Method Not Allowed", { status: 405 });
  }
  let body: string;
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
};
