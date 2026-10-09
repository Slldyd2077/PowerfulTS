"""Validate ICE deployment settings before handing them to browsers."""
import json

from pydantic import BaseModel, ConfigDict, Field, field_validator


class IceServer(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    urls: str | list[str]
    username: str | None = Field(default=None, max_length=256)
    credential: str | None = Field(default=None, max_length=1024)

    @field_validator("urls")
    @classmethod
    def validate_urls(cls, value: str | list[str]) -> str | list[str]:
        entries = [value] if isinstance(value, str) else value
        if not entries or len(entries) > 16:
            raise ValueError("ICE server 必须配置 urls")
        if any(not entry.startswith(("stun:", "stuns:", "turn:", "turns:")) or len(entry) > 2048 for entry in entries):
            raise ValueError("ICE urls 仅支持 STUN / TURN 地址")
        return value


def parse_ice_servers(raw: str) -> list[dict]:
    try:
        servers = json.loads(raw)
        if not isinstance(servers, list) or len(servers) > 16:
            raise ValueError("必须使用数组")
        return [IceServer.model_validate(server).model_dump(exclude_none=True) for server in servers]
    except (ValueError, TypeError):
        raise ValueError("SCREEN_SHARE_ICE_SERVERS 必须是有效的 ICE server JSON 数组") from None
