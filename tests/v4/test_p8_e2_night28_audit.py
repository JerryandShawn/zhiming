"""Brain28 audit executes controls on local caches, never inference or charts."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from mingjing_core.adapters.charts.benchmarks import night24_sources, night28_audit
from mingjing_core.adapters.charts.benchmarks.night28_markdown import render_markdown


def write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def mingli_data(questions: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "questions": [
            {
                "id": row["question_id"],
                "case_id": f"PRIVATE_CASE_{index}",
                "question_number": 121 + index,
                "has_answer": True,
                "birth_info": {
                    "year": 1980 + index,
                    "month": 2,
                    "day": 3,
                    "hour": 4,
                    "gender": "male",
                    "calendar_type": "solar",
                },
                **{key: row[key] for key in ("question", "options", "answer")},
            }
            for index, row in enumerate(questions)
        ]
    }


def baziqa_data(questions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"contest_id": "synthetic", "current_year": "2025"}] + [
        {
            "person_id": f"PRIVATE_CASE_{index}",
            "profile": {
                "birth": {"year": 1980 + index, "month": 2, "day": 3, "hour": 4},
                "gender": "male",
            },
            "questions": [row],
        }
        for index, row in enumerate(questions)
    ]


@pytest.fixture
def caches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    monkeypatch.setattr(
        night24_sources.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(stdout="a" * 40 + "\n"),
    )
    ming, bazi = tmp_path / "mingli", tmp_path / "baziqa"
    questions = [
        {
            "question_id": f"PRIVATE_QUESTION_{index}",
            "question": f"请问{2010 + index}年合成事业如何？PRIVATE_TEXT",
            "options": ["A PRIVATE_ONE", "B PRIVATE_TWO", "C THIRD", "D FOURTH"],
            "answer": "B",
        }
        for index in range(2)
    ]
    write(ming / "data/data.json", mingli_data(questions))
    write(bazi / "data/contest8_2025.json", baziqa_data(questions))
    return ming, bazi


def test_audit_rehearses_both_controls_and_preserves_strict_failure(
    caches: tuple[Path, Path],
) -> None:
    report = night28_audit.build_audit(*caches)
    assert report["counts"] == {
        "full_source_questions": 4,
        "subset_source_questions": 4,
        "included_questions": 4,
        "excluded_questions": 0,
    }
    assert report["current_controls"]["status"] == "available"
    assert report["current_controls"]["all_structural_checks_passed"] is True
    assert report["current_controls"]["placebo_inputs_built"] == 4
    assert report["no_chart_control"]["inputs_built"] == 4
    assert report["historical_strict_control"]["status"] == "unavailable"
    assert report["current_workflow"]["executed_by_this_audit"] is True
    assert report["historical_synthetic_workflow"]["executed_by_this_audit"] is False


def test_public_output_has_no_source_prose_ids_answers_or_birth(
    caches: tuple[Path, Path],
) -> None:
    report = night28_audit.build_audit(*caches)
    document = render_markdown(report)
    public = json.dumps(report, ensure_ascii=False) + document
    assert "PRIVATE_" not in public
    assert '"year": 1980' not in public and '"answer":' not in public
    assert "本轮4题" in document
    assert "宽松安慰剂（同源跨案例）" in document and "无盘对照" in document
    assert report["professional_corpus_scores"] is None


def test_audit_cannot_reach_network_or_chart(
    caches: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    import socket

    from mingjing_core.adapters.charts.benchmarks.engine import P8Engine

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("external_or_chart_execution_forbidden")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(P8Engine, "__init__", forbidden)
    report = night28_audit.build_audit(*caches)
    assert report["chart_calculations"] == report["real_model_requests"] == 0
    assert report["server_requests"] == report["new_downloads"] == 0


@pytest.mark.parametrize("arguments", [[], ["--mode", "live"]])
def test_cli_has_no_live_mode(arguments: list[str]) -> None:
    with pytest.raises(SystemExit) as error:
        night28_audit.main(arguments)
    assert error.value.code == 2


def test_cli_writes_redacted_evidence_without_changing_sources(
    caches: tuple[Path, Path], tmp_path: Path
) -> None:
    ming, bazi = caches
    before = {p: p.read_bytes() for root in caches for p in root.rglob("*.json")}
    output = tmp_path / "report/evidence.json"
    assert (
        night28_audit.main(
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
    assert "PRIVATE_" not in output.read_text(encoding="utf-8")
    assert "本轮4题" in output.with_suffix(".md").read_text(encoding="utf-8")
    assert all(path.read_bytes() == content for path, content in before.items())


def test_cli_cannot_overwrite_local_source(caches: tuple[Path, Path]) -> None:
    ming, bazi = caches
    with pytest.raises(SystemExit) as error:
        night28_audit.main(
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


def test_unexpected_control_error_is_redacted(
    caches: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(*args: Any, **kwargs: Any) -> Any:
        raise ValueError("PRIVATE_BIRTH_ERROR")

    monkeypatch.setattr(night28_audit, "rehearse_controls", broken)
    report = night28_audit.build_audit(*caches)
    assert report["current_controls"]["error_code"] == "e2_control_rehearsal_failed"
    assert report["no_chart_control"]["inputs_built"] == 4
    assert "PRIVATE_" not in json.dumps(report)


def test_committed_current_and_historical_controls_are_separate() -> None:
    root = Path(__file__).resolve().parents[2] / "docs/v4/evidence/P8"
    current = json.loads(
        (root / "e2-night28-controls-2026-10-20.json").read_text("utf-8")
    )
    historical = json.loads(
        (root / "e2-night24-audit-2026-10-19.json").read_text("utf-8")
    )
    assert current["counts"] == historical["counts"]
    assert current["counts"]["included_questions"] == 14
    assert current["counts"]["excluded_questions"] == 66
    assert current["historical_strict_control"] == historical["placebo_preflight"]
    assert current["current_controls"]["status"] == "available"
    assert current["current_controls"]["seed"] == 20261020
    assert len(current["current_controls"]["pairs"]) == 14
    assert current["no_chart_control"]["inputs_built"] == 14
    assert current["professional_corpus_scores"] is None
