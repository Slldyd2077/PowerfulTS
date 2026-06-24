"""应用配置。

从环境变量读取配置：
  - 过渡期桥接通道 (S-QC-Bot 透传 / TS3AudioBot 音乐)
  - 原生数据层 (SQLite + SQLAlchemy async)
  - 原生 TS3 ServerQuery 直连 (监控 / 频道租赁)

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


@dataclass(frozen=True)
class Settings:
    # ── 通道 1: S-QC-Bot (监控/用户/频道, 过渡期透传目标) ──
    sqc_bot_url: str

    # ── 通道 2: TS3AudioBot (音乐引擎) ──
    ts3ab_url: str
    ts3ab_bot_uid: str            # BASIC auth 用户名 = TS3 客户端 UID
    ts3ab_api_token: str          # BASIC auth 密码 = !api 生成的 token
    ts3ab_default_bot_id: int     # 默认操作的 bot 实例 id (通常 0)

    # ── 原生数据层 (SQLite + SQLAlchemy async, 默认零依赖文件库) ──
    database_url: str

    # ── 原生 TS3 ServerQuery 直连 (监控 / 频道租赁写操作) ──
    ts3_host: str
    ts3_query_port: int           # ServerQuery 端口 (默认 10011)
    ts3_query_user: str           # ServerQuery 账号
    ts3_query_password: str       # ServerQuery 密码
    ts3_sid: int                  # 虚拟服务器 ID (默认 1)


def get_settings() -> Settings:
    """从环境变量构造配置。"""
    return Settings(
        sqc_bot_url=os.environ.get("SQC_BOT_URL", "http://127.0.0.1:8080"),
        ts3ab_url=os.environ.get("TS3AB_URL", "http://127.0.0.1:58913"),
        ts3ab_bot_uid=os.environ.get("TS3AB_BOT_UID", ""),
        ts3ab_api_token=os.environ.get("TS3AB_API_TOKEN", ""),
        ts3ab_default_bot_id=int(os.environ.get("TS3AB_DEFAULT_BOT_ID", "0")),
        database_url=os.environ.get(
            "DATABASE_URL", "sqlite+aiosqlite:///./data/powerfults.db"
        ),
        ts3_host=os.environ.get("TS3_HOST", "127.0.0.1"),
        ts3_query_port=int(os.environ.get("TS3_QUERY_PORT", "10011")),
        ts3_query_user=os.environ.get("TS3_QUERY_USER", ""),
        ts3_query_password=os.environ.get("TS3_QUERY_PASSWORD", ""),
        ts3_sid=int(os.environ.get("TS3_SID", "1")),
    )
