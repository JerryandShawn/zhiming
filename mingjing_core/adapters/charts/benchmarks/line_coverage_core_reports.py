"""Safe lifecycle witnesses and whole-inventory line tables; no target text."""

from __future__ import annotations

import os
from copy import deepcopy
from pathlib import Path

from .line_coverage_core_fingerprint import source_snapshot
from .line_coverage_core_git import MetadataGit
from .line_coverage_manifest import ROOT, digest
from .line_coverage_own_inventory import validate_own_inventory
from .line_coverage_own_plan import CANDIDATES, build_static_plan


class Witness:
    def __init__(self, node: str) -> None:
        self.node = node
        self.selected: list[str] = []
        self.events: list[dict] = []
        self.error = None
        self.exit_code = None

    def pytest_collection_modifyitems(self, session, config, items) -> None:
        self.selected = [item.nodeid for item in items]
        if self.selected != [self.node] or any(item.fixturenames for item in items):
            self.error = "b1_selected_set_or_fixture_mismatch"
            raise ValueError(self.error)

    def pytest_runtest_logreport(self, report) -> None:
        if report.nodeid != self.node or report.when not in (
            "setup",
            "call",
            "teardown",
        ):
            self.error = "b1_lifecycle_node_or_phase_mismatch"
            return
        outcome = (
            report.outcome
            if report.outcome in ("passed", "failed", "skipped")
            else "unknown"
        )
        self.events.append(
            {
                "phase": report.when,
                "outcome": outcome,
                "xfail": hasattr(report, "wasxfail"),
            }
        )

    def pytest_sessionfinish(self, session, exitstatus) -> None:
        self.exit_code = int(exitstatus)

    def successful(self, exit_code: int) -> bool:
        expected = [
            {"phase": phase, "outcome": "passed", "xfail": False}
            for phase in ("setup", "call", "teardown")
        ]
        return (
            self.error is None
            and self.selected == [self.node]
            and digest(self.events) == digest(expected)
            and type(self.exit_code) is int
            and type(exit_code) is int
            and self.exit_code == exit_code == 0
        )

    def data(self) -> dict:
        return {
            "selected": self.selected,
            "events": self.events,
            "error_code": self.error,
            "session_exit_code": self.exit_code,
        }


def line_files(inventory: dict, counts: dict | None) -> list[dict]:
    observations = {}
    for (filename, line), count in (counts or {}).items():
        if type(line) is not int or line <= 0 or type(count) is not int or count < 0:
            raise ValueError("b1_observation_type_invalid")
        key = os.path.normcase(str(Path(filename).resolve())), line
        observations[key] = observations.get(key, 0) + count
    rows = []
    for source in inventory["files"]:
        path = os.path.normcase(str((ROOT / source["path"]).resolve()))
        rows.append(
            {
                "path": source["path"],
                "group": source["group"],
                "lf_sha256": source["lf_sha256"],
                "executable_lines": source["executable_lines"],
                "line_counts": None
                if counts is None
                else [
                    [line, observations.get((path, line), 0)]
                    for line in source["executable_lines"]
                ],
            }
        )
    return rows


def summaries(files: list[dict], complete: bool) -> dict:
    result = {}
    for group in sorted({row["group"] for row in files}) + ["own_scope_total"]:
        rows = (
            files
            if group == "own_scope_total"
            else [row for row in files if row["group"] == group]
        )
        denominator = sum(len(row["executable_lines"]) for row in rows)
        observed = (
            None
            if any(row["line_counts"] is None for row in rows)
            else sum(count > 0 for row in rows for _, count in row["line_counts"])
        )
        result[group] = {
            "files": len(rows),
            "denominator_lines": denominator,
            "observed_lines": observed,
            "line_execution_fraction": observed / denominator
            if complete and observed is not None and denominator
            else None,
        }
    return result


def _success_facts(receipt: dict) -> None:
    node = receipt.get("node_id")
    witness = Witness(node)
    lifecycle = receipt.get("lifecycle", {})
    witness.selected, witness.events = (
        lifecycle.get("selected"),
        lifecycle.get("events"),
    )
    witness.error, witness.exit_code = (
        lifecycle.get("error_code"),
        lifecycle.get("session_exit_code"),
    )
    runtime = receipt.get("runtime_before")
    before, after = receipt.get("source_before"), receipt.get("source_after")
    if (
        CANDIDATES.get(node) != "core"
        or type(receipt.get("exit_code")) is not int
        or not witness.successful(receipt["exit_code"])
    ):
        raise ValueError("b1_receipt_lifecycle_not_successful")
    if (
        receipt.get("blocked_attempts") != {}
        or receipt.get("trial_status") != "completed"
        or receipt.get("postflight_error_code") is not None
    ):
        raise ValueError("b1_receipt_guard_not_successful")
    if (
        receipt.get("observation_state") != "complete"
        or receipt.get("static_plan_execution_approved") is not False
    ):
        raise ValueError("b1_receipt_observation_not_complete")
    if (
        not isinstance(runtime, dict)
        or digest(runtime) != digest(receipt.get("runtime_after"))
        or runtime.get("runtime_sha256")
        != digest({k: v for k, v in runtime.items() if k != "runtime_sha256"})
    ):
        raise ValueError("b1_receipt_runtime_not_fixed")
    if (
        not isinstance(before, dict)
        or not isinstance(after, dict)
        or any(
            before.get(k) != after.get(k)
            for k in ("files", "git_configuration", "raw_sha256")
        )
    ):
        raise ValueError("b1_receipt_sources_not_fixed")
    safety = receipt.get("safety", {})
    if (
        type(safety.get("target_child_processes_started")) is not int
        or safety["target_child_processes_started"] != 0
        or safety.get("project_data_read_allowlist") != []
    ):
        raise ValueError("b1_receipt_safety_mismatch")


def validate_receipt(inventory: dict, receipt: dict) -> None:
    payload = {key: value for key, value in receipt.items() if key != "receipt_sha256"}
    if receipt.get("receipt_sha256") != digest(payload):
        raise ValueError("b1_receipt_integrity_invalid")
    if (
        receipt.get("version") != "p8-own-core-line-receipt-v2"
        or receipt.get("commit") != inventory["commit"]
        or receipt.get("inventory_sha256") != inventory["inventory_sha256"]
    ):
        raise ValueError("b1_receipt_fixed_inventory_mismatch")
    if (
        receipt.get("runtime") != "core"
        or receipt.get("mode") != "trace"
        or receipt.get("status") != "completed"
        or receipt.get("coverage_collected") is not True
        or receipt.get("eligible_for_union") is not True
    ):
        raise ValueError("b1_receipt_not_successful_trace")
    _success_facts(receipt)
    expected = {row["path"]: row for row in inventory["files"]}
    rows = receipt.get("files", [])
    if len(rows) != len(expected) or len({row["path"] for row in rows}) != len(rows):
        raise ValueError("b1_receipt_inventory_mismatch")
    for row in rows:
        source = expected.get(row["path"])
        if source is None or digest(
            {key: row.get(key) for key in ("group", "lf_sha256", "executable_lines")}
        ) != digest(
            {key: source[key] for key in ("group", "lf_sha256", "executable_lines")}
        ):
            raise ValueError("b1_receipt_source_mismatch")
        pairs = row.get("line_counts")
        if not isinstance(pairs, list) or any(
            not isinstance(pair, list)
            or len(pair) != 2
            or type(pair[0]) is not int
            or type(pair[1]) is not int
            or pair[1] < 0
            for pair in pairs
        ):
            raise ValueError("b1_receipt_count_type_invalid")
        if [pair[0] for pair in pairs] != source["executable_lines"]:
            raise ValueError("b1_receipt_line_inventory_mismatch")


def merge_core(inventory: dict, receipts: list[dict]) -> dict:
    git = MetadataGit(ROOT, lambda: False)
    with git.installed():
        validate_own_inventory(ROOT, inventory)
        plan = build_static_plan(
            ROOT,
            inventory,
            runtime="core",
            node_ids=tuple(
                node for node, runtime in CANDIDATES.items() if runtime == "core"
            ),
        )
    current_source = source_snapshot(inventory, git)
    if not receipts or len({row.get("receipt_sha256") for row in receipts}) != len(
        receipts
    ):
        raise ValueError("b1_union_empty_or_duplicate")
    for receipt in receipts:
        validate_receipt(inventory, receipt)
        if receipt.get("static_plan_sha256") != plan["plan_sha256"]:
            raise ValueError("b1_union_pinned_plan_mismatch")
        if any(
            receipt["source_before"].get(key) != current_source.get(key)
            for key in ("files", "git_configuration", "raw_sha256")
        ):
            raise ValueError("b1_union_current_source_mismatch")
    if (
        len({row["runtime_before"]["runtime_sha256"] for row in receipts}) != 1
        or len({row["static_plan_sha256"] for row in receipts}) != 1
    ):
        raise ValueError("b1_union_runtime_or_plan_mismatch")
    files = deepcopy(receipts[0]["files"])
    tables = [{row["path"]: row for row in receipt["files"]} for receipt in receipts]
    for row in files:
        row["line_counts"] = [
            [
                line,
                sum(table[row["path"]]["line_counts"][offset][1] for table in tables),
            ]
            for offset, line in enumerate(row["executable_lines"])
        ]
    result = {
        "version": "p8-own-core-line-union-v2",
        "commit": inventory["commit"],
        "inventory_sha256": inventory["inventory_sha256"],
        "runtime": "core",
        "source_receipt_sha256": [row["receipt_sha256"] for row in receipts],
        "files": files,
        "summary": summaries(files, True),
        "not_collected": ["charts", "child_processes", "other_threads", "native_C_JS"],
        "limits": [
            "Content integrity only, not authentication or independent proof of execution.",
            "Line events, not branch coverage, assertion quality, or professional task accuracy.",
        ],
    }
    result["union_sha256"] = digest(result)
    return result
