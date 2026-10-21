"""Real Linux flock/exec rehearsal, using inert CLI and isolated paths only."""

from __future__ import annotations

import importlib.util
import json
import os
import platform
import subprocess
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from tools.b1_linux_application_drill_contracts import ApplicationRequest, require
from tools.b1_runtime_trust import inspect_core_venv

INERT_CLI = """import json,os,pathlib,sys,time
root=pathlib.Path(__file__).resolve().parents[1]
fd=int(os.environ['B1_INERT_FD']);lock=root/'writer.lock'
assert os.fstat(fd).st_ino==lock.stat().st_ino and os.get_inheritable(fd)
ready=root/'ready.json'
temporary=root/'ready.json.tmp'
temporary.write_text(json.dumps({'pid':os.getpid(),'fd':fd,'inherited':True}),encoding='utf-8')
os.chmod(temporary,0o600);temporary.replace(ready)
assert sys.stdin.readline().strip()=='exit'
"""


def deployment(request: ApplicationRequest) -> Any:
    path = request.candidate_source / "tools/deploy_core.py"
    spec = importlib.util.spec_from_file_location("b1_fixed_deployment", path)
    require(spec and spec.loader, "APPLICATION_DEPLOYMENT_IMPORT")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def writer(request: ApplicationRequest, directory: Path) -> None:
    module = deployment(request)
    module.SKILL_WRITER_LOCK = str(directory / "writer.lock")
    module.MAINTENANCE = str(directory / "maintenance.flag")
    module.verify_release = lambda args: directory

    def inert_environment(args: Any, database: str) -> dict[str, str]:
        lock = (directory / "writer.lock").stat()
        matches = []
        for entry in Path("/proc/self/fd").iterdir():
            try:
                if entry.stat().st_ino == lock.st_ino and entry.stat().st_dev == lock.st_dev:
                    matches.append(int(entry.name))
            except FileNotFoundError:
                continue
        require(len(matches) == 1, "APPLICATION_WRITER_DESCRIPTOR")
        return {
            "B1_INERT_FD": str(matches[0]),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPYCACHEPREFIX": os.path.abspath(os.devnull),
            "PYTHONNOUSERSITE": "1",
        }

    module.load_environment = inert_environment
    module.execute_hermes_core(SimpleNamespace(), [])
    raise AssertionError("exec unexpectedly returned")


def create_inert_tree(request: ApplicationRequest) -> Path:
    directory = Path(tempfile.mkdtemp(prefix="b1-application-fence-"))
    directory.chmod(0o700)
    (directory / "venv/core/bin").mkdir(parents=True, mode=0o700)
    (directory / "venv/core/bin/python").symlink_to(request.candidate_python.resolve())
    (directory / "hermes").mkdir(mode=0o700)
    (directory / "hermes/core_consultation.py").write_text(INERT_CLI, encoding="utf-8")
    (directory / "hermes/core_consultation.py").chmod(0o600)
    return directory


def wait_ready(child: Any, directory: Path) -> dict[str, Any]:
    deadline = time.monotonic() + 10
    path = directory / "ready.json"
    while not path.exists():
        require(child.poll() is None, "APPLICATION_FENCE_WRITER_EXITED")
        require(time.monotonic() < deadline, "APPLICATION_FENCE_READY_TIMEOUT")
        time.sleep(0.02)
    observed = json.loads(path.read_text(encoding="utf-8"))
    require(observed.get("pid") == child.pid and observed.get("inherited") is True, "APPLICATION_FENCE_READY")
    return observed


def check_gate(module: Any, directory: Path) -> bool:
    (directory / "maintenance.flag").touch(mode=0o600)

    def forbidden(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("configuration/DB boundary crossed")

    module.verify_release = forbidden
    module.load_environment = forbidden
    try:
        module.execute_hermes_core(SimpleNamespace(), [])
    except ValueError as error:
        return str(error) == "Core skill unavailable during maintenance"
    return False


def fence(request: ApplicationRequest) -> dict[str, Any]:
    require(platform.system() == "Linux" and os.name == "posix", "LINUX_FCNTL_REQUIRED")
    from tools.b1_linux_application_drill_process import command, environment, writer_code

    directory = create_inert_tree(request)
    module = deployment(request)
    module.SKILL_WRITER_LOCK = str(directory / "writer.lock")
    module.MAINTENANCE = str(directory / "maintenance.flag")
    if not request.local_drill:
        inspect_core_venv()
    child = subprocess.Popen(
        command(request, writer_code(request, directory)),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        env=environment(request),
    )
    try:
        ready = wait_ready(child, directory)
        started, blocked = time.monotonic(), False
        try:
            with module.skill_writer_lock(exclusive=True, timeout=0.15):
                pass
        except TimeoutError:
            blocked = True
        elapsed = time.monotonic() - started
        require(blocked and elapsed < 2, "APPLICATION_FENCE_NOT_EXCLUSIVE")
        child.communicate("exit\n", timeout=10)
        require(child.returncode == 0, "APPLICATION_FENCE_WRITER_FAILED")
        with module.skill_writer_lock(exclusive=True, timeout=0.15):
            released = True
        require(check_gate(module, directory), "APPLICATION_MAINTENANCE_BYPASS")
        return {
            "shared_fd_survives_exec": ready["inherited"],
            "exclusive_blocked_until_cli_exit": blocked,
            "bounded_timeout_seconds": elapsed,
            "exclusive_available_after_cli_exit": released,
            "gate_rejects_before_configuration_or_db": True,
            "writer_exit_code": child.returncode,
            "writer_pid": child.pid,
            "private_evidence_directory": str(directory),
            "inert_cli_and_configuration_substituted": True,
            "real_fcntl_and_exec": True,
            "database_connections": 0,
            "systemd_or_installed_hermes_verified": False,
        }
    finally:
        if child.poll() is None:
            child.terminate()
            child.communicate(timeout=10)
