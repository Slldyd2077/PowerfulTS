import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base
from app.models import MonitorUser, ServerMember
from app.services.monitor_users import MonitorUserStore
from app.services.ts3_monitor import TS3Monitor


class ClientSnapshot:
    def __init__(self, rows):
        self.rows = rows

    def send(self, _command, **_params):
        return self.rows


def client(uid, nickname="Alice", client_type="0"):
    return {"client_unique_identifier": uid, "client_nickname": nickname,
            "client_type": client_type, "clid": "1", "cid": "1"}


class MonitorPersistenceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.engine = create_async_engine(
            f"sqlite+aiosqlite:///{Path(self.directory.name) / 'monitor.db'}"
        )
        async with self.engine.begin() as connection:
            await connection.run_sync(
                lambda conn: Base.metadata.create_all(
                    conn, tables=[MonitorUser.__table__, ServerMember.__table__]
                )
            )
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        self.store = MonitorUserStore(self.sessions)
        self.settings = SimpleNamespace(ts3_host="127.0.0.1", ts3_query_port=10011)

    async def asyncTearDown(self):
        await self.engine.dispose()
        self.directory.cleanup()

    async def monitor(self, store=None):
        monitor = TS3Monitor(self.settings, user_store=store or self.store)
        await monitor.restore_cumulative_users()
        monitor.set_loop(asyncio.get_running_loop())
        return monitor

    async def test_restart_restores_cumulative_users_even_with_no_online_clients(self):
        before = await self.monitor()
        before._conn = ClientSnapshot([client("uid-a"), client("uid-b", "Bob")])
        before._refresh_clients()
        await before.flush_cumulative_users()
        await self.engine.dispose()
        reopened = create_async_engine(str(self.engine.url))
        try:
            restored_store = MonitorUserStore(async_sessionmaker(reopened, expire_on_commit=False))
            after = await self.monitor(restored_store)
            self.assertEqual(after.get_stats()["total_users"], 2)
            self.assertEqual(after.get_stats()["online_users"], 0)
        finally:
            await reopened.dispose()

    async def test_legacy_history_is_seeded_without_changing_first_join_records(self):
        async with self.sessions() as db:
            db.add_all([ServerMember(unique_identifier="legacy-a", first_nickname="Old A"),
                        ServerMember(unique_identifier="legacy-b", first_nickname="Old B")])
            await db.commit()
        monitor = await self.monitor()
        self.assertEqual(monitor.get_stats()["total_users"], 2)
        self.assertEqual(await self.store.load(), {"legacy-a", "legacy-b"})
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(select(func.count()).select_from(ServerMember)), 2)
            self.assertEqual(await db.scalar(select(func.count()).select_from(MonitorUser)), 2)

    async def test_repeated_online_updates_and_concurrent_saves_deduplicate_uid(self):
        monitor = await self.monitor()
        snapshot = ClientSnapshot([client("uid-a")])
        monitor._conn = snapshot
        monitor._refresh_clients()
        monitor._refresh_clients()
        await monitor.flush_cumulative_users()
        snapshot.rows = []
        monitor._refresh_clients()
        monitor.client_data.clear()
        snapshot.rows = [client("uid-a", "Renamed")]
        monitor._refresh_clients()
        await monitor.flush_cumulative_users()
        await asyncio.gather(self.store.save({"uid-a"}), self.store.save({"uid-a", "uid-b"}))
        restored = await self.monitor()
        self.assertEqual(restored.get_stats()["total_users"], 2)

    async def test_query_clients_filtered_bots_and_empty_uids_stay_excluded(self):
        monitor = await self.monitor()
        monitor._conn = ClientSnapshot([client("uid-a"), client("query", "Query", "1"),
                                       client("music", "统计点播姬"), client("")])
        monitor._refresh_clients()
        await monitor.flush_cumulative_users()
        self.assertEqual(await self.store.load(), {"uid-a"})

    async def test_new_visitors_do_not_preempt_first_join_notifications(self):
        monitor = await self.monitor()
        monitor._conn = ClientSnapshot([client("uid-a")])
        monitor._refresh_clients()
        await monitor.flush_cumulative_users()
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(select(func.count()).select_from(ServerMember)), 0)

    async def test_empty_save_does_not_clear_saved_history(self):
        await self.store.save({"uid-a"})
        await self.store.save(set())
        self.assertEqual(await self.store.load(), {"uid-a"})

    async def test_failed_restore_is_surfaced_instead_of_replacing_history_with_zero(self):
        class BrokenStore:
            async def load(self):
                raise OSError("history unavailable")

        monitor = TS3Monitor(self.settings, user_store=BrokenStore())
        with self.assertRaisesRegex(OSError, "history unavailable"):
            await monitor.restore_cumulative_users()

    async def test_flush_saves_pending_users_without_a_live_event_loop(self):
        monitor = TS3Monitor(self.settings, user_store=self.store)
        await monitor.restore_cumulative_users()
        monitor._conn = ClientSnapshot([client("uid-a")])
        monitor._refresh_clients()
        await monitor.flush_cumulative_users()
        self.assertEqual(await self.store.load(), {"uid-a"})

    async def test_new_arrivals_during_a_write_are_saved_at_shutdown(self):
        started, release = asyncio.Event(), asyncio.Event()
        real_store = self.store

        class DelayedStore:
            first = True

            async def load(self):
                return await real_store.load()

            async def save(self, user_ids):
                if self.first:
                    self.first = False
                    started.set()
                    await release.wait()
                await real_store.save(user_ids)

        monitor = await self.monitor(DelayedStore())
        snapshot = ClientSnapshot([client("uid-a")])
        monitor._conn = snapshot
        monitor._refresh_clients()
        await asyncio.wait_for(started.wait(), 1)
        snapshot.rows.append(client("uid-b", "Bob"))
        monitor._refresh_clients()
        release.set()
        await monitor.flush_cumulative_users()
        self.assertEqual(await self.store.load(), {"uid-a", "uid-b"})

    async def test_failed_write_keeps_pending_users_for_retry_even_after_they_leave(self):
        real_store = self.store
        failed = asyncio.Event()

        class FlakyStore:
            attempts = 0

            async def load(self):
                return await real_store.load()

            async def save(self, user_ids):
                self.attempts += 1
                if self.attempts == 1:
                    failed.set()
                    raise OSError("temporary database failure")
                await real_store.save(user_ids)

        flaky = FlakyStore()
        monitor = await self.monitor(flaky)
        snapshot = ClientSnapshot([client("uid-a")])
        monitor._conn = snapshot
        with self.assertLogs("app.services.ts3_monitor", level="WARNING"):
            monitor._refresh_clients()
            await asyncio.wait_for(failed.wait(), 1)
            snapshot.rows = []
            monitor._refresh_clients()
            await monitor.flush_cumulative_users()
        self.assertGreaterEqual(flaky.attempts, 2)
        self.assertEqual(await self.store.load(), {"uid-a"})


if __name__ == "__main__":
    unittest.main()
