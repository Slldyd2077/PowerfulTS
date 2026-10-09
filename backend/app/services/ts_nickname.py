"""Nickname bounds for the non-SDK TeamSpeak voice client (Unicode characters)."""

TS_NICKNAME_MIN_LENGTH = 3
TS_NICKNAME_MAX_LENGTH = 30


def ts_nickname_error(nickname: str) -> str | None:
    if not nickname.strip():
        return "TS 昵称不能为空"
    if not TS_NICKNAME_MIN_LENGTH <= len(nickname) <= TS_NICKNAME_MAX_LENGTH:
        return "TS 昵称需为 3–30 个字符"
    return None
