"""应用配置。

从环境变量读取配置：
  - TSMusicBot 音乐引擎 (网易云 / QQ / B 站 多平台)
  - 原生数据层 (SQLite + SQLAlchemy async)
  - 原生 TS3 ServerQuery 直连 (监控 / 认证 / 好友)
  - 网易云音乐 API (本地 NeteaseCloudMusicApi 服务, 账号/歌单)

复制 .env.example 为 .env 并填入实际值。
"""
from __future__ import annotations

import os
from dataclasses import dataclass

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    # python-dotenv 未安装时回退到纯环境变量
    pass


def _parse_origins(raw: str) -> list[str]:
    """逗号分隔的 CORS 来源 → 去空白的列表。"""
    return [o.strip() for o in raw.split(",") if o.strip()]


@dataclass(frozen=True)
class Settings:
    # ── 原生数据层 (SQLite + SQLAlchemy async, 默认零依赖文件库) ──
    database_url: str

    # ── 网易云音乐 API (本地 NeteaseCloudMusicApi 服务) ──
    netease_api_url: str

    # ── 原生 TS3 ServerQuery 直连 (监控 / 认证 / 好友) ──
    ts3_host: str
    ts3_query_port: int           # ServerQuery 端口 (默认 10011)
    ts3_query_user: str           # ServerQuery 账号
    ts3_query_password: str       # ServerQuery 密码
    ts3_sid: int                  # 虚拟服务器 ID (默认 1)

    # ── TSMusicBot 音乐引擎 (Docker :3000) ──
    tsmusic_url: str
    tsmusic_user: str
    tsmusic_password: str
    tsmusic_bot_id: str

    # ── NapCat QQ 机器人 (HTTP API, 好友上线提醒推送; 未配置则不推送) ──
    napcat_url: str
    napcat_token: str

    # ── Steam 集成 (Web API + OpenID 2.0 登录; 未配置 API Key 则 Steam 功能降级) ──
    steam_api_key: str
    # OpenID 回调绝对 URL；留空则在 /auth/url 时从请求推断（dev 友好，生产建议显式配置）
    steam_openid_return_url: str
    steam_openid_realm: str
    # 签发 OpenID state 的 HMAC 密钥；留空则用内置默认值（开发够用，生产应显式设置）
    steam_openid_state_secret: str

    # ── CORS 允许的前端来源 (逗号分隔; 生产改为实际域名) ──
    cors_origins: list[str]


def get_settings() -> Settings:
    """从环境变量构造配置。"""
    return Settings(
        database_url=os.environ.get(
            "DATABASE_URL", "sqlite+aiosqlite:///./data/powerfults.db"
        ),
        netease_api_url=os.environ.get("NETEASE_API_URL", "http://127.0.0.1:3000"),
        ts3_host=os.environ.get("TS3_HOST", "127.0.0.1"),
        ts3_query_port=int(os.environ.get("TS3_QUERY_PORT", "10011")),
        ts3_query_user=os.environ.get("TS3_QUERY_USER", ""),
        ts3_query_password=os.environ.get("TS3_QUERY_PASSWORD", ""),
        ts3_sid=int(os.environ.get("TS3_SID", "1")),
        tsmusic_url=os.environ.get("TSMUSIC_URL", "http://127.0.0.1:3000"),
        tsmusic_user=os.environ.get("TSMUSIC_USER", ""),
        tsmusic_password=os.environ.get("TSMUSIC_PASSWORD", ""),
        tsmusic_bot_id=os.environ.get("TSMUSIC_BOT_ID", ""),
        napcat_url=os.environ.get("NAPCAT_URL", "http://127.0.0.1:3000"),
        napcat_token=os.environ.get("NAPCAT_TOKEN", ""),
        steam_api_key=os.environ.get("STEAM_API_KEY", ""),
        steam_openid_return_url=os.environ.get("STEAM_OPENID_RETURN_URL", ""),
        steam_openid_realm=os.environ.get("STEAM_OPENID_REALM", ""),
        steam_openid_state_secret=os.environ.get("STEAM_OPENID_STATE_SECRET", ""),
        cors_origins=_parse_origins(
            os.environ.get("CORS_ORIGINS", "http://localhost:5173")
        ),
    )
