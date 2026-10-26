"""Synthetic B1 receipt integrity checks; never execute a target or trace."""

from copy import deepcopy

import pytest

from mingjing_core.adapters.charts.benchmarks import (
    line_coverage_core_reports as reports,
)
from mingjing_core.adapters.charts.benchmarks.line_coverage_manifest import digest
from mingjing_core.adapters.charts.benchmarks.line_coverage_own_plan import CANDIDATES

NODE = next(k for k, v in CANDIDATES.items() if v == "core")


def inventory():
    return {
        "commit": "a" * 40,
        "inventory_sha256": "b" * 64,
        "files": [
            {
                "path": "mingjing_core/adapters/charts/benchmarks/cold.py",
                "group": "benchmarks",
                "lf_sha256": "c" * 64,
                "executable_lines": [1, 3],
            },
            {
                "path": "tests/v4/example.py",
                "group": "tests",
                "lf_sha256": "d" * 64,
                "executable_lines": [2],
            },
        ],
    }


def signed(value):
    result = deepcopy(value)
    result["receipt_sha256"] = digest(
        {k: v for k, v in result.items() if k != "receipt_sha256"}
    )
    return result


def receipt():
    source = {"files": {}, "git_configuration": {}, "raw_sha256": {}}
    runtime = {"python": {"implementation": "cpython"}, "files": {}}
    runtime["runtime_sha256"] = digest(runtime)
    result = {
        "version": "p8-own-core-line-receipt-v2",
        "runtime": "core",
        "mode": "trace",
        "commit": "a" * 40,
        "inventory_sha256": "b" * 64,
        "static_plan_sha256": "e" * 64,
        "static_plan_execution_approved": False,
        "node_id": NODE,
        "status": "completed",
        "coverage_collected": True,
        "eligible_for_union": True,
        "exit_code": 0,
        "observation_state": "complete",
        "trial_status": "completed",
        "blocked_attempts": {},
        "postflight_error_code": None,
        "source_before": source,
        "source_after": deepcopy(source),
        "runtime_before": runtime,
        "runtime_after": deepcopy(runtime),
        "safety": {
            "target_child_processes_started": 0,
            "project_data_read_allowlist": [],
        },
        "lifecycle": {
            "selected": [NODE],
            "events": [
                {"phase": p, "outcome": "passed", "xfail": False}
                for p in ("setup", "call", "teardown")
            ],
            "error_code": None,
            "session_exit_code": 0,
        },
        "files": reports.line_files(inventory(), {}),
    }
    return signed(result)


def test_all_cold_files_remain_zero_and_baseline_has_no_fake_zero_score():
    rows = reports.line_files(inventory(), {})
    assert [r["line_counts"] for r in rows] == [[[1, 0], [3, 0]], [[2, 0]]]
    assert reports.summaries(rows, True)["own_scope_total"]["denominator_lines"] == 3
    baseline = reports.line_files(inventory(), None)
    assert all(r["line_counts"] is None for r in baseline)
    assert (
        reports.summaries(baseline, False)["own_scope_total"]["observed_lines"] is None
    )


@pytest.mark.parametrize(
    "line,count", [(True, 1), (1.0, 1), (0, 1), (1, False), (1, 1.0), (1, -1)]
)
def test_observed_lines_and_counts_require_real_nonnegative_integers(line, count):
    path = str(reports.ROOT / "tests/v4/example.py")
    with pytest.raises(ValueError, match="b1_observation_type_invalid"):
        reports.line_files(inventory(), {(path, line): count})


def test_success_shape_has_full_cold_denominator():
    reports.validate_receipt(inventory(), receipt())


@pytest.mark.parametrize(
    "field,value",
    [
        ("exit_code", 1),
        ("exit_code", False),
        ("exit_code", 0.0),
        ("blocked_attempts", {"network": 1}),
        ("trial_status", "exception"),
        ("observation_state", "partial_not_eligible"),
        ("static_plan_execution_approved", True),
        ("status", "failed"),
        ("eligible_for_union", False),
    ],
)
def test_resigning_failure_flags_cannot_make_success(field, value):
    row = receipt()
    row[field] = value
    with pytest.raises(ValueError):
        reports.validate_receipt(inventory(), signed(row))


@pytest.mark.parametrize(
    "mutation",
    [
        "runtime",
        "source",
        "skip",
        "xfail_integer",
        "session_float",
        "missing_phase",
        "extra_node",
        "line_float",
        "line_bool",
        "truncated",
        "duplicate",
        "metadata_float",
    ],
)
def test_resigned_source_lifecycle_and_count_tampering_rejected(mutation):
    row = receipt()
    if mutation == "runtime":
        row["runtime_after"]["python"]["implementation"] = "other"
    elif mutation == "source":
        row["source_after"]["files"]["other"] = "private not retained"
    elif mutation == "skip":
        row["lifecycle"]["events"][1]["outcome"] = "skipped"
    elif mutation == "xfail_integer":
        row["lifecycle"]["events"][1]["xfail"] = 0
    elif mutation == "session_float":
        row["lifecycle"]["session_exit_code"] = 0.0
    elif mutation == "missing_phase":
        row["lifecycle"]["events"].pop()
    elif mutation == "extra_node":
        row["lifecycle"]["selected"].append(NODE + "_other")
    elif mutation == "line_float":
        row["files"][0]["line_counts"][0][0] = 1.0
    elif mutation == "line_bool":
        row["files"][0]["line_counts"][0][1] = False
    elif mutation == "truncated":
        row["files"].pop()
    elif mutation == "duplicate":
        row["files"][1] = deepcopy(row["files"][0])
    else:
        row["files"][0]["executable_lines"] = [1.0, 3]
    with pytest.raises(ValueError):
        reports.validate_receipt(inventory(), signed(row))


def test_union_rebuilds_inventory_before_accepting_signed_tables(monkeypatch):
    events = []

    class Git:
        def __init__(self, *args):
            pass

        def installed(self):
            from contextlib import nullcontext

            return nullcontext()

    def reject(*args):
        events.append("rebuilt")
        raise ValueError("synthetic_inventory_rejected")

    monkeypatch.setattr(reports, "MetadataGit", Git)
    monkeypatch.setattr(reports, "validate_own_inventory", reject)
    with pytest.raises(ValueError, match="synthetic_inventory_rejected"):
        reports.merge_core(inventory(), [receipt()])
    assert events == ["rebuilt"]


def test_union_path_order_uses_its_own_source_table(monkeypatch):
    from contextlib import nullcontext

    class Git:
        def __init__(self, *args):
            pass

        def installed(self):
            return nullcontext()

    first = receipt()
    second = receipt()
    second["files"].reverse()
    second["files"][0]["line_counts"][0][1] = 3
    second = signed(second)
    monkeypatch.setattr(reports, "MetadataGit", Git)
    monkeypatch.setattr(reports, "validate_own_inventory", lambda *args: None)
    monkeypatch.setattr(
        reports, "build_static_plan", lambda *args, **kwargs: {"plan_sha256": "e" * 64}
    )
    monkeypatch.setattr(
        reports, "source_snapshot", lambda *args: first["source_before"]
    )
    result = reports.merge_core(inventory(), [first, second])
    assert result["files"][0]["line_counts"] == [[1, 0], [3, 0]]
    assert result["files"][1]["line_counts"] == [[2, 3]]
