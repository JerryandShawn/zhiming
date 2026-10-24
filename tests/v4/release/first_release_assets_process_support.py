"""Local argv projection reaches the real launcher; only fixed native dispatch is synthetic."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from first_release_service_process_support import child_environment
from first_release_support import ROOT

STDOUT = "SYNTHETIC_NATIVE_STDOUT\n"
BODY = "SYNTHETIC_ASSETS_MEMORY_BODY"
CHILD = r"""
import json,os,sys,urllib.request
value=json.loads(sys.stdin.readline())
sys.path.insert(0,value["candidate"])
import httpx
from tools import first_release_service as launcher

def forbidden(*args,**kwargs):
    raise AssertionError("ASSETS_TEST_EXTERNAL_HTTP_FORBIDDEN")

httpx.HTTPTransport.handle_request=forbidden
urllib.request.urlopen=forbidden

def native(binding,args):
    if binding.role!=value["role"] or args!=value["native_args"]:
        raise AssertionError("ASSETS_TEST_NATIVE_ARGUMENT_MISMATCH")
    from mingjing_core.application.memory import MemoryService
    from mingjing_core.repositories.postgres import PostgresRepository
    repo=PostgresRepository(os.environ["ZHIMING_DATABASE_URL"],initialize=False,max_size=1)
    try:
        MemoryService(repo).receive("synthetic",content="SYNTHETIC_ASSETS_MEMORY_BODY",
            channel="synthetic",source_id=value["source"])
    finally:
        repo.close()
    sys.stdout.write("SYNTHETIC_NATIVE_STDOUT\n")

launcher._native=native
raise SystemExit(launcher.main(value["arguments"]))
"""


def run_common(command: list[str], dsn: str, *, role: str, native_args: list[str], source: str):
    assert command[1:3] == ["-m", "tools.first_release_service"]
    assert Path(command[0]).is_absolute() and Path(command[0]).is_file()
    payload = dict(candidate=str(ROOT), arguments=command[3:], role=role, native_args=native_args, source=source)
    return subprocess.run(
        [command[0], "-u", "-B", "-X", "utf8", "-c", CHILD],
        input=json.dumps(payload) + "\n",
        env=child_environment(dsn),
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        timeout=20,
    )
