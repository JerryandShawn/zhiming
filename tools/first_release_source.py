"""Verify the reviewed packed source; runtime installation and restore remain separate gates."""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path, PurePosixPath
from typing import Any

from tools.first_release_contracts import LOCKS, ReleasePin, RestoreRejected, digest, ordinary, read_json, require

MANIFEST = "__release_manifest__.json"
MIGRATION_DIR = "mingjing_core/repositories/migrations"


def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def safe_member(name: Any) -> PurePosixPath:
    require(isinstance(name, str) and name and "\\" not in name and ":" not in name, "MANIFEST_MEMBER_PATH")
    relative = PurePosixPath(name)
    require(not relative.is_absolute() and ".." not in relative.parts and str(relative) == name, "MANIFEST_MEMBER_PATH")
    return relative


def verify_row(root: Path, name: str, record: Any) -> None:
    relative = safe_member(name)
    require(isinstance(record, dict) and set(record) == {"sha256", "git_blob_sha1", "mode"}, "MANIFEST_MEMBER_FIELDS")
    require(digest(record["sha256"]) and digest(record["git_blob_sha1"], 40), "MANIFEST_MEMBER_DIGEST")
    require(type(record["mode"]) is int and record["mode"] in {0o644, 0o755}, "MANIFEST_MEMBER_MODE")
    path = root.joinpath(*relative.parts)
    ordinary(path)
    content = path.read_bytes()
    require(hashlib.sha256(content).hexdigest() == record["sha256"], "SOURCE_MEMBER_CHANGED")
    blob = hashlib.sha1(b"blob " + str(len(content)).encode() + b"\0" + content).hexdigest()
    require(blob == record["git_blob_sha1"], "SOURCE_GIT_BLOB_CHANGED")


def verify_members(root: Path, expected: set[str]) -> None:
    def blocked(error: OSError) -> None:
        raise RestoreRejected("SOURCE_TRAVERSAL_FAILED") from None

    observed = set()
    for directory, names, filenames in os.walk(root, followlinks=False, onerror=blocked):
        current = Path(directory)
        for name in names:
            ordinary(current / name, directory=True)
        # These have independent future runtime gates; their contents are not source attestation.
        if current == root:
            names[:] = [name for name in names if name not in {"venv", "artifacts"}]
        for name in filenames:
            ordinary(current / name)
            observed.add((current / name).relative_to(root).as_posix())
    require(observed == expected, "UNMANIFESTED_OR_MISSING_SOURCE")


def verify_migrations(root: Path, files: dict[str, Any], pin: ReleasePin) -> None:
    actual = {}
    for name in files:
        if not name.startswith(MIGRATION_DIR + "/") or not name.endswith(".sql"):
            continue
        require(re.fullmatch(MIGRATION_DIR + r"/[0-9]{4}_[A-Za-z0-9_]+\.sql", name), "MIGRATION_MEMBER_NAME")
        version = str(int(PurePosixPath(name).name[:4]))
        require(version not in actual, "DUPLICATE_MIGRATION_VERSION")
        actual[version] = hashlib.sha256((root / name).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    require(actual == dict(pin.migrations), "CORE_ONLY_MIGRATIONS_1_8_MISMATCH")


def verify_source(root: Path, pin: ReleasePin) -> dict[str, Any]:
    ordinary(root, directory=True)
    manifest_path = root / MANIFEST
    ordinary(manifest_path)
    require(file_digest(manifest_path) == pin.manifest_sha256, "REVIEWED_MANIFEST_CHANGED")
    manifest = read_json(manifest_path)
    require(set(manifest) == {"schema", "commit", "files"}, "SOURCE_MANIFEST_FIELDS")
    require(
        manifest["schema"] == "core3-release-v1" and manifest["commit"] == pin.candidate, "SOURCE_CANDIDATE_MISMATCH"
    )
    files = manifest["files"]
    require(isinstance(files, dict) and files and len(files) <= 50_000, "SOURCE_FILE_SET")
    for name, record in files.items():
        verify_row(root, name, record)
    verify_members(root, {*files, MANIFEST})
    verify_migrations(root, files, pin)
    require(set(LOCKS) <= set(files), "SOURCE_LOCK_MISSING")
    require(all(file_digest(root / name) == expected for name, expected in pin.locks), "REVIEWED_LOCK_CHANGED")
    k3 = read_json(root / "k3-tokenizer.lock.json")
    require(
        k3.get("format") == "zhiming-public-k3-tokenizer-v1" and k3.get("allow_special_tokens") is False,
        "TOKENIZER_LOCK_CONTRACT",
    )
    return {
        "candidate": pin.candidate,
        "manifest_sha256": pin.manifest_sha256,
        "profile": pin.profile,
        "source_files_checked": len(files),
        "migrations": dict(pin.migrations),
        "locks": dict(pin.locks),
        "runtime_verified": False,
        "native_restore_completed": False,
        "publication": False,
    }
