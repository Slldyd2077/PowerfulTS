"""轻量 TS3 ServerQuery 客户端 (socket 实现)。

不依赖 ts3 库 / telnetlib（Python 3.13+ 已移除 telnetlib），跨 Python 3.11+ 稳定。
封装 TS3 SQ 文本协议：TCP 连接 + 命令收发 + TS3 转义/解析。

协议要点：
  - 客户端命令以 \\n 结尾
  - 服务器响应行以 \\n\\r (LF CR) 结尾
  - 响应末尾为 `error id=0 msg=ok`（成功）或 `error id=N msg=...`
  - 多条目用 | 分隔，字段用空格分隔，key=value
  - 值用 TS3 转义：\\s=空格 \\p=| \\/=/ \\\\=\\ 等
"""
from __future__ import annotations

import logging
import socket

logger = logging.getLogger(__name__)

_LINE_END = b"\n\r"
_MAX_RESPONSE = 8 * 1024 * 1024  # 单次响应缓冲上限 8MB，防恶意/异常响应 OOM

# TS3 转义解码映射
_UNESCAPE_MAP: dict[str, str] = {
    "\\": "\\", "/": "/", "s": " ", "p": "|",
    "n": "\n", "r": "\r", "t": "\t", "f": "\f",
    "a": "\a", "v": "\v", "b": "\b",
}


class TS3QueryError(Exception):
    """TS3 ServerQuery 返回的非零 error。"""

    def __init__(self, error_id: int, msg: str) -> None:
        self.error_id = error_id
        self.msg = msg
        super().__init__(f"TS3 ServerQuery 错误 [{error_id}]: {msg}")


class TS3QueryClient:
    """同步 TS3 ServerQuery 客户端（基于 socket，无 telnetlib 依赖）。"""

    def __init__(self, host: str, port: int, timeout: float = 10.0) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self._sock: socket.socket | None = None
        self._buf = b""

    # ───────────────────── 连接 ─────────────────────

    def connect(self) -> None:
        """建立 TCP 连接并读取欢迎消息。"""
        self._sock = socket.create_connection((self.host, self.port), self.timeout)
        self._sock.settimeout(self.timeout)
        self._read_welcome()

    def _read_welcome(self) -> None:
        # 连接后 SQ 发送两行欢迎 (TS3 / Welcome...)，各以 \n\r 结尾
        self._recv_until(_LINE_END)
        self._recv_until(_LINE_END)

    def close(self) -> None:
        if self._sock is not None:
            try:
                self._sock.sendall(b"quit\n")
            except Exception:
                pass
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None
        self._buf = b""

    # ───────────────────── 底层收发 ─────────────────────

    def _recv_until(self, delimiter: bytes) -> bytes:
        assert self._sock is not None
        while delimiter not in self._buf:
            if len(self._buf) > _MAX_RESPONSE:
                raise ConnectionError("TS3 响应超过大小上限 (8MB)，疑似协议异常")
            chunk = self._sock.recv(4096)
            if not chunk:
                raise ConnectionError("TS3 ServerQuery 连接已关闭")
            self._buf += chunk
        idx = self._buf.index(delimiter) + len(delimiter)
        data, self._buf = self._buf[:idx], self._buf[idx:]
        return data

    # ───────────────────── 命令 ─────────────────────

    def send(self, command: str, **params: object) -> list[dict]:
        """发送命令，返回响应条目列表（每条 dict）。

        flag 参数用 True（如 uid=True）；命令失败抛 TS3QueryError。
        """
        assert self._sock is not None
        cmd = self._build_command(command, params)
        self._sock.sendall(cmd.encode("utf-8"))
        return self._read_response()

    def _build_command(self, command: str, params: dict) -> str:
        parts = [command]
        for key, value in params.items():
            if value is True:
                parts.append(key)  # flag 参数
            elif value is False or value is None:
                continue
            else:
                parts.append(f"{key}={self._escape(value)}")
        return " ".join(parts) + "\n"

    def _read_response(self) -> list[dict]:
        data_parts: list[str] = []
        while True:
            line = self._recv_until(_LINE_END)[:-2].decode("utf-8", errors="replace")
            if line.startswith("error"):
                err = self._parse_entry(line[len("error"):].strip())
                err_id = int(err.get("id", "0"))
                if err_id != 0:
                    raise TS3QueryError(err_id, self._unescape(err.get("msg", "")))
                break
            data_parts.append(line)
        if not data_parts:
            return []
        full = "".join(data_parts)
        return [self._parse_entry(e) for e in full.split("|")]

    # ───────────────────── 解析 / 转义 ─────────────────────

    @staticmethod
    def _parse_entry(entry: str) -> dict:
        result: dict = {}
        for token in entry.split(" "):
            if not token:
                continue
            if "=" in token:
                key, _, value = token.partition("=")
                result[key] = TS3QueryClient._unescape(value)
            else:
                result[token] = ""
        return result

    @staticmethod
    def _escape(value: object) -> str:
        s = str(value)
        # 顺序：先 \\ 再其他（其余转义会引入反斜杠）
        s = s.replace("\\", "\\\\")
        s = s.replace("/", "\\/")
        s = s.replace(" ", "\\s")
        s = s.replace("|", "\\p")
        s = s.replace("\n", "\\n")
        s = s.replace("\r", "\\r")
        s = s.replace("\t", "\\t")
        return s

    @staticmethod
    def _unescape(s: str) -> str:
        result: list[str] = []
        i = 0
        n = len(s)
        while i < n:
            c = s[i]
            if c == "\\" and i + 1 < n:
                result.append(_UNESCAPE_MAP.get(s[i + 1], s[i + 1]))
                i += 2
            else:
                result.append(c)
                i += 1
        return "".join(result)
