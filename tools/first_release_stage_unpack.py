"""Standalone Python 3.11 stage bootstrap; copy with its reviewed SHA before execution."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tarfile
from pathlib import Path, PurePosixPath

MANIFEST = "__release_manifest__.json"


def require(condition: object) -> None:
    if not condition:
        raise ValueError("STAGE_UNPACK_REJECTED_PRESERVE_ALL")


def safe_name(name: str) -> str:
    path = PurePosixPath(name)
    require(bool(name) and bool(path.parts) and not path.is_absolute() and ".." not in path.parts and "\\" not in name)
    require(str(path) == name)
    return name


def extract_member(archive, member, destination: Path, expected: dict | None) -> None:
    require(member.isfile())
    content = archive.extractfile(member)
    require(content is not None)
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    sha = hashlib.sha256()
    blob = hashlib.sha1(b"blob " + str(member.size).encode() + b"\0")
    with os.fdopen(descriptor, "wb") as stream:
        while chunk := content.read(1024 * 1024):
            stream.write(chunk)
            sha.update(chunk)
            blob.update(chunk)
        stream.flush()
        os.fsync(stream.fileno())
    if expected is not None:
        require(expected["sha256"] == sha.hexdigest() and expected["git_blob_sha1"] == blob.hexdigest())
        require(expected["mode"] in {0o644, 0o755})
        os.chmod(destination, expected["mode"])


def unpack(artifact: Path, checksum: str, candidate: str, release: Path, *, local_drill: bool = False) -> dict:
    require(re.fullmatch(r"[0-9a-f]{40}", candidate) and re.fullmatch(r"[0-9a-f]{64}", checksum))
    require(local_drill or os.name == "posix")
    require(local_drill or release == Path("/root/zhiming-core-fr-stage/releases") / candidate)
    require(artifact.is_file() and not artifact.is_symlink() and not os.path.lexists(release))
    require(release.parent.is_dir() and release.parent.resolve() == release.parent.absolute())
    with artifact.open("rb") as raw:
        require(hashlib.file_digest(raw, "sha256").hexdigest() == checksum)
        raw.seek(0)
        with tarfile.open(fileobj=raw, mode="r:gz") as archive:
            members = archive.getmembers()
            names = [safe_name(member.name) for member in members]
            require(len(names) == len(set(names)) and all(member.isfile() for member in members))
            manifest = json.load(archive.extractfile(MANIFEST))
            require(manifest["schema"] == "core3-release-v1" and manifest["commit"] == candidate)
            require(set(names) == {MANIFEST, *manifest["files"]})
            release.mkdir(mode=0o700)
            for member in members:
                extract_member(archive, member, release / member.name, manifest["files"].get(member.name))
        raw.seek(0)
        require(hashlib.file_digest(raw, "sha256").hexdigest() == checksum)
    return {
        "status": "unpacked_new_release",
        "candidate_commit": candidate,
        "artifact_sha256": checksum,
        "tracked_files": len(manifest["files"]),
        "service_started": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--artifact-sha256", required=True)
    parser.add_argument("--release", type=Path, required=True)
    parser.add_argument("--local-drill", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = unpack(args.artifact, args.artifact_sha256, args.candidate, args.release, local_drill=args.local_drill)
    except Exception:
        print("STAGE_UNPACK_REJECTED_PRESERVE_ALL")
        return 2
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
