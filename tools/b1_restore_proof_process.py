"""Restricted pg_restore and pinned Python child processes; errors never echo inputs."""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import asdict
from pathlib import Path
from typing import Any

from psycopg.conninfo import conninfo_to_dict

from tools.b1_restore_proof_contracts import OWNER_ENV, WRITER_ENV, ProofRequest
from tools.b1_restore_replay_contracts import (
    ReplayRejected,
    file_hash,
    regular,
    require,
)
from tools.b1_runtime_trust import inspect_core_venv


def environment(request: ProofRequest) -> dict[str, str]:
    result = {
        key: os.environ[key] for key in ("PATH", "SystemRoot", "WINDIR", "TEMP", "TMP", "LANG") if key in os.environ
    }
    result.update(
        LANGSMITH_TRACING="false",
        LANGCHAIN_TRACING_V2="false",
        OTEL_SDK_DISABLED="true",
        CORE_FEISHU_ENABLED="false",
        PYTHONDONTWRITEBYTECODE="1",
        PYTHONNOUSERSITE="1",
    )
    dsns = request.dsns()
    for name in (OWNER_ENV, WRITER_ENV):
        result[name] = dsns["owner" if name == OWNER_ENV else "writer"]
    passfile = os.environ.get("B1_PROOF_PGPASSFILE")
    if passfile:
        regular(Path(passfile), private=True, local_drill=request.local_drill)
        result["B1_PROOF_PGPASSFILE"] = passfile
    return result


def restore_archive(request: ProofRequest) -> dict[str, Any]:
    require(file_hash(request.pg_restore) == request.pg_restore_sha256, "PG_RESTORE_CHANGED")
    if not request.local_drill:
        for binary in (request.pg_restore, request.candidate_python, request.candidate_python.resolve()):
            for item in (binary, *binary.parents):
                observed = item.stat()
                require(observed.st_uid == 0 and observed.st_mode & 0o022 == 0, "RESTORE_EXECUTABLE_NOT_TRUSTED")
    env = environment(request)
    for key, value in conninfo_to_dict(request.dsn("owner")).items():
        name = {
            "host": "PGHOST",
            "port": "PGPORT",
            "user": "PGUSER",
            "password": "PGPASSWORD",
            "dbname": "PGDATABASE",
            "hostaddr": "PGHOSTADDR",
            "passfile": "PGPASSFILE",
        }.get(key)
        if name:
            env[name] = value
    version = subprocess.run(
        [str(request.pg_restore), "--version"], env=env, capture_output=True, timeout=10, check=False
    )
    require(version.returncode == 0 and re.search(rb"PostgreSQL\) 15\.", version.stdout), "PG_RESTORE15_REQUIRED")
    result = subprocess.run(
        [
            str(request.pg_restore),
            "--exit-on-error",
            "--single-transaction",
            "--no-owner",
            "--no-acl",
            "--dbname=" + request.database,
            str(request.dump),
        ],
        env=env,
        capture_output=True,
        timeout=600,
        check=False,
    )
    require(result.returncode == 0, "PG_RESTORE_FAILED")
    return {"executed": True, "exit_code": result.returncode, "executable_sha256": request.pg_restore_sha256}


def worker_code(request: ProofRequest, phase: str) -> str:
    require(phase in {"migrate", "replay"}, "WORKER_PHASE")
    root = str(Path(__file__).resolve().parents[1])
    return (
        "import sys,json,pathlib\n"
        f"sys.path.insert(0,{root!r})\n"
        "from tools.b1_restore_proof_contracts import ProofRequest\n"
        "from tools.b1_restore_replay_contracts import ReplayRejected\n"
        "from tools.core_incremental_contracts import UpgradeRejected\n"
        "from tools.b1_restore_proof_worker import migrate,replay\n"
        "value=json.load(sys.stdin);fields=value['request']\n"
        "for k in ('request','backup','dump','backup_ledger','ledger',"
        "'candidate_source','candidate_python','pg_restore'):"
        "fields[k]=pathlib.Path(fields[k])\n"
        "request=ProofRequest(**fields)\n"
        "sys.path.insert(0,str(request.candidate_source))\n"
        "try:\n"
        f" result={phase}(request" + (",value['document']" if phase == "replay" else "") + ")\n"
        " print(json.dumps(result,sort_keys=True))\n"
        "except (ReplayRejected,UpgradeRejected) as error:\n"
        " print(json.dumps({'code':str(error)}),file=sys.stderr);sys.exit(2)\n"
        "except Exception:\n"
        " print(json.dumps({'code':'PINNED_CANDIDATE_PHASE_FAILED'}),file=sys.stderr);sys.exit(2)\n"
    )


def python_prefix(executable: Path) -> list[str]:
    # -B forbids writing, but still reads timestamp-valid poisoned pyc files.
    return [str(executable), "-I", "-B", "-X", "pycache_prefix=" + os.path.abspath(os.devnull)]


def run_worker(request: ProofRequest, phase: str, document: dict[str, Any]) -> dict[str, Any]:
    if not request.local_drill:
        inspect_core_venv()
    fields = {key: str(value) if isinstance(value, Path) else value for key, value in asdict(request).items()}
    result = subprocess.run(
        [*python_prefix(request.candidate_python), "-c", worker_code(request, phase)],
        input=json.dumps({"request": fields, "document": document}),
        env=environment(request),
        capture_output=True,
        encoding="utf-8",
        timeout=180,
        check=False,
    )
    if result.returncode:
        # Even trusted child code can fail before its exception boundary. Never return raw stderr.
        raise ReplayRejected("PINNED_" + phase.upper() + "_FAILED")
    value = json.loads(result.stdout)
    require(isinstance(value, dict), "PINNED_WORKER_RECEIPT")
    return value
