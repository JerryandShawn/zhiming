"""Metadata-only rechecks; account for the verified Web process during opening."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from tools.b1_publication_contracts import require


def web_client_ports(pid: int, proc: Path = Path("/proc")) -> set[int]:
    """Match socket inodes owned by the exact systemd MainPID and its children."""
    require(pid > 1, "WEB_PID_MISSING")
    pending, visited, inodes = [pid], set(), set()
    while pending:
        current = pending.pop()
        require(len(visited) < 256, "WEB_PROCESS_TREE_TOO_LARGE")
        if current in visited:
            continue
        visited.add(current)
        root = proc / str(current)
        children = root / "task" / str(current) / "children"
        pending.extend(int(item) for item in children.read_text().split())
        for descriptor in (root / "fd").iterdir():
            try:
                target = os.readlink(descriptor)
            except FileNotFoundError:
                continue
            if target.startswith("socket:[") and target.endswith("]"):
                inodes.add(target[8:-1])
    ports = set()
    for name in ("tcp", "tcp6"):
        for line in (proc / "net" / name).read_text().splitlines()[1:]:
            fields = line.split()
            if len(fields) > 9 and fields[9] in inodes and fields[3] == "01":
                if int(fields[2].rsplit(":", 1)[1], 16) == 5432:
                    ports.add(int(fields[1].rsplit(":", 1)[1], 16))
    return ports


def no_unknown_clients(database: Any, allowed_ports: set[int]) -> None:
    with database._connection("owner") as connection:
        connection.execute("SET TRANSACTION READ ONLY")
        rows = connection.execute(
            "SELECT usename,host(client_addr) AS host,client_port FROM pg_stat_activity "
            "WHERE datname=current_database() AND pid<>pg_backend_pid() AND backend_type='client backend'"
        ).fetchall()
    for row in rows:
        require(row["host"] in {"127.0.0.1", "::1"}
                and row["usename"] == "zhiming_core_live_writer"
                and row["client_port"] in allowed_ports, "UNKNOWN_CLIENT_DURING_OPENING")
