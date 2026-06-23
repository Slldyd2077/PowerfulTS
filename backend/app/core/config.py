"""应用配置。

从环境变量读取两条桥接通道的目标地址与认证凭据。
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
    # ── 通道 1: S-QC-Bot (监控/用户/频道, 现状透传目标) ──
    sqc_bot_url: str

    # ── 通道 2: TS3AudioBot (音乐引擎) ──
    ts3ab_url: str
    ts3ab_bot_uid: str            # BASIC auth 用户名 = TS3 客户端 UID
    ts3ab_api_token: str          # BASIC auth 密码 = !api 生成的 token
    ts3ab_default_bot_id: int     # 默认操作的 bot 实例 id (通常 0)


def get_settings() -> Settings:
    """从环境变量构造配置。"""
    return Settings(
        sqc_bot_url=os.environ.get("SQC_BOT_URL", "http://127.0.0.1:8080"),
        ts3ab_url=os.environ.get("TS3AB_URL", "http://127.0.0.1:58913"),
        ts3ab_bot_uid=os.environ.get("TS3AB_BOT_UID", ""),
        ts3ab_api_token=os.environ.get("TS3AB_API_TOKEN", ""),
        ts3ab_default_bot_id=int(os.environ.get("TS3AB_DEFAULT_BOT_ID", "0")),
    )
