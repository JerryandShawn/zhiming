"""Core-only fixed-node trace trial; captured test text is discarded."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import trace
from datetime import timedelta, timezone
from pathlib import Path
from time import perf_counter
from unittest.mock import patch
from uuid import uuid4

from ....timekit.clock import get_clock
from .handoff_offline import denied, offline_runtime
from .line_coverage_manifest import ROOT, build_manifest, check_worktree, digest

CORE_PYTHON = ROOT.parent / "zhiming-v4/.venv-core/Scripts/python.exe"
NODES = (
    "tests/v4/test_p8_e2_night28_controls.py::test_matching_is_reproducible_and_independent_of_input_order",
    "tests/v4/test_p8_e2_night28_controls.py::test_no_chart_only_has_original_question_and_permuted_options",
    "tests/v4/test_p8_e2_night28_controls.py::test_empty_batch_is_available_without_a_fabricated_score",
)


class Discard(io.TextIOBase):
    """No retained output buffer, even when pytest displays private assertion data."""

    def write(self, value: str) -> int:
        return len(value)


def validate_node(node: str) -> None:
    if node not in NODES:
        raise ValueError("coverage_node_not_allowlisted")


def _execute(root: Path, node: str, temporary: Path) -> int:
    import pytest

    arguments = [
        "-c",
        str(root / "pytest.ini"),
        "--noconftest",
        "-o",
        "addopts=",
        "-p",
        "no:cacheprovider",
        "--assert=plain",
        "--tb=no",
        "-q",
        "--basetemp",
        str(temporary / "pytest-base"),
        node,
    ]
    return int(pytest.main(arguments))


def _line_files(root: Path, manifest: dict, counts: dict) -> list[dict]:
    normalized_counts = {}
    for (filename, line), count in counts.items():
        if type(line) is int and line > 0 and type(count) is int and count >= 0:
            key = (os.path.normcase(str(Path(filename).resolve())), line)
            normalized_counts[key] = normalized_counts.get(key, 0) + count
    result = []
    for source in manifest["files"]:
        name = os.path.normcase(str((root / source["path"]).resolve()))
        result.append(
            {
                "path": source["path"],
                "lf_sha256": source["lf_sha256"],
                "group": source["group"],
                "executable_lines": source["executable_lines"],
                "line_counts": [
                    [line, normalized_counts.get((name, line), 0)]
                    for line in source["executable_lines"]
                ],
            }
        )
    return result


def summaries(files: list[dict], *, collected: bool = True) -> dict:
    result = {}
    for group in ("runtime", "research", "tests", "selected_scope_total"):
        rows = (
            files
            if group == "selected_scope_total"
            else [row for row in files if row["group"] == group]
        )
        denominator = sum(len(row["executable_lines"]) for row in rows)
        covered = sum(count > 0 for row in rows for _, count in row["line_counts"])
        result[group] = {
            "files": len(rows),
            "denominator_lines": denominator,
            "executed_lines": covered if collected else None,
            "line_execution_fraction": covered / denominator
            if collected and denominator
            else None,
        }
    return result


def _trial(root: Path, node: str, traced: bool) -> tuple[int, float, dict, str]:
    temporary = _fresh_temporary(root)
    tracer = trace.Trace(
        count=True, trace=False, ignoredirs=(sys.prefix, sys.base_prefix)
    )
    status, code = "completed", 1
    begin = perf_counter()
    try:
        with (
            offline_runtime(),
            patch.object(subprocess, "run", denied),
            patch.object(subprocess, "Popen", denied),
            patch.dict(
                os.environ,
                PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
                PYTEST_ADDOPTS="",
                TEMP=str(temporary),
                TMP=str(temporary),
                TMPDIR=str(temporary),
            ),
            patch.object(tempfile, "tempdir", str(temporary)),
            patch.object(sys, "dont_write_bytecode", True),
            contextlib.redirect_stdout(Discard()),
            contextlib.redirect_stderr(Discard()),
        ):
            code = (
                tracer.runfunc(_execute, root, node, temporary)
                if traced
                else _execute(root, node, temporary)
            )
    except (Exception, SystemExit):
        status = "entrypoint_failed_output_discarded"
    finally:
        sys.settrace(None)
    return (
        code,
        perf_counter() - begin,
        tracer.results().counts if traced else {},
        status,
    )


def _fresh_temporary(root: Path) -> Path:
    parent = (root / "private/tmp/line-coverage-trials").resolve()
    if not parent.is_relative_to(root.resolve()):
        raise ValueError("coverage_temporary_path_invalid")
    parent.mkdir(parents=True, exist_ok=True)
    target = parent / uuid4().hex
    if target.exists() or (target / "pytest-base").exists():
        raise ValueError("coverage_temporary_path_exists")
    target.mkdir(exist_ok=False)
    return target


def _runtime_guard(manifest: dict, node: str, traced: bool) -> None:
    validate_node(node)
    if not isinstance(traced, bool):
        raise ValueError("coverage_mode_invalid")
    if Path(sys.executable).resolve() != CORE_PYTHON.resolve():
        raise ValueError("coverage_core_interpreter_required")
    if sys.gettrace() is not None:
        raise ValueError("coverage_existing_trace_refused")
    if Path.cwd().resolve() != ROOT:
        raise ValueError("coverage_workspace_cwd_required")
    if node.split("::", 1)[0] not in {
        row["path"] for row in manifest["execution_guards"]
    }:
        raise ValueError("coverage_entrypoint_not_pinned")


def _report(manifest: dict, node: str, traced: bool, trial: tuple, files: list) -> dict:
    code, elapsed, _, status = trial
    return {
        "version": "p8-stdlib-line-report-v1",
        "runtime": "core",
        "commit": manifest["commit"],
        "manifest_sha256": manifest["manifest_sha256"],
        "scope_is_complete_for_own_code": False,
        "coverage_collected": traced,
        "mode": "trace" if traced else "baseline",
        "entrypoint": node,
        "status": status,
        "exit_code": code,
        "observed_seconds": elapsed,
        "python_executable": str(Path(sys.executable).resolve()),
        "python_version": list(sys.version_info[:3]),
        "files": files,
        "summary": summaries(files, collected=traced),
        "not_collected": [
            "charts",
            "child_processes",
            "other_threads",
            "native_C_JS",
            "uncommitted_tools",
            "uncommitted_code",
        ],
        "safety": {
            "network_calls": 0,
            "model_calls": 0,
            "child_processes": 0,
            "captured_output_retained": False,
            "pytest_conftest_loaded": False,
        },
        "limits": [
            "Line executions within this fixed node invocation, not branch or assertion coverage.",
            "Initialization before tracing is excluded; no total-own-code or 90-percent claim.",
            "Traced elapsed time includes pytest/instrumentation and is not product performance.",
        ],
    }


def _instrumentation() -> list[dict]:
    result = []
    for name in ("manifest", "run", "merge"):
        path = Path(__file__).with_name("line_coverage_" + name + ".py")
        raw = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        result.append(
            {
                "path": path.relative_to(ROOT).as_posix(),
                "lf_sha256": hashlib.sha256(raw).hexdigest(),
            }
        )
    return result


def collect(manifest: dict, node: str, *, traced: bool = True) -> dict:
    _runtime_guard(manifest, node, traced)
    before = check_worktree(ROOT, manifest)
    instrumentation = _instrumentation()
    started = get_clock().now().astimezone(timezone(timedelta(hours=8))).isoformat()
    trial = _trial(ROOT, node, traced)
    after = check_worktree(ROOT, manifest)
    if instrumentation != _instrumentation():
        raise ValueError("coverage_instrumentation_changed")
    files = _line_files(ROOT, manifest, trial[2])
    result = _report(manifest, node, traced, trial, files)
    result["uncommitted_instrumentation_sources"] = instrumentation
    result.update(
        worktree_raw_sha256_before=before["raw_sha256"],
        worktree_raw_sha256_after=after["raw_sha256"],
        observed_HEAD_before=before["observed_HEAD"],
        observed_HEAD_after=after["observed_HEAD"],
        started_at_beijing=started,
        completed_at_beijing=get_clock()
        .now()
        .astimezone(timezone(timedelta(hours=8)))
        .isoformat(),
    )
    result["report_sha256"] = digest(result)
    return result


def _write(path: Path, value: dict) -> None:
    target = path.resolve()
    if (
        not target.is_relative_to(ROOT / "docs/v4/evidence/P8")
        or target.suffix != ".json"
    ):
        raise ValueError("coverage_output_path_invalid")
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.exit(2, "coverage_arguments_invalid\n")


def main(argv: list[str] | None = None) -> int:
    parser = Parser(description="Pinned offline Core line-execution trial")
    parser.add_argument(
        "--mode", choices=("manifest", "baseline", "trace"), required=True
    )
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--node", choices=NODES, default=NODES[0])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.mode == "manifest":
            result = build_manifest(ROOT)
        else:
            if args.manifest is None:
                raise ValueError("coverage_manifest_required")
            result = collect(
                json.loads(args.manifest.read_bytes()),
                args.node,
                traced=args.mode == "trace",
            )
        _write(args.output, result)
    except (Exception, SystemExit):
        parser.exit(2, "coverage_trial_refused_or_failed\n")
    print(str(args.output))
    return 0 if result.get("exit_code", 0) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
