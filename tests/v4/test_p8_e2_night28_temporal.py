"""Fixed-donor chronology is reported without redrawing or leaking birthdays."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from mingjing_core.adapters.charts.benchmarks.night28_controls import (
    SEED,
    same_source_placebo,
)
from mingjing_core.adapters.charts.benchmarks.night28_temporal_preflight import (
    main,
    temporal_order,
    temporal_preflight,
)
from mingjing_core.adapters.charts.benchmarks.records import (
    BirthMetadata,
    Question,
    fingerprint,
)


def birth(**changes: Any) -> BirthMetadata:
    return replace(
        BirthMetadata(1980, 2, 3, 4, 5, "男", "PRIVATE_LOCATION", "solar"), **changes
    )


@pytest.mark.parametrize(
    ("given", "year", "expected"),
    [
        ({"year": 2000}, 1999, "birth_definitely_after_annual_snapshot"),
        ({"year": 1980}, 1999, "birth_definitely_not_after_annual_snapshot"),
        ({"year": 2000, "month": 8}, 2000, "birth_definitely_after_annual_snapshot"),
        (
            {"year": 2000, "month": 6},
            2000,
            "birth_definitely_not_after_annual_snapshot",
        ),
        (
            {"year": 2000, "month": 7, "day": 1},
            2000,
            "verified_timezone_required_to_order_instants",
        ),
        ({"calendar": "lunar"}, 2000, "birth_calendar_not_explicit_solar"),
        ({"year": None}, 2000, "birth_fields_incomplete"),
        ({"year": 2000, "minute": None}, 2000, "birth_fields_incomplete"),
    ],
)
def test_chronology_uses_only_explicit_calendar_and_offset_bounds(
    given: dict[str, Any], year: int, expected: str
) -> None:
    assert temporal_order(birth(**given), year) == expected


@pytest.mark.parametrize("year", [True, "2025", None, 1599, 2200])
def test_unresolved_target_year_is_not_replaced_by_today(year: Any) -> None:
    with pytest.raises(ValueError, match="target_year_invalid"):
        temporal_order(birth(), year)


def test_case_keeps_seed_birth_assignment_and_eligibility_while_flagging_conflict() -> (
    None
):
    rows = [
        Question(
            id=f"PRIVATE_ID_{index}",
            case_id=f"PRIVATE_CASE_{index}",
            text=f"请问{year}年会有什么合成事件？PRIVATE_TEXT",
            options=tuple((letter, "PRIVATE_OPTION_" + letter) for letter in "ABCD"),
            answer="A",
            birth=birth(year=birth_year),
            source="synthetic",
            competition_year=2025,
        )
        for index, (year, birth_year) in enumerate(((1990, 1980), (2024, 2000)))
    ]
    assignment = same_source_placebo(rows, SEED)
    report = temporal_preflight(rows, SEED)
    assert same_source_placebo(rows, SEED) == assignment
    assert report["questions"] == len(rows) == 2
    assert report["donor_birth_year_after_target_year_count"] == 1
    assert report["donor_temporal_order_counts"] == {
        "birth_definitely_after_annual_snapshot": 1,
        "birth_definitely_not_after_annual_snapshot": 1,
    }
    assert report["original_temporal_order_counts"] == {
        "birth_definitely_not_after_annual_snapshot": 2,
    }
    assert report["matching_changed"] is report["seed_changed"] is False
    assert (
        report["retries"]
        == report["chart_calculations"]
        == report["real_model_requests"]
        == 0
    )
    assert report["chart_preflight_executed"] is False
    assert report["complete_chart_calculability_established"] is False
    public = json.dumps(report, ensure_ascii=False)
    assert "PRIVATE_" not in public
    assert '"birth"' not in public and '"answer"' not in public
    assert all(fingerprint(row.birth.public_input()) not in public for row in rows)


def test_committed_preflight_retains_all_fourteen_and_two_temporal_blockers() -> None:
    path = Path(__file__).resolve().parents[2] / "docs/v4/evidence/P8"
    report = json.loads(
        (path / "e2-night28-temporal-preflight-2026-10-20.json").read_text("utf8")
    )
    original = json.loads(
        (path / "e2-night28-controls-2026-10-20.json").read_text("utf8")
    )
    assert report["questions"] == len(report["pair_audit"]) == 14
    assert report["donor_birth_year_after_target_year_count"] == 2
    assert (
        original["temporal_calculability"]["pair_assignment_sha256"]
        == report["pair_assignment_sha256"]
    )
    assert (
        original["current_controls"]["status_scope"]
        == "input_structure_only_not_chart_calculability"
    )
    assert original["counts"]["included_questions"] == 14
    assert original["professional_corpus_scores"] is None
    assert original["current_controls"]["seed"] == report["seed"] == 20261020


@pytest.mark.parametrize("arguments", [[], ["--mode", "live"]])
def test_preflight_cli_does_not_offer_live_execution(arguments: list[str]) -> None:
    with pytest.raises(SystemExit) as error:
        main(arguments)
    assert error.value.code == 2
