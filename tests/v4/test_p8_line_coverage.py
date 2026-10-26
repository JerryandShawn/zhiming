"""Pinned tiny Git fixtures, retained under this worktree's private/tmp only."""

from __future__ import annotations

import io
import subprocess
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

import pytest

from mingjing_core.adapters.charts.benchmarks import line_coverage_run as runner
from mingjing_core.adapters.charts.benchmarks.line_coverage_manifest import (
    METHOD,
    ROOT,
    build_manifest,
    check_worktree,
    digest,
    executable_lines,
    normalized,
    safe_root,
    validate_manifest,
)
from mingjing_core.adapters.charts.benchmarks.line_coverage_merge import (
    merge_reports,
    validate_report,
)


def _git(root: Path, *arguments: str) -> str:
    if not root.resolve().is_relative_to(ROOT / "private/tmp"):
        raise ValueError("coverage_test_repository_outside_private_tmp")
    hooks = root / "empty-hooks"
    hooks.mkdir(exist_ok=True)
    result = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.name=Coverage Synthetic Test",
            "-c",
            "user.email=coverage-synthetic@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "-c",
            "core.hooksPath=" + str(hooks),
            *arguments,
        ],
        capture_output=True,
        check=True,
        timeout=10,
    )
    return result.stdout.decode("utf-8").strip()


def _repository() -> tuple[Path, dict]:
    parent = ROOT / "private/tmp/coverage-unit-fixtures"
    parent.mkdir(parents=True, exist_ok=True)
    root = parent / uuid4().hex
    root.mkdir(exist_ok=False)
    _git(root, "init", "--quiet")
    (root / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "--quiet", "-m", "Synthetic fixture base")
    base = _git(root, "rev-parse", "HEAD")
    package, tests = root / "mingjing_core", root / "tests/v4"
    package.mkdir()
    tests.mkdir(parents=True)
    (package / "a.py").write_bytes(
        b"value = 1\ndef twice(number):\n    return number * 2\n"
    )
    (package / "cold.py").write_bytes(b"def never_imported():\n    return 7\n")
    (tests / "test_p8_fixture.py").write_bytes(
        b"def test_value():\n    assert 1 == 1\n"
    )
    _git(root, "add", ".")
    _git(root, "commit", "--quiet", "-m", "Synthetic fixed sources")
    head = _git(root, "rev-parse", "HEAD")
    return root, build_manifest(root, base, head)


@pytest.fixture(scope="module")
def repository():
    return _repository()


def _receipt(root: Path, manifest: dict, runtime: str = "core", count: int = 1) -> dict:
    source = manifest["files"][0]
    observations = {(str(root / source["path"]), source["executable_lines"][0]): count}
    report = {
        "version": "p8-stdlib-line-report-v1",
        "runtime": runtime,
        "commit": manifest["commit"],
        "manifest_sha256": manifest["manifest_sha256"],
        "scope_is_complete_for_own_code": False,
        "coverage_collected": True,
        "mode": "trace",
        "status": "completed",
        "exit_code": 0,
        "files": runner._line_files(root, manifest, observations),
    }
    report["report_sha256"] = digest(report)
    return report


def _resign(value: dict, field: str) -> None:
    value.pop(field, None)
    value[field] = digest(value)


def test_complete_committed_scope_keeps_cold_files_and_uses_line_tables(repository):
    _, manifest = repository
    validate_manifest(manifest)
    assert manifest["denominator_method"] == METHOD
    assert manifest["scope_is_complete_for_own_code"] is False
    assert len(manifest["files"]) == 3
    cold = next(row for row in manifest["files"] if row["path"].endswith("cold.py"))
    assert cold["executable_lines"] == [1, 2]
    assert all(row["executable_lines"] for row in manifest["files"])
    assert any(row["path"] == "pytest.ini" for row in manifest["execution_guards"])


def test_crlf_worktree_is_accepted_and_raw_hash_still_records_difference(repository):
    root, manifest = repository
    path = root / "mingjing_core/a.py"
    original = path.read_bytes()
    before = check_worktree(root, manifest)
    try:
        path.write_bytes(normalized(original).replace(b"\n", b"\r\n"))
        after = check_worktree(root, manifest)
        assert (
            before["raw_sha256"]["mingjing_core/a.py"]
            != after["raw_sha256"]["mingjing_core/a.py"]
        )
    finally:
        path.write_bytes(original)


def test_changed_denominator_or_pytest_configuration_is_rejected(repository):
    root, manifest = repository
    for relative in ("mingjing_core/a.py", "pytest.ini"):
        path = root / relative
        original = path.read_bytes()
        try:
            path.write_bytes(original + b"# uncommitted change\n")
            with pytest.raises(ValueError, match="source_changed"):
                check_worktree(root, manifest)
        finally:
            path.write_bytes(original)


def test_docs_only_head_can_advance_without_relabeling_observed_commit():
    root, manifest = _repository()
    (root / "notes.md").write_text("Synthetic evidence only.\n", encoding="utf-8")
    _git(root, "add", "notes.md")
    _git(root, "commit", "--quiet", "-m", "Synthetic evidence metadata")
    observed = check_worktree(root, manifest)
    assert observed["observed_HEAD"] != manifest["commit"]
    (root / "mingjing_core/new.py").write_text("value = 4\n", encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "--quiet", "-m", "Synthetic additional source")
    with pytest.raises(ValueError, match="observed_head_source_changed"):
        check_worktree(root, manifest)


@pytest.mark.parametrize("line", [0, -1, None, True])
def test_invalid_denominator_lines_are_refused_even_after_resigning(repository, line):
    root, original = repository
    manifest = deepcopy(original)
    manifest["files"][0]["executable_lines"] = [line]
    _resign(manifest, "manifest_sha256")
    with pytest.raises(ValueError):
        check_worktree(root, manifest)


@pytest.mark.parametrize("mutation", ["duplicate", "omit", "escape", "fake_hash"])
def test_rehashed_manifest_cannot_change_the_pinned_denominator(repository, mutation):
    root, original = repository
    manifest = deepcopy(original)
    if mutation == "duplicate":
        manifest["files"].append(deepcopy(manifest["files"][0]))
    elif mutation == "omit":
        manifest["files"].pop()
    elif mutation == "escape":
        manifest["files"][0]["path"] = "../outside.py"
    else:
        manifest["files"][0]["lf_sha256"] = "0" * 64
    _resign(manifest, "manifest_sha256")
    with pytest.raises(ValueError):
        check_worktree(root, manifest)


def test_empty_observations_still_list_every_file_with_zero_counts(repository):
    root, manifest = repository
    files = runner._line_files(root, manifest, {})
    assert len(files) == len(manifest["files"])
    assert all(count == 0 for row in files for _, count in row["line_counts"])
    assert runner.summaries(files)["selected_scope_total"]["executed_lines"] == 0
    assert (
        runner.summaries(files, collected=False)["selected_scope_total"][
            "executed_lines"
        ]
        is None
    )


def test_synthetic_core_charts_merge_preserves_denominator_and_unions_hits(repository):
    root, manifest = repository
    core, charts = _receipt(root, manifest), _receipt(root, manifest, "charts", 2)
    result = merge_reports(manifest, [core, charts], root=root)
    assert result["runtimes_collected"] == ["charts", "core"]
    assert result["not_collected"] == []
    assert result["files"][0]["line_counts"][0][1] == 3
    assert result["summary"]["selected_scope_total"]["executed_lines"] == 1
    assert result["scope_is_complete_for_own_code"] is False
    core_only = merge_reports(manifest, [core], root=root)
    assert core_only["not_collected"] == ["charts"]


@pytest.mark.parametrize("count", [-1, True, 1.2])
def test_invalid_counts_are_refused_after_resigning(repository, count):
    root, manifest = repository
    report = _receipt(root, manifest)
    report["files"][0]["line_counts"][0][1] = count
    _resign(report, "report_sha256")
    with pytest.raises(ValueError, match="count_invalid"):
        validate_report(manifest, report)


@pytest.mark.parametrize(
    "field,value",
    [
        ("mode", "baseline"),
        ("runtime", "unknown"),
        ("commit", "0" * 40),
        ("coverage_collected", False),
    ],
)
def test_noncomparable_reports_cannot_be_merged(repository, field, value):
    root, manifest = repository
    report = _receipt(root, manifest)
    report[field] = value
    _resign(report, "report_sha256")
    with pytest.raises(ValueError):
        merge_reports(manifest, [report], root=root)


def test_duplicate_receipt_and_missing_file_are_rejected(repository):
    root, manifest = repository
    report = _receipt(root, manifest)
    with pytest.raises(ValueError, match="duplicate_report"):
        merge_reports(manifest, [report, report], root=root)
    report["files"].pop()
    _resign(report, "report_sha256")
    with pytest.raises(ValueError, match="file_inventory_mismatch"):
        validate_report(manifest, report)


@pytest.mark.parametrize(
    "node",
    [
        "tests/v4",
        "tests",
        "tests/v4/test_p8_bazi_rules.py",
        "private/secret.py::test_run",
        "-k any",
        "SECRET_BODY",
    ],
)
def test_only_exact_safe_nodes_can_be_selected(node):
    with pytest.raises(ValueError, match="node_not_allowlisted"):
        runner.validate_node(node)


def test_discard_sink_retains_no_text_and_parser_errors_redact_input(capsys):
    sink = runner.Discard()
    assert sink.write("SYNTHETIC_PRIVATE_BIRTH_TEXT") == 28
    assert not isinstance(sink, io.StringIO)
    with pytest.raises(SystemExit):
        runner.main(["--mode", "SECRET_BODY", "--output", "x"])
    assert "SECRET_BODY" not in capsys.readouterr().err


def test_fresh_temporary_directory_is_new_and_inside_this_worktree():
    first, second = runner._fresh_temporary(ROOT), runner._fresh_temporary(ROOT)
    assert first != second and first.is_dir() and second.is_dir()
    assert first.is_relative_to(ROOT / "private/tmp")
    assert not (first / "pytest-base").exists()


def test_existing_trace_and_non_core_execution_are_refused(repository, monkeypatch):
    _, manifest = repository
    monkeypatch.setattr(runner, "CORE_PYTHON", Path(runner.sys.executable).resolve())
    monkeypatch.setattr(runner.sys, "gettrace", lambda: object())
    with pytest.raises(ValueError, match="existing_trace_refused"):
        runner.collect(manifest, runner.NODES[0])
    monkeypatch.setattr(runner.sys, "executable", "not-the-core-interpreter")
    with pytest.raises(ValueError, match="core_interpreter_required"):
        runner.collect(manifest, runner.NODES[0])


def test_source_denominator_has_nested_code_but_no_zero_or_blank_lines():
    lines = executable_lines(
        b"# comment\n\ndef outside():\n    def inside():\n        return 3\n    return inside()\n",
        "synthetic.py",
    )
    assert 3 in lines and 4 in lines and 5 in lines and 6 in lines
    assert 0 not in lines and 1 not in lines and 2 not in lines


def test_fake_repository_root_is_rejected():
    with pytest.raises(ValueError, match="outside_workspace"):
        safe_root(ROOT.parent)


def test_raw_blobs_ignore_autocrlf_and_export_subst_archive_transformations():
    root, original = _repository()
    (root / ".gitattributes").write_text(
        "mingjing_core/a.py export-subst\n", encoding="utf-8"
    )
    (root / "mingjing_core/a.py").write_text(
        'value = "$Format:%H$"\n', encoding="utf-8"
    )
    _git(root, "add", ".")
    _git(root, "commit", "--quiet", "-m", "Synthetic archive expansion")
    head = _git(root, "rev-parse", "HEAD")
    manifest = build_manifest(root, original["base_commit"], head)
    source = next(
        row for row in manifest["files"] if row["path"] == "mingjing_core/a.py"
    )
    assert source["git_blob_id"] == _git(
        root, "rev-parse", head + ":mingjing_core/a.py"
    )
    assert source["executable_lines"] == [1]
    assert check_worktree(root, manifest)["observed_HEAD"] == head


def test_same_resolved_filename_counts_are_added_without_double_counting_lines(
    repository,
):
    root, manifest = repository
    source = manifest["files"][0]
    line = source["executable_lines"][0]
    path = root / source["path"]
    alternative = str(path.parent) + "/./" + path.name
    files = runner._line_files(
        root, manifest, {(str(path), line): 1, (alternative, line): 2}
    )
    assert files[0]["line_counts"][0] == [line, 3]
    assert runner.summaries(files)["selected_scope_total"]["executed_lines"] == 1


def test_merge_keeps_actual_runtime_line_counts_in_separate_tables(repository):
    root, manifest = repository
    result = merge_reports(
        manifest,
        [_receipt(root, manifest), _receipt(root, manifest, "charts", 2)],
        root=root,
    )
    assert result["per_runtime"]["core"]["files"][0]["line_counts"][0][1] == 1
    assert result["per_runtime"]["charts"]["files"][0]["line_counts"][0][1] == 2


def test_evidence_output_is_exclusive_and_never_overwrites_an_observation(
    repository, monkeypatch
):
    root, _ = repository
    monkeypatch.setattr(runner, "ROOT", root)
    target = root / "docs/v4/evidence/P8/synthetic-counts.json"
    runner._write(target, {"line_counts": [[1, 2]]})
    before = target.read_bytes()
    with pytest.raises(FileExistsError):
        runner._write(target, {"line_counts": [[1, 9]]})
    assert target.read_bytes() == before


def test_failed_trial_discards_private_output_and_exception_text(monkeypatch, capsys):
    def failure(*args):
        print("SYNTHETIC_PRIVATE_OUTPUT")
        raise RuntimeError("SYNTHETIC_PRIVATE_EXCEPTION")

    monkeypatch.setattr(runner, "_execute", failure)
    code, _, _, status = runner._trial(ROOT, runner.NODES[0], True)
    assert code == 1 and status == "entrypoint_failed_output_discarded"
    assert "SYNTHETIC_PRIVATE" not in capsys.readouterr().out
