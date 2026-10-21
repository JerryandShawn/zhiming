"""Pinned interpreter subprocesses with no inherited provider, tracing, or PG settings."""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import asdict
from pathlib import Path
from typing import Any

from tools.b1_linux_application_drill_contracts import DSN_ENV, ApplicationBlocked, ApplicationRequest, require


def environment(request: ApplicationRequest) -> dict[str, str]:
    result = {
        key: os.environ[key] for key in ("PATH", "SystemRoot", "WINDIR", "TEMP", "TMP", "LANG") if key in os.environ
    }
    result.update(
        PYTHONDONTWRITEBYTECODE="1",
        PYTHONNOUSERSITE="1",
        LANGSMITH_TRACING="false",
        LANGCHAIN_TRACING_V2="false",
        OTEL_SDK_DISABLED="true",
        CORE_FEISHU_ENABLED="false",
    )
    if request.phase == "backfill":
        result[DSN_ENV] = request.dsn()
    return result


def fields(request: ApplicationRequest) -> dict[str, Any]:
    return {key: str(value) if isinstance(value, Path) else value for key, value in asdict(request).items()}


def command(request: ApplicationRequest, code: str) -> list[str]:
    # -B only stops writes; a non-directory prefix also prevents reading package-local stale bytecode.
    return [
        str(request.candidate_python),
        "-I",
        "-B",
        "-X",
        "pycache_prefix=" + os.path.abspath(os.devnull),
        "-c",
        code,
    ]


def initialization(request: ApplicationRequest) -> str:
    root = str(Path(__file__).resolve().parents[1])
    return (
        "import sys,json,pathlib\n" + f"sys.path.insert(0,{root!r})\n"
        "from tools.b1_linux_application_drill_contracts import ApplicationRequest,ApplicationBlocked\n"
        f"fields=json.loads({json.dumps(fields(request))!r})\n"
        "for k in ('candidate_source','candidate_python'):fields[k]=pathlib.Path(fields[k])\n"
        "request=ApplicationRequest(**fields)\n"
        "sys.path.insert(0,str(request.candidate_source))\n"
    )


def writer_code(request: ApplicationRequest, directory: Path) -> str:
    return (
        initialization(request) + "from tools.b1_linux_application_drill_fence import writer\n"
        f"writer(request,pathlib.Path({str(directory)!r}))\n"
    )


def worker_code(request: ApplicationRequest) -> str:
    # Load controller tools before prepending the candidate's regular tools package.
    root = str(Path(__file__).resolve().parents[1])
    return (
        "import sys,json,pathlib\n" + f"sys.path.insert(0,{root!r})\n"
        "from tools.b1_linux_application_drill_contracts import ApplicationRequest,ApplicationBlocked\n"
        "from tools.b1_linux_application_drill_runtime import runtime_capability\n"
        "from tools.b1_linux_application_drill_backfill import backfill_primary\n"
        "from tools.b1_linux_application_drill_fence import fence\n"
        "fields=json.load(sys.stdin)\n"
        "for k in ('candidate_source','candidate_python'):fields[k]=pathlib.Path(fields[k])\n"
        "request=ApplicationRequest(**fields)\nsys.path.insert(0,str(request.candidate_source))\n"
        "try:\n"
        " capability=runtime_capability(request)\n"
        " result={'runtime_only':True,'database_connections':0}\n"
        " if request.phase=='backfill':result=backfill_primary(request)\n"
        " if request.phase=='fence':result=fence(request)\n"
        " print(json.dumps({'runtime':capability,'result':result},sort_keys=True))\n"
        "except ApplicationBlocked as error:\n"
        " print(json.dumps({'code':str(error)}),file=sys.stderr);sys.exit(2)\n"
        "except Exception:\n"
        " print(json.dumps({'code':'APPLICATION_PINNED_WORKER_FAILED'}),file=sys.stderr);sys.exit(2)\n"
    )


def run_worker(request: ApplicationRequest) -> dict[str, Any]:
    request.validate()
    result = subprocess.run(
        command(request, worker_code(request)),
        input=json.dumps(fields(request)),
        env=environment(request),
        capture_output=True,
        encoding="utf-8",
        timeout=180,
        check=False,
    )
    if result.returncode:
        try:
            code = json.loads(result.stderr)["code"]
        except (ValueError, TypeError, KeyError):
            code = "APPLICATION_PINNED_WORKER_FAILED"
        raise ApplicationBlocked(
            code if re.fullmatch(r"[A-Z][A-Z0-9_]{3,80}", str(code)) else "APPLICATION_PINNED_WORKER_FAILED"
        )
    value = json.loads(result.stdout)
    require(isinstance(value, dict) and set(value) == {"runtime", "result"}, "APPLICATION_WORKER_RECEIPT")
    return value
