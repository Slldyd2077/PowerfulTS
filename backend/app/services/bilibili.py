"""Bilibili 常量。

B 站点播（搜索 / 播放）已由 TSMusicBot 多平台引擎提供（platform=bilibili），
本模块仅保留图片代理所需的 UA / Referer 常量。
"""
from __future__ import annotations

BILI_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
BILI_REFERER = "https://www.bilibili.com"
