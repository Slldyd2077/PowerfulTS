"""每个账号一个网页通话 bot：用户在 TS 里的「网页分身」。

和音乐 bot 完全分开——归属只记在 voice_bots 表，不进 bot_ownerships，所以它不会
出现在音乐控制的实例列表里，也不参与点歌 / 共享 / 跟随那套逻辑。

生命周期：加入通话时按需创建并连接，挂断或浏览器断开后延迟收回（留一小段宽限期，
避免刷新页面或短暂断线就把 bot 踢下线再重连一遍）。
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Account, BotOwnership, VoiceBot
from .tsmusic_client import TSMusicClient

logger = logging.getLogger(__name__)

# 断开后多久真正把 bot 停掉。刷新页面/网络抖动会在这个窗口内重新接上。
RELEASE_GRACE_SECONDS = 20.0
# 等 bot 连上 TS 的上限。
CONNECT_TIMEOUT_SECONDS = 25.0
_CONNECT_POLL_SECONDS = 0.5


class VoiceBotError(RuntimeError):
    """开通话机器人失败，且原因可以直接展示给用户。"""


@dataclass
class _BotTarget:
    server_address: str
    server_port: int


async def _resolve_server_target(tsmusic: TSMusicClient, db: AsyncSession) -> _BotTarget:
    """通话 bot 连哪个 TS 服务器：照抄一个已有 bot 的配置。

    不用 settings.ts3_host：那是给 PowerfulTS 自己的 ServerQuery 用的（常是 127.0.0.1），
    而 bot 跑在 TSMusicBot 容器里，得用容器视角的地址（通常 host.docker.internal）。
    已有 bot 的配置就是现成的正确答案。
    """
    rows = await db.execute(select(BotOwnership.bot_id))
    for (bot_id,) in rows.all():
        config = await tsmusic.get_bot_config(bot_id)
        address = str(config.get("serverAddress") or "").strip()
        if address:
            try:
                port = int(config.get("serverPort") or 9987)
            except (TypeError, ValueError):
                port = 9987
            return _BotTarget(address, port)
    raise VoiceBotError("还没有任何机器人配置可参照，请先在「音乐控制」里创建一个机器人")


class VoiceBotManager:
    """按账号维护通话 bot 的创建、连接与延迟回收。"""

    def __init__(self, tsmusic_provider) -> None:
        self._tsmusic_provider = tsmusic_provider
        self._locks: dict[int, asyncio.Lock] = {}
        self._release_tasks: dict[int, asyncio.Task] = {}

    def _lock_for(self, account_id: int) -> asyncio.Lock:
        lock = self._locks.get(account_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[account_id] = lock
        return lock

    async def acquire(self, db: AsyncSession, account: Account) -> dict:
        """拿到（必要时创建并连接）该账号的通话 bot，返回 {botId, nickname}。"""
        tsmusic = self._tsmusic_provider()
        async with self._lock_for(account.id):
            self._cancel_release(account.id)
            bot_id = await self._ensure_bot(db, tsmusic, account)
            await self._ensure_connected(tsmusic, bot_id)
            return {"botId": bot_id, "nickname": account.ts_nickname}

    async def current_bot_id(self, db: AsyncSession, account_id: int) -> str | None:
        """已开通的通话 bot id（没有则 None）。不创建、不连接。"""
        row = await db.execute(
            select(VoiceBot.bot_id).where(VoiceBot.account_id == account_id)
        )
        found = row.first()
        return found[0] if found else None

    def schedule_release(self, account_id: int, bot_id: str) -> None:
        """浏览器断开后延迟停机；宽限期内重新 acquire 会取消这次停机。"""
        self._cancel_release(account_id)
        self._release_tasks[account_id] = asyncio.create_task(
            self._release_after_grace(account_id, bot_id)
        )

    async def release_now(self, account_id: int, bot_id: str) -> None:
        """用户明确挂断：立刻停机，不等宽限期。"""
        self._cancel_release(account_id)
        await self._stop(bot_id)

    def _cancel_release(self, account_id: int) -> None:
        task = self._release_tasks.pop(account_id, None)
        if task is not None and not task.done():
            task.cancel()

    async def _release_after_grace(self, account_id: int, bot_id: str) -> None:
        try:
            await asyncio.sleep(RELEASE_GRACE_SECONDS)
        except asyncio.CancelledError:
            return
        self._release_tasks.pop(account_id, None)
        await self._stop(bot_id)

    async def _stop(self, bot_id: str) -> None:
        try:
            await self._tsmusic_provider().stop_bot(bot_id)
            logger.info("通话 bot 已下线: %s", bot_id)
        except Exception:
            logger.warning("停止通话 bot 失败: %s", bot_id, exc_info=True)

    async def _ensure_bot(
        self, db: AsyncSession, tsmusic: TSMusicClient, account: Account
    ) -> str:
        recorded = await self.current_bot_id(db, account.id)
        upstream_ids = {b.get("id") for b in await tsmusic.list_bots()}
        if recorded and recorded in upstream_ids:
            return recorded

        if recorded:
            # 上游已经没有这个 bot（容器重建 / 被手工删掉），记录作废重建。
            logger.info("通话 bot %s 在上游已不存在，重新创建", recorded)
            await db.execute(
                VoiceBot.__table__.delete().where(VoiceBot.account_id == account.id)
            )
            await db.commit()

        target = await _resolve_server_target(tsmusic, db)
        try:
            created = await tsmusic.create_bot({
                "name": account.ts_nickname,
                "nickname": account.ts_nickname,
                "serverAddress": target.server_address,
                "serverPort": target.server_port,
                "defaultChannel": "",
                "channelPassword": "",
                "serverPassword": "",
            })
        except Exception as exc:
            raise VoiceBotError("创建通话机器人失败，请确认 TSMusicBot 正在运行") from exc

        bot_id = str(created.get("id") or "")
        if not bot_id:
            raise VoiceBotError("TSMusicBot 没有返回新机器人的 id")
        db.add(VoiceBot(account_id=account.id, bot_id=bot_id))
        await db.commit()
        logger.info("为账号 %s 创建通话 bot %s", account.ts_nickname, bot_id)
        return bot_id

    async def _ensure_connected(self, tsmusic: TSMusicClient, bot_id: str) -> None:
        if await self._is_connected(tsmusic, bot_id):
            return
        try:
            await tsmusic.start_bot(bot_id)
        except Exception as exc:
            raise VoiceBotError("通话机器人未能连接 TS 服务器") from exc

        waited = 0.0
        while waited < CONNECT_TIMEOUT_SECONDS:
            await asyncio.sleep(_CONNECT_POLL_SECONDS)
            waited += _CONNECT_POLL_SECONDS
            if await self._is_connected(tsmusic, bot_id):
                return
        raise VoiceBotError("通话机器人连接 TS 超时，请稍后重试")

    @staticmethod
    async def _is_connected(tsmusic: TSMusicClient, bot_id: str) -> bool:
        for bot in await tsmusic.list_bots():
            if bot.get("id") == bot_id:
                return bot.get("status") == "connected"
        return False
