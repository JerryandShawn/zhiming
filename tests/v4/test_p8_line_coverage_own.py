"""Static inventories/plans only: no target imports, Charts or trace sampling."""

from __future__ import annotations

import subprocess
import sys
from contextlib import contextmanager
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
from mingjing_core.adapters.charts.benchmarks.line_coverage_own_plan import (
    CANDIDATES,
    CHARTS_FILE,
    CORE_FILE,
    build_static_plan,
    validate_static_plan,
)

HISTORICAL = "ef5fed9a3fc4e1b727e6077f5b99f41be31e6f7b"
CORE_NODE = next(node for node, runtime in CANDIDATES.items() if runtime == "core")
CHARTS_NODE = next(node for node, runtime in CANDIDATES.items() if runtime == "charts")


def _git(root: Path, *arguments: str) -> str:
    result = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.name=Static Inventory Test",
            "-c",
            "user.email=static-inventory@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "-c",
            "core.hooksPath=" + str(root / ".git/no-hooks"),
            *arguments,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=True,
        timeout=10,
    )
    return result.stdout.decode("utf-8").strip()


def _commit(root: Path, message: str) -> str:
    _git(root, "add", ".")
    _git(root, "commit", "--quiet", "-m", message)
    return _git(root, "rev-parse", "HEAD")


def _write(root: Path, path: str, value: str) -> None:
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(value, encoding="utf-8", newline="\n")


def _repository() -> tuple[Path, str, str, str]:
    parent = ROOT / "private/tmp/own-inventory-fixtures"
    parent.mkdir(parents=True, exist_ok=True)
    root = parent / uuid4().hex
    root.mkdir(exist_ok=False)
    _git(root, "init", "--quiet")
    _write(root, "pytest.ini", "[pytest]\n")
    _write(root, "legacy.py", "old_value = 1\n")
    base = _commit(root, "Synthetic before P8")
    _write(root, "mingjing_core/calculations/bazi/elements.py", "INITIAL = 1\n")
    funcs = "\n".join(
        "def " + node.split("::")[-1] + "():\n    return 1\n"
        for node, runtime in CANDIDATES.items()
        if runtime == "core"
    )
    _write(
        root,
        CORE_FILE,
        'raise RuntimeError("STATIC_TARGET_MUST_NOT_EXECUTE")\n' + funcs,
    )
    cutover = _commit(root, "Synthetic initial implementation")
    _write(
        root, "mingjing_core/adapters/charts/benchmarks/static_tool.py", "VALUE = 2\n"
    )
    _write(root, "tests/v4/p8_sample_context.py", "HELPER = 1\n")
    _write(
        root,
        CHARTS_FILE,
        "import unittest\nclass NativeDailyTransit(unittest.TestCase):\n"
        "    @classmethod\n    def setUpClass(cls):\n"
        "        raise RuntimeError('MUST_NOT_EXECUTE')\n"
        "    def test_daily_day_pillars_advance_one_sexagenary_step(self):\n"
        "        return 1\n",
    )
    observed = _commit(root, "Synthetic observed implementation")
    return root, base, cutover, observed


@pytest.fixture(scope="module")
def repository() -> tuple[Path, str, str, str]:
    return _repository()


@pytest.fixture
def mutable_repository() -> tuple[Path, str, str, str]:
    return _repository()


@contextmanager
def _policy(repository):
    root, base, cutover, observed = repository
    with patch.object(source, "ORIGIN", base), patch.object(source, "CUTOVER", cutover):
        yield root, base, observed


def _build(repository):
    with _policy(repository) as (root, base, observed):
        return build_own_inventory(root, base_commit=base, commit=observed)


def _validate(repository, inventory):
    with _policy(repository) as (root, _, _):
        validate_own_inventory(root, inventory)


def _plan(repository, inventory, runtime="core", nodes=(CORE_NODE,)):
    with _policy(repository) as (root, _, _):
        return build_static_plan(root, inventory, runtime=runtime, node_ids=nodes)


def _resign(value: dict, field: str):
    value.pop(field, None)
    value[field] = digest(value)


def test_real_fixed_history_keeps_initial_ten_and_all_tools_native_and_helpers():
    result = build_own_inventory(ROOT, base_commit=source.ORIGIN, commit=HISTORICAL)
    assert result["summary"]["own_scope_total"] == {
        "files": 214,
        "denominator_lines": 22741,
    }
    assert result["initial_carry_forward_unchanged_count"] == 10
    assert result["summary"]["research"]["files"] == 51
    assert result["summary"]["native_tests"]["files"] == 13
    assert result["summary"]["v4_helpers"]["files"] == 3
    assert result["summary"]["verification_tool"]["files"] == 1
    assert result["inventory_complete_for_p8_history"] is True
    assert result["coverage_collected"] is False
    assert not any("line_counts" in row for row in result["files"])


def test_static_sources_and_native_class_hooks_never_execute(repository):
    inventory = _build(repository)
    assert len(inventory["files"]) == 5
    assert inventory["initial_carry_forward_unchanged_count"] == 2
    assert {row["path"] for row in inventory["excluded_preexisting_python"]} == {
        "legacy.py"
    }
    plan = _plan(repository, inventory, "charts", (CHARTS_NODE,))
    assert plan["execution_approved"] is plan["coverage_collected"] is False
    assert (
        plan["entries"][0]["lifecycle_hooks"][0]["name"]
        == "NativeDailyTransit.setUpClass"
    )
    assert plan["denominator_files"] == 5
    assert plan["unselected_files_still_in_denominator"] is True


@pytest.mark.parametrize(
    "mutation", ["omit", "duplicate", "line0", "fake_sha", "coverage", "complete"]
)
def test_rehashed_inventory_cannot_omit_or_change_fixed_git_sources(
    repository, mutation
):
    inventory = deepcopy(_build(repository))
    if mutation == "omit":
        inventory["files"].pop()
    elif mutation == "duplicate":
        inventory["files"].append(deepcopy(inventory["files"][0]))
    elif mutation == "line0":
        inventory["files"][0]["executable_lines"] = [0]
    elif mutation == "fake_sha":
        inventory["files"][0]["lf_sha256"] = "0" * 64
    elif mutation == "coverage":
        inventory["coverage_collected"] = True
    else:
        inventory["inventory_complete_for_p8_history"] = False
    _resign(inventory, "inventory_sha256")
    with pytest.raises(ValueError):
        _validate(repository, inventory)


def test_new_explicit_commit_adds_file_without_freezing_count_or_upgrading_automatically(
    mutable_repository,
):
    repository = mutable_repository
    old = _build(repository)
    root, base, cutover, observed = repository
    _write(root, "mingjing_core/adapters/charts/benchmarks/next_tool.py", "NEXT = 3\n")
    new = _commit(root, "Synthetic later tool")
    assert len(_build(repository)["files"]) == 5
    updated = _build((root, base, cutover, new))
    assert len(updated["files"]) == 6 and updated["commit"] != old["commit"]
    _validate(repository, old)


def test_deleted_owned_path_is_a_separate_ledger_not_a_silent_denominator_omission(
    mutable_repository,
):
    repository = mutable_repository
    root, base, cutover, _ = repository
    (root / "mingjing_core/adapters/charts/benchmarks/static_tool.py").unlink()
    observed = _commit(root, "Synthetic deletion")
    result = _build((root, base, cutover, observed))
    assert len(result["files"]) == 4
    assert result["deleted_owned_python"] == [
        {
            "path": "mingjing_core/adapters/charts/benchmarks/static_tool.py",
            "reason": "absent_in_observed_commit",
        }
    ]


def test_changed_python_outside_approved_ownership_requires_review(mutable_repository):
    repository = mutable_repository
    root, base, cutover, _ = repository
    _write(root, "outside.py", "value = 8\n")
    observed = _commit(root, "Synthetic ownership boundary")
    with pytest.raises(ValueError, match="requires_scope_review"):
        _build((root, base, cutover, observed))


@pytest.mark.parametrize(
    "path",
    [
        "../secret.py",
        "C:/secret.py",
        "a\\b.py",
        "/secret.py",
        "./file.py",
        "a//b.py",
        "",
    ],
)
def test_noncanonical_paths_are_rejected(path):
    with pytest.raises(ValueError, match="path_invalid"):
        source.canonical_path(path)


@pytest.mark.parametrize("revision", ["HEAD", "ef5fed9", "0" * 39, "G" * 40, None])
def test_observed_commit_must_be_an_explicit_full_sha(repository, revision):
    with (
        _policy(repository) as (root, base, _),
        pytest.raises(ValueError, match="full_commit_required"),
    ):
        build_own_inventory(root, base_commit=base, commit=revision)


@pytest.mark.parametrize(
    "nodes",
    [
        (CORE_FILE,),
        ("tests/v4",),
        (CORE_NODE + "[injected]",),
        (CHARTS_NODE,),
        (CORE_NODE, CORE_NODE),
        (None,),
        (),
    ],
)
def test_static_plan_only_accepts_exact_unique_candidates_of_same_runtime(
    repository, nodes
):
    with pytest.raises(ValueError):
        _plan(repository, _build(repository), nodes=nodes)


def test_core_static_plan_binds_config_hash_and_exact_ast_span(repository):
    inventory = _build(repository)
    plan = _plan(repository, inventory)
    assert plan["pinned_configuration"][0]["path"] == "pytest.ini"
    assert plan["entries"][0]["target"]["start_line"] > 0
    assert plan["entries"][0]["lifecycle_hooks"] == []
    assert plan["entries"][0]["hidden_import_or_helper_effects_proven_safe"] is False
    with _policy(repository) as (root, _, _):
        validate_static_plan(root, inventory, plan)


@pytest.mark.parametrize("mutation", ["execution", "span", "config", "denominator"])
def test_rehashed_plan_cannot_change_execution_state_or_ast_metadata(
    repository, mutation
):
    inventory = _build(repository)
    plan = _plan(repository, inventory)
    if mutation == "execution":
        plan["execution_approved"] = True
    elif mutation == "span":
        plan["entries"][0]["target"]["start_line"] = 10000
    elif mutation == "config":
        plan["pinned_configuration"][0]["lf_sha256"] = "0" * 64
    else:
        plan["denominator_files"] = 1
    _resign(plan, "plan_sha256")
    with _policy(repository) as (root, _, _), pytest.raises(ValueError):
        validate_static_plan(root, inventory, plan)


def test_core_fixture_or_parameter_requirement_is_not_silently_bypassed(
    mutable_repository,
):
    repository = mutable_repository
    root, base, cutover, _ = repository
    name = CORE_NODE.split("::")[-1]
    _write(
        root,
        CORE_FILE,
        "def " + name + "(private_fixture):\n    return private_fixture\n",
    )
    observed = _commit(root, "Synthetic fixture boundary")
    changed = root, base, cutover, observed
    with pytest.raises(ValueError, match="fixture_or_parameter_review_required"):
        _plan(changed, _build(changed))


def test_cutover_f23_cannot_replace_the_approved_before_initial_base():
    with pytest.raises(ValueError, match="approved_origin_required"):
        build_own_inventory(ROOT, base_commit=source.CUTOVER, commit=HISTORICAL)


@pytest.mark.parametrize("number", [1.0, True])
def test_same_numeric_value_with_wrong_line_type_is_refused_after_resigning(
    repository, number
):
    inventory = _build(repository)
    inventory["files"][0]["executable_lines"] = [number]
    _resign(inventory, "inventory_sha256")
    with pytest.raises(ValueError, match="line_type_invalid"):
        _validate(repository, inventory)


def test_other_cpython_version_is_refused_without_running_git_or_sources():
    with (
        patch.object(sys, "version_info", (3, 12, 0)),
        pytest.raises(ValueError, match="cpython311_required"),
    ):
        build_own_inventory(ROOT, base_commit=source.ORIGIN, commit=HISTORICAL)


def test_wrong_native_base_class_needs_review_not_assumed_unittest(mutable_repository):
    repository = mutable_repository
    root, base, cutover, _ = repository
    _write(
        root,
        CHARTS_FILE,
        "class NativeDailyTransit:\n"
        "    def test_daily_day_pillars_advance_one_sexagenary_step(self):\n"
        "        return 1\n",
    )
    observed = _commit(root, "Synthetic native base review")
    changed = root, base, cutover, observed
    with pytest.raises(ValueError, match="unittest_base_review_required"):
        _plan(changed, _build(changed), "charts", (CHARTS_NODE,))


def test_zero_line_file_and_new_helper_remain_in_the_dynamic_inventory(
    mutable_repository,
):
    repository = mutable_repository
    root, base, cutover, _ = repository
    _write(root, "mingjing_core/adapters/charts/benchmarks/empty_module.py", "")
    _write(root, "tests/v4/helpers/local_fixture.py", "HELPER = 5\n")
    observed = _commit(root, "Synthetic zero-line and helper sources")
    result = _build((root, base, cutover, observed))
    assert len(result["files"]) == 7
    empty = next(
        row for row in result["files"] if row["path"].endswith("empty_module.py")
    )
    assert empty["executable_lines"] == []
    assert result["summary"]["v4_helpers"]["files"] == 2
