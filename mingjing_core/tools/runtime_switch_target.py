"""Validate an explicit disposable loopback target before any connection."""

from __future__ import annotations

import hashlib
import os
import re

import psycopg
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from mingjing_core.application.runtime_settings import verify_local_identity

LOOPBACK = frozenset({"localhost", "127.0.0.1", "::1"})
PARAMETERS = frozenset(
    {
        "host",
        "hostaddr",
        "port",
        "dbname",
        "user",
        "password",
        "sslmode",
        "connect_timeout",
    }
)


class TargetError(ValueError):
    """Only fixed public messages may reach CLI output."""


def local_target(environment: str, dsn: str, schema: str) -> tuple[str, str]:
    if environment != "local":
        raise TargetError("stage 入口尚未启用；本命令当前只允许本机隔离测试库")
    if not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]{0,62}", schema):
        raise TargetError("数据库分区标识无效")
    if os.getenv("PGSERVICE") or os.getenv("PGOPTIONS"):
        raise TargetError("请移除继承的 PostgreSQL 服务或启动参数")
    try:
        params = conninfo_to_dict(dsn)
    except (psycopg.Error, TypeError):
        raise TargetError("需要明确的本机隔离测试库配置") from None
    _validate_parameters(params)
    host = params["host"]
    params.update(
        hostaddr="127.0.0.1" if host == "localhost" else host,
        port=params.get("port", "5432"),
        connect_timeout="5",
        sslmode="disable",
        passfile=os.devnull,
        application_name="core-local-runtime-switch",
    )
    identity = ":".join(
        (params["hostaddr"], params["port"], params["dbname"], params["user"], schema)
    )
    return make_conninfo(**params), hashlib.sha256(identity.encode()).hexdigest()


def _validate_parameters(params: dict[str, str]) -> None:
    database = params.get("dbname", "").lower()
    try:
        port = int(params.get("port", "5432"))
    except ValueError:
        port = 0
    if (
        params.keys() - PARAMETERS
        or params.get("host") not in LOOPBACK
        or params.get("hostaddr", "127.0.0.1") not in LOOPBACK
        or not params.get("user")
        or not 1 <= port <= 65535
        or not re.search(r"(?:test|eval|p0)", database)
        or re.search(r"(?:stage|live|prod)", database)
    ):
        raise TargetError(
            "只允许明确的 loopback 隔离 test/eval/p0 库；禁止 stage、生产或远程目标"
        )


def verify_target(repo: object, dsn: str) -> None:
    verify_local_identity(repo, conninfo_to_dict(dsn))
