"""Canonical Git bytes and standalone isolated bootstrap; no SSH or service actions."""

from __future__ import annotations

import hashlib
import io
import json
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

from tools.first_release_stage_package import make_bundle
from tools.first_release_stage_unpack import MANIFEST, unpack


def git(root: Path, *arguments: str) -> str:
    result = subprocess.run(["git", *arguments], cwd=root, capture_output=True, text=True)
    assert result.returncode == 0, "synthetic Git operation failed"
    return result.stdout.strip()


@pytest.fixture
def package(tmp_path):
    root = tmp_path / "synthetic-source"
    root.mkdir()
    git(root, "init", "-q", "-b", "synthetic-fr-stage")
    git(root, "config", "user.name", "Synthetic")
    git(root, "config", "user.email", "synthetic@example.invalid")
    git(root, "config", "commit.gpgsign", "false")
    (root / ".gitignore").write_text("private/\n", encoding="utf-8")
    (root / "entry.py").write_text("print('SYNTHETIC_CANONICAL_BYTES')\n", encoding="utf-8")
    git(root, "add", ".gitignore", "entry.py")
    git(root, "commit", "-qm", "synthetic pinned source")
    candidate = git(root, "rev-parse", "HEAD")
    (root / "private").mkdir()
    (root / "private/ignored.env").write_text("SYNTHETIC_IGNORED_DATA", encoding="utf-8")
    artifact = tmp_path / "candidate.tar.gz"
    receipt = make_bundle(root, candidate, artifact)
    return root, candidate, artifact, receipt


def test_canonical_package_is_exclusive_and_standalone_bootstrap_runs_in_isolated_python(package, tmp_path):
    root, candidate, artifact, receipt = package
    checksum = hashlib.sha256(artifact.read_bytes()).hexdigest()
    assert receipt["sha256"] == checksum
    with tarfile.open(artifact, "r:gz") as archive:
        manifest = json.load(archive.extractfile(MANIFEST))
        assert set(manifest["files"]) == {"entry.py", ".gitignore"}
    with pytest.raises(FileExistsError):
        make_bundle(root, candidate, artifact)
    assert hashlib.sha256(artifact.read_bytes()).hexdigest() == checksum
    helper = Path(__file__).resolve().parents[3] / "tools/first_release_stage_unpack.py"
    release = tmp_path / "new-release"
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            str(helper),
            "--candidate",
            candidate,
            "--artifact",
            str(artifact),
            "--artifact-sha256",
            checksum,
            "--release",
            str(release),
            "--local-drill",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0 and json.loads(result.stdout)["status"] == "unpacked_new_release"
    assert (release / "entry.py").read_bytes() == git(root, "show", candidate + ":entry.py").encode() + b"\n"
    assert not (release / "private").exists()
    with pytest.raises(ValueError):
        unpack(artifact, checksum, candidate, release, local_drill=True)
    assert (release / "entry.py").is_file()


def test_wrong_archive_hash_and_traversal_preserve_all_existing_files(package, tmp_path):
    _, candidate, artifact, _ = package
    release = tmp_path / "never-created"
    with pytest.raises(ValueError):
        unpack(artifact, "f" * 64, candidate, release, local_drill=True)
    assert not release.exists()
    malicious = tmp_path / "unsafe.tar.gz"
    with tarfile.open(malicious, "w:gz") as archive:
        info = tarfile.TarInfo("../escaped.py")
        info.size = 1
        archive.addfile(info, io.BytesIO(b"x"))
    with pytest.raises(ValueError):
        unpack(malicious, hashlib.sha256(malicious.read_bytes()).hexdigest(), candidate, release, local_drill=True)
    assert not release.exists() and not (tmp_path / "escaped.py").exists()
