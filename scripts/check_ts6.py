#!/usr/bin/env python3
"""Run native SSH Query contract checks against a dedicated TS6 test server.

Uses TS3_* environment configuration; creates and deletes one temporary channel.
TS6_SMOKE_ALLOW_WRITES=1 is required to avoid mutating an unintended live server.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import time
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.core.config import get_settings
from app.services.ts3_monitor import TS3Monitor
from app.services.ts3_query import TS3QueryClient


def main() -> None:
    if os.environ.get("TS6_SMOKE_ALLOW_WRITES") != "1":
        raise SystemExit("Use a dedicated test server and set TS6_SMOKE_ALLOW_WRITES=1")
    settings = get_settings()
    if settings.ts3_query_transport != "ssh":
        raise SystemExit("TS3_QUERY_TRANSPORT=ssh is required")
    client = TS3QueryClient(
        settings.ts3_host, settings.ts3_query_port, transport="ssh",
        username=settings.ts3_query_user, password=settings.ts3_query_password,
        ssh_known_hosts=settings.ts3_query_ssh_known_hosts or None,
    )
    name = f"PowerfulTS 测试 | {uuid4().hex[:12]}"
    try:
        client.connect()
        client.authenticate(settings.ts3_query_user, settings.ts3_query_password)
        version = client.send("version")[0]["version"]
        if not version.startswith("6."):
            raise RuntimeError("The test target must be a TS6 server")
        client.send("use", sid=settings.ts3_sid)
        assert client.send("channellist")
        cid = int(client.send("channelcreate", channel_name=name, channel_flag_permanent=1)[0]["cid"])
        try:
            assert client.send("channelinfo", cid=cid)[0]["channel_name"] == name
            client.send("channeledit", cid=cid, channel_name=f"{name} updated")
            assert client.send("channelinfo", cid=cid)[0]["channel_name"] == f"{name} updated"
        finally:
            client.send("channeldelete", cid=cid, force=1)
    finally:
        client.close()
    # TS6 can rate-limit closely spaced SSH connection attempts.
    time.sleep(3)
    monitor = TS3Monitor(settings)
    try:
        monitor._connect()
        monitor._poll_once()
        assert monitor.running and monitor.channel_tree
        assert monitor.get_stats()["serverquery_transport"] == "ssh"
    finally:
        monitor._disconnect()
    print(json.dumps({"serverVersion": version, "nativeSSH": True,
                      "channelCRUD": True, "monitorSnapshot": True}))


if __name__ == "__main__":
    main()
