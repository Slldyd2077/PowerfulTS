"""Every TeamSpeak workflow must honor the configured ServerQuery transport."""
from types import SimpleNamespace
from unittest.mock import Mock, patch
import socket
import threading

import paramiko
import pytest

from app.services import bot_idle_manager, bot_mover, ts3_auth, voice_exclusivity
from app.services.ts3_monitor import TS3Monitor


def settings(transport=None):
    values = dict(ts3_host="ts.example", ts3_query_port=10011,
                  ts3_query_user="query", ts3_query_password="secret", ts3_sid=2)
    if transport is not None:
        values.update(ts3_query_transport=transport,
                      ts3_query_ssh_known_hosts="/config/known_hosts" if transport == "ssh" else "",
                      ts3_query_port=10022 if transport == "ssh" else 10011)
    return SimpleNamespace(**values)


CLIENTS = [
    {"client_type": "0", "clid": "7", "cid": "9", "client_nickname": "Alice",
     "client_unique_identifier": "user-uid"},
    {"client_type": "0", "clid": "42", "cid": "3", "client_nickname": "MusicBot",
     "client_unique_identifier": "bot-uid"},
]
ACCOUNT = SimpleNamespace(ts_nickname="Alice", unique_identifier="user-uid")


def invoke(workflow, config):
    if workflow == "monitor":
        monitor = TS3Monitor(config)
        monitor._connect()
        monitor._disconnect()
    elif workflow == "verify":
        assert ts3_auth.send_verify_code(config, "Alice", "123456") == "user-uid"
    elif workflow == "private_message":
        assert ts3_auth.send_private_message(config, "Alice", "hello")
    elif workflow == "move":
        assert bot_mover.move_bot_to_user(config, 42, "MusicBot", ACCOUNT)["moved"]
    elif workflow == "idle":
        assert bot_idle_manager.fetch_ts_clients(config) == CLIENTS
    elif workflow == "kick":
        assert voice_exclusivity.kick_real_ts_client_for_account(config, ACCOUNT, exclude_clid=42)
    elif workflow == "presence":
        assert voice_exclusivity.is_ts_client_connection_present(config, "user-uid", 7)


MODULES = {"monitor": "ts3_monitor", "verify": "ts3_auth", "private_message": "ts3_auth",
           "move": "bot_mover", "idle": "bot_idle_manager", "kick": "voice_exclusivity",
           "presence": "voice_exclusivity"}


@pytest.mark.parametrize("workflow", MODULES)
@pytest.mark.parametrize("transport", [None, "raw", "ssh"])
def test_all_workflows_use_transport_credentials_and_authenticate(workflow, transport):
    config = settings(transport)
    conn = Mock()
    conn.send.side_effect = lambda command, **params: CLIENTS if command == "clientlist" else []
    with patch(f"app.services.{MODULES[workflow]}.TS3QueryClient", return_value=conn) as factory:
        invoke(workflow, config)
    factory.assert_called_once_with(
        config.ts3_host, config.ts3_query_port, transport=transport or "raw",
        username="query", password="secret",
        ssh_known_hosts="/config/known_hosts" if transport == "ssh" else None,
    )
    conn.connect.assert_called_once_with()
    conn.authenticate.assert_called_once_with("query", "secret")
    conn.send.assert_any_call("use", sid=2)
    assert all(call.args[0] != "login" for call in conn.send.call_args_list)
    conn.close.assert_called_once_with()


@pytest.mark.parametrize("transport", [None, "raw", "ssh"])
def test_stats_expose_query_transport_without_guessing_server_generation(transport):
    snapshot = TS3Monitor(settings(transport)).get_stats()
    assert snapshot["serverquery_transport"] == (transport or "raw")
    assert "server_family" not in snapshot


@pytest.mark.parametrize("failure_stage", ["connect", "authenticate", "select_server"])
def test_monitor_closes_failed_initial_connection(failure_stage):
    conn = Mock()
    if failure_stage == "select_server":
        conn.send.side_effect = ConnectionError("server not available")
    else:
        getattr(conn, failure_stage).side_effect = ConnectionError("server not available")
    monitor = TS3Monitor(settings("ssh"))
    with patch("app.services.ts3_monitor.TS3QueryClient", return_value=conn):
        with pytest.raises(ConnectionError):
            monitor._connect()
    conn.close.assert_called_once_with()
    assert monitor._conn is None
    assert not monitor.running


@pytest.fixture(scope="module")
def ssh_host_key():
    return paramiko.RSAKey.generate(2048)


@pytest.fixture(params=["raw", "ssh"])
def loopback_query(request, tmp_path, ssh_host_key):
    """Real sockets and SSH crypto, with a minimal ServerQuery protocol peer."""
    transport_kind = request.param
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    listener.settimeout(5)
    port = listener.getsockname()[1]
    known_hosts = tmp_path / "known_hosts"
    known_hosts.write_text(
        f"[127.0.0.1]:{port} {ssh_host_key.get_name()} {ssh_host_key.get_base64()}\n",
        encoding="utf-8",
    )
    commands, authentications, errors = [], [], []
    shell_requested = threading.Event()

    class QuerySSHServer(paramiko.ServerInterface):
        def check_auth_password(self, username, password):
            authentications.append((username, password))
            return paramiko.AUTH_SUCCESSFUL if (username, password) == ("query", "secret") else paramiko.AUTH_FAILED

        def check_channel_request(self, kind, chanid):
            return paramiko.OPEN_SUCCEEDED if kind == "session" else paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED

        def check_channel_shell_request(self, channel):
            shell_requested.set()
            return True

    def serve():
        wire = ssh_transport = channel = None
        try:
            wire, _address = listener.accept()
            wire.settimeout(5)
            if transport_kind == "ssh":
                ssh_transport = paramiko.Transport(wire)
                ssh_transport.add_server_key(ssh_host_key)
                ssh_transport.start_server(server=QuerySSHServer())
                channel = ssh_transport.accept(5)
                if channel is None or not shell_requested.wait(5):
                    raise TimeoutError("SSH Query shell was not opened")
                peer = channel
                peer.settimeout(5)
            else:
                peer = wire
            peer.sendall(b"TS3\n\rWelcome to the TeamSpeak ServerQuery interface.\n\r")
            buffered = b""
            while True:
                chunk = peer.recv(4096)
                if not chunk:
                    break
                buffered += chunk
                while b"\n" in buffered:
                    line, buffered = buffered.split(b"\n", 1)
                    command = line.decode("utf-8").strip()
                    commands.append(command)
                    if command == "quit":
                        return
                    if command.startswith("clientlist"):
                        peer.sendall(
                            b"client_type=0 clid=7 cid=9 client_nickname=Alice client_unique_identifier=user-uid|"
                            b"client_type=0 clid=42 cid=3 client_nickname=MusicBot client_unique_identifier=bot-uid\n\r"
                        )
                    peer.sendall(b"error id=0 msg=ok\n\r")
        except Exception as exc:
            errors.append(exc)
        finally:
            if ssh_transport is not None:
                ssh_transport.close()
            if wire is not None:
                wire.close()

    worker = threading.Thread(target=serve, daemon=True)
    worker.start()
    config = SimpleNamespace(**{
        **vars(settings(transport_kind)),
        "ts3_host": "127.0.0.1", "ts3_query_port": port,
        "ts3_query_ssh_known_hosts": str(known_hosts) if transport_kind == "ssh" else "",
    })
    try:
        yield config, commands, authentications
    finally:
        listener.close()
        worker.join(6)
        assert not worker.is_alive(), "Loopback query did not close"
        assert not errors, errors


@pytest.mark.parametrize("workflow", MODULES)
def test_workflows_over_real_tcp_and_authenticated_ssh(loopback_query, workflow):
    config, commands, authentications = loopback_query
    invoke(workflow, config)
    if config.ts3_query_transport == "ssh":
        assert authentications == [("query", "secret")]
        assert not any(command.startswith("login") for command in commands)
    else:
        assert "login client_login_name=query client_login_password=secret" in commands
    assert "use sid=2" in commands
