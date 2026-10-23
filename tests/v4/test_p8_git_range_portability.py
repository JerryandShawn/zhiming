"""Real deep synthetic Git ranges preserve deleted paths with longpaths disabled."""

from __future__ import annotations

import subprocess
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest

from mingjing_core.adapters.charts.benchmarks import line_coverage_own_sources as source
from mingjing_core.adapters.charts.benchmarks.line_coverage_manifest import ROOT, digest
from mingjing_core.adapters.charts.benchmarks.line_coverage_own_inventory import (
    build_own_inventory,
    validate_own_inventory,
)

TRANSIENT = "mingjing_core/skills/synthetic_transient.py"


def _git(root: Path, *args: str) -> str:
    if not root.resolve().is_relative_to(ROOT / "private/tmp"):
        raise ValueError("range_fixture_outside_private_tmp")
    hooks = root / "empty-hooks"
    hooks.mkdir(exist_ok=True)
    result = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.name=Synthetic Deep Range",
            "-c",
            "user.email=synthetic-range@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "-c",
            "core.fsmonitor=false",
            "-c",
            "core.longpaths=false",
            "-c",
            "core.hooksPath=" + str(hooks),
            *args,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=True,
        timeout=10,
    )
    return result.stdout.decode("utf8").strip()


def _write(root: Path, name: str, body: str) -> None:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf8", newline="\n")


def _commit(root: Path) -> str:
    _git(root, "add", ".")
    _git(root, "commit", "--quiet", "-m", "Synthetic only: deep range history")
    return _git(root, "rev-parse", "HEAD")


@pytest.fixture(scope="module")
def deep_history() -> tuple[Path, str, str, str]:
    parent = ROOT / "private/tmp/git-range-fixtures" / uuid4().hex
    padding = "d" * max(1, 185 - len(str(parent)) - 1)
    root = parent / padding
    root.mkdir(parents=True, exist_ok=False)
    _git(root, "init", "--quiet", "--object-format=sha1")
    _git(root, "config", "core.longpaths", "false")
    _write(root, "pytest.ini", "[pytest]\n")
    _write(root, "legacy.py", "SYNTHETIC_LEGACY = 1\n")
    base = _commit(root)
    _write(root, "mingjing_core/skills/synthetic_kept.py", "SYNTHETIC_KEPT = 1\n")
    cutover = _commit(root)
    _write(root, TRANSIENT, "SYNTHETIC_TRANSIENT = 1\n")
    _commit(root)
    (root / TRANSIENT).unlink()
    observed = _commit(root)
    assert len(str(root)) >= 185
    assert len(str(root)) + 1 + len(base + ".." + observed) > 260
    assert _git(root, "config", "--get", "core.longpaths") == "false"
    return root, base, cutover, observed


def test_deep_revision_range_has_an_explicit_empty_pathspec(deep_history, monkeypatch):
    root, base, _, observed = deep_history
    recorded = []
    actual_git = source.git_bytes

    def observed_git(root, *args, input_bytes=None):
        recorded.append(args)
        return actual_git(root, *args, input_bytes=input_bytes)

    monkeypatch.setattr(source, "git_bytes", observed_git)
    deleted = source.deleted_paths(root, base, observed, source.tree(root, observed))
    assert deleted == [TRANSIENT]
    revision_calls = [args for args in recorded if args[0] == "rev-list"]
    assert revision_calls == [
        ("rev-list", "--ancestry-path", base + ".." + observed, "--")
    ]


def test_deep_net_zero_deletion_cannot_be_resigned_out_of_the_ledger(deep_history):
    root, base, cutover, observed = deep_history
    assert (
        TRANSIENT not in _git(root, "diff", "--name-only", base, observed).splitlines()
    )
    with patch.object(source, "ORIGIN", base), patch.object(source, "CUTOVER", cutover):
        inventory = build_own_inventory(root, base_commit=base, commit=observed)
        assert inventory["deleted_owned_python"] == [
            {"path": TRANSIENT, "reason": "absent_in_observed_commit"}
        ]
        assert {row["path"] for row in inventory["files"]} == {
            "mingjing_core/skills/synthetic_kept.py"
        }
        assert inventory["coverage_collected"] is False
        validate_own_inventory(root, inventory)
        changed = deepcopy(inventory)
        changed["deleted_owned_python"] = []
        changed.pop("inventory_sha256")
        changed["inventory_sha256"] = digest(changed)
        with pytest.raises(ValueError, match="pinned_source_mismatch"):
            validate_own_inventory(root, changed)
