"""Explicit stage-restore replay; validate by default and never select live implicitly."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from tools.b1_restore_replay_contracts import (
    DSN_ENV,
    ReplayRejected,
    RestoreRequest,
    file_hash,
    load_document,
    regular,
    require,
    verify_candidate,
)


def worker_code() -> str:
    root = Path(__file__).resolve().parents[1]
    return (
        "import sys,json,pathlib\n"
        f"sys.path.insert(0,{str(root)!r})\n"
        "from tools.b1_restore_replay_contracts import RestoreRequest,ReplayRejected\n"
        "from tools.b1_restore_replay_worker import replay\n"
        "value=json.load(sys.stdin);args=value['request']\n"
        "for name in ('candidate_source','candidate_python','ledger'):args[name]=pathlib.Path(args[name])\n"
        "request=RestoreRequest(**args)\n"
        "sys.path.insert(0,str(request.candidate_source))\n"
        "try: print(json.dumps(replay(request,value['document']),sort_keys=True))\n"
        "except ReplayRejected as error:\n"
        " print(json.dumps({'code':str(error)}),file=sys.stderr);sys.exit(2)\n"
        "except Exception:\n"
        " print(json.dumps({'code':'CANDIDATE_BUSINESS_REPLAY_FAILED'}),file=sys.stderr);sys.exit(2)\n"
    )


def worker_environment(request: RestoreRequest) -> dict[str, str]:
    environment = {
        key: os.environ[key] for key in ("PATH", "SystemRoot", "WINDIR", "TEMP", "TMP", "LANG") if key in os.environ
    }
    environment.update(
        {
            DSN_ENV: request.dsn(),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
            "LANGSMITH_TRACING": "false",
            "LANGCHAIN_TRACING_V2": "false",
            "CORE_FEISHU_ENABLED": "false",
        }
    )
    return environment


def safe_worker_failure(stderr: str) -> ReplayRejected:
    try:
        code = json.loads(stderr)["code"]
    except (ValueError, TypeError, KeyError):
        code = "CANDIDATE_REPLAY_FAILED"
    safe = {
        "RESTORE_IDENTITY",
        "POSTGRES15_REQUIRED",
        "SERVER_LOOPBACK_ONLY",
        "MIGRATION_ROLE_ELEVATED",
        "DATABASE_OWNER",
        "RESTORE_SCHEMA7_CHECKSUMS",
        "COMPLETE_OWNER_LEDGER_REQUIRED",
        "RESTORE_NOT_QUIESCENT",
        "OTHER_RESTORE_SESSIONS",
        "RESTORE_REPLAY_LOCKED",
        "WRONG_CANDIDATE_IMPORT",
        "CANDIDATE_BUSINESS_REPLAY_FAILED",
        "CANDIDATE_REPLAY_FAILED",
    }
    return ReplayRejected(code if code in safe else "CANDIDATE_REPLAY_FAILED")


def run_candidate(request: RestoreRequest, document: dict[str, Any]) -> dict[str, Any]:
    request.validate()
    verify_candidate(request.candidate_source)
    require(document == load_document(request), "LEDGER_DOCUMENT_CHANGED")
    regular(request.candidate_python.resolve())
    fields = asdict(request)
    fields.update({name: str(fields[name]) for name in ("candidate_source", "candidate_python", "ledger")})
    result = subprocess.run(
        [
            str(request.candidate_python),
            "-I",
            "-B",
            "-X",
            "pycache_prefix=" + os.path.abspath(os.devnull),
            "-c",
            worker_code(),
        ],
        input=json.dumps({"request": fields, "document": document}),
        env=worker_environment(request),
        capture_output=True,
        encoding="utf-8",
        timeout=120,
        check=False,
    )
    if result.returncode:
        raise safe_worker_failure(result.stderr)
    try:
        receipt = json.loads(result.stdout)
    except (ValueError, TypeError):
        raise ReplayRejected("CANDIDATE_RECEIPT_INVALID") from None
    require(
        isinstance(receipt, dict) and receipt.get("schema") == "b1-stage-restore-replay-v1",
        "CANDIDATE_RECEIPT_INVALID",
    )
    receipt["candidate_python_sha256"] = file_hash(request.candidate_python)
    receipt["posix_permissions_verified"] = os.name == "posix"
    return receipt


def protected_output(path: Path, receipt: dict[str, Any]) -> None:
    require(
        path.parent.is_dir() and not path.exists() and not path.is_symlink(),
        "NEW_RECEIPT_REQUIRED",
    )
    require(not any(parent.is_symlink() for parent in path.parents), "NEW_RECEIPT_REQUIRED")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(receipt, stream, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    for name in (
        "operation-id",
        "scope",
        "database",
        "schema",
        "candidate-source",
        "candidate-python",
        "ledger",
        "ledger-sha256",
    ):
        result.add_argument("--" + name, required=True)
    result.add_argument("--local-drill", action="store_true")
    result.add_argument("--quiesced", action="store_true")
    result.add_argument("--apply", action="store_true")
    result.add_argument("--output", type=Path)
    return result


def request_from(args: argparse.Namespace) -> RestoreRequest:
    return RestoreRequest(
        args.operation_id,
        args.scope,
        args.database,
        args.schema,
        Path(args.candidate_source),
        Path(args.candidate_python),
        Path(args.ledger),
        args.ledger_sha256,
        args.local_drill,
    )


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    request = request_from(args)
    try:
        request.validate()
        verify_candidate(request.candidate_source)
        document = load_document(request)
        if not args.apply:
            print(
                json.dumps(
                    {
                        "valid": True,
                        "apply": False,
                        "database_connections": 0,
                        "external_sends": 0,
                    }
                )
            )
            return 0
        require(
            args.quiesced and args.output is not None,
            "EXPLICIT_QUIESCED_APPLY_REQUIRED",
        )
        require(args.local_drill or sys.platform == "linux", "LINUX_STAGE_REQUIRED")
        require(
            not args.output.exists() and args.output.parent.is_dir(),
            "NEW_RECEIPT_REQUIRED",
        )
        receipt = run_candidate(request, document)
        protected_output(args.output, receipt)
        print(
            json.dumps(
                {
                    "applied": True,
                    "changed": receipt["changed"],
                    "external_sends": 0,
                    "model_calls": 0,
                }
            )
        )
        return 0
    except ReplayRejected as error:
        print(
            json.dumps({"ok": False, "code": str(error), "model_calls": 0, "external_sends": 0}),
            file=sys.stderr,
        )
    except Exception:
        print(
            json.dumps(
                {
                    "ok": False,
                    "code": "RESTORE_REPLAY_FAILED",
                    "model_calls": 0,
                    "external_sends": 0,
                }
            ),
            file=sys.stderr,
        )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
