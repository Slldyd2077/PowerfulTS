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
from datetime import datetime

from sqlalchemy import delete, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Account, BotOwnership, Session, VoiceBot
from .tsmusic_client import TSMusicClient
from .voice_exclusivity import (
    VoiceExclusivityError,
    kick_real_ts_client_for_account,
)

logger = logging.getLogger(__name__)

# 断开后多久真正把 bot 停掉。刷新页面/网络抖动会在这个窗口内重新接上。
RELEASE_GRACE_SECONDS = 20.0
# 等 bot 连上 TS 的上限。
CONNECT_TIMEOUT_SECONDS = 25.0
_CONNECT_POLL_SECONDS = 0.5
MAX_ACTIVE_GUEST_VOICE_BOTS = 10


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

    def __init__(self, tsmusic_provider, session_factory=None, *, settings=None) -> None:
        self._tsmusic_provider = tsmusic_provider
        self._session_factory = session_factory
        self._settings = settings
        self._locks: dict[int, asyncio.Lock] = {}
        self._guest_capacity_lock = asyncio.Lock()
        self._release_tasks: dict[int, asyncio.Task] = {}
        self._release_specs: dict[int, tuple[str, bool]] = {}
        self._native_preempted_accounts: set[int] = set()

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
            if self._settings is not None:
                recorded_bot_id = await self.current_bot_id(db, account.id)
                recorded_bot_clid = None
                if recorded_bot_id:
                    try:
                        recorded_bot_clid = await tsmusic.get_bot_client_id(
                            recorded_bot_id
                        )
                    except Exception:
                        # _ensure_bot below owns stale-record recovery. A missing
                        # upstream bot must not prevent the pre-connect UID check.
                        logger.info(
                            "旧网页通话 bot 无法解析 clid，将按离线记录恢复: %s",
                            recorded_bot_id,
                        )
                try:
                    await asyncio.to_thread(
                        kick_real_ts_client_for_account,
                        self._settings,
                        account,
                        exclude_clid=recorded_bot_clid,
                    )
                except VoiceExclusivityError as exc:
                    raise VoiceBotError(str(exc)) from exc
            if account.role == "guest":
                # Production runs a single backend process; serialize the global
                # capacity check and reservation so burst joins cannot overshoot.
                async with self._guest_capacity_lock:
                    await self._ensure_guest_capacity(db, account)
                    bot_id = await self._ensure_bot(db, tsmusic, account)
            else:
                bot_id = await self._ensure_bot(db, tsmusic, account)
            await self._ensure_connected(tsmusic, bot_id)
            if self._settings is not None:
                bot_clid = await tsmusic.get_bot_client_id(bot_id)
                try:
                    await asyncio.to_thread(
                        kick_real_ts_client_for_account,
                        self._settings,
                        account,
                        exclude_clid=bot_clid,
                    )
                except VoiceExclusivityError as exc:
                    await self._discard_web_bot(account.id, bot_id)
                    raise VoiceBotError(str(exc)) from exc
            self._native_preempted_accounts.discard(account.id)
            return {"botId": bot_id, "nickname": account.ts_nickname}

    async def current_bot_id(self, db: AsyncSession, account_id: int) -> str | None:
        """已开通的通话 bot id（没有则 None）。不创建、不连接。"""
        row = await db.execute(
            select(VoiceBot.bot_id).where(VoiceBot.account_id == account_id)
        )
        found = row.first()
        return found[0] if found else None

    async def ensure_existing_connected(
        self, db: AsyncSession, account_id: int
    ) -> str:
        """Return the account's existing voice bot after proving it is usable."""
        async with self._lock_for(account_id):
            if account_id in self._native_preempted_accounts:
                raise VoiceBotError("TeamSpeak 客户端已上线，网页通话已断开")
            release_spec = self._release_specs.get(account_id)
            bot_id = await self.current_bot_id(db, account_id)
            if not bot_id:
                raise VoiceBotError("请先加入通话")
            await self._ensure_connected(self._tsmusic_provider(), bot_id)
            if release_spec is not None:
                release_bot_id, destroy = release_spec
                self.schedule_release(
                    account_id, release_bot_id, destroy=destroy
                )
            return bot_id

    def schedule_release(
        self, account_id: int, bot_id: str, *, destroy: bool = False
    ) -> None:
        """浏览器断开后延迟停机；宽限期内重新 acquire 会取消这次停机。"""
        if account_id in self._native_preempted_accounts:
            return
        self._cancel_release(account_id)
        self._release_specs[account_id] = (bot_id, destroy)
        self._release_tasks[account_id] = asyncio.create_task(
            self._release_after_grace(account_id, bot_id, destroy=destroy)
        )

    async def keep_alive(self, account_id: int) -> None:
        """Claim the account lease before a browser starts consuming voice."""
        async with self._lock_for(account_id):
            if account_id in self._native_preempted_accounts:
                raise VoiceBotError("TeamSpeak 客户端已上线，网页通话已断开")
            self._cancel_release(account_id)

    async def release_now(
        self, account_id: int, bot_id: str, *, destroy: bool = False
    ) -> None:
        """用户明确挂断：立刻停机，不等宽限期。"""
        async with self._lock_for(account_id):
            self._cancel_release(account_id)
            await self._retire(account_id, bot_id, destroy=destroy)

    async def preempt_if_native_present(
        self,
        account_id: int,
        bot_id: str,
        *,
        is_present,
        close_downlink,
    ) -> bool:
        """Atomically revalidate the native winner and retire the web identity."""
        async with self._lock_for(account_id):
            if not await is_present():
                return False
            self._native_preempted_accounts.add(account_id)
            self._cancel_release(account_id)
            try:
                await close_downlink()
            except Exception:
                logger.warning(
                    "真实 TS 接管时关闭网页下行失败: %s",
                    bot_id,
                    exc_info=True,
                )
            await self._remove_and_disconnect_web_bot(account_id, bot_id)
            return True

    async def _discard_web_bot(self, account_id: int, bot_id: str) -> None:
        """Fail a web acquire closed without marking it as native-preempted."""
        await self._remove_and_disconnect_web_bot(account_id, bot_id)

    async def _remove_and_disconnect_web_bot(
        self, account_id: int, bot_id: str
    ) -> None:
        # Remove the local capability first: even if upstream cleanup fails,
        # /voice/start and microphone recovery can no longer resurrect it.
        await self._delete_voice_bot_record(account_id, bot_id)
        try:
            await self._tsmusic_provider().delete_bot(bot_id)
        except Exception:
            logger.warning(
                "网页通话互斥失败后删除 bot 失败: %s",
                bot_id,
                exc_info=True,
            )
            await self._stop(bot_id)

    def _cancel_release(self, account_id: int) -> None:
        task = self._release_tasks.pop(account_id, None)
        self._release_specs.pop(account_id, None)
        if task is not None and not task.done():
            task.cancel()

    async def _release_after_grace(
        self, account_id: int, bot_id: str, *, destroy: bool
    ) -> None:
        current_task = asyncio.current_task()
        try:
            await asyncio.sleep(RELEASE_GRACE_SECONDS)
            async with self._lock_for(account_id):
                if self._release_tasks.get(account_id) is not current_task:
                    return
                await self._retire(account_id, bot_id, destroy=destroy)
        except asyncio.CancelledError:
            return
        finally:
            if self._release_tasks.get(account_id) is current_task:
                self._release_tasks.pop(account_id, None)
                self._release_specs.pop(account_id, None)

    async def _retire(self, account_id: int, bot_id: str, *, destroy: bool) -> None:
        if not destroy:
            await self._stop(bot_id)
            return
        try:
            await self._tsmusic_provider().delete_bot(bot_id)
            await self._delete_voice_bot_record(account_id, bot_id)
            logger.info("临时通话 bot 已删除: %s", bot_id)
        except Exception:
            logger.warning("删除临时通话 bot 失败: %s", bot_id, exc_info=True)
            await self._stop(bot_id)

    async def _delete_voice_bot_record(self, account_id: int, bot_id: str) -> None:
        if self._session_factory is None:
            return
        async with self._session_factory() as db:
            await db.execute(
                delete(VoiceBot).where(
                    VoiceBot.account_id == account_id,
                    VoiceBot.bot_id == bot_id,
                )
            )
            await db.commit()

    async def cleanup_expired_guests(self, db: AsyncSession) -> int:
        """Delete upstream identities before removing expired guest accounts."""
        has_active_session = exists(
            select(Session.token).where(
                Session.account_id == Account.id,
                Session.expires_at > datetime.now(),
            )
        )
        rows = (
            await db.execute(
                select(Account.id, VoiceBot.bot_id)
                .outerjoin(VoiceBot, VoiceBot.account_id == Account.id)
                .where(Account.role == "guest", ~has_active_session)
            )
        ).all()
        removable_ids: list[int] = []
        for account_id, bot_id in rows:
            if bot_id:
                try:
                    await self._tsmusic_provider().delete_bot(bot_id)
                except Exception:
                    logger.warning(
                        "清理过期游客通话 bot 失败: %s", bot_id, exc_info=True
                    )
                    continue
            removable_ids = [*removable_ids, account_id]
        if removable_ids:
            account_ids = tuple(dict.fromkeys(removable_ids))
            await db.execute(
                delete(VoiceBot).where(VoiceBot.account_id.in_(account_ids))
            )
            await db.execute(
                delete(Session).where(Session.account_id.in_(account_ids))
            )
            await db.execute(delete(Account).where(Account.id.in_(account_ids)))
            await db.commit()
        return len(dict.fromkeys(removable_ids))

    async def _ensure_guest_capacity(self, db: AsyncSession, account: Account) -> None:
        if account.role != "guest" or await self.current_bot_id(db, account.id):
            return
        active_count = await db.scalar(
            select(func.count(func.distinct(VoiceBot.id)))
            .join(Account, Account.id == VoiceBot.account_id)
            .join(Session, Session.account_id == Account.id)
            .where(
                Account.role == "guest",
                Session.expires_at > datetime.now(),
            )
        )
        if int(active_count or 0) >= MAX_ACTIVE_GUEST_VOICE_BOTS:
            raise VoiceBotError("游客通话席位已满，请稍后再试")

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
                if bot.get("status") != "connected":
                    return False
                client_id = await tsmusic.get_bot_client_id(bot_id)
                return isinstance(client_id, int) and client_id > 0
        return False
