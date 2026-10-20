"""Preview or conditionally change a local owner's v3/v4 routing setting."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections.abc import Sequence
from typing import Any

import psycopg
from psycopg_pool import PoolTimeout

from mingjing_core.application.runtime_settings import RuntimeSettingsService
from mingjing_core.domain.contracts import EvidenceError, RevisionConflict, ScopeError
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.tools.runtime_switch_target import (
    TargetError,
    local_target,
    verify_target,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="本机隔离库 v3/v4 路由开关；不验证模型或部署就绪"
    )
    result.add_argument("--owner", required=True)
    result.add_argument("--runtime", required=True, choices=("v3", "v4"))
    result.add_argument("--environment", choices=("local", "stage"), default="local")
    result.add_argument("--dsn-env", default="CORE_TEST_DSN")
    result.add_argument("--schema", default="mingjing_core")
    result.add_argument("--expect-runtime", choices=("v3", "v4"))
    result.add_argument("--request-id")
    result.add_argument("--apply", action="store_true")
    return result


def execute(args: argparse.Namespace) -> dict[str, Any]:
    if args.environment != "local":
        raise TargetError("stage 入口尚未启用；本命令当前只允许本机隔离测试库")
    if args.apply and (args.expect_runtime is None or args.request_id is None):
        raise TargetError("写入必须同时指定 --expect-runtime 和 --request-id")
    if not args.apply and (
        args.expect_runtime is not None or args.request_id is not None
    ):
        raise TargetError("预览不接受写入旧值或请求标识；请核对是否需要显式 --apply")
    dsn, target = local_target(
        args.environment, os.getenv(args.dsn_env, ""), args.schema
    )
    repo = PostgresRepository(dsn, schema=args.schema, initialize=False, max_size=1)
    try:
        verify_target(repo, dsn)
        service = RuntimeSettingsService(repo)
        if args.apply:
            receipt = service.apply(
                args.owner,
                args.runtime,
                expected_runtime=args.expect_runtime,
                request_id=args.request_id,
            )
        else:
            receipt = service.preview(args.owner, args.runtime)
        return dict(
            receipt,
            target_sha256=target,
            owner_sha256=hashlib.sha256(args.owner.encode()).hexdigest(),
        )
    finally:
        repo.close()


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        receipt = execute(args)
    except (
        TargetError,
        ScopeError,
        RevisionConflict,
        EvidenceError,
        psycopg.Error,
        PoolTimeout,
    ) as error:
        code, message = public_error(error)
        print(
            json.dumps(
                {"status": "rejected", "code": code, "message": message},
                ensure_ascii=False,
            )
        )
        return 2
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
    return 0


def public_error(error: Exception) -> tuple[str, str]:
    if isinstance(error, TargetError):
        return "target_or_arguments", str(error)
    if isinstance(error, ScopeError):
        return "owner_scope", "目标用户不存在或未获授权；未修改路由"
    if isinstance(error, RevisionConflict):
        return "precondition", "运行时旧值已改变，请重新预览；未修改路由"
    if isinstance(error, EvidenceError):
        return (
            "invalid_state_or_replay",
            "设置、数据版本或请求重放不符合约束；未修改路由",
        )
    return "database", "数据库校验或操作失败；详情未输出，请检查本机隔离配置"


if __name__ == "__main__":
    raise SystemExit(main())
