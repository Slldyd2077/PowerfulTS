"""Steam 集成路由。

绑定走 Steam OpenID 2.0（弹窗回传 postMessage，不依赖前端地址配置）。
查询走 services.steam_client.SteamClient（app.state 单例）。
好友共同游戏需互关好友关系（FriendService.check_mutual_friends）。
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Annotated
from urllib.parse import parse_qs, urlparse

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..deps import get_current_account
from ..models import Account, Friend
from ..services.friend_service import FriendService
from ..services.steam_client import SteamClient

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/steam", tags=["steam"])


def get_steam(request: Request) -> SteamClient:
    """单例 SteamClient（随 app.state 生命周期；admin 热重载替换该引用）。"""
    return request.app.state.steam


SteamDep = Annotated[SteamClient, Depends(get_steam)]
AccountDep = Annotated[Account, Depends(get_current_account)]


def _binding_info(account: Account) -> dict:
    """账号的 Steam 绑定摘要。"""
    return {
        "bound": bool(account.steamid64),
        "steamid64": account.steamid64,
        "persona": account.steam_persona,
        "avatar_url": account.steam_avatar_url,
        "profile_url": account.steam_profile_url,
        "bound_at": account.steam_bound_at.isoformat() if account.steam_bound_at else None,
    }


def _icon_url(appid: object, img_icon_url: object) -> str:
    """构造游戏图标 URL（GetOwnedGames 返回 img_icon_url 哈希；空则空串）。"""
    if not img_icon_url:
        return ""
    return (
        f"https://media.steampowered.com/steamcommunity/public/images/apps/"
        f"{appid}/{img_icon_url}.jpg"
    )


def _not_configured() -> HTTPException:
    return HTTPException(status_code=502, detail="Steam 未配置 API Key，请联系管理员")


# ───────────────────────── OpenID 绑定 ─────────────────────────


@router.post("/auth/url")
async def steam_auth_url(request: Request, account: AccountDep, steam: SteamDep):
    """生成 Steam OpenID 跳转 URL（state 编码 account_id；return_to/realm 留空时从请求推断）。"""
    if not steam.configured:
        raise _not_configured()
    if not steam.openid_configured:
        raise HTTPException(status_code=502, detail="未配置 STEAM_OPENID_STATE_SECRET，无法安全绑定")
    base_url = str(request.base_url)
    return_to_base, realm = steam.resolve_return_to(base_url)
    state = steam.issue_state(account.id)
    url = steam.build_auth_url(state, return_to_base, realm)
    return {"url": url}


@router.get("/auth/callback", response_class=HTMLResponse)
async def steam_auth_callback(
    request: Request,
    steam: SteamDep,
    db: AsyncSession = Depends(get_db),
):
    """Steam OpenID 回调（无需登录态；account_id 从 state 解出）。

    弹窗回传模式：返回一段 HTML，用 postMessage 通知前端弹窗绑定结果并关闭窗口。
    避免依赖前端公网地址（dev/生产统一）。
    """
    params = dict(request.query_params)
    # state 必须取自已被 Steam 签名的 openid.return_to（顶层 state query 未签名，不可信）
    return_to = params.get("openid.return_to", "")
    try:
        state = parse_qs(urlparse(return_to).query).get("state", [""])[0]
    except Exception:
        state = ""

    def _fail(error: str) -> HTMLResponse:
        return HTMLResponse(_callback_html(False, error))

    account_id = steam.verify_state(state)
    if account_id is None:
        return _fail("Steam 登录状态已过期，请重新绑定")

    steamid = await steam.verify_callback(params)
    if not steamid:
        return _fail("Steam 登录验证失败，请重试")

    # 唯一性：一个 Steam 账号只能绑一个站内账号（DB 级 UNIQUE INDEX 兜底，防 TOCTOU）
    clash = await db.scalar(
        select(Account).where(Account.steamid64 == steamid, Account.id != account_id)
    )
    if clash is not None:
        return _fail("该 Steam 账号已被其他用户绑定")

    account = await db.get(Account, account_id)
    if account is None:
        return _fail("账号不存在")

    account.steamid64 = steamid
    account.steam_bound_at = datetime.now()
    # 若已配置 API Key，顺便取昵称/头像/资料链接；否则仅存 steamid（后续 /me 会降级）
    if steam.configured:
        summaries = await steam.get_player_summaries([steamid])
        summary = summaries.get(steamid)
        if summary:
            account.steam_persona = summary.get("personaname")
            account.steam_avatar_url = summary.get("avatarfull")
            account.steam_profile_url = summary.get("profileurl")
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        return _fail("该 Steam 账号已被其他用户绑定")
    return HTMLResponse(_callback_html(True, None))


def _callback_html(success: bool, error: str | None) -> str:
    """弹窗绑定结果页：postMessage 回传前端，并尝试关闭弹窗。"""
    payload = "true" if success else "false"
    msg = "绑定成功，正在返回…" if success else f"绑定失败：{error or '未知错误'}"
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>Steam 绑定</title>
<style>body{{font-family:system-ui,sans-serif;text-align:center;padding:60px;color:#333}}
.ok{{color:#22c55e}}.err{{color:#ef4444}}</style></head>
<body><p class="{'ok' if success else 'err'}" style="font-size:1.2em">{msg}</p>
<script>
(function(){{
  var data = {{type: 'steam_bound', success: {payload}}};
  try {{ window.opener.postMessage(data, '*'); }} catch(e) {{}}
  setTimeout(function(){{
    try {{ window.close(); }} catch(e) {{}}
    if (!window.opener) {{ window.location.href = '/'; }}
  }}, 600);
}})();
</script></body></html>"""


@router.delete("/auth")
async def steam_unbind(account: AccountDep, db: AsyncSession = Depends(get_db)):
    """解绑 Steam（清空 5 个字段）。"""
    account.steamid64 = None
    account.steam_persona = None
    account.steam_avatar_url = None
    account.steam_profile_url = None
    account.steam_bound_at = None
    await db.commit()
    return {"success": True}


# ───────────────────────── 我的 Steam ─────────────────────────


@router.get("/me")
async def steam_me(account: AccountDep, steam: SteamDep):
    """我的 Steam 概况（绑定信息 + 实时在线状态/当前游戏）。"""
    info = _binding_info(account)
    status = None
    if account.steamid64 and steam.configured:
        summaries = await steam.get_player_summaries([account.steamid64])
        status = steam.derive_status(summaries.get(account.steamid64))
    return {**info, "status": status}


@router.get("/me/games")
async def steam_my_games(account: AccountDep, steam: SteamDep):
    """我的游戏库（按总时长降序，含近两周时长与图标）。"""
    if not account.steamid64:
        raise HTTPException(status_code=400, detail="尚未绑定 Steam 账号")
    if not steam.configured:
        raise _not_configured()
    games = await steam.get_owned_games(account.steamid64)
    if games is None:
        raise HTTPException(status_code=502, detail="Steam 暂时不可达，请稍后再试")
    games_sorted = sorted(games, key=lambda g: int(g.get("playtime_forever", 0) or 0), reverse=True)
    return {"games": [
        {
            "appid": g.get("appid"),
            "name": g.get("name", f"App {g.get('appid')}"),
            "playtime_forever_hours": round(int(g.get("playtime_forever", 0) or 0) / 60, 1),
            "playtime_2weeks_hours": round(int(g.get("playtime_2weeks", 0) or 0) / 60, 1),
            "icon_url": _icon_url(g.get("appid"), g.get("img_icon_url")),
        }
        for g in games_sorted
    ]}


# ───────────────────────── 好友 Steam ─────────────────────────


@router.get("/friends")
async def steam_friends(account: AccountDep, steam: SteamDep, db: AsyncSession = Depends(get_db)):
    """好友的 Steam 在线状态（单向好友；未绑定 Steam 的好友也列出但标记未绑）。"""
    rows = (
        await db.execute(
            select(Account.id, Account.ts_nickname, Account.steamid64, Account.steam_persona,
                   Account.steam_avatar_url)
            .join(Friend, Friend.friend_account_id == Account.id)
            .where(Friend.account_id == account.id)
        )
    ).all()
    # 仅对已绑定好友批量查 Steam 摘要（未绑定的不消耗 API）
    bound: list[tuple] = [r for r in rows if r.steamid64]
    summaries: dict[str, dict] = {}
    if bound and steam.configured:
        summaries = await steam.get_player_summaries([r.steamid64 for r in bound])

    friends = []
    for r in rows:
        entry = {
            "account_id": r.id,
            "ts_nickname": r.ts_nickname,
            "bound": bool(r.steamid64),
            "persona": r.steam_persona,
            "avatar_url": r.steam_avatar_url,
            "status": None,
        }
        if r.steamid64:
            entry["status"] = steam.derive_status(summaries.get(r.steamid64))
        friends.append(entry)
    return {"friends": friends}


@router.get("/friends/{friend_account_id}/common-games")
async def steam_common_games(
    friend_account_id: int,
    account: AccountDep,
    steam: SteamDep,
    db: AsyncSession = Depends(get_db),
):
    """与某好友的共同游戏（需互关好友；双方均绑定 Steam）。返回交集 + 双方时长。"""
    svc = FriendService(db)
    if not await svc.check_mutual_friends(account.id, friend_account_id):
        raise HTTPException(status_code=403, detail="仅互关好友可查看共同游戏")
    friend = await db.get(Account, friend_account_id)
    if friend is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    if not account.steamid64 or not friend.steamid64:
        raise HTTPException(status_code=400, detail="双方均需绑定 Steam 账号")
    if not steam.configured:
        raise _not_configured()

    my_games, friend_games = await asyncio.gather(
        steam.get_owned_games(account.steamid64),
        steam.get_owned_games(friend.steamid64),
    )
    if my_games is None or friend_games is None:
        raise HTTPException(status_code=502, detail="Steam 暂时不可达，请稍后再试")

    my_map = {int(g["appid"]): g for g in my_games if "appid" in g}
    friend_map = {int(g["appid"]): g for g in friend_games if "appid" in g}
    common_ids = set(my_map) & set(friend_map)

    common = []
    for appid in common_ids:
        mg = my_map[appid]
        fg = friend_map[appid]
        my_h = int(mg.get("playtime_forever", 0) or 0) / 60
        fr_h = int(fg.get("playtime_forever", 0) or 0) / 60
        common.append({
            "appid": appid,
            "name": mg.get("name") or fg.get("name") or f"App {appid}",
            "my_hours": round(my_h, 1),
            "friend_hours": round(fr_h, 1),
            "icon_url": _icon_url(appid, mg.get("img_icon_url") or fg.get("img_icon_url")),
        })
    # 按双方总时长降序（最能体现"共同爱好"）
    common.sort(key=lambda x: x["my_hours"] + x["friend_hours"], reverse=True)
    return {
        "friend_nickname": friend.ts_nickname,
        "friend_persona": friend.steam_persona,
        "common_games": common,
        "total": len(common),
    }


# ───────────────────────── 全服排行 ─────────────────────────


@router.get("/leaderboard")
async def steam_leaderboard(
    account: AccountDep,
    steam: SteamDep,
    game: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """全服 Steam 玩家排行。game=appid 时按单游戏时长；否则按总时长。"""
    if not steam.configured:
        raise _not_configured()
    rows = (
        await db.execute(
            select(Account.id, Account.ts_nickname, Account.steam_persona,
                   Account.steam_avatar_url, Account.steamid64)
            .where(Account.steamid64.is_not(None))
            .order_by(Account.ts_nickname)
        )
    ).all()
    if not rows:
        return {"entries": [], "game": game}

    sem = asyncio.Semaphore(5)  # 限流并发拉取游戏库，避免 burst 触发 Steam 限流

    async def fetch(row):
        async with sem:
            games = await steam.get_owned_games(row.steamid64)
        if games is None:
            return None
        if game:
            target = next((g for g in games if str(g.get("appid")) == game), None)
            hours = (int(target.get("playtime_forever", 0) or 0) / 60) if target else 0.0
            return {
                "account_id": row.id, "ts_nickname": row.ts_nickname,
                "persona": row.steam_persona, "avatar_url": row.steam_avatar_url,
                "hours": round(hours, 1),
            }
        total_min = sum(int(g.get("playtime_forever", 0) or 0) for g in games)
        return {
            "account_id": row.id, "ts_nickname": row.ts_nickname,
            "persona": row.steam_persona, "avatar_url": row.steam_avatar_url,
            "hours": round(total_min / 60, 1),
            "game_count": len(games),
        }

    results = await asyncio.gather(*[fetch(r) for r in rows])
    entries = [r for r in results if r is not None and r["hours"] > 0]
    entries.sort(key=lambda x: x["hours"], reverse=True)
    return {"entries": entries, "game": game}
