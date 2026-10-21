"""Mock Windows API checks, not evidence of actual job/process containment."""

from types import SimpleNamespace

import pytest

from mingjing_core.adapters.charts.benchmarks import line_coverage_core_job as native


class API:
    def __init__(self):
        self.calls = []
        self.failed = set()
        self.count = 1
        self.last_error = 18
        self.thread_rows = [(123, 321)]

    def _result(self, name, result):
        self.calls.append(name)
        return 0 if name in self.failed else result

    def CreateJobObjectW(self, *args):
        return self._result("create", 10)

    def SetInformationJobObject(self, handle, kind, value, size):
        assert handle == 10 and kind == 9 and value._obj.basic.flags == 0x2000
        return self._result("limits", 1)

    def GetProcessId(self, handle):
        return self._result("process_id", 123 if handle == 20 else 999)

    def AssignProcessToJobObject(self, *args):
        return self._result("assign", 1)

    def QueryInformationJobObject(self, handle, kind, result, size, length):
        assert kind == 1
        result._obj.active = self.count
        return self._result("accounting", 1)

    def CreateToolhelp32Snapshot(self, *args):
        return self._result("snapshot", 30)

    def Thread32First(self, handle, value):
        if "thread_first" in self.failed:
            return 0
        self.remaining = list(self.thread_rows)
        value._obj.pid, value._obj.tid = self.remaining.pop(0)
        return 1

    def Thread32Next(self, handle, value):
        if "thread_next" in self.failed:
            self.last_error = 5
            return 0
        if not self.remaining:
            self.last_error = 18
            return 0
        value._obj.pid, value._obj.tid = self.remaining.pop(0)
        return 1

    def OpenThread(self, *args):
        return self._result("thread_open", 40)

    def GetProcessIdOfThread(self, *args):
        return self._result("thread_owner", 123)

    def ResumeThread(self, *args):
        return self._result("resume", 1)

    def CloseHandle(self, *args):
        return self._result("close", 1)

    def TerminateJobObject(self, *args):
        self.count = 0
        return self._result("terminate", 1)


@pytest.fixture
def setup(monkeypatch):
    api = API()
    monkeypatch.setattr(native, "native_api", lambda: api)
    monkeypatch.setattr(
        native.ctypes, "get_last_error", lambda: api.last_error, raising=False
    )
    return api


def child():
    return SimpleNamespace(pid=123, _handle=20, poll=lambda: None)


def test_assign_before_unique_primary_thread_resume(setup):
    job = native.WindowsJob()
    job.assign(child())
    job.resume(child())
    assert setup.calls.index("assign") < setup.calls.index("resume")
    assert setup.calls.count("close") == 2  # Snapshot and thread handles.
    job.terminate()
    assert job.active() == 0
    job.close()
    assert job.handle is None


@pytest.mark.parametrize(
    "operation,code",
    [("create", "job_create_failed"), ("limits", "job_kill_on_close_failed")],
)
def test_job_creation_failures_never_return_a_ready_job(setup, operation, code):
    setup.failed.add(operation)
    with pytest.raises(native.JobFailure, match=code):
        native.WindowsJob()


@pytest.mark.parametrize(
    "operation,code",
    [
        ("process_id", "child_process_id_query_failed"),
        ("assign", "job_assignment_failed"),
        ("accounting", "job_accounting_failed"),
    ],
)
def test_assignment_fail_closed(setup, operation, code):
    job = native.WindowsJob()
    setup.failed.add(operation)
    with pytest.raises(native.JobFailure, match=code):
        job.assign(child())
    assert "resume" not in setup.calls


@pytest.mark.parametrize("pid", [True, 0, -1, 123.0])
def test_owned_pid_must_be_positive_real_integer(setup, pid):
    value = child()
    value.pid = pid
    assert not native.WindowsJob().owns(value)


def test_nonunique_suspended_primary_thread_never_resumes(setup):
    setup.thread_rows = [(123, 321), (123, 322)]
    job = native.WindowsJob()
    with pytest.raises(native.JobFailure, match="suspended_primary_thread_not_unique"):
        job.resume(child())
    assert "resume" not in setup.calls


@pytest.mark.parametrize(
    "operation,code",
    [
        ("snapshot", "thread_snapshot_failed"),
        ("thread_first", "thread_enumeration_failed"),
        ("thread_next", "thread_enumeration_incomplete"),
        ("thread_open", "primary_thread_open_failed"),
        ("thread_owner", "primary_thread_owner_mismatch"),
        ("resume", "primary_thread_resume_count_invalid"),
    ],
)
def test_resume_native_failure_paths(setup, operation, code):
    job = native.WindowsJob()
    setup.failed.add(operation)
    with pytest.raises(native.JobFailure, match=code):
        job.resume(child())


def test_preexisting_more_than_one_process_refuses_resume(setup):
    setup.count = 2
    with pytest.raises(native.JobFailure, match="resume_ownership_failed"):
        native.WindowsJob().resume(child())


@pytest.mark.parametrize(
    "operation,code",
    [("terminate", "job_termination_failed"), ("close", "job_handle_close_failed")],
)
def test_cleanup_failure_is_not_claimed_clean(setup, operation, code):
    job = native.WindowsJob()
    setup.failed.add(operation)
    with pytest.raises(native.JobFailure, match=code):
        job.terminate() if operation == "terminate" else job.close()
    assert job.handle == 10


def test_unproven_nonwindows_environment_refused(monkeypatch):
    monkeypatch.setattr(native, "os", SimpleNamespace(name="unapproved"))
    with pytest.raises(native.JobFailure, match="windows_64bit_required"):
        native.native_api()


def test_assignment_rejects_already_exited_launcher(setup):
    value = child()
    value.poll = lambda: 0
    with pytest.raises(native.JobFailure, match="suspended_child_ownership_failed"):
        native.WindowsJob().assign(value)


def test_assignment_rejects_multiple_active_processes(setup):
    setup.count = 2
    with pytest.raises(
        native.JobFailure, match="suspended_job_not_exactly_one_process"
    ):
        native.WindowsJob().assign(child())


def test_snapshot_close_failure_is_preserved(setup):
    job = native.WindowsJob()
    setup.failed.add("close")
    with pytest.raises(native.JobFailure, match="thread_snapshot_close_failed"):
        job.resume(child())
    assert "resume" not in setup.calls


def test_primary_thread_close_failure_is_preserved(setup, monkeypatch):
    job = native.WindowsJob()
    monkeypatch.setattr(setup, "CloseHandle", lambda handle: 0 if handle == 40 else 1)
    with pytest.raises(native.JobFailure, match="primary_thread_close_failed"):
        job.resume(child())


def test_missing_primary_thread_refuses_resume(setup):
    job = native.WindowsJob()
    setup.thread_rows = [(999, 321)]
    with pytest.raises(native.JobFailure, match="suspended_primary_thread_not_unique"):
        job.resume(child())


def test_unexpected_previous_suspend_count_refused(setup, monkeypatch):
    job = native.WindowsJob()
    monkeypatch.setattr(setup, "ResumeThread", lambda handle: 2)
    with pytest.raises(native.JobFailure, match="primary_thread_resume_count_invalid"):
        job.resume(child())


def test_job_zero_active_deadline_is_enforced_with_fake_clock(setup, monkeypatch):
    job = native.WindowsJob()
    monkeypatch.setattr(setup, "TerminateJobObject", lambda *args: 1)
    values = iter([0.0, 3.0])
    monkeypatch.setattr(native, "monotonic", lambda: next(values))
    with pytest.raises(native.JobFailure, match="job_cleanup_deadline_exceeded"):
        job.terminate()


def test_constructor_cleanup_failure_keeps_original_failure_context(setup):
    setup.failed.update(("limits", "close"))
    with pytest.raises(native.JobFailure, match="job_handle_close_failed") as result:
        native.WindowsJob()
    assert result.value.__context__.code == "job_kill_on_close_failed"
