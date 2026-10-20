"""Exclusive durable capability metadata with POSIX 0600 or a private Windows DACL."""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import re
import subprocess
from ctypes import wintypes
from pathlib import Path
from typing import Any


def _windows_sid() -> str:
    advapi, kernel = (
        ctypes.WinDLL("advapi32", use_last_error=True),
        ctypes.WinDLL("kernel32", use_last_error=True),
    )
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    advapi.OpenProcessToken.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.HANDLE),
    ]
    advapi.GetTokenInformation.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    advapi.ConvertSidToStringSidW.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(wintypes.LPWSTR),
    ]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.LocalFree.argtypes = [wintypes.HANDLE]
    token = wintypes.HANDLE()
    if not advapi.OpenProcessToken(kernel.GetCurrentProcess(), 8, ctypes.byref(token)):
        raise OSError("WINDOWS_OWNER_SID_UNAVAILABLE")
    try:
        needed = wintypes.DWORD()
        advapi.GetTokenInformation(token, 1, None, 0, ctypes.byref(needed))
        buffer = ctypes.create_string_buffer(needed.value)
        if not advapi.GetTokenInformation(token, 1, buffer, needed, ctypes.byref(needed)):
            raise OSError("WINDOWS_OWNER_SID_UNAVAILABLE")
        sid = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_void_p)).contents
        value = wintypes.LPWSTR()
        if not advapi.ConvertSidToStringSidW(sid, ctypes.byref(value)):
            raise OSError("WINDOWS_OWNER_SID_UNAVAILABLE")
        try:
            result = value.value
            if not isinstance(result, str) or re.fullmatch(r"S-1-[0-9-]+", result) is None:
                raise OSError("WINDOWS_OWNER_SID_UNAVAILABLE")
            return result
        finally:
            kernel.LocalFree(ctypes.cast(value, wintypes.HANDLE))
    finally:
        kernel.CloseHandle(token)


def _icacls(arguments: list[str]) -> bytes:
    executable = str(Path(os.environ.get("SYSTEMROOT", "C:/Windows")) / "System32/icacls.exe")
    environment = {
        name: os.environ[name]
        for name in os.environ
        if re.search(r"KEY|TOKEN|SECRET|PASSWORD|PASSWD|DSN|DATABASE_URL", name, re.I) is None
    }
    try:
        result = subprocess.run(
            [executable, *arguments],
            capture_output=True,
            timeout=10,
            check=False,
            creationflags=0x08000000,
            env=environment,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise OSError("WINDOWS_PRIVATE_ACL_UNAVAILABLE") from None
    if result.returncode != 0:
        raise OSError("WINDOWS_PRIVATE_ACL_UNAVAILABLE")
    return result.stdout


def audit_parent(path: Path) -> dict[str, Any]:
    parent = path.absolute().parent
    if parent != parent.resolve(strict=True) or not parent.is_dir():
        raise OSError("RECEIPT_PARENT_REPARSE_OR_MISSING")
    if os.name == "nt":
        digest = hashlib.sha256(_icacls([str(parent)])).hexdigest()
        return {"path": str(parent), "platform": "windows", "parent_acl_sha256": digest}
    mode = parent.stat().st_mode & 0o777
    if mode & 0o022:
        raise OSError("RECEIPT_PARENT_IS_GROUP_OR_WORLD_WRITABLE")
    return {"path": str(parent), "platform": "posix", "parent_mode": oct(mode)}


def write_private_receipt(path: Path, receipt: dict[str, Any]) -> dict[str, Any]:
    audit = audit_parent(path)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        if os.name == "nt":
            _icacls(
                [
                    str(path.absolute()),
                    "/inheritance:r",
                    "/grant:r",
                    f"*{_windows_sid()}:(F)",
                    "*S-1-5-18:(F)",
                ]
            )
            audit["file_protection"] = "explicit-current-user-and-system-dacl"
        else:
            os.fchmod(stream.fileno(), 0o600)
            audit["file_mode"] = "0600"
        json.dump(receipt, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    if os.name != "nt":
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    return audit
