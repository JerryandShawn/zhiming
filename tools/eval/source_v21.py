"""Bind E1 to a clean P1 source snapshot before any P2 business quick wins."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any

from tools.eval.contract_v2 import VERSION
from tools.eval.runner import ROOT, _source_digest

P2_ONLY = ("mingjing_core/timekit/now_block.py", "mingjing_core/memory/threads.py")


def execution_digest() -> str:
    digest = hashlib.sha256(_source_digest().encode())
    paths = [path for path in (ROOT / "tools/eval").rglob("*") if path.suffix in {".yaml", ".md", ".json"}]
    paths += list((ROOT / "config").glob("*.yaml"))
    for path in sorted(paths):
        digest.update(path.relative_to(ROOT).as_posix().encode())
        digest.update(b"\x00")
        digest.update(path.read_bytes())
    return digest.hexdigest()


def assert_old_v3() -> None:
    if os.getenv("MODELS_CONFIG") or os.getenv("MINGJING_MODEL_PORT") == "v2":
        raise SystemExit("E1 old-v3 baseline requires the new model-port switches to remain off")
    if any((ROOT / name).exists() for name in P2_ONLY):
        raise SystemExit("P2 business code is present; use the frozen pre-P2 P1 execution snapshot")


def freeze_source(path: Path) -> dict[str, Any]:
    assert_old_v3()
    changed = subprocess.run(
        ["git", "diff", "HEAD", "--name-only", "--", "tools/eval", "mingjing_core", "config", "requirements*.lock"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    untracked = subprocess.run(
        [
            "git",
            "ls-files",
            "--others",
            "--exclude-standard",
            "--",
            "tools/eval",
            "mingjing_core",
            "config",
            "requirements*.lock",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    if changed or untracked:
        raise SystemExit("Commit the reviewed P1 A/C execution sources before freezing E1")
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()
    manifest = {
        "contract_version": VERSION,
        "source_commit": commit,
        "source_sha256": _source_digest(),
        "execution_sha256": execution_digest(),
        "baseline_runtime": "unchanged-v3-ConfiguredModel",
        "frozen_before_p2": True,
        "target_model": "k3",
        "judge_model": "k3-256k",
        "model_port_enabled": False,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return manifest


def verify_source(path: Path | None) -> dict[str, Any]:
    assert_old_v3()
    if path is None or not path.is_file():
        raise SystemExit("Live E1 requires an immutable P1 execution-source manifest")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    expected = {
        "contract_version": VERSION,
        "baseline_runtime": "unchanged-v3-ConfiguredModel",
        "frozen_before_p2": True,
        "model_port_enabled": False,
        "target_model": "k3",
        "judge_model": "k3-256k",
    }
    if (
        any(manifest.get(key) != value for key, value in expected.items())
        or manifest.get("source_sha256") != _source_digest()
        or manifest.get("execution_sha256") != execution_digest()
    ):
        raise SystemExit("E1 source/contract/model identity changed; never resume with P2 or a different checkout")
    return manifest
