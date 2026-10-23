"""Pinned CPython line-table denominator; no source text enters the report."""

from __future__ import annotations

import dis
import hashlib
import io
import json
import re
import subprocess
import sys
from pathlib import Path
from types import CodeType
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
BASE_COMMIT = "f23b942ce698a3f7ee0b98c918d43053fe773433"
OBSERVED_COMMIT = "6c140cd635e8769dac5481b91c0da2520cd78680"
DEFAULT_SCOPES = ("mingjing_core/", "tests/v4/")
METHOD = "cpython-3.11-compile-optimize0-recursive-dis-findlinestarts-v1"


def digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def normalized(raw: bytes) -> bytes:
    return raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def safe_root(root: Path) -> Path:
    resolved = root.resolve()
    if resolved != ROOT and not resolved.is_relative_to(ROOT / "private/tmp"):
        raise ValueError("coverage_repository_outside_workspace")
    if not (resolved / ".git").exists():
        raise ValueError("coverage_git_repository_required")
    if resolved != ROOT and (
        not (resolved / ".git").is_dir()
        or not (resolved / ".git").resolve().is_relative_to(resolved)
    ):
        raise ValueError("coverage_temporary_git_directory_required")
    return resolved


def git_bytes(root: Path, *arguments: str, input_bytes: bytes | None = None) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(root), *arguments],
        input=input_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
        timeout=10,
    )
    if result.returncode:
        raise ValueError("coverage_git_read_failed")
    return result.stdout


def commit_id(root: Path, revision: str) -> str:
    if not isinstance(revision, str) or not re.fullmatch(r"[a-f0-9]{40}", revision):
        raise ValueError("coverage_full_commit_required")
    actual = git_bytes(root, "rev-parse", "--verify", revision + "^{commit}")
    if actual.decode("ascii").strip() != revision:
        raise ValueError("coverage_commit_mismatch")
    return revision


def executable_lines(raw: bytes, filename: str) -> list[int]:
    if sys.implementation.name != "cpython" or sys.version_info[:2] != (3, 11):
        raise ValueError("coverage_cpython311_required")
    try:
        code = compile(raw, filename, "exec", dont_inherit=True, optimize=0)
    except (SyntaxError, ValueError, UnicodeError):
        raise ValueError("coverage_source_compile_failed") from None
    pending, lines = [code], set()
    while pending:
        item = pending.pop()
        lines.update(line for _, line in dis.findlinestarts(item) if line and line > 0)
        pending.extend(value for value in item.co_consts if isinstance(value, CodeType))
    return sorted(lines)


def source_group(path: str) -> str:
    if path.startswith("tests/"):
        return "tests"
    return "research" if "/benchmarks/" in path else "runtime"


def _changed_paths(root: Path, base: str, commit: str) -> list[str]:
    raw = git_bytes(
        root,
        "diff",
        "--name-only",
        "-z",
        "--no-renames",
        "--diff-filter=ACMRT",
        base,
        commit,
    )
    paths = [value.decode("utf-8") for value in raw.split(b"\0") if value]
    return sorted(path for path in paths if path.endswith(".py"))


def _blob_id(raw: bytes) -> str:
    return hashlib.sha1(
        b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw, usedforsecurity=False
    ).hexdigest()


def _tree_blobs(root: Path, commit: str) -> dict[str, str]:
    rows = git_bytes(root, "ls-tree", "-r", "-z", commit).split(b"\0")
    result = {}
    for row in rows:
        if row:
            header, path = row.split(b"\t", 1)
            mode, kind, identity = header.split()
            if kind == b"blob" and mode in (b"100644", b"100755"):
                result[path.decode("utf-8")] = identity.decode("ascii")
    return result


def _sources(root: Path, commit: str, scopes: tuple[str, ...]) -> dict[str, bytes]:
    identities = {
        path: identity
        for path, identity in _tree_blobs(root, commit).items()
        if path == "pytest.ini" or (path.endswith(".py") and path.startswith(scopes))
    }
    ordered = sorted(identities)
    request = "".join(identities[path] + "\n" for path in ordered).encode("ascii")
    raw = git_bytes(root, "cat-file", "--batch", input_bytes=request)
    stream, sources = io.BytesIO(raw), {}
    for path in ordered:
        header = stream.readline().rstrip(b"\n").split()
        if len(header) != 3 or header[0].decode("ascii") != identities[path]:
            raise ValueError("coverage_git_batch_identity_invalid")
        if header[1] != b"blob" or not header[2].isdigit():
            raise ValueError("coverage_git_batch_header_invalid")
        value = stream.read(int(header[2]))
        if stream.read(1) != b"\n" or _blob_id(value) != identities[path]:
            raise ValueError("coverage_not_raw_git_blob")
        sources[path] = value
    if stream.read(1):
        raise ValueError("coverage_git_batch_extra_data")
    return sources


def _source(root: Path, path: str, raw: bytes) -> dict:
    if ".." in Path(path).parts or Path(path).is_absolute() or "\\" in path:
        raise ValueError("coverage_source_path_invalid")
    canonical = normalized(raw)
    blob = _blob_id(raw)
    return {
        "path": path,
        "group": source_group(path),
        "git_blob_id": blob,
        "git_raw_sha256": hashlib.sha256(raw).hexdigest(),
        "lf_sha256": hashlib.sha256(canonical).hexdigest(),
        "executable_lines": executable_lines(canonical, str(root / path)),
    }


def build_manifest(
    root: Path,
    base_commit: str = BASE_COMMIT,
    commit: str = OBSERVED_COMMIT,
    scopes: tuple[str, ...] = DEFAULT_SCOPES,
) -> dict:
    root = safe_root(root)
    if not scopes or len(set(scopes)) != len(scopes):
        raise ValueError("coverage_scope_invalid")
    if any(value not in DEFAULT_SCOPES for value in scopes):
        raise ValueError("coverage_scope_invalid")
    base, head = commit_id(root, base_commit), commit_id(root, commit)
    if git_bytes(root, "rev-parse", "--show-object-format").strip() != b"sha1":
        raise ValueError("coverage_git_sha1_object_format_required")
    changed = _changed_paths(root, base, head)
    selected = [path for path in changed if path.startswith(scopes)]
    if not selected:
        raise ValueError("coverage_scope_empty")
    sources = _sources(root, head, scopes)
    result = {
        "version": "p8-stdlib-line-manifest-v1",
        "base_commit": base,
        "commit": head,
        "scopes": list(scopes),
        "scope_is_complete_for_own_code": False,
        "selection": "all-added-or-modified-Python-files-in-selected-prefixes-full-file",
        "excluded_changed_python_count": len(changed) - len(selected),
        "denominator_method": METHOD,
        "denominator_python": list(sys.version_info[:3]),
        "files": [
            _source(root, path, sources[path]) for path in selected if path in sources
        ],
        "execution_guards": [
            {"path": path, "lf_sha256": hashlib.sha256(normalized(raw)).hexdigest()}
            for path, raw in sorted(sources.items())
        ],
        "limits": [
            "Selected committed scope only; uncommitted tools and other code are not a total-own-code claim.",
            "CPython line-table denominator, not coverage.py or branch coverage; C/JS and child processes excluded.",
        ],
    }
    result["manifest_sha256"] = digest(result)
    if len(result["files"]) != len(selected):
        raise ValueError("coverage_source_not_regular_file")
    return result


def validate_manifest(manifest: dict) -> None:
    claimed = manifest.get("manifest_sha256")
    payload = {
        key: value for key, value in manifest.items() if key != "manifest_sha256"
    }
    if claimed != digest(payload) or manifest.get("denominator_method") != METHOD:
        raise ValueError("coverage_manifest_integrity_invalid")
    paths = [row["path"] for row in manifest["files"]]
    if len(paths) != len(set(paths)) or paths != sorted(paths):
        raise ValueError("coverage_manifest_paths_invalid")
    for row in manifest["files"]:
        lines = row["executable_lines"]
        if any(type(line) is not int or line <= 0 for line in lines):
            raise ValueError("coverage_denominator_line_invalid")
        if lines != sorted(set(lines)):
            raise ValueError("coverage_denominator_line_invalid")


def check_worktree(root: Path, manifest: dict) -> dict[str, str]:
    root = safe_root(root)
    validate_manifest(manifest)
    rebuilt = build_manifest(
        root, manifest["base_commit"], manifest["commit"], tuple(manifest["scopes"])
    )
    if rebuilt != manifest:
        raise ValueError("coverage_manifest_pinned_source_mismatch")
    observed_head = git_bytes(root, "rev-parse", "HEAD").decode("ascii").strip()
    delta = git_bytes(
        root,
        "diff",
        "--name-only",
        "-z",
        "--no-renames",
        manifest["commit"],
        observed_head,
    )
    changed = [path.decode("utf-8") for path in delta.split(b"\0") if path]
    if any(
        path == "pytest.ini"
        or (path.endswith(".py") and path.startswith(tuple(manifest["scopes"])))
        for path in changed
    ):
        raise ValueError("coverage_observed_head_source_changed")
    observed = {}
    for source in manifest["execution_guards"]:
        path = (root / source["path"]).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError("coverage_worktree_source_missing")
        raw = path.read_bytes()
        if hashlib.sha256(normalized(raw)).hexdigest() != source["lf_sha256"]:
            raise ValueError("coverage_worktree_source_changed")
        observed[source["path"]] = hashlib.sha256(raw).hexdigest()
    return {"observed_HEAD": observed_head, "raw_sha256": observed}
