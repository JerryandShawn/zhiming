"""Synthetic Git histories and a frozen real artifact; never interchangeable."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from uuid import uuid4

from mingjing_core.adapters.charts.benchmarks.line_coverage_manifest import ROOT, digest

REAL_ORIGIN = "7fa5e10a4dbe0e2878e28c6f6a115f17d013aaa2"
REAL_CUTOVER = "f23b942ce698a3f7ee0b98c918d43053fe773433"
REAL_OBSERVED = "ef5fed9a3fc4e1b727e6077f5b99f41be31e6f7b"
REAL_INVENTORY_SHA = "6b4d2c868ce430bc04498ea8c56734a919a578b04b1d263452fe3043142d2d57"
INITIAL_PATHS = (
    "mingjing_core/calculations/bazi/__init__.py",
    "mingjing_core/calculations/bazi/calendar_layers.py",
    "mingjing_core/calculations/bazi/elements.py",
    "mingjing_core/calculations/bazi/stars.py",
    "mingjing_core/calculations/bazi/strength.py",
    "mingjing_core/calculations/bazi/structure.py",
    "mingjing_core/calculations/bazi/supplement.py",
    "tests/v4/test_p8_bazi_rules.py",
    "tests/v4/test_p8_chart_process.py",
    "tools/verify_p8_calculators.py",
)
LATER_PATHS = (
    "mingjing_core/adapters/charts/synthetic_history.py",
    "mingjing_core/skills/synthetic_history.py",
    "mingjing_core/adapters/charts/benchmarks/synthetic_history.py",
    "tests/test_p8_synthetic_history.py",
    "tests/v4/p8_synthetic_history_context.py",
)


def historical_snapshot() -> dict:
    """Verify a published snapshot, without claiming Git reconstruction in CI."""
    path = ROOT / "docs/v4/evidence/P8/night28-own-inventory-ef5fed9-static.json"
    value = json.loads(path.read_text(encoding="utf8"))
    payload = {key: item for key, item in value.items() if key != "inventory_sha256"}
    assert value["inventory_sha256"] == digest(payload) == REAL_INVENTORY_SHA
    assert value["history_base_commit"] == REAL_ORIGIN
    assert value["cutover_reference_commit"] == REAL_CUTOVER
    assert value["commit"] == REAL_OBSERVED
    carried = {
        row["path"]
        for row in value["files"]
        if row["initial_carry_forward_unchanged_since_cutover"]
    }
    assert carried == set(INITIAL_PATHS)
    assert carried <= {row["path"] for row in value["static_source_guards"]}
    return value


def _git(root: Path, *args: str) -> str:
    if not root.resolve().is_relative_to(ROOT / "private/tmp"):
        raise ValueError("synthetic_history_outside_private_tmp")
    hooks = root / "empty-hooks"
    hooks.mkdir(exist_ok=True)
    result = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.name=Synthetic Portable Coverage",
            "-c",
            "user.email=synthetic-coverage@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "-c",
            "core.fsmonitor=false",
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


def _write(root: Path, path: str, body: str) -> None:
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf8", newline="\n")


def _commit(root: Path, description: str) -> str:
    _git(root, "add", ".")
    _git(root, "commit", "--quiet", "-m", "Synthetic only: " + description)
    return _git(root, "rev-parse", "HEAD")


def synthetic_history_repository() -> tuple[Path, str, str, str]:
    """Carry ten named initial paths using fake contents and fake Git identities."""
    root = ROOT / "private/tmp/coverage-portable-history" / uuid4().hex
    root.mkdir(parents=True, exist_ok=False)
    _git(root, "init", "--quiet", "--object-format=sha1")
    _write(root, "README.fixture.md", "SYNTHETIC; not real P8 history or sources.\n")
    _write(root, "pytest.ini", "[pytest]\n")
    _write(root, "legacy.py", "SYNTHETIC_PREEXISTING = 1\n")
    origin = _commit(root, "origin before implementation")
    for index, path in enumerate(INITIAL_PATHS):
        _write(root, path, f"SYNTHETIC_INITIAL = {index}\n")
    cutover = _commit(root, "ten initial independent dummy files")
    for index, path in enumerate(LATER_PATHS):
        _write(root, path, f"SYNTHETIC_LATER = {index}\n")
    observed = _commit(root, "five later group representatives")
    return root, origin, cutover, observed
