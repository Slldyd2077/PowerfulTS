"""PowerfulTS-side bot idle enforcement.

TSMusicBot exposes idle settings, but keeping the actual channel occupancy check
here lets us use the native TS3 ServerQuery monitor rules and handle multi-bot
channels consistently: bots do not count as listeners for each other.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Iterable
from typing import TYPE_CHECKING

from ..core.config import Settings
from .ts3_query import TS3QueryClient

if TYPE_CHECKING:
    from .tsmusic_client import TSMusicClient

logger = logging.getLogger(__name__)

DEFAULT_POLL_INTERVAL = 30


def _int_or_none(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _norm_nickname(value: object) -> str:
    return str(value or "").strip()


def _is_regular_client(client: dict) -> bool:
    return str(client.get("client_type", "0")) != "1"


def channel_human_count(clients: Iterable[dict], cid: int, bot_nicknames: set[str]) -> int:
    """Count non-bot regular TS clients in a channel."""
    count = 0
    for client in clients:
        if not _is_regular_client(client):
            continue
        if _int_or_none(client.get("cid")) != cid:
            continue
        if _norm_nickname(client.get("client_nickname")) in bot_nicknames:
            continue
        count += 1
    return count


def bot_channel_map(clients: Iterable[dict], bot_nicknames: set[str]) -> dict[str, int]:
    """Return bot nickname -> current cid for visible connected bot clients."""
    channels: dict[str, int] = {}
    for client in clients:
        if not _is_regular_client(client):
            continue
        nick = _norm_nickname(client.get("client_nickname"))
        if nick not in bot_nicknames:
            continue
        cid = _int_or_none(client.get("cid"))
        if cid is not None:
            channels[nick] = cid
    return channels


def fetch_ts_clients(settings: Settings) -> list[dict]:
    """Fetch raw TS3 clientlist with a short-lived ServerQuery connection."""
    conn = TS3QueryClient(settings.ts3_host, settings.ts3_query_port)
    try:
        conn.connect()
        conn.send(
            "login",
            client_login_name=settings.ts3_query_user,
            client_login_password=settings.ts3_query_password,
        )
        conn.send("use", sid=settings.ts3_sid)
        return conn.send("clientlist", uid=True)
    finally:
        conn.close()


class BotIdleManager:
    """Background task for auto-pause and auto-disconnect when bot channels empty."""

    def __init__(
        self,
        settings: Settings,
        tsmusic: TSMusicClient,
        poll_interval: int = DEFAULT_POLL_INTERVAL,
    ) -> None:
        self._settings = settings
        self._tsmusic = tsmusic
        self._poll_interval = max(5, poll_interval)
        self._task: asyncio.Task | None = None
        self._idle_since: dict[str, float] = {}
        self._auto_paused: set[str] = set()

    def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._task = asyncio.create_task(self._run(), name="bot-idle-manager")
        logger.info("bot idle manager 已启动")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None
        logger.info("bot idle manager 已停止")

    async def _run(self) -> None:
        while True:
            try:
                await self.poll_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("bot idle manager 巡检异常")
            await asyncio.sleep(self._poll_interval)

    async def poll_once(self) -> None:
        if not self._settings.ts3_query_user or not self._settings.ts3_query_password:
            return

        bot_settings = await self._tsmusic.get_bot_settings()
        idle_timeout_minutes = _int_or_none(bot_settings.get("idleTimeoutMinutes")) or 0
        auto_pause = bool(bot_settings.get("autoPauseOnEmpty", False))
        if idle_timeout_minutes <= 0:
            self._idle_since.clear()
        if idle_timeout_minutes <= 0 and not auto_pause:
            self._auto_paused.clear()
            return

        bots = [
            bot for bot in await self._tsmusic.list_bots()
            if bot.get("id") and bot.get("status") == "connected"
        ]
        if not bots:
            self._idle_since.clear()
            self._auto_paused.clear()
            return

        nick_results = await asyncio.gather(
            *(self._tsmusic.get_bot_nickname(str(bot["id"])) for bot in bots),
            return_exceptions=True,
        )
        bot_nick_by_id: dict[str, str] = {}
        for bot, result in zip(bots, nick_results, strict=False):
            if isinstance(result, Exception):
                logger.warning("获取 bot %s 昵称失败: %s", bot.get("id"), result)
                continue
            nick = _norm_nickname(result)
            if nick:
                bot_nick_by_id[str(bot["id"])] = nick

        if not bot_nick_by_id:
            return

        clients = await asyncio.to_thread(fetch_ts_clients, self._settings)
        bot_nicks = set(bot_nick_by_id.values())
        channels_by_nick = bot_channel_map(clients, bot_nicks)
        now = time.monotonic()
        active_bot_ids = {str(bot["id"]) for bot in bots}

        for stale_bot_id in set(self._idle_since) - active_bot_ids:
            self._idle_since.pop(stale_bot_id, None)
            self._auto_paused.discard(stale_bot_id)

        for bot in bots:
            bot_id = str(bot["id"])
            nick = bot_nick_by_id.get(bot_id)
            cid = channels_by_nick.get(nick or "")
            if cid is None:
                self._idle_since.pop(bot_id, None)
                self._auto_paused.discard(bot_id)
                continue

            humans = channel_human_count(clients, cid, bot_nicks)
            if humans > 0:
                self._idle_since.pop(bot_id, None)
                if bot_id in self._auto_paused:
                    await self._resume_auto_paused(bot_id)
                continue

            if auto_pause and bot.get("playing") and not bot.get("paused") and bot_id not in self._auto_paused:
                await self._pause_empty_bot(bot_id, nick or bot_id)

            if idle_timeout_minutes <= 0:
                continue

            idle_since = self._idle_since.setdefault(bot_id, now)
            if now - idle_since < idle_timeout_minutes * 60:
                continue

            logger.info(
                "bot %s 频道 cid=%s 无非 bot 用户超过 %s 分钟，自动下线",
                nick or bot_id,
                cid,
                idle_timeout_minutes,
            )
            await self._tsmusic.stop_bot(bot_id)
            self._idle_since.pop(bot_id, None)
            self._auto_paused.discard(bot_id)

    async def _pause_empty_bot(self, bot_id: str, label: str) -> None:
        try:
            await self._tsmusic.pause(bot_id)
            self._auto_paused.add(bot_id)
            logger.info("bot %s 频道无人，已自动暂停", label)
        except Exception:
            logger.warning("bot %s 自动暂停失败", label, exc_info=True)

    async def _resume_auto_paused(self, bot_id: str) -> None:
        try:
            await self._tsmusic.resume(bot_id)
        except Exception:
            logger.warning("bot %s 自动恢复失败", bot_id, exc_info=True)
        finally:
            self._auto_paused.discard(bot_id)
