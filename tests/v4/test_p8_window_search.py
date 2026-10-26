"""Synthetic scoring contracts; native daily integration has separate evidence."""

from __future__ import annotations

import copy
from datetime import date

import pytest

from mingjing_core.adapters.charts.tool_evidence import (
    content_hash,
    evidence_result,
    pointer,
)
from mingjing_core.adapters.charts.window_search import (
    _days,
    _score_results,
    _weights,
    window_search,
)
from mingjing_core.adapters.charts.window_search_scoring import weight_of

NATAL = {
    "owner_user_id": "synthetic-owner-ayuan",
    "subject_id": "synthetic-ayuan",
    "revision": 1,
    "operation_id": "synthetic-window",
}


def daily(day: str, contexts: list[dict], *, scope: dict | None = None) -> dict:
    data = {"date": day, "conditions": copy.deepcopy(contexts)}
    hits = [
        {
            "rule_id": f"synthetic.actual.{index}",
            "met": True,
            "school": "synthetic-fact-only",
            "source": "synthetic-test",
            "context": context,
            "evidence_paths": [f"/data/conditions/{index}"],
        }
        for index, context in enumerate(contexts)
    ]
    return evidence_result(
        "synthetic-daily-test-only", data, hits, ["synthetic-test"], scope or NATAL
    )


def context(system: str, kind: str, **values: object) -> dict:
    return {"system": system, "kind": kind, **values}


@pytest.mark.parametrize("purpose", ["签约", "面试", "搬家", "出行", "表白", "开业"])
def test_every_purpose_has_real_signed_and_neutral_rules_with_recomputable_score(
    purpose: str,
) -> None:
    contexts = [
        context(
            "bazi", "relation", relation="六合", complete=True, target_layers=["daily"]
        ),
        context(
            "bazi",
            "relation",
            relation="六冲",
            complete=True,
            target_layers=["yearly", "monthly"],
        ),
        context("astro", "aspect", aspect="合相"),
    ]
    source = daily("2026-10-21", contexts)
    before = copy.deepcopy(source)
    result = _score_results(NATAL, ["2026-10-21"], purpose, [source])
    row = result["data"]["candidates"][0]
    assert row["positive_hits"] and row["negative_hits"] and row["neutral_hits"]
    assert row["score"] == sum(hit["contribution"] for hit in result["rule_hits"])
    assert source == before
    assert result["effects"]["model_calls"] == result["effects"]["writes"] == 0
    assert result["data"]["method"]["election_hours_searched"] is False


def test_score_order_and_date_tie_are_stable_without_removing_negative_days() -> None:
    days = ["2026-10-21", "2026-10-22", "2026-10-23"]
    negative = context("ziwei", "mutagen", mutagen="忌", layer="daily")
    positive = context("astro", "aspect", aspect="拱相")
    rows = [
        daily(days[0], [negative]),
        daily(days[1], [positive]),
        daily(days[2], [positive]),
    ]
    result = _score_results(NATAL, days, "签约", rows)
    ordered = result["data"]["candidates"]
    assert [row["date"] for row in ordered] == [days[1], days[2], days[0]]
    assert [row["rank"] for row in ordered] == [1, 2, 3]
    assert ordered[-1]["score"] < 0
    assert result == _score_results(NATAL, days, "签约", rows)


def test_incomplete_relation_gets_zero_and_no_unearned_positive_hit() -> None:
    source = daily(
        "2026-10-21",
        [
            context(
                "bazi",
                "relation",
                relation="三合",
                complete=False,
                target_layers=["daily"],
            )
        ],
    )
    result = _score_results(NATAL, ["2026-10-21"], "表白", [source])
    row = result["data"]["candidates"][0]
    assert row["score"] == 0
    assert row["positive_hits"] == row["negative_hits"] == []
    assert (
        result["rule_hits"][0]["context"]["reason"] == "incomplete_relation_zero_weight"
    )


def test_every_alias_resolves_to_actual_copied_facts_and_published_weights() -> None:
    source = daily(
        "2026-10-21", [context("bazi", "ten_god", ten_god="正官", layer="monthly")]
    )
    result = _score_results(NATAL, ["2026-10-21"], "面试", [source])
    for kind in ("c", "r"):
        for alias in result["aliases"][kind]:
            assert content_hash(pointer(result, alias["path"])) == alias["value_sha256"]
    observed = result["data"]["observations"][0]
    assert observed["kind"].startswith("derived_copy")
    assert observed["daily_document_id"] == source["document_id"]
    assert observed["facts"][0]["value"] == source["data"]["conditions"][0]
    assert observed["facts_sha256"] == content_hash(observed["facts"])
    index = result["data"]["candidates"][0]["positive_hits"][0]["rule_hit_index"]
    assert result["aliases"]["r"][index]["alias"] == "r1"


@pytest.mark.parametrize(
    "invalid",
    [
        None,
        {},
        [],
        {"start_date": "2026-10-21"},
        {"start_date": "2026-10-22", "end_date": "2026-10-21"},
    ],
)
def test_invalid_range_is_rejected_before_calculation(invalid: object) -> None:
    with pytest.raises(ValueError, match="window_range_invalid"):
        _days(invalid)


@pytest.mark.parametrize(
    "invalid",
    [
        "2026-02-29",
        "20261021",
        "2026-W43-3",
        "2026-10-21T00:00:00",
        True,
        "1900-12-31",
        "2100-01-01",
    ],
)
def test_dates_are_explicit_supported_civil_dates(invalid: object) -> None:
    with pytest.raises(ValueError, match="window_date_invalid"):
        _days({"start_date": invalid, "end_date": "2026-12-31"})


def test_one_day_and_366_day_ranges_are_inclusive_and_367_is_rejected() -> None:
    assert _days({"start_date": "2026-10-21", "end_date": "2026-10-21"}) == [
        "2026-10-21"
    ]
    days = _days({"start_date": "2028-01-01", "end_date": "2028-12-31"})
    assert len(days) == 366 and "2028-02-29" in days
    assert date.fromisoformat(days[-1]).year == 2028
    with pytest.raises(ValueError, match="window_range_too_large"):
        _days({"start_date": "2028-01-01", "end_date": "2029-01-01"})


@pytest.mark.parametrize("purpose", ["投资稳赢", "签約", "", None, {}, True])
def test_unknown_purpose_does_not_start_daily_preparation(purpose: object) -> None:
    with pytest.raises(ValueError, match="window_purpose_invalid"):
        window_search({}, {}, purpose)


@pytest.mark.parametrize(
    "key,value",
    [
        ("owner_user_id", "other"),
        ("subject_id", "other"),
        ("revision", 2),
        ("operation_id", "other"),
    ],
)
def test_foreign_daily_scope_is_rejected(key: str, value: object) -> None:
    source = daily("2026-10-21", [], scope={**NATAL, key: value})
    with pytest.raises(ValueError, match="window_daily_scope_mismatch"):
        _score_results(NATAL, ["2026-10-21"], "签约", [source])


def test_stale_day_and_tampered_source_are_rejected() -> None:
    with pytest.raises(ValueError, match="window_daily_date_mismatch"):
        _score_results(NATAL, ["2026-10-21"], "签约", [daily("2026-10-22", [])])
    source = daily("2026-10-21", [])
    source["data"]["injected"] = True
    with pytest.raises(ValueError, match="window_daily_evidence_invalid"):
        _score_results(NATAL, ["2026-10-21"], "签约", [source])


def test_no_silent_missing_days_or_unrecognized_scoring() -> None:
    with pytest.raises(ValueError):
        _score_results(
            NATAL, ["2026-10-21", "2026-10-22"], "签约", [daily("2026-10-21", [])]
        )
    source = daily("2026-10-21", [context("unknown", "unknown")])
    result = _score_results(NATAL, ["2026-10-21"], "签约", [source])
    assert result["rule_hits"] == []
    assert result["data"]["candidates"][0]["score"] == 0
    assert (
        result["data"]["ignored_conditions"][0]["reason"]
        == "unsupported_daily_condition"
    )


@pytest.mark.parametrize(
    "layer,expected", [("yearly", 2), ("monthly", 4), ("daily", 6)]
)
def test_year_month_day_factors_are_explicit(layer: str, expected: int) -> None:
    value = context("ziwei", "mutagen", mutagen="禄", layer=layer)
    weighted = weight_of(value, _weights(), "开业")
    assert weighted["contribution"] == expected


@pytest.mark.parametrize("offset", [-1, True, False, 0.5, "1", None])
def test_offset_requires_nonnegative_integer_before_calculation(offset: object) -> None:
    with pytest.raises(ValueError, match="window_offset_invalid"):
        window_search(
            NATAL,
            {"start_date": "2026-10-21", "end_date": "2026-10-21"},
            "签约",
            offset=offset,
        )


@pytest.mark.parametrize("limit", [0, -1, 32, True, False, 1.5, "1", None])
def test_limit_is_explicitly_bounded_before_calculation(limit: object) -> None:
    with pytest.raises(ValueError, match="window_limit_invalid"):
        window_search(
            NATAL,
            {"start_date": "2026-10-21", "end_date": "2026-10-21"},
            "签约",
            limit=limit,
        )


def test_pages_reassemble_full_ranking_and_rebind_local_evidence() -> None:
    days = _days({"start_date": "2026-10-21", "end_date": "2026-10-27"})
    rows = [
        daily(day, [context("bazi", "ten_god", ten_god="正官", layer="daily")])
        for day in days
    ]
    full = _score_results(NATAL, days, "签约", rows)
    combined = []
    for offset in (0, 2, 4, 6):
        page = _score_results(NATAL, days, "签约", rows, offset=offset, limit=2)
        assert page == _score_results(NATAL, days, "签约", rows, offset=offset, limit=2)
        assert page["data"]["ranking_summary"] == full["data"]["ranking_summary"]
        assert (
            page["data"]["trace"]["query_sha256"]
            == full["data"]["trace"]["query_sha256"]
        )
        for candidate in page["data"]["candidates"]:
            combined.append((candidate["date"], candidate["rank"], candidate["score"]))
        for alias in page["aliases"]["c"]:
            assert content_hash(pointer(page, alias["path"])) == alias["value_sha256"]
        pagination = page["data"]["pagination"]
        assert pagination["total"] == 7
        assert pagination["returned"] == min(2, 7 - offset)
        assert pagination["has_more"] is (offset < 6)
        assert pagination["next_offset"] == (offset + 2 if offset < 6 else None)
    assert combined == [
        (row["date"], row["rank"], row["score"]) for row in full["data"]["candidates"]
    ]


@pytest.mark.parametrize("offset", [7, 8, 1_000_000])
def test_beyond_last_page_has_honest_empty_hits_and_full_trace(offset: int) -> None:
    days = _days({"start_date": "2026-10-21", "end_date": "2026-10-27"})
    rows = [daily(day, [context("astro", "aspect", aspect="拱相")]) for day in days]
    result = _score_results(NATAL, days, "签约", rows, offset=offset)
    data = result["data"]
    assert data["candidates"] == data["observations"] == result["rule_hits"] == []
    assert result["aliases"] == {"c": [], "r": []}
    assert len(data["ranking_summary"]) == 7
    assert data["trace"]["source"] and data["trace"]["school"]
    assert data["trace"]["ranking_summary_sha256"] == content_hash(
        data["ranking_summary"]
    )
    assert data["pagination"] == {
        "total": 7,
        "offset": offset,
        "limit": 31,
        "returned": 0,
        "has_more": False,
        "next_offset": None,
    }
    for row in data["ranking_summary"]:
        assert row["score"] == row["positive_sum"] + row["negative_sum"]
