"""Merge only identical pinned line denominators, with runtime provenance intact."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from .line_coverage_manifest import ROOT, build_manifest, digest, validate_manifest
from .line_coverage_run import summaries


def validate_report(manifest: dict, report: dict) -> None:
    validate_manifest(manifest)
    payload = {key: value for key, value in report.items() if key != "report_sha256"}
    if report.get("report_sha256") != digest(payload):
        raise ValueError("coverage_report_integrity_invalid")
    if report.get("manifest_sha256") != manifest["manifest_sha256"]:
        raise ValueError("coverage_report_manifest_mismatch")
    if report.get("commit") != manifest["commit"]:
        raise ValueError("coverage_report_commit_mismatch")
    if report.get("runtime") not in ("core", "charts"):
        raise ValueError("coverage_report_runtime_invalid")
    if report.get("coverage_collected") is not True or report.get("mode") != "trace":
        raise ValueError("coverage_report_not_traced")
    if (
        report.get("status") != "completed"
        or type(report.get("exit_code")) is not int
        or report["exit_code"] != 0
        or report.get("scope_is_complete_for_own_code") is not False
    ):
        raise ValueError("coverage_report_incomplete")
    expected = {row["path"]: row for row in manifest["files"]}
    rows = report.get("files", [])
    if len(rows) != len(expected) or len({row["path"] for row in rows}) != len(rows):
        raise ValueError("coverage_report_file_inventory_mismatch")
    for row in rows:
        source = expected.get(row["path"])
        if source is None or any(
            row.get(key) != source[key]
            for key in ("lf_sha256", "group", "executable_lines")
        ):
            raise ValueError("coverage_report_denominator_mismatch")
        pairs = row.get("line_counts", [])
        if not isinstance(pairs, list) or any(
            not isinstance(pair, list)
            or len(pair) != 2
            or type(pair[0]) is not int
            or type(pair[1]) is not int
            or pair[1] < 0
            for pair in pairs
        ):
            raise ValueError("coverage_report_count_invalid")
        if [pair[0] for pair in pairs] != source["executable_lines"]:
            raise ValueError("coverage_report_line_inventory_mismatch")


def _sum_files(reports: list[dict]) -> list[dict]:
    files = deepcopy(reports[0]["files"])
    merged = {row["path"]: row for row in files}
    for row in files:
        row["line_counts"] = [[line, 0] for line in row["executable_lines"]]
    for report in reports:
        for row in report["files"]:
            target = merged[row["path"]]["line_counts"]
            for index, (_, count) in enumerate(row["line_counts"]):
                target[index][1] += count
    return files


def _runtime_tables(reports: list[dict]) -> dict:
    result = {}
    for runtime in sorted({row["runtime"] for row in reports}):
        selected = [row for row in reports if row["runtime"] == runtime]
        files = _sum_files(selected)
        result[runtime] = {
            "source_report_sha256": [row["report_sha256"] for row in selected],
            "files": files,
            "summary": summaries(files),
        }
    return result


def merge_reports(manifest: dict, reports: list[dict], *, root: Path = ROOT) -> dict:
    if not reports:
        raise ValueError("coverage_no_reports")
    if len({report.get("report_sha256") for report in reports}) != len(reports):
        raise ValueError("coverage_duplicate_report")
    rebuilt = build_manifest(
        root, manifest["base_commit"], manifest["commit"], tuple(manifest["scopes"])
    )
    if manifest != rebuilt:
        raise ValueError("coverage_manifest_pinned_source_mismatch")
    for report in reports:
        validate_report(manifest, report)
    files, tables = _sum_files(reports), _runtime_tables(reports)
    runtimes = sorted(tables)
    result = {
        "version": "p8-stdlib-line-union-v1",
        "commit": manifest["commit"],
        "manifest_sha256": manifest["manifest_sha256"],
        "runtimes_collected": runtimes,
        "scope_is_complete_for_own_code": False,
        "source_report_sha256": [row["report_sha256"] for row in reports],
        "files": files,
        "summary": summaries(files),
        "per_runtime": tables,
        "not_collected": [
            runtime for runtime in ("core", "charts") if runtime not in runtimes
        ],
        "limits": [
            "Per-line sum and execution union only; not branch coverage or isolation-chain tracing.",
            "This selected fixed commit excludes uncommitted tools and is not all-current-code coverage.",
            "Receipt hashes bind content integrity, not a signature or independent proof that a run occurred.",
        ],
    }
    result["union_sha256"] = digest(result)
    return result
