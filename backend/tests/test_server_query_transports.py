"""Protocol and connection lifecycle tests for raw and native SSH Query."""
import socket
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services.ts3_query import TS3QueryClient, TS3QueryError


class Wire:
    def __init__(self, chunks):
        self.chunks = iter(chunks)
        self.sent = []
        self.closed = False
        self.timeout = None

    def recv(self, size):
        chunk = next(self.chunks, b"")
        if isinstance(chunk, Exception):
            raise chunk
        return chunk

    def sendall(self, data):
        self.sent.append(data)

    def settimeout(self, timeout):
        self.timeout = timeout

    def close(self):
        self.closed = True

    def invoke_shell(self):
        pass


def ssh_fixture(wire):
    client = MagicMock()
    client.get_transport.return_value.open_session.return_value = wire
    module = SimpleNamespace(SSHClient=MagicMock(return_value=client), RejectPolicy=MagicMock())
    return module, client


class QueryTransportTests(unittest.TestCase):
    def test_real_ssh_shell_ack_is_bounded_and_closes_connection(self):
        """A real SSH peer authenticates but never acknowledges its shell request."""
        import paramiko

        shell_requested = threading.Event()
        release_peer = threading.Event()
        peer_transports = []
        worker_errors = []
        elapsed = []

        class SilentShellPeer(paramiko.ServerInterface):
            def check_auth_password(self, username, password):
                return paramiko.AUTH_SUCCESSFUL

            def check_channel_request(self, kind, chanid):
                return paramiko.OPEN_SUCCEEDED

            def check_channel_shell_request(self, channel):
                shell_requested.set()
                release_peer.wait(3)
                return True

        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        listener.settimeout(2)
        port = listener.getsockname()[1]
        host_key = paramiko.RSAKey.generate(2048)

        def serve():
            accepted, _ = listener.accept()
            transport = paramiko.Transport(accepted)
            peer_transports.append(transport)
            transport.add_server_key(host_key)
            transport.start_server(server=SilentShellPeer())
            channel = transport.accept(2)
            release_peer.wait(3)
            if channel is not None:
                channel.close()

        with tempfile.TemporaryDirectory() as folder:
            known_hosts = Path(folder) / "known_hosts"
            known_hosts.write_text(
                f"[127.0.0.1]:{port} {host_key.get_name()} {host_key.get_base64()}\n", encoding="utf-8"
            )
            conn = TS3QueryClient("127.0.0.1", port, timeout=0.2, transport="ssh",
                                  username="test-query", password="test-secret", ssh_known_hosts=str(known_hosts))

            def connect():
                started = time.monotonic()
                try:
                    conn.connect()
                except Exception as exc:
                    worker_errors.append(exc)
                elapsed.append(time.monotonic() - started)

            server = threading.Thread(target=serve, daemon=True)
            worker = threading.Thread(target=connect, daemon=True)
            server.start()
            worker.start()
            try:
                self.assertTrue(shell_requested.wait(0.8), f"Peer did not reach SSH shell request: {worker_errors}")
                worker.join(0.8)
                self.assertFalse(worker.is_alive(), "SSH shell ACK permanently blocks Query connection")
                self.assertLess(elapsed[0], 1)
                self.assertIsInstance(worker_errors[0], ConnectionError)
                self.assertIn("TimeoutError", str(worker_errors[0]))
                self.assertIsNone(conn._sock)
                self.assertIsNone(conn._ssh_client)
                self.assertFalse(any(t.name == "server-query-shell-deadline" for t in threading.enumerate()))
            finally:
                release_peer.set()
                for transport in peer_transports:
                    transport.close()
                listener.close()
                worker.join(1)
                server.join(1)
                conn.close()

    def test_raw_login_and_escaped_command_regression(self):
        wire = Wire([b"TS3\n\rWelcome query\n\r", b"error id=0 msg=ok\n\r",
                     b"clid=2 client_nickname=hello\\sworld|clid=3\n\rerror id=0 msg=ok\n\r"])
        with patch("app.services.ts3_query.socket.create_connection", return_value=wire):
            conn = TS3QueryClient("localhost", 10011)
            conn.connect()
            conn.authenticate("query", "p a|ss")
            result = conn.send("clientlist", uid=True, ignored=False, unset=None)
            conn.close()
        self.assertEqual(result, [{"clid": "2", "client_nickname": "hello world"}, {"clid": "3"}])
        self.assertEqual(wire.sent, [b"login client_login_name=query client_login_password=p\\sa\\pss\n",
                                     b"clientlist -uid\n", b"quit\n"])
        self.assertTrue(wire.closed)

    def test_native_ssh_authenticates_during_handshake_without_raw_login(self):
        wire = Wire([b"TS3\n\rWelcome query\n\r", b"virtualserver_name=TS6\n\rerror id=0 msg=ok\n\r"])
        module, client = ssh_fixture(wire)
        with patch.dict(sys.modules, {"paramiko": module}):
            conn = TS3QueryClient("ts6", 10022, timeout=4, transport="ssh", username="query",
                                  password="secret", ssh_known_hosts="keys/known_hosts")
            conn.connect()
            conn.authenticate("query", "secret")
            self.assertEqual(conn.send("serverinfo"), [{"virtualserver_name": "TS6"}])
            conn.close()
        client.load_system_host_keys.assert_called_once_with()
        client.load_host_keys.assert_called_once_with("keys/known_hosts")
        client.set_missing_host_key_policy.assert_called_once_with(module.RejectPolicy.return_value)
        client.connect.assert_called_once_with(hostname="ts6", port=10022, username="query", password="secret",
                                              timeout=4, banner_timeout=4, auth_timeout=4,
                                              look_for_keys=False, allow_agent=False)
        client.get_transport.return_value.open_session.assert_called_once_with(timeout=4)
        self.assertEqual(wire.timeout, 4)
        self.assertEqual(wire.sent, [b"serverinfo\n", b"quit\n"])
        self.assertTrue(wire.closed)
        client.close.assert_called_once_with()

    def test_ssh_uses_system_known_hosts_when_custom_path_is_empty(self):
        wire = Wire([b"TS3\n\rWelcome\n\r"])
        module, client = ssh_fixture(wire)
        with patch.dict(sys.modules, {"paramiko": module}):
            conn = TS3QueryClient("ts6", 10022, transport="ssh", username="q", password="p")
            conn.connect()
            conn.close()
        client.load_host_keys.assert_not_called()

    def test_failed_ssh_handshake_closes_client_without_leaking_credentials(self):
        for failure in ("Authentication failed", "Unknown host key", "Host key mismatch"):
            with self.subTest(failure=failure):
                module, client = ssh_fixture(Wire([]))
                client.connect.side_effect = RuntimeError(failure)
                with patch.dict(sys.modules, {"paramiko": module}):
                    conn = TS3QueryClient("ts6", 10022, transport="ssh", username="q", password="secret")
                    with self.assertRaises(ConnectionError) as raised:
                        conn.connect()
                    conn.close()
                self.assertNotIn("secret", str(raised.exception))
                client.close.assert_called_once_with()

    def test_ssh_shell_open_failure_closes_session_and_client(self):
        wire = Wire([])
        wire.invoke_shell = MagicMock(side_effect=OSError("shell rejected"))
        module, client = ssh_fixture(wire)
        with patch.dict(sys.modules, {"paramiko": module}):
            conn = TS3QueryClient("ts6", 10022, transport="ssh", username="q", password="p")
            with self.assertRaises(ConnectionError):
                conn.connect()
        self.assertTrue(wire.closed)
        client.close.assert_called_once_with()

    def test_raw_greeting_disconnect_closes_connection(self):
        wire = Wire([b"TS3\n\r"])
        with patch("app.services.ts3_query.socket.create_connection", return_value=wire):
            conn = TS3QueryClient("localhost", 10011)
            with self.assertRaises(ConnectionError):
                conn.connect()
        self.assertTrue(wire.closed)

    def test_fragmented_utf8_notifications_and_alternate_newlines(self):
        payload = "notifycliententerview clid=9\r\n\r\nclid=2 client_nickname=音乐\\s房间\r\nerror id=0 msg=ok\r\n".encode()
        wire = Wire([b"TS3\r\nWelcome\r\n"] + [payload[i:i+1] for i in range(len(payload))])
        with patch("app.services.ts3_query.socket.create_connection", return_value=wire):
            conn = TS3QueryClient("localhost", 10011)
            conn.connect()
            self.assertEqual(conn.send("clientlist"), [{"clid": "2", "client_nickname": "音乐 房间"}])
            conn.close()

    def test_response_error_is_decoded_once(self):
        wire = Wire([b"TS3\n\rWelcome\n\r", b"error id=256 msg=literal\\\\s\\sdenied\n\r"])
        with patch("app.services.ts3_query.socket.create_connection", return_value=wire):
            conn = TS3QueryClient("localhost", 10011)
            conn.connect()
            with self.assertRaises(TS3QueryError) as raised:
                conn.send("clientmove", clid=3, cid=8)
            conn.close()
        self.assertEqual(raised.exception.error_id, 256)
        self.assertEqual(raised.exception.msg, "literal\\s denied")

    def test_server_error_does_not_desynchronize_next_command(self):
        wire = Wire([b"TS3\n\rWelcome\n\r", b"error id=256 msg=denied\n\r",
                     b"clid=1\n\rerror id=0 msg=ok\n\r"])
        with patch("app.services.ts3_query.socket.create_connection", return_value=wire):
            conn = TS3QueryClient("localhost", 10011)
            conn.connect()
            with self.assertRaises(TS3QueryError):
                conn.send("clientmove")
            self.assertEqual(conn.send("clientlist"), [{"clid": "1"}])
            conn.close()

    def test_disconnected_or_timed_out_command_closes_transport(self):
        for tail in (b"", socket.timeout("timed out")):
            wire = Wire([b"TS3\n\rWelcome\n\r", tail])
            with patch("app.services.ts3_query.socket.create_connection", return_value=wire):
                conn = TS3QueryClient("localhost", 10011)
                conn.connect()
                with self.assertRaises((ConnectionError, OSError)):
                    conn.send("clientlist")
                self.assertTrue(wire.closed)

    def test_rejects_invalid_transport_and_command_injection(self):
        with self.assertRaises(ValueError):
            TS3QueryClient("host", 10022, transport="ftp")
        wire = Wire([b"TS3\n\rWelcome\n\r"])
        with patch("app.services.ts3_query.socket.create_connection", return_value=wire):
            conn = TS3QueryClient("localhost", 10011)
            conn.connect()
            for command, params in [("clientlist\nquit", {}), ("clientlist", {"bad\nquit": "x"})]:
                with self.assertRaises(ValueError):
                    conn.send(command, **params)
            self.assertEqual(wire.sent, [])
            conn.close()

    def test_raw_and_ssh_parameter_escape_roundtrip(self):
        value = "路径\\s / |\n\r\t"
        self.assertEqual(TS3QueryClient._unescape(TS3QueryClient._escape(value)), value)

    def test_ssh_rejects_login_and_changed_credentials(self):
        wire = Wire([b"TS3\n\rWelcome\n\r"])
        module, _ = ssh_fixture(wire)
        with patch.dict(sys.modules, {"paramiko": module}):
            conn = TS3QueryClient("ts6", 10022, transport="ssh", username="q", password="p")
            conn.connect()
            with self.assertRaises(ValueError):
                conn.send("login", client_login_name="q", client_login_password="p")
            with self.assertRaises(ValueError):
                conn.authenticate("q", "changed")
            self.assertEqual(wire.sent, [])
            conn.close()

    def test_ssh_missing_dependency_or_credentials_reports_actionable_failure(self):
        for module, username, password in [(None, "q", "p"), (None, "", "")]:
            with patch.dict(sys.modules, {"paramiko": module}):
                conn = TS3QueryClient("ts6", 10022, transport="ssh", username=username, password=password)
                with self.assertRaises(ConnectionError):
                    conn.connect()

    def test_ssh_missing_transport_closes_client(self):
        module, client = ssh_fixture(Wire([]))
        client.get_transport.return_value = None
        with patch.dict(sys.modules, {"paramiko": module}):
            conn = TS3QueryClient("ts6", 10022, transport="ssh", username="q", password="p")
            with self.assertRaises(ConnectionError):
                conn.connect()
        client.close.assert_called_once_with()

    def test_invalid_greetings_fail_and_release_connection(self):
        for greeting in (b"error id=256 msg=denied\n", b"invalid\n" * 16):
            wire = Wire([greeting])
            with patch("app.services.ts3_query.socket.create_connection", return_value=wire):
                conn = TS3QueryClient("localhost", 10011)
                with self.assertRaises(ConnectionError):
                    conn.connect()
            self.assertTrue(wire.closed)

    def test_response_limits_cover_long_lines_and_many_short_lines(self):
        for response in (b"x" * 41, b"data=x\n" * 8):
            wire = Wire([b"TS3\nWelcome\n", response])
            with patch("app.services.ts3_query.socket.create_connection", return_value=wire), \
                 patch("app.services.ts3_query._MAX_RESPONSE", 40):
                conn = TS3QueryClient("localhost", 10011)
                conn.connect()
                with self.assertRaises(ConnectionError):
                    conn.send("clientlist")
            self.assertTrue(wire.closed)

    def test_empty_success_and_idempotent_close(self):
        wire = Wire([b"TS3\nWelcome\n", b"error id=0 msg=ok\n"])
        with patch("app.services.ts3_query.socket.create_connection", return_value=wire):
            conn = TS3QueryClient("localhost", 10011)
            conn.connect()
            self.assertEqual(conn.send("whoami"), [])
            conn.close()
            conn.close()
        self.assertEqual(wire.sent, [b"whoami\n", b"quit\n"])

    def test_reconnect_closes_old_connection(self):
        first, second = Wire([b"TS3\nWelcome\n"]), Wire([b"TS3\nWelcome\n"])
        with patch("app.services.ts3_query.socket.create_connection", side_effect=[first, second]):
            conn = TS3QueryClient("localhost", 10011)
            conn.connect()
            conn.connect()
            self.assertTrue(first.closed)
            self.assertFalse(second.closed)
            conn.close()

    def test_authenticate_requires_a_connection(self):
        with self.assertRaises(ConnectionError):
            TS3QueryClient("localhost", 10011).authenticate("q", "p")

    def test_send_before_connection_reports_connection_error(self):
        with self.assertRaises(ConnectionError):
            TS3QueryClient("localhost", 10011).send("clientlist")


if __name__ == "__main__":
    unittest.main()
