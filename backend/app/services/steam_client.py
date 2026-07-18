"""Steam Web API + OpenID 2.0 客户端。

绑定走 Steam OpenID 2.0（stateless 验签，无需落库存 state），
数据查询走 Steam Web API（玩家摘要 / 游戏库）。

未配置 API Key 或 Steam 不可达时优雅降级（warning 不抛），与 napcat/netease 一致。
结构对照 napcat_client.py：__init__ 持 httpx.AsyncClient 单例 + 方法 try/except 优雅降级 + close()。
缓存对照 tsmusic_client._meta_cache：内存 FIFO + TTL。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import re
import time
from collections import OrderedDict
from urllib.parse import urlencode, urlparse

import httpx

logger = logging.getLogger(__name__)

STEAM_OPENID_ENDPOINT = "https://steamcommunity.com/openid/login"
STEAM_OPENID_NS = "http://specs.openid.net/auth/2.0"
IDENTITY_SELECT = "http://specs.openid.net/auth/2.0/identifier_select"

# personastate 字段映射（口径取自 S-QC-Bot steam_utils.steam_api）
PERSONA_STATE = {
    0: "离线",
    1: "在线",
    2: "忙碌",
    3: "离开",
    4: "打瞌睡",
    5: "想交易",
    6: "想玩游戏",
}

# 注意：state 签名密钥不设默认值——未配置 STEAM_OPENID_STATE_SECRET 时拒绝签发（防伪造绑定劫持）

_SUMMARY_TTL = 90          # 秒：在线状态变化较快
_GAMES_TTL = 6 * 3600      # 秒：游戏库变化慢
_CACHE_MAX = 1024          # 每类缓存 FIFO 上限
_SUMMARY_BATCH = 100       # GetPlayerSummaries 单次最多 100 个 steamid

_CLAIMED_ID_RE = re.compile(r"openid/id/(\d{17})")


def _b64e(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64d(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


class SteamClient:
    """Steam Web API + OpenID 2.0 客户端（单例，随 app.state 生命周期）。"""

    def __init__(
        self,
        api_key: str = "",
        openid_return_url: str = "",
        openid_realm: str = "",
        state_secret: str = "",
        timeout: float = 10.0,
    ) -> None:
        self._key = (api_key or "").strip()
        self._return_url = (openid_return_url or "").strip()
        self._realm = (openid_realm or "").strip()
        # state 签名密钥：无默认值，未配置则拒绝签发 state（防伪造绑定劫持）
        self._state_secret = (state_secret or "").strip()
        self._http = httpx.AsyncClient(base_url="https://api.steampowered.com", timeout=timeout)
        # 内存缓存：steamid -> (timestamp, value)，LRU + TTL（OrderedDict 按访问顺序淘汰）
        self._summary_cache: OrderedDict[str, tuple[float, dict]] = OrderedDict()
        self._games_cache: OrderedDict[str, tuple[float, list]] = OrderedDict()
        # TS 联动快照：ts_nickname -> 当前游戏名（后台 task 单写，监控线程只读）
        self._current_game_by_nick: dict[str, str] = {}

    @property
    def configured(self) -> bool:
        """是否配置了 API Key（未配置则 Steam 查询类功能降级）。"""
        return bool(self._key)

    @property
    def openid_configured(self) -> bool:
        """是否配置了 OpenID state 密钥（未配置则拒绝绑定，防伪造）。"""
        return bool(self._state_secret)

    # ───────────────────────── OpenID 2.0 ─────────────────────────

    def resolve_return_to(self, request_base_url: str) -> tuple[str, str]:
        """确定 (return_to_base, realm)。base 不含 state（由 build_auth_url 拼接）。

        return_url 配置为空时从请求推断（dev 友好），realm 留空则取 return_to 的 scheme://host。
        """
        base = self._return_url or (request_base_url.rstrip("/") + "/api/steam/auth/callback")
        realm = self._realm
        if not realm:
            parsed = urlparse(base)
            realm = f"{parsed.scheme}://{parsed.netloc}"
        return base, realm

    def issue_state(self, account_id: int, ttl: int = 600) -> str:
        """签发一次性 state：payload=account_id:expiry，HMAC-SHA256 签名，base64url 编码。
        未配置 state 密钥时返回空串（调用方应阻止绑定流程）。"""
        if not self._state_secret:
            logger.error("Steam OpenID state 密钥未配置（STEAM_OPENID_STATE_SECRET），拒绝签发")
            return ""
        exp = int(time.time()) + ttl
        payload = f"{account_id}:{exp}".encode()
        sig = hmac.new(self._state_secret.encode(), payload, hashlib.sha256).digest()
        return _b64e(payload) + "." + _b64e(sig)

    def verify_state(self, state: str) -> int | None:
        """校验 state 的 HMAC 与过期时间，返回 account_id（失败/过期返回 None）。"""
        if not self._state_secret or not state:
            return None
        try:
            payload_b64, sig_b64 = state.split(".", 1)
            payload = _b64d(payload_b64)
            sig = _b64d(sig_b64)
        except Exception:
            return None
        expected = hmac.new(self._state_secret.encode(), payload, hashlib.sha256).digest()
        if not hmac.compare_digest(sig, expected):
            return None
        try:
            account_id_str, exp_str = payload.decode().split(":", 1)
            if int(time.time()) > int(exp_str):
                return None
            return int(account_id_str)
        except Exception:
            return None

    def build_auth_url(self, state: str, return_to_base: str, realm: str) -> str:
        """拼 Steam OpenID 2.0 checkid_setup URL；state 经 return_to 的 query 透传。"""
        sep = "&" if "?" in return_to_base else "?"
        return_to = f"{return_to_base}{sep}state={state}"
        params = {
            "openid.ns": STEAM_OPENID_NS,
            "openid.mode": "checkid_setup",
            "openid.return_to": return_to,
            "openid.realm": realm,
            "openid.identity": IDENTITY_SELECT,
            "openid.claimed_id": IDENTITY_SELECT,
        }
        return STEAM_OPENID_ENDPOINT + "?" + urlencode(params)

    async def verify_callback(self, openid_params: dict[str, str]) -> str | None:
        """stateless 验签：把回调 openid.* 参数 + mode=check_authentication POST 给 Steam，
        响应含 is_valid:true 即通过；从 claimed_id 提取 steamid64 返回。失败返回 None。"""
        params = {k: v for k, v in openid_params.items() if k.startswith("openid.")}
        params["openid.mode"] = "check_authentication"
        try:
            resp = await self._http.post(STEAM_OPENID_ENDPOINT, data=params)
            if resp.status_code != 200:
                logger.warning("Steam OpenID 验签 HTTP %s", resp.status_code)
                return None
            body = resp.text
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("Steam OpenID 验签请求失败: %s", exc)
            return None
        if "is_valid:true" not in body:
            logger.warning("Steam OpenID 验签未通过: %s", body[:200])
            return None
        claimed = openid_params.get("openid.claimed_id", "")
        match = _CLAIMED_ID_RE.search(claimed)
        return match.group(1) if match else None

    # ───────────────────────── Web API ─────────────────────────

    @staticmethod
    def _cache_get(cache: dict, key: str, ttl: int):
        entry = cache.get(key)
        if entry is None:
            return None
        ts, val = entry
        if time.time() - ts > ttl:
            return None
        return val

    @staticmethod
    def _cache_set(cache: OrderedDict, key: str, val) -> None:
        cache[key] = (time.time(), val)
        cache.move_to_end(key)  # 更新/新增都移到末尾，确保按访问顺序淘汰（LRU）
        while len(cache) > _CACHE_MAX:
            cache.popitem(last=False)  # 淘汰最久未访问的一条

    async def get_player_summaries(self, steamids: list[str]) -> dict[str, dict]:
        """批量取玩家摘要，返回 {steamid: summary}。带 90s 缓存；>100 个分批。"""
        if not self._key or not steamids:
            return {}
        result: dict[str, dict] = {}
        todo: list[str] = []
        for sid in steamids:
            cached = self._cache_get(self._summary_cache, sid, _SUMMARY_TTL)
            if cached is not None:
                result[sid] = cached
            else:
                todo.append(sid)
        for i in range(0, len(todo), _SUMMARY_BATCH):
            batch = todo[i : i + _SUMMARY_BATCH]
            try:
                resp = await self._http.get(
                    "/ISteamUser/GetPlayerSummaries/v2/",
                    params={"key": self._key, "steamids": ",".join(batch)},
                )
                resp.raise_for_status()
                players = resp.json().get("response", {}).get("players", [])
            except (httpx.HTTPError, ValueError) as exc:
                logger.warning("Steam GetPlayerSummaries 失败: %s", exc)
                players = []
            for player in players:
                sid = player.get("steamid")
                if sid:
                    self._cache_set(self._summary_cache, sid, player)
                    result[sid] = player
        return result

    async def get_owned_games(self, steamid: str) -> list[dict] | None:
        """取玩家游戏库（含 name + playtime_2weeks + playtime_forever）。

        私密资料 / 无游戏返回空列表；网络失败返回 None（调用方可区分）。
        带 6h 缓存。
        """
        if not self._key:
            return None
        cached = self._cache_get(self._games_cache, steamid, _GAMES_TTL)
        if cached is not None:
            return cached
        try:
            resp = await self._http.get(
                "/IPlayerService/GetOwnedGames/v1/",
                params={
                    "key": self._key,
                    "steamid": steamid,
                    "include_appinfo": "true",
                    "include_played_free_games": "true",
                },
            )
            resp.raise_for_status()
            data = resp.json().get("response", {})
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("Steam GetOwnedGames 失败 (%s): %s", steamid, exc)
            return None
        games = data.get("games") if data else None
        if games is None:
            games = []  # 私密或空库，缓存空列表避免反复请求
        self._cache_set(self._games_cache, steamid, games)
        return games

    # ───────────────────────── 状态派生 ─────────────────────────

    @staticmethod
    def derive_status(summary: dict | None) -> dict:
        """从 player summary 派生统一状态视图（state 文本与 ts3_monitor 对齐：游戏中/在线/离线）。"""
        if not summary:
            return {"online": False, "state": "离线", "current_game": None}
        persona_state = int(summary.get("personastate", 0) or 0)
        game = summary.get("gameextrainfo") or None
        if game:
            state_text = "游戏中"
        else:
            state_text = PERSONA_STATE.get(persona_state, "在线" if persona_state > 0 else "离线")
        return {
            "online": persona_state > 0,
            "state": state_text,
            "current_game": game,
            "persona_state": persona_state,
        }

    # ───────────────────────── TS 联动快照 ─────────────────────────

    def update_status_snapshot(self, game_by_nick: dict[str, str | None]) -> None:
        """后台 task 刷新当前游戏快照。值非空表示正在玩该游戏。"""
        self._current_game_by_nick = {k: v for k, v in game_by_nick.items() if v}

    def get_current_game_sync(self, nickname: str) -> str | None:
        """供 TS 监控线程同步调用：返回该昵称当前 Steam 游戏，无则 None。只读内存。"""
        return self._current_game_by_nick.get(nickname)

    async def close(self) -> None:
        await self._http.aclose()
