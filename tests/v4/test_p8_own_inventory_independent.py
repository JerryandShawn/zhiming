"""Independent static-A attacks; no target imports, Charts or trace collection."""

from __future__ import annotations

import builtins
import hashlib
import subprocess
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest
from p8_coverage_history_context import INITIAL_PATHS, synthetic_history_repository

from mingjing_core.adapters.charts.benchmarks import line_coverage_own_sources as source
from mingjing_core.adapters.charts.benchmarks.line_coverage_manifest import ROOT, digest
from mingjing_core.adapters.charts.benchmarks.line_coverage_own_inventory import (
    build_own_inventory,
    validate_own_inventory,
)
from mingjing_core.adapters.charts.benchmarks.line_coverage_own_plan import (
    CANDIDATES,
    CORE_FILE,
    build_static_plan,
    validate_static_plan,
)

CORE_NODE = next(node for node, runtime in CANDIDATES.items() if runtime == "core")


def _git(root: Path, *args: str, input_bytes: bytes | None = None) -> bytes:
    return subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.name=Independent Static A",
            "-c",
            "user.email=static-a@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "-c",
            "core.hooksPath=" + str(root / ".git/no-hooks"),
            *args,
        ],
        input=input_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=True,
        timeout=10,
    ).stdout


def _write(root: Path, name: str, text: str) -> None:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf8", newline="\n")
    _git(root, "add", "--", name)


def _commit(root: Path) -> str:
    _git(root, "commit", "--quiet", "-m", "Synthetic independent static-A fixture")
    return _git(root, "rev-parse", "HEAD").decode().strip()


def _repository(*, symlink: bool = False) -> tuple:
    root = ROOT / "private/tmp/own-independent" / uuid4().hex
    root.mkdir(parents=True, exist_ok=False)
    _git(root, "init", "--quiet")
    _write(root, "pytest.ini", "[pytest]\n")
    _write(root, "legacy.py", "PREEXISTING = 1\n")
    if symlink:
        identity = (
            _git(root, "hash-object", "-w", "--stdin", input_bytes=b"legacy.py\n")
            .decode()
            .strip()
        )
        _git(
            root,
            "update-index",
            "--add",
            "--cacheinfo",
            "120000," + identity + ",legacy_link.py",
        )
    base = _commit(root)
    text = "raise RuntimeError('TARGET_IMPORT_MUST_NOT_HAPPEN')\n"
    text += f"def {CORE_NODE.split('::')[-1]}():\n    return 1\n"
    _write(root, CORE_FILE, text)
    _write(root, "mingjing_core/calculations/bazi/independent.py", "INITIAL = 1\n")
    cutover = _commit(root)
    _write(root, "mingjing_core/skills/later.py", "LATER = 2\n")
    return root, base, cutover, _commit(root)


@contextmanager
def _policy(repository: tuple):
    root, base, cutover, observed = repository
    with patch.object(source, "ORIGIN", base), patch.object(source, "CUTOVER", cutover):
        yield root, base, observed


def _build(repository: tuple) -> dict:
    with _policy(repository) as (root, base, observed):
        return build_own_inventory(root, base_commit=base, commit=observed)


def _resign(value: dict, key: str) -> None:
    value.pop(key, None)
    value[key] = digest(value)


@pytest.fixture(scope="module")
def portable_history() -> tuple:
    return synthetic_history_repository()


@pytest.fixture(scope="module")
def repository() -> tuple:
    return _repository()


def test_synthetic_initial_ten_are_full_paths_not_just_a_matching_count(
    portable_history,
) -> None:
    root, base, cutover, observed = portable_history
    inventory = _build(portable_history)
    first = set(
        _git(
            root,
            "diff",
            "--name-only",
            "--no-renames",
            base,
            cutover,
            "--",
            "*.py",
        )
        .decode()
        .splitlines()
    )
    later = set(
        _git(
            root,
            "diff",
            "--name-only",
            "--no-renames",
            cutover,
            observed,
            "--",
            "*.py",
        )
        .decode()
        .splitlines()
    )
    expected = first - later
    recorded = {
        row["path"]
        for row in inventory["files"]
        if row["initial_carry_forward_unchanged_since_cutover"]
    }
    assert len(expected) == 10 and recorded == expected == set(INITIAL_PATHS)
    assert expected <= {row["path"] for row in inventory["static_source_guards"]}


def test_resigning_an_inventory_with_cutover_as_origin_does_not_authorize_the_base(
    portable_history,
) -> None:
    root, _, cutover, _ = portable_history
    changed = deepcopy(_build(portable_history))
    changed["history_base_commit"] = cutover
    _resign(changed, "inventory_sha256")
    with (
        _policy(portable_history),
        pytest.raises(ValueError, match="approved_origin_required"),
    ):
        validate_own_inventory(root, changed)


def test_synthetic_ten_carry_fixture_exercises_every_owned_group(portable_history):
    inventory = _build(portable_history)
    assert inventory["summary"]["own_scope_total"] == {
        "files": 15,
        "denominator_lines": 15,
    }
    assert inventory["initial_carry_forward_unchanged_count"] == 10
    assert set(inventory["summary"]) == {
        "charts_runtime",
        "bazi_calculations",
        "core_skills",
        "research",
        "native_tests",
        "v4_helpers",
        "v4_tests",
        "verification_tool",
        "own_scope_total",
    }
    assert inventory["inventory_complete_for_p8_history"] is True
    assert inventory["coverage_collected"] is False
    assert not any("line_counts" in row for row in inventory["files"])


def test_unchanged_legacy_python_symlink_is_rejected_by_full_tree_scan() -> None:
    fixture = _repository(symlink=True)
    with pytest.raises(ValueError, match="nonregular_source_refused"):
        _build(fixture)


@pytest.mark.parametrize(
    "mutation", ["same_length_changed_payload", "truncated_payload"]
)
def test_git_batch_header_does_not_substitute_for_full_blob_identity(
    mutation: str,
) -> None:
    raw = b"VALUE = 1\n"
    identity = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
    value = raw.replace(b"1", b"2") if mutation.startswith("same") else raw[:-2]
    response = f"{identity} blob {len(raw)}\n".encode() + value + b"\n"
    with (
        patch.object(source, "git_bytes", return_value=response),
        pytest.raises(ValueError, match="git_blob_content_invalid"),
    ):
        source.raw_sources(ROOT, {"mingjing_core/skills/example.py": identity})


def test_net_zero_add_delete_cannot_be_resigned_out_of_the_ledger() -> None:
    fixture = _repository()
    root, base, cutover, _ = fixture
    name = "mingjing_core/skills/transient.py"
    _write(root, name, "TRANSIENT = 1\n")
    _commit(root)
    (root / name).unlink()
    _git(root, "add", "--", name)
    observed = _commit(root)
    fixture = root, base, cutover, observed
    assert (
        name
        not in _git(root, "diff", "--name-only", base, observed).decode().splitlines()
    )
    inventory = _build(fixture)
    assert name in {row["path"] for row in inventory["deleted_owned_python"]}
    inventory["deleted_owned_python"] = []
    _resign(inventory, "inventory_sha256")
    with (
        _policy(fixture),
        pytest.raises(ValueError, match="pinned_source_mismatch"),
    ):
        validate_own_inventory(root, inventory)


def test_equal_float_ast_line_cannot_survive_resigning_a_static_plan(
    repository,
) -> None:
    inventory = _build(repository)
    with _policy(repository) as (root, _, _):
        plan = build_static_plan(root, inventory, runtime="core", node_ids=(CORE_NODE,))
        target = plan["entries"][0]["target"]
        target["start_line"] = float(target["start_line"])
        _resign(plan, "plan_sha256")
        with pytest.raises(ValueError, match="pinned_source_mismatch"):
            validate_static_plan(root, inventory, plan)


@pytest.mark.parametrize("key", ["execution_approved", "coverage_collected"])
def test_numeric_zero_is_not_the_unapproved_uncollected_boolean_state(
    repository, key: str
) -> None:
    inventory = _build(repository)
    with _policy(repository) as (root, _, _):
        plan = build_static_plan(root, inventory, runtime="core", node_ids=(CORE_NODE,))
        plan[key] = 0
        _resign(plan, "plan_sha256")
        with pytest.raises(ValueError, match="static_state_invalid"):
            validate_static_plan(root, inventory, plan)


def test_static_candidate_with_unsafe_import_body_is_not_imported_or_approved(
    repository, monkeypatch
) -> None:
    inventory = _build(repository)
    original = builtins.__import__
    attempted = []

    def guarded(name: str, *args, **kwargs):
        if name.startswith(
            ("tests.v4.test_p8_e2_night28_controls", "test_p8_e2_night28_controls")
        ):
            attempted.append(name)
            raise AssertionError("candidate import is forbidden during static planning")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    monkeypatch.setattr(
        pytest, "main", lambda *args: pytest.fail("pytest collection forbidden")
    )
    with _policy(repository) as (root, _, _):
        plan = build_static_plan(root, inventory, runtime="core", node_ids=(CORE_NODE,))
    assert attempted == []
    assert plan["execution_approved"] is plan["coverage_collected"] is False
    assert plan["entries"][0]["hidden_import_or_helper_effects_proven_safe"] is False
    assert plan["unselected_files_still_in_denominator"] is True
