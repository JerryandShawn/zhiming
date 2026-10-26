"""Synthetic supervisor tests; no native/job/child execution is performed."""

import subprocess
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from mingjing_core.adapters.charts.benchmarks import (
    line_coverage_core_supervisor as subject,
)
from mingjing_core.adapters.charts.benchmarks.line_coverage_core_job import JobFailure
from mingjing_core.adapters.charts.benchmarks.line_coverage_own_plan import CANDIDATES

NODE = next(k for k, v in CANDIDATES.items() if v == "core")


@pytest.fixture
def sandbox(monkeypatch):
    base = subject.ROOT / "private/tmp" / ("supervisor-unit-" + uuid4().hex)
    base.mkdir(parents=True)
    evidence = base / "evidence"
    evidence.mkdir()
    for key, name in [
        ("CORE", "core.exe"),
        ("BOOTSTRAP", "bootstrap.py"),
        ("TASKKILL", "taskkill.exe"),
    ]:
        path = base / name
        path.write_bytes(b"only synthetic executable bytes, never executed")
        monkeypatch.setattr(subject, key, path)
    monkeypatch.setattr(subject, "EVIDENCE", evidence)
    monkeypatch.setattr(subject, "TEMP", base / "runs")
    inventory = evidence / "inventory.json"
    inventory.write_text("{}")
    plan = evidence / "plan.json"
    plan.write_text("{}")
    return dict(
        commit="a" * 40,
        inventory=inventory,
        plan=plan,
        node=NODE,
        mode="baseline",
        output=evidence / "new.json",
    )


class Handle:
    def __init__(self):
        self.closed = False

    def Close(self):
        self.closed = True


class Child:
    def __init__(self):
        self.pid = 123
        self._handle = Handle()
        self.code = None
        self.killed = False

    def poll(self):
        return self.code

    def kill(self):
        self.killed = True
        self.code = 1

    def wait(self, **kwargs):
        self.code = 1 if self.code is None else self.code
        return self.code


class Job:
    def __init__(self, child):
        self.child = child
        self.count = 1
        self.closed = False
        self.events = []

    def owns(self, child):
        return child is self.child

    def assign(self, child):
        self.events.append("assign")

    def resume(self, child):
        self.events.append("resume")

    def active(self):
        return self.count

    def terminate(self, seconds):
        self.events.append("terminate")
        self.count = 0
        self.child.code = 1

    def close(self):
        self.events.append("close")
        self.closed = True


def test_exact_launch_shape_and_all_output_discarded(sandbox, monkeypatch):
    child = Child()
    job = Job(child)
    calls = []
    monkeypatch.setattr(subject, "WindowsJob", lambda: job)

    def popen(command, **options):
        calls.append((command, options))
        return child

    monkeypatch.setattr(subject.subprocess, "Popen", popen)
    monkeypatch.setattr(
        subject,
        "_wait",
        lambda *args: {
            "state": "launcher_exited_job_empty",
            "child_exit_code": 0,
            "timed_out": False,
            "job_active": 0,
        },
    )
    result = subject.supervise(**sandbox)
    command, options = calls[0]
    assert command[1:5] == ["-I", "-S", "-B", "-X"]
    assert command[5].startswith("pycache_prefix=") and command[6] == str(
        subject.BOOTSTRAP
    )
    assert options["creationflags"] == 0x08000004 and options["shell"] is False
    assert all(
        options[key] == subprocess.DEVNULL for key in ("stdin", "stdout", "stderr")
    )
    assert (
        job.events == ["assign", "resume", "terminate", "close"]
        and child._handle.closed
    )
    assert result["actual_coverage_acceptance"] is False
    assert Path(result["supervisor_artifact"]).is_file()


@pytest.mark.parametrize(
    "field,value",
    [
        ("commit", "HEAD"),
        ("commit", "a" * 39),
        ("node", "other.py::test"),
        ("mode", "live"),
    ],
)
def test_unknown_scope_refused_before_creation(sandbox, field, value):
    sandbox[field] = value
    with pytest.raises(ValueError):
        subject.specification(**sandbox)


@pytest.mark.parametrize("field", ["inventory", "plan", "output"])
def test_artifacts_outside_exact_evidence_range_refused(sandbox, field):
    sandbox[field] = subject.ROOT / "private/tmp/outside.json"
    with pytest.raises(ValueError):
        subject.specification(**sandbox)


def test_preexisting_output_refused(sandbox):
    sandbox["output"].write_text("{}")
    with pytest.raises(ValueError, match="supervisor_output_must_be_new"):
        subject.specification(**sandbox)


def test_command_is_fixed_and_commit_never_auto_upgrades(sandbox):
    spec = subject.specification(**sandbox)
    command = subject._command(spec, subject.TEMP / "cache")
    assert command[command.index("--commit") + 1] == "a" * 40
    assert command[command.index("--node") + 1] == NODE


def test_launcher_exit_alone_not_completion(monkeypatch):
    child = Child()
    child.code = 0
    job = Job(child)
    job.count = 2
    times = iter([0.0, 0.0, 46.0])
    monkeypatch.setattr(subject, "monotonic", lambda: next(times))
    monkeypatch.setattr(subject, "sleep", lambda _: None)
    result = subject._wait(child, job, {})
    assert result["timed_out"] is True and result["job_active"] == 0
    assert result["taskkill"] == "not_run_launcher_already_exited"
    assert "terminate" in job.events


def test_live_owned_timeout_uses_fixed_system32_pid_tree_flags(monkeypatch):
    child = Child()
    job = Job(child)
    calls = []
    monkeypatch.setattr(subject, "_unchanged", lambda _: None)

    def run(command, **options):
        calls.append((command, options))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(subject.subprocess, "run", run)
    result = subject._kill_tree(child, job, {})
    assert calls[0][0] == [str(subject.TASKKILL), "/PID", "123", "/T", "/F"]
    assert calls[0][1]["shell"] is False and calls[0][1]["timeout"] == 2.0
    assert result["taskkill"] == "attempted_owned_live_launcher"


def test_foreign_pid_never_sent_to_taskkill(monkeypatch):
    child = Child()
    job = Job(Child())
    with pytest.raises(JobFailure, match="timeout_child_ownership_lost"):
        subject._kill_tree(child, job, {})


@pytest.mark.parametrize("kind", ["timeout", "start"])
def test_taskkill_failure_is_recorded_for_job_fallback(monkeypatch, kind):
    child = Child()
    job = Job(child)
    monkeypatch.setattr(subject, "_unchanged", lambda _: None)

    def fail(*args, **kwargs):
        if kind == "timeout":
            raise subprocess.TimeoutExpired("synthetic", 2)
        raise OSError("synthetic body must never be logged")

    monkeypatch.setattr(subject.subprocess, "run", fail)
    result = subject._kill_tree(child, job, {})
    assert result["taskkill"] == (
        "taskkill_deadline_exceeded" if kind == "timeout" else "taskkill_start_failed"
    )
    assert "synthetic" not in str(result)


@pytest.mark.parametrize("phase", ["create", "assign", "resume"])
def test_pre_resume_failure_is_closed_and_no_plain_popen_fallback(
    sandbox, monkeypatch, phase
):
    child = Child()
    job = Job(child)
    launches = []

    def factory():
        if phase == "create":
            raise JobFailure("synthetic_job_create_failure")
        return job

    def reject(*args):
        raise JobFailure("synthetic_" + phase + "_failure")

    if phase != "create":
        monkeypatch.setattr(job, phase, reject)
    monkeypatch.setattr(subject, "WindowsJob", factory)
    monkeypatch.setattr(
        subject.subprocess,
        "Popen",
        lambda *args, **kwargs: launches.append(args) or child,
    )
    result = subject.supervise(**sandbox)
    assert result["state"] == "supervision_refused"
    assert len(launches) == (0 if phase == "create" else 1)
    if phase != "create":
        assert job.closed and child._handle.closed
    if phase == "assign":
        assert child.killed


def test_cleanup_failure_does_not_get_success_receipt(sandbox, monkeypatch):
    child = Child()
    job = Job(child)
    monkeypatch.setattr(subject, "WindowsJob", lambda: job)
    monkeypatch.setattr(subject.subprocess, "Popen", lambda *args, **kwargs: child)
    monkeypatch.setattr(
        subject,
        "_wait",
        lambda *args: {
            "state": "launcher_exited_job_empty",
            "child_exit_code": 0,
            "timed_out": False,
            "job_active": 0,
        },
    )
    monkeypatch.setattr(
        job,
        "terminate",
        lambda *args: (_ for _ in ()).throw(JobFailure("synthetic_cleanup_failure")),
    )
    result = subject.supervise(**sandbox)
    assert result["state"] == "cleanup_unverified" and result["cleanup_failures"]
    assert job.closed and child._handle.closed


def test_content_change_rejected_without_logging_content(sandbox):
    spec = subject.specification(**sandbox)
    sandbox["plan"].write_text("synthetic changed private-like content")
    with pytest.raises(JobFailure, match="fixed_launch_content_changed"):
        subject._unchanged(spec)


def test_environment_drops_credentials_and_tracking(monkeypatch):
    monkeypatch.setenv("SYNTHETIC_API_KEY", "not-a-secret")
    monkeypatch.setenv("KIMI_MODEL", "not-a-model")
    result = subject._environment()
    assert "SYNTHETIC_API_KEY" not in result and "KIMI_MODEL" not in result
    assert (
        result["LANGCHAIN_TRACING_V2"] == "false"
        and result["LANGSMITH_TRACING"] == "false"
    )


def test_cleanup_attempts_later_stages_after_kill_and_wait_failures(monkeypatch):
    child = Child()
    job = Job(child)
    events = []

    def failed_kill():
        events.append("kill")
        raise OSError("SYNTHETIC_PRIVATE_MARKER")

    def failed_wait(**kwargs):
        events.append("wait")
        raise subprocess.TimeoutExpired("synthetic", 3)

    monkeypatch.setattr(child, "kill", failed_kill)
    monkeypatch.setattr(child, "wait", failed_wait)
    failures = subject._cleanup(child, job, False)
    assert len(failures) == 2 and events == ["kill", "wait"]
    assert job.events == ["terminate", "close"] and child._handle.closed
    assert "SYNTHETIC_PRIVATE_MARKER" not in str(failures)


def test_job_close_and_process_close_failures_both_preserved(monkeypatch):
    child = Child()
    job = Job(child)
    monkeypatch.setattr(
        job,
        "close",
        lambda: (_ for _ in ()).throw(JobFailure("job_handle_close_failed", 6)),
    )
    monkeypatch.setattr(
        child._handle, "Close", lambda: (_ for _ in ()).throw(OSError("synthetic"))
    )
    result = subject._cleanup(child, job, True)
    assert [row["code"] for row in result] == [
        "job_handle_close_failed",
        "owned_process_handle_close_failed",
    ]


def test_absent_native_process_handle_close_fails_closed():
    child = Child()
    child._handle = 20
    result = subject._cleanup(child, Job(child), True)
    assert result[-1]["code"] == "owned_process_handle_close_unavailable"


def test_launcher_exit_nonzero_stays_nonzero_when_job_empty():
    child = Child()
    child.code = 1
    job = Job(child)
    job.count = 0
    result = subject._wait(child, job, {})
    assert result["child_exit_code"] == 1 and result["timed_out"] is False


def test_existing_started_record_never_overwritten(sandbox):
    path = subject.TEMP.parent / "exclusive.json"
    subject._save(path, {"state": "started"})
    with pytest.raises(FileExistsError):
        subject._save(path, {"state": "replaced"})
    assert path.read_text().find("started") >= 0
