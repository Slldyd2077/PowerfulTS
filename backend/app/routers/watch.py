"""Browser watch rooms authenticated by one-use capabilities and TS channel membership."""
from __future__ import annotations

import asyncio
import json

import anyio
import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import AsyncSessionLocal, get_db
from ..deps import VoiceAccountDep
from ..services.auth_service import AuthService
from ..services.watch_room import RoomPeer

router = APIRouter(prefix="/music/voice/watch", tags=["watch"])


async def channel_for(app, db, account_id: int, bot_id: str | None = None) -> int | None:
    current = await app.state.voice_bots.current_bot_id(db, account_id)
    if not current or (bot_id and current != bot_id) or not app.state.ts3_monitor.running:
        return None
    clid = await app.state.tsmusic.get_bot_client_id(current)
    return app.state.ts3_monitor.get_voice_overview(clid)["botCid"] if clid else None


@router.post("/ticket")
async def open_room(request: Request, account: VoiceAccountDep, db: AsyncSession = Depends(get_db)):
    if not await request.app.state.watch_limiter.allow(str(account.id)):
        raise HTTPException(429, "共享连接请求过于频繁，请稍后重试")
    try:
        cid = await channel_for(request.app, db, account.id)
    except (httpx.HTTPError, ValueError):
        raise HTTPException(502, "无法确认当前通话频道")
    if not cid:
        raise HTTPException(409, "请先加入网页通话并等待频道连接成功")
    bot_id = await request.app.state.voice_bots.current_bot_id(db, account.id)
    ticket = await request.app.state.watch_tickets.create(account.id, bot_id)
    return {"path": f"/api/music/voice/watch/{ticket.id}/socket",
            "iceServers": request.app.state.watch_ice_servers}


async def send_messages(websocket: WebSocket, peer: RoomPeer) -> None:
    while True:
        message = await peer.queue.get()
        if message["type"] in ("overflow", "revoked"):
            code = 4408 if message["type"] == "overflow" else 4403
            await websocket.close(code=code, reason="共享连接已结束，请在当前频道重新加入")
            return
        await asyncio.wait_for(websocket.send_json(message), 5)


async def check_membership(websocket: WebSocket, peer: RoomPeer, bot_id: str) -> None:
    while True:
        await asyncio.sleep(3)
        async with AsyncSessionLocal() as db:
            expiry = await AuthService(db).get_active_session_expiry(peer.account_id)
            cid = await channel_for(websocket.app, db, peer.account_id, bot_id)
        if expiry is None or cid != peer.cid:
            websocket.app.state.watch_rooms.remove_account(peer.account_id)
            await websocket.close(code=4403, reason="通话频道或登录状态已变化，请重新加入共享")
            return


@router.websocket("/{ticket_id}/socket")
async def room_socket(websocket: WebSocket, ticket_id: str):
    # A capability must not be consumed by a socket from another website.
    origin = websocket.headers.get("origin", "")
    configured = websocket.app.state.watch_origins
    scheme = websocket.headers.get("x-forwarded-proto") or ("https" if websocket.url.scheme == "wss" else "http")
    same_origin = f"{scheme}://{websocket.headers.get('host', '')}"
    if origin not in configured and origin != same_origin:
        await websocket.close(code=4403)
        return
    tickets = websocket.app.state.watch_tickets
    ticket = await tickets.claim(ticket_id)
    if ticket is None:
        await websocket.close(code=4401)
        return
    peer = None
    tasks: list[asyncio.Task] = []
    rooms = websocket.app.state.watch_rooms
    try:
        async with AsyncSessionLocal() as db:
            account = await AuthService(db).get_by_id(ticket.account_id)
            expiry = await AuthService(db).get_active_session_expiry(ticket.account_id)
            cid = await channel_for(websocket.app, db, ticket.account_id, ticket.bot_id)
        if account is None or expiry is None or cid is None:
            await websocket.close(code=4403)
            return
        await websocket.accept()
        peer = RoomPeer(ticket.account_id, account.ts_nickname, cid)
        rooms.join(peer)
        tasks = [asyncio.create_task(send_messages(websocket, peer)),
                 asyncio.create_task(check_membership(websocket, peer, ticket.bot_id))]

        async def receive_messages():
            count = 0
            window_start = asyncio.get_running_loop().time()
            while True:
                packet = await websocket.receive()
                if packet["type"] == "websocket.disconnect":
                    raise WebSocketDisconnect(packet.get("code", 1000))
                raw = packet.get("text")
                if not isinstance(raw, str):
                    peer.intentional_leave = True
                    await websocket.close(code=1003, reason="共享接口只接收状态消息")
                    return
                now = asyncio.get_running_loop().time()
                if now - window_start >= 1:
                    count, window_start = 0, now
                count += 1
                if len(raw) > 24000 or count > 60:
                    await websocket.close(code=4408, reason="共享消息过大或过于频繁")
                    return
                try:
                    payload = json.loads(raw)
                    if not isinstance(payload, dict):
                        raise ValueError("共享消息必须是对象")
                    rooms.handle(peer, payload)
                except (ValueError, KeyError) as exc:
                    rooms.emit(peer, {"type": "error", "message": str(exc)})

        tasks.append(asyncio.create_task(receive_messages()))
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            task.result()
    except WebSocketDisconnect:
        pass
    except (ValueError, httpx.HTTPError, TimeoutError, RuntimeError):
        if websocket.application_state != WebSocketState.DISCONNECTED:
            await websocket.close(code=1011, reason="共享连接失败，请重新加入")
    finally:
        # Remove the peer before an await can be interrupted during ASGI shutdown.
        if peer:
            rooms.disconnect(peer)
        for task in tasks:
            task.cancel()
        # AnyIO cancellation remains active at every await until we leave its
        # scope. Shield finalization so draining tasks cannot skip lease release.
        with anyio.CancelScope(shield=True):
            try:
                await asyncio.gather(*tasks, return_exceptions=True)
            finally:
                await tickets.release(ticket)
