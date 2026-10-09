import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.routers.auth import NicknameRequest, RegisterRequest, register, send_code
from app.services.voice_bot import VoiceBotError, VoiceBotManager


@pytest.mark.parametrize("nickname", ["1", "雪凌", "a" * 31, "中" * 31, "😀😀"])
def test_registration_rejects_invalid_ts_nickname_before_verification(nickname):
    async def scenario():
        result = await register(
            RegisterRequest(ts_nickname=nickname, password="test-password"),
            SimpleNamespace(), None,
        )
        assert result == {"success": False, "error": "TS 昵称需为 3–30 个字符"}

    asyncio.run(scenario())


@pytest.mark.parametrize("nickname", ["ab", "a" * 31])
def test_invalid_nickname_is_rejected_before_sending_ts_verification(nickname):
    async def scenario():
        result = await send_code(NicknameRequest(ts_nickname=nickname), SimpleNamespace(), None)
        assert result == {"success": False, "error": "TS 昵称需为 3–30 个字符"}

    asyncio.run(scenario())


@pytest.mark.parametrize("nickname", ["1", "雪凌", "a" * 31, "中" * 31, "😀😀"])
def test_existing_invalid_nickname_fails_before_upstream_access(nickname):
    async def scenario():
        provider = Mock()
        manager = VoiceBotManager(provider)
        account = SimpleNamespace(id=17, ts_nickname=nickname, role="member")
        with pytest.raises(VoiceBotError, match="3–30"):
            await manager.acquire(None, account)
        provider.assert_not_called()

    asyncio.run(scenario())
