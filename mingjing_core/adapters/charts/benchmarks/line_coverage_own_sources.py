"""Static Git inputs for the explicit P8-history inventory; never imports targets."""

from __future__ import annotations

import hashlib
import io
from pathlib import Path, PurePosixPath

from .line_coverage_manifest import git_bytes, normalized

ORIGIN = "7fa5e10a4dbe0e2878e28c6f6a115f17d013aaa2"
CUTOVER = "f23b942ce698a3f7ee0b98c918d43053fe773433"


def canonical_path(path: str) -> None:
    if not isinstance(path, str):
        raise ValueError("own_inventory_path_invalid")
    value = PurePosixPath(path)
    if (
        not path
        or value.is_absolute()
        or any(part in (".", "..") for part in value.parts)
        or value.as_posix() != path
        or "\\" in path
        or ":" in path
        or any(ord(character) < 32 for character in path)
    ):
        raise ValueError("own_inventory_path_invalid")


def classify(path: str) -> str:
    canonical_path(path)
    if not path.endswith(".py"):
        raise ValueError("own_inventory_python_path_required")
    if path.startswith("mingjing_core/adapters/charts/"):
        return "research" if "/benchmarks/" in path else "charts_runtime"
    if path.startswith("mingjing_core/calculations/bazi/"):
        return "bazi_calculations"
    if path.startswith("mingjing_core/skills/"):
        return "core_skills"
    name = PurePosixPath(path).name
    if path.startswith("tests/v4/"):
        if path.startswith("tests/v4/helpers/"):
            return "v4_helpers"
        if name.startswith("test_p8"):
            return "v4_tests"
        if name.startswith("p8_") and name.endswith("_context.py"):
            return "v4_helpers"
    if path.startswith("tests/test_p8") and len(PurePosixPath(path).parts) == 2:
        return "native_tests"
    if path == "tools/verify_p8_calculators.py":
        return "verification_tool"
    raise ValueError("own_inventory_changed_python_requires_scope_review")


def tree(root: Path, commit: str) -> dict[str, str]:
    result = {}
    for row in git_bytes(root, "ls-tree", "-r", "-z", commit).split(b"\0"):
        if not row:
            continue
        header, raw_path = row.split(b"\t", 1)
        mode, kind, identity = header.split()
        path = raw_path.decode("utf-8")
        if path.endswith(".py") or path == "pytest.ini":
            canonical_path(path)
            if kind != b"blob" or mode not in (b"100644", b"100755"):
                raise ValueError("own_inventory_nonregular_source_refused")
            result[path] = identity.decode("ascii")
    return result


def changed(root: Path, base: str, commit: str) -> dict[str, str]:
    rows = git_bytes(
        root, "diff", "--name-status", "-z", "--no-renames", base, commit, "--", "*.py"
    ).split(b"\0")
    if rows[-1] != b"" or (len(rows) - 1) % 2:
        raise ValueError("own_inventory_git_diff_invalid")
    result = {}
    for index in range(0, len(rows) - 1, 2):
        status, path = rows[index].decode("ascii"), rows[index + 1].decode("utf-8")
        canonical_path(path)
        if status not in ("A", "M", "T", "D") or path in result:
            raise ValueError("own_inventory_git_change_invalid")
        classify(path)
        result[path] = status
    return result


def raw_sources(root: Path, identities: dict[str, str]) -> dict[str, bytes]:
    ordered = sorted(identities)
    request = "".join(identities[path] + "\n" for path in ordered).encode("ascii")
    stream = io.BytesIO(git_bytes(root, "cat-file", "--batch", input_bytes=request))
    result = {}
    for path in ordered:
        header = stream.readline().rstrip(b"\n").split()
        if len(header) != 3 or header[:2] != [identities[path].encode(), b"blob"]:
            raise ValueError("own_inventory_git_blob_header_invalid")
        if not header[2].isdigit():
            raise ValueError("own_inventory_git_blob_length_invalid")
        value = stream.read(int(header[2]))
        actual = hashlib.sha1(
            b"blob " + str(len(value)).encode() + b"\0" + value, usedforsecurity=False
        ).hexdigest()
        if (
            len(value) != int(header[2])
            or actual != identities[path]
            or stream.read(1) != b"\n"
        ):
            raise ValueError("own_inventory_git_blob_content_invalid")
        result[path] = value
    if stream.read(1):
        raise ValueError("own_inventory_git_blob_extra_data")
    return result


def lf_hash(raw: bytes) -> str:
    return hashlib.sha256(normalized(raw)).hexdigest()


def deleted_paths(root: Path, base: str, commit: str, current: dict) -> list[str]:
    revisions = git_bytes(root, "rev-list", "--ancestry-path", base + ".." + commit)
    raw = git_bytes(
        root,
        "diff-tree",
        "--stdin",
        "--root",
        "--no-commit-id",
        "-r",
        "-m",
        "-z",
        "--diff-filter=D",
        "--no-renames",
        "--name-only",
        input_bytes=revisions,
    )
    deleted = sorted({row.decode("utf-8") for row in raw.split(b"\0") if row})
    result = []
    for path in deleted:
        if path.endswith(".py") and path not in current:
            classify(path)
            result.append(path)
    return result
