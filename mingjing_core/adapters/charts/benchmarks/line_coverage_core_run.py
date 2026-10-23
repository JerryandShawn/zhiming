"""One fresh isolated Core pytest invocation; no child test interpreter."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import trace
from datetime import timedelta, timezone
from pathlib import Path
from time import perf_counter

from ....timekit.clock import get_clock
from .line_coverage_core_boundary import Gate, boundaries
from .line_coverage_core_fingerprint import (
    bootstrap_guard,
    loaded_modules,
    runtime_snapshot,
    source_snapshot,
)
from .line_coverage_core_git import MetadataGit
from .line_coverage_core_reports import Witness, line_files, summaries
from .line_coverage_manifest import ROOT, digest
from .line_coverage_own_plan import CANDIDATES, validate_static_plan

USED = False
PHASE = "arguments"
NODES = tuple(node for node, runtime in CANDIDATES.items() if runtime == "core")


def _clock() -> str:
    return get_clock().now().astimezone(timezone(timedelta(hours=8))).isoformat()


def _selected(node: str, mode: str) -> None:
    if node not in NODES or mode not in ("baseline", "trace"):
        raise ValueError("b1_exact_core_node_and_mode_required")
    target = (ROOT / node.split("::")[0]).resolve()
    for module in tuple(sys.modules.values()):
        name = getattr(module, "__file__", None)
        if name and Path(name).resolve() == target:
            raise ValueError("b1_target_module_already_imported")


def _execute(gate: Gate, witness: Witness, node: str, cache: Path) -> int:
    gate.active = True
    try:
        import pytest

        args = [
            "-c",
            str(ROOT / "pytest.ini"),
            "--noconftest",
            "-o",
            "addopts=",
            "--assert=plain",
            "--capture=no",
            "--basetemp",
            str(cache.parent / "pytest-base"),
        ]
        for plugin in (
            "cacheprovider",
            "logging",
            "junitxml",
            "doctest",
            "faulthandler",
            "terminal",
        ):
            args.extend(("-p", "no:" + plugin))
        args.append(node)
        return int(pytest.main(args, plugins=[witness]))
    finally:
        gate.active = False


def _trial(gate: Gate, witness: Witness, node: str, mode: str, cache: Path) -> tuple:
    tracer = trace.Trace(
        count=True,
        trace=False,
        ignoredirs=(
            sys.base_prefix,
            str(ROOT.parent / "zhiming-v4/.venv-core/Lib/site-packages"),
        ),
    )
    begin, code, status = perf_counter(), 1, "completed"
    try:
        with boundaries(gate):
            if mode == "trace":
                code = tracer.runfunc(_execute, gate, witness, node, cache)
            else:
                code = _execute(gate, witness, node, cache)
    except BaseException:
        status = "b1_target_exception_output_discarded"
    finally:
        gate.active = False
        if sys.gettrace() is not None:
            status = "b1_unexpected_trace_remained"
            sys.settrace(None)
        if sys.getprofile() is not None:
            status = "b1_unexpected_profile_remained"
            sys.setprofile(None)
    counts = tracer.results().counts if mode == "trace" else None
    return code, status, perf_counter() - begin, counts


def _snapshot_unchanged(before: dict, after: dict) -> bool:
    return (
        before["files"] == after["files"]
        and before["git_configuration"] == after["git_configuration"]
    )


def _receipt(
    inventory: dict,
    plan: dict,
    node: str,
    mode: str,
    witness: Witness,
    trial: tuple,
    gate: Gate,
    valid: bool,
) -> dict:
    code, status, elapsed, counts = trial
    passed = (
        status == "completed"
        and witness.successful(code)
        and not gate.blocked
        and valid
    )
    files = line_files(inventory, counts)
    return {
        "version": "p8-own-core-line-receipt-v2",
        "runtime": "core",
        "commit": inventory["commit"],
        "inventory_sha256": inventory["inventory_sha256"],
        "static_plan_sha256": plan["plan_sha256"],
        "static_plan_execution_approved": False,
        "mode": mode,
        "node_id": node,
        "status": "completed" if passed else "failed",
        "exit_code": code,
        "coverage_collected": mode == "trace",
        "eligible_for_union": passed and mode == "trace",
        "observation_state": "complete" if passed else "partial_not_eligible",
        "target_seconds": elapsed,
        "trial_status": status,
        "lifecycle": witness.data(),
        "blocked_attempts": dict(gate.blocked),
        "bytecode_probes_not_loaded": gate.skipped_bytecode_probes,
        "files": files,
        "summary": summaries(files, passed and mode == "trace"),
        "not_collected": ["charts", "child_processes", "other_threads", "native_C_JS"],
        "safety": {
            "captured_test_text_retained": False,
            "project_data_read_allowlist": [],
            "target_child_processes_started": 0,
            "python_guard_not_os_sandbox": True,
        },
        "limits": [
            "Import lines count as execution, not calculation assertions or professional accuracy.",
            "Cold/bootstrap/preflight lines stay zero; no synthetic backfill, no branch coverage claim.",
            "Ignored unimported source is not globally scanned; actual reads/imports use the fingerprinted allowlist.",
        ],
    }


def _postflight(
    inventory: dict,
    git: MetadataGit,
    reads: dict,
    source_before: dict,
    runtime_before: dict,
) -> tuple:
    source_after, runtime_after, modules = None, None, None
    try:
        source_after, runtime_after = (
            source_snapshot(inventory, git),
            runtime_snapshot(),
        )
        modules = loaded_modules(reads)
        valid = (
            _snapshot_unchanged(source_before, source_after)
            and runtime_before == runtime_after
        )
        error = None
    except Exception:
        valid, error = False, "b1_postflight_fingerprint_failed"
    return valid, error, source_after, runtime_after, modules


def collect_core(
    inventory: dict, plan: dict, *, node: str, mode: str, commit: str
) -> dict:
    global USED, PHASE
    PHASE = "bootstrap"
    cache = bootstrap_guard()
    if USED:
        raise ValueError("b1_fresh_interpreter_per_invocation_required")
    USED = True
    PHASE = "selection"
    _selected(node, mode)
    if inventory.get("commit") != commit or not re.fullmatch(r"[a-f0-9]{40}", commit):
        raise ValueError("b1_explicit_fixed_commit_required")
    started = _clock()
    gate = Gate(set(), cache)
    git = MetadataGit(ROOT, lambda: gate.active)
    PHASE = "plan_validation"
    with git.installed():
        validate_static_plan(ROOT, inventory, plan)
    if plan["runtime"] != "core" or node not in {
        row["node_id"] for row in plan["entries"]
    }:
        raise ValueError("b1_node_not_in_static_core_plan")
    if sorted(row["node_id"] for row in plan["entries"]) != sorted(NODES):
        raise ValueError("b1_complete_three_node_plan_required")
    PHASE = "preflight_sources"
    source_before = source_snapshot(inventory, git)
    PHASE = "preflight_runtime"
    runtime_before = runtime_snapshot()
    reads = dict(source_before["files"], **runtime_before["files"])
    before_modules = loaded_modules(reads)
    gate.allowed_reads = {os.path.normcase(path) for path in reads}
    witness = Witness(node)
    PHASE = "target"
    trial = _trial(gate, witness, node, mode, cache)
    PHASE = "postflight"
    valid, post_error, source_after, runtime_after, after_modules = _postflight(
        inventory, git, reads, source_before, runtime_before
    )
    PHASE = "receipt"
    result = _receipt(inventory, plan, node, mode, witness, trial, gate, valid)
    result.update(
        started_at_beijing=started,
        completed_at_beijing=_clock(),
        observed_HEAD_before=source_before["observed_HEAD"],
        observed_HEAD_after=source_after["observed_HEAD"] if source_after else None,
        source_before=source_before,
        source_after=source_after,
        runtime_before=runtime_before,
        runtime_after=runtime_after,
        loaded_modules_before=before_modules,
        loaded_modules_after=after_modules,
        postflight_error_code=post_error,
        metadata_git_processes=git.calls,
        git_binary_sha256=git.sha256,
        process_id=os.getpid(),
        actual_launch_xoptions_sha256=digest(dict(sys._xoptions)),
    )
    result["receipt_sha256"] = digest(result)
    return result


def _input(path: Path) -> dict:
    actual = path.resolve()
    if (
        path.is_symlink()
        or path.absolute() != actual
        or not actual.is_relative_to(ROOT / "docs/v4/evidence/P8")
        or actual.suffix != ".json"
        or actual.stat().st_size > 20_000_000
    ):
        raise ValueError("b1_input_artifact_path_refused")
    value = json.loads(actual.read_bytes())
    if not isinstance(value, dict):
        raise ValueError("b1_input_artifact_shape_invalid")
    return value


def _write(path: Path, value: dict) -> None:
    actual = path.resolve()
    if (
        path.is_symlink()
        or path.absolute() != actual
        or not actual.is_relative_to(ROOT / "docs/v4/evidence/P8")
        or actual.suffix != ".json"
    ):
        raise ValueError("b1_output_artifact_path_refused")
    actual.parent.mkdir(parents=True, exist_ok=True)
    with actual.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.exit(2, "b1_arguments_invalid\n")


def main(argv: list[str] | None = None) -> int:
    parser = Parser(description="Explicit fresh Core-only B1 invocation")
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--node", choices=NODES, required=True)
    parser.add_argument("--mode", choices=("baseline", "trace"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = collect_core(
            _input(args.inventory),
            _input(args.plan),
            node=args.node,
            mode=args.mode,
            commit=args.commit,
        )
    except BaseException:
        result = {
            "version": "p8-own-core-line-refusal-v2",
            "status": "invocation_refused",
            "error_code": "b1_fixed_phase_failed_no_test_text_retained",
            "phase": PHASE,
            "attempted_mode": args.mode,
            "coverage_collected": False,
            "eligible_for_union": False,
            "recorded_at_beijing": _clock(),
        }
        result["receipt_sha256"] = digest(result)
    try:
        _write(args.output, result)
    except Exception:
        parser.exit(2, "b1_evidence_write_refused\n")
    print(str(args.output))
    return 0 if result.get("status") == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
