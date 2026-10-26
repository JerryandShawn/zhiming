"""Night audit uses actual denominators and never publishes local source bodies."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from mingjing_core.adapters.charts.benchmarks import night24_sources
from mingjing_core.adapters.charts.benchmarks.loaders_v2 import load_corpus_v2
from mingjing_core.adapters.charts.benchmarks.night24_audit import build_audit, main
from mingjing_core.adapters.charts.benchmarks.night24_markdown import render_markdown
from mingjing_core.adapters.charts.benchmarks.night24_sources import audit_source
from mingjing_core.adapters.charts.benchmarks.scripted_v2 import DISCLAIMER

SENSITIVE = "synthetic-sensitive-source-id-19881231"
QUESTION = "请问2010年的合成事业测试如何？"
OPTIONS = ["A 合成选项一", "B 合成选项二", "C 合成选项三", "D 合成选项四"]


def item(ident: str, **changes: Any) -> dict[str, Any]:
    return {
        "question_id": ident,
        "question": QUESTION,
        "options": OPTIONS,
        "answer": "B",
    } | changes


def baziqa(year: int, questions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {"contest_id": "synthetic", "current_year": str(year)},
        {
            "person_id": SENSITIVE,
            "profile": {
                "birth": {"year": 1988, "month": 12, "day": 31, "hour": 8},
                "gender": "male",
            },
            "questions": questions,
        },
    ]


def mingli(number: int, ident: str, **changes: Any) -> dict[str, Any]:
    return {
        "id": ident,
        "case_id": ident + "-case",
        "question_number": number,
        "question": QUESTION,
        "options": OPTIONS,
        "answer": "B",
        "has_answer": True,
        "birth_info": {
            "year": 1988,
            "month": 12,
            "day": 31,
            "hour": 8,
            "gender": "male",
            "calendar_type": "solar",
        },
    } | changes


def write(path: Path, value: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return path


@pytest.fixture
def caches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    monkeypatch.setattr(
        night24_sources.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(stdout="a" * 40 + "\n"),
    )
    ming, bazi = tmp_path / "mingli", tmp_path / "baziqa"
    write(ming / "data/data.json", {"questions": [mingli(121, SENSITIVE)]})
    write(bazi / "data/contest8_2025.json", baziqa(2025, [item(SENSITIVE)]))
    return ming, bazi


def test_subset_keeps_outside_years_and_missing_labels_out_of_its_denominator(
    caches: tuple[Path, Path],
) -> None:
    ming, bazi = caches
    write(
        ming / "data/data.json",
        {
            "questions": [
                mingli(81, "outside"),
                mingli(121, "good"),
                mingli(122, "no-year", question="无目标年合成题"),
                mingli(123, "bad-label", options=["A 一", "B 二", "三", "D 四"]),
            ]
        },
    )
    write(
        bazi / "data/contest8_2023.json",
        baziqa(
            2023,
            [
                item(
                    "outside-missing-label",
                    options=["A 一", "B 二", "三", "D 四"],
                )
            ],
        ),
    )
    write(
        bazi / "data/contest8_2025.json",
        baziqa(
            2025,
            [
                item("good"),
                item("bad", options=["A 一", "B 二", "三", "D 四"]),
                item("unresolved", question="1988年出生，未注明预测年份。"),
            ],
        ),
    )
    report = build_audit(ming, bazi)
    assert report["counts"] == {
        "full_source_questions": 8,
        "subset_source_questions": 6,
        "included_questions": 2,
        "excluded_questions": 4,
    }
    assert report["excluded_reasons"] == {
        "missing_or_invalid_option_labels": 2,
        "no_explicit_target_year": 1,
        "explicit_year_target_unresolved": 1,
    }
    assert report["reference_counts_match"] is False
    assert all(row["competition_year"] == 2025 for row in report["included_audit"])
    assert all(row["question_target_year"] == 2010 for row in report["included_audit"])


@pytest.mark.parametrize("collision", ["duplicate_id", "case_birth_conflict"])
def test_global_validation_precedes_2025_subset_and_matches_official_loader(
    caches: tuple[Path, Path],
    collision: str,
) -> None:
    ming, _ = caches
    outside = mingli(81, "outside")
    selected = mingli(121, "selected")
    if collision == "duplicate_id":
        selected["id"] = outside["id"]
        expected = "duplicate_question_identity"
    else:
        selected["case_id"] = outside["case_id"]
        selected["birth_info"]["year"] = 1989
        expected = "inconsistent_birth_for_source_case"
    path = write(ming / "data/data.json", {"questions": [outside, selected]})
    report, records = audit_source(ming, "mingli")
    assert (
        records
        == list(load_corpus_v2(path, "mingli", competition_year=2025).records)
        == []
    )
    assert report["full_source_questions"] == 2
    assert report["subset_source_questions"] == report["subset_excluded_questions"] == 1
    assert report["subset_excluded_reasons"] == {expected: 1}


def test_schema_exclusion_identity_uses_original_full_file_index(
    caches: tuple[Path, Path],
) -> None:
    ming, _ = caches
    path = write(
        ming / "data/data.json",
        {
            "questions": [
                mingli(81, "outside"),
                mingli(121, SENSITIVE, options=["A 一", "B 二", "三", "D 四"]),
            ]
        },
    )
    report, records = audit_source(ming, "mingli")
    assert records == []
    actual = report["files"][0]["excluded_audit"]
    official = [
        row
        for row in load_corpus_v2(path, "mingli").report["excluded_audit"]
        if row["reason"] == "missing_or_invalid_option_labels"
    ]
    assert [row["question_identity_sha256"] for row in actual] == [
        row["question_identity_sha256"] for row in official
    ]


def test_changed_source_recomputes_counts_and_hash_instead_of_returning_14(
    caches: tuple[Path, Path],
) -> None:
    ming, bazi = caches
    before = build_audit(ming, bazi)
    path = write(
        ming / "data/data.json",
        {
            "questions": [
                mingli(121, SENSITIVE),
                mingli(122, "additional"),
            ]
        },
    )
    after = build_audit(ming, bazi)
    assert before["counts"]["included_questions"] == 2
    assert after["counts"]["included_questions"] == 3
    new_file = after["sources"][0]["files"][0]
    assert (
        new_file["source_file_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    )
    assert (
        new_file["source_file_sha256"]
        != before["sources"][0]["files"][0]["source_file_sha256"]
    )


def test_reports_publish_only_hashes_years_and_offsets_not_source_identifiers_or_prose(
    caches: tuple[Path, Path],
) -> None:
    report = build_audit(*caches)
    document = render_markdown(report)
    public = json.dumps(report, ensure_ascii=False) + document
    for forbidden in (SENSITIVE, QUESTION, *OPTIONS, '"year": 1988', '"month": 12'):
        assert forbidden not in public
    assert document.startswith(DISCLAIMER + "\n")
    assert "不是40题样本" in document and "不是本次纳入题数的实测置信区间" in document
    assert report["professional_corpus_scores"] is None
    assert report["professional_corpus_confidence_interval"] is None
    assert report["chart_calculations"] == report["real_model_requests"] == 0
    for row in report["included_audit"]:
        assert row["evidence_spans"] == [[2, 7]]
        assert (
            len(row["question_identity_sha256"])
            == len(row["case_identity_sha256"])
            == 64
        )


def test_source_failures_redact_raw_error_and_path_identifiers(
    caches: tuple[Path, Path],
) -> None:
    ming, _ = caches
    (ming / "data/data.json").write_text("{" + SENSITIVE, encoding="utf-8")
    with pytest.raises(ValueError) as error:
        audit_source(ming, "mingli")
    assert str(error.value) == "e2_local_source_audit_failed"
    assert error.value.__suppress_context__ is True
    assert SENSITIVE not in str(error.value)


@pytest.mark.parametrize("arguments", [[], ["--mode", "live"]])
def test_cli_accepts_only_explicit_scripted_mode(arguments: list[str]) -> None:
    with pytest.raises(SystemExit) as error:
        main(arguments)
    assert error.value.code == 2


def test_cli_writes_both_public_tables_and_preserves_cache_files(
    caches: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    ming, bazi = caches
    before = {p: p.read_bytes() for root in caches for p in root.rglob("*.json")}
    output = tmp_path / "report/evidence.json"
    assert (
        main(
            [
                "--mode",
                "scripted",
                "--mingli-root",
                str(ming),
                "--baziqa-root",
                str(bazi),
                "--output",
                str(output),
            ]
        )
        == 0
    )
    assert output.exists() and output.with_suffix(".md").exists()
    assert all(path.read_bytes() == data for path, data in before.items())
    assert (
        json.loads(output.read_text(encoding="utf-8"))["counts"][
            "subset_source_questions"
        ]
        == 2
    )


def test_cli_rejects_output_inside_a_source_cache(caches: tuple[Path, Path]) -> None:
    ming, bazi = caches
    with pytest.raises(SystemExit) as error:
        main(
            [
                "--mode",
                "scripted",
                "--mingli-root",
                str(ming),
                "--baziqa-root",
                str(bazi),
                "--output",
                str(ming / "data/data.json"),
            ]
        )
    assert error.value.code == 2


def test_metadata_audit_cannot_reach_chart_or_network_paths(
    caches: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import socket

    from mingjing_core.adapters.charts.benchmarks.engine import P8Engine

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("metadata audit reached an external execution path")

    monkeypatch.setattr(P8Engine, "__init__", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    report = build_audit(*caches)
    assert report["chart_calculations"] == report["server_requests"] == 0
    assert report["synthetic_workflow"]["executed_by_this_audit"] is False
    assert report["synthetic_workflow"]["configurations"] == [
        "C0",
        "C1",
        "C2",
        "C3",
        "C4a",
        "C4b",
    ]


def test_committed_hash_only_manifest_keeps_actual_14_and_66_denominators() -> None:
    path = (
        Path(__file__).resolve().parents[2]
        / "docs/v4/evidence/P8/e2-night24-audit-2026-10-19.json"
    )
    report = json.loads(path.read_text(encoding="utf-8"))
    assert report["counts"] == {
        "full_source_questions": 360,
        "subset_source_questions": 80,
        "included_questions": 14,
        "excluded_questions": 66,
    }
    assert len(report["included_audit"]) == 14
    assert (
        len(report["excluded_audit"]) == sum(report["excluded_reasons"].values()) == 66
    )
    assert report["excluded_reasons"] == {
        "no_explicit_target_year": 61,
        "explicit_year_target_unresolved": 5,
    }
    assert report["target_year_equals_competition_year_count"] == 0
    preflight = report["placebo_preflight"]
    assert preflight["actual_call_count"] == 1 and preflight["retries"] == 0
    assert preflight["status"] == "unavailable"
    assert (
        preflight["multi_year_case_count"],
        preflight["group_count"],
        preflight["singleton_group_count"],
    ) == (5, 13, 12)
    assert all(
        len(row["question_identity_sha256"]) == 64
        for row in report["included_audit"] + report["excluded_audit"]
    )
    assert report["real_model_requests"] == report["chart_calculations"] == 0
