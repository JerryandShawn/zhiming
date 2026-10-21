"""Windows job containment candidate; OS behavior still requires a separate trial."""

from __future__ import annotations

import ctypes
import os
import subprocess
from ctypes import wintypes as w
from time import monotonic, sleep


class JobFailure(RuntimeError):
    def __init__(self, code: str, winerror: int = 0) -> None:
        self.code, self.winerror = code, int(winerror)
        super().__init__(code)


class Limits(ctypes.Structure):
    _fields_ = [
        ("user", ctypes.c_longlong),
        ("job_user", ctypes.c_longlong),
        ("flags", w.DWORD),
        ("minimum", ctypes.c_size_t),
        ("maximum", ctypes.c_size_t),
        ("active", w.DWORD),
        ("affinity", ctypes.c_size_t),
        ("priority", w.DWORD),
        ("scheduling", w.DWORD),
    ]


class Extended(ctypes.Structure):
    _fields_ = [
        ("basic", Limits),
        ("io", ctypes.c_ulonglong * 6),
        ("process_memory", ctypes.c_size_t),
        ("job_memory", ctypes.c_size_t),
        ("peak_process", ctypes.c_size_t),
        ("peak_job", ctypes.c_size_t),
    ]


class Accounting(ctypes.Structure):
    _fields_ = [
        ("times", ctypes.c_longlong * 4),
        ("faults", w.DWORD),
        ("total", w.DWORD),
        ("active", w.DWORD),
        ("terminated", w.DWORD),
    ]


class ThreadEntry(ctypes.Structure):
    _fields_ = [
        ("size", w.DWORD),
        ("usage", w.DWORD),
        ("tid", w.DWORD),
        ("pid", w.DWORD),
        ("priority", w.LONG),
        ("delta", w.LONG),
        ("flags", w.DWORD),
    ]


def native_api():
    if os.name != "nt" or ctypes.sizeof(ctypes.c_void_p) != 8:
        raise JobFailure("windows_64bit_required")
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    signatures = {
        "CreateJobObjectW": (w.HANDLE, (ctypes.c_void_p, w.LPCWSTR)),
        "SetInformationJobObject": (
            w.BOOL,
            (w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD),
        ),
        "AssignProcessToJobObject": (w.BOOL, (w.HANDLE, w.HANDLE)),
        "QueryInformationJobObject": (
            w.BOOL,
            (w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD, ctypes.c_void_p),
        ),
        "TerminateJobObject": (w.BOOL, (w.HANDLE, w.UINT)),
        "CloseHandle": (w.BOOL, (w.HANDLE,)),
        "GetProcessId": (w.DWORD, (w.HANDLE,)),
        "GetProcessIdOfThread": (w.DWORD, (w.HANDLE,)),
        "CreateToolhelp32Snapshot": (w.HANDLE, (w.DWORD, w.DWORD)),
        "Thread32First": (w.BOOL, (w.HANDLE, ctypes.POINTER(ThreadEntry))),
        "Thread32Next": (w.BOOL, (w.HANDLE, ctypes.POINTER(ThreadEntry))),
        "OpenThread": (w.HANDLE, (w.DWORD, w.BOOL, w.DWORD)),
        "ResumeThread": (w.DWORD, (w.HANDLE,)),
    }
    for name, (result, args) in signatures.items():
        function = getattr(api, name)
        function.restype, function.argtypes = result, args
    return api


class WindowsJob:
    def __init__(self) -> None:
        self.api = native_api()
        self.handle = self.api.CreateJobObjectW(None, None)
        if not self.handle:
            self._fail("job_create_failed")
        try:
            limits = Extended()
            limits.basic.flags = (
                0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE; no breakaway.
            )
            self._check(
                self.api.SetInformationJobObject(
                    self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)
                ),
                "job_kill_on_close_failed",
            )
        except BaseException:
            self.close()
            raise

    def _fail(self, code: str):
        raise JobFailure(code, ctypes.get_last_error())

    def _check(self, value, code: str):
        if not value:
            self._fail(code)
        return value

    def owns(self, child: subprocess.Popen) -> bool:
        handle = getattr(child, "_handle", None)
        if type(child.pid) is not int or child.pid <= 0 or handle is None:
            return False
        owner = self._check(
            self.api.GetProcessId(int(handle)), "child_process_id_query_failed"
        )
        return owner == child.pid

    def assign(self, child: subprocess.Popen) -> None:
        if not self.owns(child) or child.poll() is not None:
            raise JobFailure("suspended_child_ownership_failed")
        self._check(
            self.api.AssignProcessToJobObject(self.handle, int(child._handle)),
            "job_assignment_failed",
        )
        if self.active() != 1:
            raise JobFailure("suspended_job_not_exactly_one_process")

    def active(self) -> int:
        result = Accounting()
        self._check(
            self.api.QueryInformationJobObject(
                self.handle, 1, ctypes.byref(result), ctypes.sizeof(result), None
            ),
            "job_accounting_failed",
        )
        return int(result.active)

    def _threads(self, pid: int) -> list[int]:
        snapshot = self.api.CreateToolhelp32Snapshot(4, 0)
        if snapshot in (None, 0, ctypes.c_void_p(-1).value):
            self._fail("thread_snapshot_failed")
        try:
            entry = ThreadEntry()
            entry.size = ctypes.sizeof(entry)
            ok = self.api.Thread32First(snapshot, ctypes.byref(entry))
            if not ok:
                self._fail("thread_enumeration_failed")
            result = []
            while ok:
                if entry.pid == pid:
                    result.append(int(entry.tid))
                ok = self.api.Thread32Next(snapshot, ctypes.byref(entry))
            if ctypes.get_last_error() != 18:  # ERROR_NO_MORE_FILES
                self._fail("thread_enumeration_incomplete")
            return result
        finally:
            self._check(self.api.CloseHandle(snapshot), "thread_snapshot_close_failed")

    def resume(self, child: subprocess.Popen) -> None:
        if not self.owns(child) or self.active() != 1:
            raise JobFailure("resume_ownership_failed")
        threads = self._threads(child.pid)
        if len(threads) != 1:
            raise JobFailure("suspended_primary_thread_not_unique")
        thread = self._check(
            self.api.OpenThread(0x802, False, threads[0]), "primary_thread_open_failed"
        )
        try:
            if self.api.GetProcessIdOfThread(thread) != child.pid:
                raise JobFailure("primary_thread_owner_mismatch")
            if self.api.ResumeThread(thread) != 1:
                self._fail("primary_thread_resume_count_invalid")
        finally:
            self._check(self.api.CloseHandle(thread), "primary_thread_close_failed")

    def terminate(self, seconds: float = 3.0) -> None:
        self._check(
            self.api.TerminateJobObject(self.handle, 1), "job_termination_failed"
        )
        end = monotonic() + seconds
        while self.active():
            if monotonic() >= end:
                raise JobFailure("job_cleanup_deadline_exceeded")
            sleep(0.01)

    def close(self) -> None:
        if self.handle is not None:
            self._check(self.api.CloseHandle(self.handle), "job_handle_close_failed")
            self.handle = None
