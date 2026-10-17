"""Reject remote or non-test databases before opening an evaluation repository."""

import os
import re

import psycopg
from psycopg.conninfo import conninfo_to_dict, make_conninfo

LOOPBACK = {"localhost", "127.0.0.1", "::1"}


def validate_local_dsn(dsn: str) -> None:
    try:
        params = conninfo_to_dict(dsn)
    except psycopg.Error:
        raise ValueError("CORE_TEST_DSN must identify an explicit local test database") from None
    database = params.get("dbname", "").lower()
    if (
        params.get("host") not in LOOPBACK
        or params.get("hostaddr", "127.0.0.1") not in LOOPBACK
        or params.get("service")
        or not re.search(r"(?:test|eval|p0)", database)
        or re.search(r"(?:stage|live|prod)", database)
    ):
        raise ValueError("Evaluation requires an explicit loopback test database; stage/live are forbidden")


def local_dsn(dsn: str) -> str:
    validate_local_dsn(dsn)
    if os.getenv("PGSERVICE"):
        raise ValueError("Evaluation refuses inherited PostgreSQL service routing")
    params = conninfo_to_dict(dsn)
    host = params["host"]
    params["hostaddr"] = "127.0.0.1" if host == "localhost" else host
    params["port"] = params.get("port", "5432")
    params.pop("service", None)
    return make_conninfo(**params)


def verify_local_postgres(dsn: str) -> None:
    validate_local_dsn(dsn)
    with psycopg.connect(local_dsn(dsn), connect_timeout=5, autocommit=True) as connection:
        version, address = connection.execute(
            "SELECT current_setting('server_version_num')::int, host(inet_server_addr())"
        ).fetchone()
        if not 150000 <= version < 160000 or address not in {"127.0.0.1", "::1"}:
            raise ValueError("Evaluation requires a loopback PostgreSQL 15 server")
