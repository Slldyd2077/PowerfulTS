"""原生 TS3 监控路由。

替代透传 S-QC-Bot 的 /api/stats、/api/channels，
直接从 app.state.ts3_monitor 的内存快照返回（前端契约不变）。
必须在 catch-all 代理之前注册。
"""
from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/stats")
async def stats(request: Request) -> dict:
    """TS3 服务器统计（在线用户 / 游戏分布 / 运行时长）。"""
    monitor = request.app.state.ts3_monitor
    return monitor.get_stats()


@router.get("/channels")
async def channels(request: Request) -> dict:
    """TS3 频道列表。"""
    monitor = request.app.state.ts3_monitor
    return monitor.get_channels()
