"""Fixed B1 child supervision candidate; native containment is not yet OS-tested."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from datetime import timedelta, timezone
from pathlib import Path
from time import monotonic, sleep
from uuid import uuid4

from ....timekit.clock import get_clock
from .line_coverage_core_fingerprint import CORE
from .line_coverage_core_git import safe_environment
from .line_coverage_core_job import JobFailure, WindowsJob
from .line_coverage_manifest import ROOT, digest
from .line_coverage_own_plan import CANDIDATES

BOOTSTRAP = (
    ROOT / "mingjing_core/adapters/charts/benchmarks/line_coverage_core_bootstrap.py"
)
EVIDENCE = ROOT / "docs/v4/evidence/P8"
TEMP = ROOT / "private/tmp"
TASKKILL = Path("C:/Windows/System32/taskkill.exe")
DEADLINE_SECONDS = 45.0
TASKKILL_SECONDS = 2.0
CLEANUP_SECONDS = 3.0


def _path(path: Path, *, existing: bool) -> Path:
    actual = path.resolve()
    if (
        path.absolute() != actual
        or path.is_symlink()
        or not actual.is_relative_to(EVIDENCE)
        or actual.suffix != ".json"
    ):
        raise ValueError("supervisor_evidence_path_refused")
    if existing and (not actual.is_file() or actual.stat().st_size > 20_000_000):
        raise ValueError("supervisor_input_artifact_refused")
    if not existing and actual.exists():
        raise ValueError("supervisor_output_must_be_new")
    return actual


def specification(
    *, commit: str, inventory: Path, plan: Path, node: str, mode: str, output: Path
) -> dict:
    if (
        not isinstance(commit, str)
        or not isinstance(node, str)
        or not isinstance(mode, str)
        or not re.fullmatch("[a-f0-9]{40}", commit)
        or CANDIDATES.get(node) != "core"
        or mode not in ("baseline", "trace")
    ):
        raise ValueError("supervisor_fixed_core_specification_required")
    if not CORE.is_file() or not BOOTSTRAP.is_file() or not TASKKILL.is_file():
        raise ValueError("supervisor_fixed_executable_missing")
    paths = {
        "inventory": _path(inventory, existing=True),
        "plan": _path(plan, existing=True),
        "output": _path(output, existing=False),
    }
    if paths["inventory"] == paths["plan"] or paths["output"] in (
        paths["inventory"],
        paths["plan"],
    ):
        raise ValueError("supervisor_artifacts_must_be_distinct")
    sources = (
        Path(__file__).resolve(),
        Path(__file__).with_name("line_coverage_core_job.py").resolve(),
    )
    hashes = {
        str(path): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (
            CORE,
            BOOTSTRAP,
            TASKKILL,
            paths["inventory"],
            paths["plan"],
            *sources,
        )
    }
    return {
        "commit": commit,
        "node": node,
        "mode": mode,
        "paths": paths,
        "fixed_sha256": hashes,
    }


def _unchanged(spec: dict) -> None:
    for name, expected in spec["fixed_sha256"].items():
        if hashlib.sha256(Path(name).read_bytes()).hexdigest() != expected:
            raise JobFailure("fixed_launch_content_changed")


def _command(spec: dict, cache: Path) -> list[str]:
    command = [
        str(CORE),
        "-I",
        "-S",
        "-B",
        "-X",
        "pycache_prefix=" + str(cache),
        str(BOOTSTRAP),
    ]
    for key in ("inventory", "plan"):
        command.extend(("--" + key, str(spec["paths"][key])))
    command.extend(
        (
            "--commit",
            spec["commit"],
            "--node",
            spec["node"],
            "--mode",
            spec["mode"],
            "--output",
            str(spec["paths"]["output"]),
        )
    )
    return command


def _environment() -> dict[str, str]:
    environment = safe_environment()
    environment.update(
        PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
        PYTEST_ADDOPTS="",
        PYDANTIC_DISABLE_PLUGINS="__all__",
        LANGCHAIN_TRACING_V2="false",
        LANGSMITH_TRACING="false",
    )
    return environment


def _kill_tree(child: subprocess.Popen, job: WindowsJob, spec: dict) -> dict:
    if not job.owns(child):
        raise JobFailure("timeout_child_ownership_lost")
    if child.poll() is not None:
        return {"taskkill": "not_run_launcher_already_exited", "exit_code": None}
    _unchanged(spec)
    try:
        result = subprocess.run(
            [str(TASKKILL), "/PID", str(child.pid), "/T", "/F"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=TASKKILL_SECONDS,
            check=False,
            shell=False,
            env=_environment(),
            creationflags=0x08000000,
        )
        return {
            "taskkill": "attempted_owned_live_launcher",
            "exit_code": int(result.returncode),
        }
    except subprocess.TimeoutExpired:
        return {"taskkill": "taskkill_deadline_exceeded", "exit_code": None}
    except Exception:
        return {"taskkill": "taskkill_start_failed", "exit_code": None}


def _wait(child: subprocess.Popen, job: WindowsJob, spec: dict) -> dict:
    end = monotonic() + DEADLINE_SECONDS
    while True:
        exit_code = child.poll()
        active = job.active()
        if exit_code is not None and active == 0:
            return {
                "state": "launcher_exited_job_empty",
                "child_exit_code": exit_code,
                "timed_out": False,
                "job_active": 0,
            }
        if monotonic() >= end:
            result = _kill_tree(child, job, spec)
            job.terminate(CLEANUP_SECONDS)
            return {
                "state": "deadline_job_terminated",
                "child_exit_code": child.poll(),
                "timed_out": True,
                "job_active": job.active(),
                **result,
            }
        sleep(0.01)


def _failures(error: BaseException) -> list[dict]:
    result = []
    while error is not None and len(result) < 5:
        if isinstance(error, JobFailure):
            result.append({"code": error.code, "winerror": error.winerror})
        error = error.__context__
    return result or [{"code": "supervisor_fixed_phase_failed", "winerror": 0}]


def _attempt(operation) -> list[dict]:
    try:
        operation()
    except BaseException as error:
        return _failures(error)
    return []


def _close_process(child) -> None:
    close = getattr(child._handle, "Close", None)
    if close is None:
        raise JobFailure("owned_process_handle_close_unavailable")
    try:
        close()
    except Exception as error:
        raise JobFailure(
            "owned_process_handle_close_failed", getattr(error, "winerror", 0) or 0
        ) from None


def _cleanup(child, job, assigned: bool) -> list[dict]:
    failures = []
    if child is not None and not assigned:
        failures.extend(
            _attempt(lambda: child.kill() if child.poll() is None else None)
        )
    if job is not None:
        failures.extend(_attempt(lambda: job.terminate(CLEANUP_SECONDS)))
    if child is not None:
        failures.extend(_attempt(lambda: child.wait(timeout=CLEANUP_SECONDS)))
    if job is not None:
        failures.extend(_attempt(job.close))
    if child is not None:
        failures.extend(_attempt(lambda: _close_process(child)))
    return failures


def _save(path: Path, payload: dict) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def _workspace(spec: dict) -> tuple[Path, Path, dict]:
    if TEMP.resolve() != TEMP.absolute() or not TEMP.resolve().is_relative_to(ROOT):
        raise ValueError("supervisor_private_temp_path_refused")
    folder = TEMP / ("core-supervisor-" + uuid4().hex)
    folder.mkdir(parents=True, exist_ok=False)
    cache = folder / "cache"
    cache.mkdir()
    record = {
        "version": "p8-core-supervisor-v1",
        "started_at_beijing": get_clock()
        .now()
        .astimezone(timezone(timedelta(hours=8)))
        .isoformat(),
        **{key: spec[key] for key in ("commit", "node", "mode", "fixed_sha256")},
        "execution_evidence": "native_behavior_not_established_by_unit_tests",
        "actual_coverage_acceptance": False,
        "state": "started_not_final",
    }
    _save(folder / "started.json", record)
    return folder, cache, record


def supervise(
    *, commit: str, inventory: Path, plan: Path, node: str, mode: str, output: Path
) -> dict:
    spec = specification(
        commit=commit,
        inventory=inventory,
        plan=plan,
        node=node,
        mode=mode,
        output=output,
    )
    folder, cache, record = _workspace(spec)
    child, job, assigned = None, None, False
    phase = "job_create"
    try:
        job = WindowsJob()
        _unchanged(spec)
        phase = "suspended_launch"
        child = subprocess.Popen(
            _command(spec, cache),
            cwd=ROOT,
            env=_environment(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=False,
            close_fds=True,
            creationflags=0x08000004,
        )
        phase = "job_assign"
        job.assign(child)
        assigned = True
        phase = "primary_thread_resume"
        job.resume(child)
        phase = "wait"
        record.update(_wait(child, job, spec))
        _unchanged(spec)
    except BaseException as error:
        record.update(
            state="supervision_refused", phase=phase, failures=_failures(error)
        )
    finally:
        cleanup = _cleanup(child, job, assigned)
        if cleanup:
            record.update(state="cleanup_unverified", cleanup_failures=cleanup)
    record.update(
        completed_at_beijing=get_clock()
        .now()
        .astimezone(timezone(timedelta(hours=8)))
        .isoformat(),
        supervisor_artifact=str(folder / "final.json"),
    )
    record["supervisor_sha256"] = digest(record)
    _save(folder / "final.json", record)
    return record
