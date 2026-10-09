"""Channel-scoped watch state and WebRTC signaling; never transports media bytes."""
from __future__ import annotations

import asyncio
import secrets
import time
from dataclasses import dataclass, field
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


class RoomCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    type: Literal["start", "stop", "playback", "signal", "ping", "transfer", "ready", "pause", "settings", "leave"]
    kind: Literal["sync", "screen"] | None = None
    source: Literal["direct", "site"] | None = None
    url: str = Field(default="", max_length=2048)
    shareId: str = Field(default="", max_length=64)
    position: float = Field(default=0, ge=0, le=604800, allow_inf_nan=False)
    paused: bool = True
    rate: float = Field(default=1, ge=0.25, le=4, allow_inf_nan=False)
    target: str = Field(default="", max_length=64)
    description: dict | None = None
    candidate: dict | None = None
    sentAt: float = Field(default=0, ge=0, allow_inf_nan=False)
    ready: bool = False
    waitForMembers: bool = True
    allowMemberPause: bool = True
    live: bool = False

    @field_validator("url")
    @classmethod
    def safe_url(cls, value: str) -> str:
        if not value:
            return value
        try:
            parsed = urlsplit(value)
            if (parsed.scheme not in ("http", "https") or not parsed.hostname
                    or parsed.username or parsed.password):
                raise ValueError("视频地址必须是 HTTP(S) 地址且不能包含账号密码")
            _ = parsed.port
        except ValueError as exc:
            raise ValueError("视频地址无效") from exc
        return value


@dataclass
class RoomPeer:
    account_id: int
    nickname: str
    cid: int
    id: str = field(default_factory=lambda: secrets.token_urlsafe(12))
    queue: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=64))
    ready: bool = False
    ready_at: float = 0
    intentional_leave: bool = False


@dataclass
class WatchRoom:
    peers: dict[str, RoomPeer] = field(default_factory=dict)
    share: dict | None = None
    host: str | None = None
    offline: dict[int, tuple[RoomPeer, float]] = field(default_factory=dict)


class WatchRooms:
    def __init__(self) -> None:
        self.rooms: dict[int, WatchRoom] = {}

    def join(self, peer: RoomPeer) -> None:
        self.tick(peer.cid)
        room = self.rooms.setdefault(peer.cid, WatchRoom())
        if len(room.peers) + len(room.offline) >= 9 and peer.account_id not in room.offline:
            raise ValueError("共享房间最多支持 9 人")
        if any(p.account_id == peer.account_id for p in room.peers.values()):
            raise ValueError("当前账号已在另一个页面加入共享")
        previous = room.offline.pop(peer.account_id, None)
        if previous:
            peer.id = previous[0].id
        room.peers[peer.id] = peer
        self.emit(peer, {"type": "welcome", "peerId": peer.id})
        self.broadcast_state(peer.cid)

    @staticmethod
    def emit(peer: RoomPeer, message: dict) -> None:
        try:
            peer.queue.put_nowait(message)
        except asyncio.QueueFull:
            # Slow clients must reconnect for a fresh snapshot, not accumulate SDP.
            while not peer.queue.empty():
                peer.queue.get_nowait()
            peer.queue.put_nowait({"type": "overflow"})

    def snapshot(self, cid: int) -> dict:
        room = self.rooms[cid]
        return {
            "type": "room", "cid": cid, "serverTime": time.time() * 1000,
            "peers": [{"id": p.id, "nickname": p.nickname} for p in room.peers.values()],
            "share": room.share, "host": room.host,
        }

    def broadcast_state(self, cid: int) -> None:
        self.recompute(cid)
        state = self.snapshot(cid)
        for peer in self.rooms[cid].peers.values():
            self.emit(peer, state)

    def leave(self, peer: RoomPeer) -> None:
        room = self.rooms.get(peer.cid)
        if not room or room.peers.pop(peer.id, None) is None:
            return
        if room.share and room.share["owner"] == peer.id:
            room.share = None
        if room.host == peer.id:
            room.host = None
        room.offline.pop(peer.account_id, None)
        if room.peers or room.offline:
            self.broadcast_state(peer.cid)
        else:
            del self.rooms[peer.cid]

    def disconnect(self, peer: RoomPeer) -> None:
        room = self.rooms.get(peer.cid)
        if not room or room.peers.get(peer.id) is not peer:
            return
        if peer.intentional_leave or not room.share or room.share["kind"] != "sync" or room.share["live"]:
            self.leave(peer)
            return
        room.peers.pop(peer.id)
        room.offline[peer.account_id] = (peer, time.monotonic() + 20)
        self.broadcast_state(peer.cid)

    def recompute(self, cid: int) -> None:
        room = self.rooms[cid]
        share = room.share
        if not share or share["kind"] != "sync":
            return
        waiting = []
        if share["waitForMembers"] and not share["live"]:
            now = time.monotonic()
            waiting = [{"nickname": p.nickname, "reason": "loading"}
                       for p in room.peers.values() if not p.ready or now - p.ready_at > 6]
            waiting += [{"nickname": p.nickname, "reason": "offline"} for p, _ in room.offline.values()]
        paused = share["requestedPaused"] or bool(waiting)
        timestamp = time.time() * 1000
        if paused != share["paused"]:
            elapsed = 0 if share["paused"] else max(0, timestamp - share["updatedAt"]) / 1000
            share = {**share, "position": share["position"] + elapsed * share["rate"], "updatedAt": timestamp}
        room.share = {**share, "paused": paused, "waiting": waiting}

    def tick(self, cid: int) -> None:
        room = self.rooms.get(cid)
        if room is None:
            return
        before = room.share
        now = time.monotonic()
        expired = [p for p, deadline in room.offline.values() if deadline <= now]
        for peer in expired:
            room.offline.pop(peer.account_id, None)
            if room.host == peer.id:
                room.host, room.share = None, None
        if not room.peers and not room.offline:
            del self.rooms[cid]
            return
        self.recompute(cid)
        if before != room.share or expired:
            self.broadcast_state(cid)

    async def cleanup_loop(self) -> None:
        while True:
            await asyncio.sleep(1)
            for cid in tuple(self.rooms):
                self.tick(cid)

    def remove_account(self, account_id: int) -> None:
        for room in tuple(self.rooms.values()):
            for peer in tuple(room.peers.values()):
                if peer.account_id == account_id:
                    self.leave(peer)
                    self.emit(peer, {"type": "revoked"})
            previous = room.offline.get(account_id)
            if previous:
                room.offline.pop(account_id)
                if room.host == previous[0].id:
                    room.host, room.share = None, None
                self.tick(previous[0].cid)

    def handle(self, peer: RoomPeer, payload: dict) -> None:
        try:
            command = RoomCommand.model_validate(payload)
        except ValidationError as exc:
            raise ValueError("无效的共享消息") from exc
        room = self.rooms.get(peer.cid)
        if room is None or room.peers.get(peer.id) is not peer:
            raise ValueError("已退出共享房间，请重新加入")
        share = room.share
        if command.type == "leave":
            peer.intentional_leave = True
            self.leave(peer)
            self.emit(peer, {"type": "revoked"})
            return
        if command.type == "ping":
            self.emit(peer, {"type": "pong", "sentAt": command.sentAt,
                             "serverTime": time.time() * 1000})
            return
        if command.type == "start":
            if room.host is not None and room.host != peer.id:
                raise ValueError("仅房主可以发起共享，请让房主转交权限")
            if share:
                raise ValueError("已有成员正在共享，请先停止当前共享")
            if command.kind not in ("sync", "screen"):
                raise ValueError("请选择共享模式")
            if command.kind == "sync" and (not command.url or not command.source):
                raise ValueError("请提供视频地址和播放方式")
            room.share = {
                "id": secrets.token_urlsafe(12), "owner": peer.id,
                "kind": command.kind, "source": command.source, "url": command.url,
                "position": 0, "paused": True, "rate": 1,
                "requestedPaused": True, "waiting": [], "live": command.live,
                "waitForMembers": command.waitForMembers, "allowMemberPause": command.allowMemberPause,
                "updatedAt": time.time() * 1000,
            }
            room.host = peer.id
            for member in room.peers.values():
                member.ready, member.ready_at = False, 0
            room.offline.clear()
        elif command.type in ("ready", "pause", "settings"):
            if not share or share["id"] != command.shareId or share["kind"] != "sync":
                raise ValueError("当前不是同步观看")
            if command.type == "ready":
                peer.ready, peer.ready_at = command.ready, time.monotonic()
            elif command.type == "pause":
                if room.host != peer.id and not share["allowMemberPause"]:
                    raise ValueError("房主未开启成员暂停权限")
                # Viewers may pause; only the host resumes so another viewer cannot undo it.
                if not command.paused and room.host != peer.id:
                    raise ValueError("请让房主继续播放")
                room.share = {**share, "requestedPaused": command.paused}
            else:
                if room.host != peer.id:
                    raise ValueError("仅房主可以更改观看设置")
                room.share = {**share, "waitForMembers": command.waitForMembers,
                              "allowMemberPause": command.allowMemberPause}
        elif command.type == "transfer":
            if room.host != peer.id or command.target == peer.id or command.target not in room.peers:
                raise ValueError("仅房主可以转交给同频道已加入共享的成员")
            room.host = command.target
            if share:
                if share["kind"] == "screen":
                    # Screen capture permission cannot be delegated to another browser.
                    room.share = None
                else:
                    room.share = {**share, "owner": command.target}
        elif command.type in ("stop", "playback"):
            if not share or room.host != peer.id or share["id"] != command.shareId:
                raise ValueError("仅当前房主可以控制共享")
            if command.type == "stop":
                room.share = None
            else:
                if share["kind"] != "sync":
                    raise ValueError("屏幕共享没有播放进度")
                room.share = {**share, "position": command.position, "requestedPaused": command.paused,
                              "rate": command.rate, "updatedAt": time.time() * 1000}
        elif command.type == "signal":
            target = room.peers.get(command.target)
            if (not share or share["kind"] != "screen" or share["id"] != command.shareId
                    or not target or target.id == peer.id
                    or share["owner"] not in (peer.id, target.id)):
                raise ValueError("无权转发到这个共享连接")
            description = command.description
            if description is not None:
                expected = "offer" if peer.id == share["owner"] else "answer"
                if (set(description) != {"type", "sdp"} or description.get("type") != expected
                        or not isinstance(description.get("sdp"), str)
                        or len(description["sdp"]) > 16000):
                    raise ValueError("无效的会话描述")
            candidate = command.candidate
            if candidate is not None:
                if (not isinstance(candidate.get("candidate"), str)
                        or len(candidate["candidate"]) > 2048
                        or set(candidate) - {"candidate", "sdpMid", "sdpMLineIndex", "usernameFragment"}):
                    raise ValueError("无效的 ICE 候选")
            if (description is None) == (candidate is None):
                raise ValueError("信令必须包含一个描述或候选")
            self.emit(target, {"type": "signal", "from": peer.id, "shareId": share["id"],
                               "description": description, "candidate": candidate})
            return
        self.broadcast_state(peer.cid)
