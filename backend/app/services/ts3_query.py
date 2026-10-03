"""TeamSpeak ServerQuery 客户端：TS3 raw TCP 和 TS3/TS6 原生 SSH。

不依赖 ts3 库 / telnetlib（Python 3.13+ 已移除 telnetlib），跨 Python 3.11+ 稳定。
封装共享 SQ 文本协议，SSH 在握手阶段认证，并严格校验服务器主机密钥。

协议要点：
  - 客户端命令以 \\n 结尾
  - 服务器响应行以 \\n\\r (LF CR) 结尾
  - 响应末尾为 `error id=0 msg=ok`（成功）或 `error id=N msg=...`
  - 多条目用 | 分隔，字段用空格分隔，key=value
  - 值用 TS3 转义：\\s=空格 \\p=| \\/=/ \\\\=\\ 等
"""
from __future__ import annotations

import logging
import re
import socket
import threading
from typing import Any

logger = logging.getLogger(__name__)

_MAX_RESPONSE = 8 * 1024 * 1024  # 单次响应缓冲上限 8MB，防恶意/异常响应 OOM
_COMMAND_NAME = re.compile(r"[a-zA-Z][a-zA-Z0-9_]*\Z")

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
    """同步 Query 客户端；调用者仍可放在现有线程 / asyncio.to_thread 中。"""

    def __init__(
        self, host: str, port: int, timeout: float = 10.0, *,
        transport: str = "raw", username: str = "", password: str = "",
        ssh_known_hosts: str | None = None,
    ) -> None:
        if transport not in {"raw", "ssh"}:
            raise ValueError("ServerQuery transport 必须为 raw 或 ssh")
        self.host = host
        self.port = port
        self.timeout = timeout
        self.transport = transport
        self._username = username
        self._password = password
        self._ssh_known_hosts = ssh_known_hosts
        # Paramiko Channel 和 socket 共享 sendall/recv/settimeout/close API。
        self._sock: Any | None = None
        self._ssh_client: Any | None = None
        self._buf = b""

    # ───────────────────── 连接 ─────────────────────

    def connect(self) -> None:
        """建立连接并读取欢迎消息；任一步失败都释放已创建的资源。"""
        self.close()
        try:
            if self.transport == "ssh":
                self._connect_ssh()
            else:
                self._sock = socket.create_connection((self.host, self.port), self.timeout)
                self._sock.settimeout(self.timeout)
            self._read_welcome()
        except Exception:
            self.close()
            raise

    def _connect_ssh(self) -> None:
        if not self._username or not self._password:
            raise ConnectionError("SSH ServerQuery 需要 Query 用户名和密码")
        try:
            import paramiko
        except ImportError as exc:
            raise ConnectionError("SSH ServerQuery 需要安装 paramiko 依赖") from exc
        client = paramiko.SSHClient()
        self._ssh_client = client
        try:
            client.load_system_host_keys()
            if self._ssh_known_hosts:
                client.load_host_keys(self._ssh_known_hosts)
            client.set_missing_host_key_policy(paramiko.RejectPolicy())
            client.connect(
                hostname=self.host, port=self.port,
                username=self._username, password=self._password,
                timeout=self.timeout, banner_timeout=self.timeout, auth_timeout=self.timeout,
                look_for_keys=False, allow_agent=False,
            )
            transport = client.get_transport()
            if transport is None:
                raise ConnectionError("SSH transport 未建立")
            channel = transport.open_session(timeout=self.timeout)
            self._sock = channel
            channel.settimeout(self.timeout)
            # ServerQuery 是协议 shell；不要申请交互式终端 PTY 或执行远端 OS 命令。
            self._invoke_ssh_shell(channel, client)
        except Exception as exc:
            raise ConnectionError(
                f"SSH ServerQuery 连接失败 ({type(exc).__name__})；"
                "请检查 Query 账号、SSH 端口及已核验的 known_hosts 主机密钥"
            ) from exc

    def _invoke_ssh_shell(self, channel: Any, client: Any) -> None:
        """Bound the shell ACK: Paramiko's request wait ignores channel timeout."""
        expired = threading.Event()

        def abort_shell() -> None:
            expired.set()
            # Close transport first: this releases Channel._wait_for_event and
            # prevents channel.close from waiting for a peer during rekeying.
            try:
                client.close()
            finally:
                channel.close()

        deadline = threading.Timer(self.timeout, abort_shell)
        deadline.name = "server-query-shell-deadline"
        deadline.daemon = True
        deadline.start()
        try:
            try:
                channel.invoke_shell()
            except Exception:
                if expired.is_set():
                    raise TimeoutError("SSH ServerQuery shell ACK 超时") from None
                raise
            if expired.is_set():
                raise TimeoutError("SSH ServerQuery shell ACK 超时")
        finally:
            deadline.cancel()
            deadline.join(timeout=self.timeout)

    def authenticate(self, username: str, password: str) -> None:
        """raw 用 login；SSH 已在握手认证，不再发送不受支持的 login 命令。"""
        if self._sock is None:
            raise ConnectionError("ServerQuery 尚未连接")
        if self.transport == "ssh":
            if username != self._username or password != self._password:
                raise ValueError("SSH Query 认证凭据与连接握手不一致")
            return
        self.send("login", client_login_name=username, client_login_password=password)

    def _read_welcome(self) -> None:
        # Query SSH 沿用 TS3 文本协议；支持 LF CR、CR LF 和 LF 行尾。
        for _ in range(16):
            line = self._read_line()
            if line.startswith("Welcome"):
                return
            if line.startswith("error "):
                raise ConnectionError("ServerQuery 在欢迎阶段返回错误")
        raise ConnectionError("ServerQuery 欢迎消息无效")

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
        if self._ssh_client is not None:
            try:
                self._ssh_client.close()
            except Exception:
                logger.debug("SSH Query 清理连接失败", exc_info=True)
            self._ssh_client = None
        self._buf = b""

    # ───────────────────── 底层收发 ─────────────────────

    def _read_line(self) -> str:
        if self._sock is None:
            raise ConnectionError("ServerQuery 尚未连接")
        while b"\n" not in self._buf:
            chunk = self._sock.recv(4096)
            if not chunk:
                raise ConnectionError("ServerQuery 连接已关闭")
            self._buf += chunk
            if len(self._buf) > _MAX_RESPONSE:
                raise ConnectionError("ServerQuery 响应超过大小上限 (8MB)，疑似协议异常")
        idx = self._buf.index(b"\n") + 1
        data, self._buf = self._buf[:idx], self._buf[idx:]
        return data.strip(b"\r\n").decode("utf-8", errors="replace")

    # ───────────────────── 命令 ─────────────────────

    def send(self, command: str, **params: object) -> list[dict]:
        """发送命令，返回响应条目列表（每条 dict）。

        flag 参数用 True（如 uid=True）；命令失败抛 TS3QueryError。
        """
        if self._sock is None:
            raise ConnectionError("ServerQuery 尚未连接")
        if self.transport == "ssh" and command == "login":
            raise ValueError("SSH Query 已在连接握手认证，请使用 authenticate")
        cmd = self._build_command(command, params)
        try:
            self._sock.sendall(cmd.encode("utf-8"))
            return self._read_response()
        except TS3QueryError:
            raise
        except Exception:
            # 半条响应 / 超时后不可复用，否则下个命令会消费上个命令的响应。
            self.close()
            raise

    def _build_command(self, command: str, params: dict) -> str:
        if not _COMMAND_NAME.fullmatch(command):
            raise ValueError("ServerQuery 命令名无效")
        parts = [command]
        for key, value in params.items():
            if not _COMMAND_NAME.fullmatch(key):
                raise ValueError("ServerQuery 参数名无效")
            if value is True:
                parts.append(f"-{key}")  # TS3 选项用 - 前缀（如 clientlist -uid）
            elif value is False or value is None:
                continue
            else:
                parts.append(f"{key}={self._escape(value)}")
        return " ".join(parts) + "\n"

    def _read_response(self) -> list[dict]:
        data_parts: list[str] = []
        response_size = 0
        while True:
            line = self._read_line()
            response_size += len(line.encode("utf-8"))
            if response_size > _MAX_RESPONSE:
                raise ConnectionError("ServerQuery 响应超过大小上限 (8MB)，疑似协议异常")
            if not line or line.startswith("notify"):
                continue
            if line.startswith("error "):
                err = self._parse_entry(line[len("error"):].strip())
                err_id = int(err.get("id", "0"))
                if err_id != 0:
                    raise TS3QueryError(err_id, err.get("msg", ""))
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
