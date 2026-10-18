"""Hand-calculated null tests and conservative calibration boundaries."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime
from types import SimpleNamespace
from typing import Any

import pytest

from mingjing_core.adapters.charts.rectification_workbench import signals, statistics
from mingjing_core.adapters.charts.rectification_workbench.contracts import (
    AnnualSignalCache,
    canonical,
    rules_identity,
)
from mingjing_core.adapters.charts.rectification_workbench.envelope import (
    conclusion_metadata,
    holdout_ranks,
)
from mingjing_core.adapters.charts.rectification_workbench.evaluation import (
    generated_events,
    session,
    synthetic_cache,
)
from mingjing_core.adapters.charts.rectification_workbench.sessions import (
    FrozenSession,
    freeze_round2,
)
from mingjing_core.adapters.charts.rectification_workbench.statistics import (
    _null_distribution,
    assess_statistics,
    calibrate,
    evaluate,
    round2_prompt,
    wilson,
)

Fixture = tuple[AnnualSignalCache, list[dict[str, Any]], FrozenSession]


@pytest.fixture
def fixture() -> Fixture:
    cache = synthetic_cache(1, "statistical-tests")
    rows = generated_events(cache, known=None, seed_value=43)
    return cache, rows, session(cache, rows, "statistics-session")


def raw_nulls(
    group: str,
    *,
    margin: int = 0,
    p_value: float = 1,
    shape: tuple[int, int] = (12, 16),
) -> list[dict[str, Any]]:
    version, rules_hash = rules_identity()
    return [
        {
            "session_fingerprint": f"{group}-{index}",
            "events_hash": f"events-{group}-{index}",
            "annual_cache_hash": f"cache-{group}-{index}",
            "signal_provenance": (
                "artificial_independent_binary_signals_not_real_charts"
            ),
            "candidate_count": shape[0],
            "event_count": shape[1],
            "rules_version": version,
            "rules_hash": rules_hash,
            "p_value": p_value,
            "alpha": 0.05,
            "holdout": {"supported": True},
            "unique_leader": margin > 0,
            "margin": margin,
        }
        for index in range(200)
    ]


def test_wilson_known_values_and_invalid_counts() -> None:
    assert wilson(0, 200) == pytest.approx((0, 0.018845326377266575))
    assert wilson(5, 10) == pytest.approx((0.236593090512564, 0.763406909487436))
    for successes, total in ((1, 0), (-1, 10), (11, 10), (True, 10), (1, True)):
        with pytest.raises(ValueError, match="invalid_binomial_counts"):
            wilson(successes, total)


def test_permutation_uses_type_specific_age_pool_and_is_deterministic(
    fixture: Fixture,
) -> None:
    cache, rows, frozen = fixture
    tables = {
        "education": tuple(
            (0,) * 12 if year <= 2010 else (99,) * 12 for year in cache.years
        )
    }
    events = [dict(rows[0], type="education", year=1990)]
    result = _null_distribution(events, tables, cache, frozen, 1)
    assert result == [0] * 1000
    assert result == _null_distribution(events, tables, cache, frozen, 1)


def test_plus_one_p_value_has_exact_floor_and_counts_equal_scores(
    fixture: Fixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache, _, frozen = fixture
    ones = replace(
        cache,
        values=tuple(
            tuple((1,) * len(cache.signal_ids) for _ in cache.candidate_ids)
            for _ in cache.years
        ),
    )
    monkeypatch.setattr(statistics, "_null_distribution", lambda *args: [0] * 1000)
    result = assess_statistics(frozen, ones)
    assert result["p_value"] == 1 / 1001
    assert result["alpha"] == 0.05
    score = result["full_scores"][0]
    monkeypatch.setattr(statistics, "_null_distribution", lambda *args: [score] * 1000)
    assert assess_statistics(frozen, ones)["p_value"] == 1


def test_tied_candidates_fail_all_gates_and_no_chart_calls(
    fixture: Fixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache, _, frozen = fixture
    zeros = replace(
        cache,
        values=tuple(
            tuple((0,) * len(cache.signal_ids) for _ in cache.candidate_ids)
            for _ in cache.years
        ),
    )

    def forbidden(*args: Any) -> None:
        raise AssertionError("1000 permutations must not re-chart")

    monkeypatch.setattr(signals, "load_engine", forbidden)
    calibration = calibrate(raw_nulls("cal"), raw_nulls("val"))
    result = evaluate(frozen, zeros, calibration)
    assert result["p_value"] == 1
    assert result["holdout"]["rank_bounds"] == [1, 12]
    assert result["holdout"]["supported"] is False
    assert result["conclusion"] == "分不出来"
    assert result["selected_candidate"] is None
    assert all(row["holdout_rank"] == 12 for row in result["candidates"])
    assert result["model_calls"] == result["writes"] == 0
    assert "top_three" not in canonical(result)


def test_calibration_needs_disjoint_independent_two_hundred_each() -> None:
    calibration, validation = raw_nulls("cal"), raw_nulls("val")
    with pytest.raises(ValueError, match="need_200"):
        calibrate(calibration[:-1], validation)
    with pytest.raises(ValueError, match="overlap_or_duplicate"):
        calibrate(calibration, calibration)
    validation[0]["rules_hash"] = "changed"
    with pytest.raises(ValueError, match="rules_mismatch"):
        calibrate(calibration, validation)


def test_delta_is_selected_on_calibration_only_and_validation_cannot_retune() -> None:
    calibration = calibrate(
        raw_nulls("cal", margin=1, p_value=0.01),
        raw_nulls("val", margin=3, p_value=0.01),
    )
    assert calibration.delta == 2
    assert calibration.calibration_false_positives == 0
    assert calibration.validation_false_positives == 200
    assert calibration.usable is False


def test_delta_cannot_transfer_between_signal_families_or_unseen_event_counts() -> None:
    calibration = calibrate(raw_nulls("cal"), raw_nulls("val"))
    base = raw_nulls("known")[0]
    assert calibration.covers(base)
    assert not calibration.covers(dict(base, event_count=11))
    assert not calibration.covers(dict(base, signal_provenance="real_Charts"))
    with pytest.raises(ValueError, match="mixed_signal_family"):
        calibrate(raw_nulls("cal"), raw_nulls("val", shape=(12, 11)))


def test_unknown_month_is_metadata_only_not_a_fake_date(fixture: Fixture) -> None:
    cache, rows, _ = fixture
    initial = session(cache, rows, "same-seed")
    monthly = session(cache, [dict(row, month=3) for row in rows], "same-seed")
    left, right = assess_statistics(initial, cache), assess_statistics(monthly, cache)
    for key in ("p_value", "margin", "train_scores", "holdout_scores"):
        assert left[key] == right[key]
    evidence = signals.event_evidence(cache, 0, monthly.event_rows(1)[0])
    assert evidence["month_not_used_for_year_only_test"]
    assert all("ref" not in row for row in evidence["for"] + evidence["against"])


def test_round_two_question_is_neutral_and_never_a_third_round(
    fixture: Fixture,
) -> None:
    cache, _, frozen = fixture
    prompt = round2_prompt(frozen, cache)
    assert prompt["age_range"][0] >= 6
    assert not any(
        word in prompt["question"]
        for word in ("career", "结婚", "生育", "H01", "时辰", "事业", "搬家")
    )
    second = freeze_round2(
        frozen,
        [{"id": "later", "type": "career", "year": 2000, "added_in_round": 2}],
        user_confirmed=True,
    )
    with pytest.raises(ValueError, match="maximum_two_rounds"):
        round2_prompt(second, cache)


def test_current_year_is_cut_off_at_clock_date_not_end_of_year() -> None:
    table = {
        name: SimpleNamespace(toYmdHms=lambda: "2026-02-04 04:02:00")
        for name in ("立春", "LI_CHUN")
    }
    solar = SimpleNamespace(
        getLunar=lambda: SimpleNamespace(getJieQiTable=lambda: table)
    )
    engine = SimpleNamespace(Solar=SimpleNamespace(fromYmdHms=lambda *args: solar))
    context = {
        "as_of_date": "2026-10-18",
        "p8": {
            "decade_luck": {
                "decades": [
                    {
                        "nominal_start_at": "2026-11-01T00:00:00+08:00",
                        "nominal_end_exclusive": "2036-11-01T00:00:00+08:00",
                    }
                ]
            }
        },
    }
    pieces = signals._pieces(context, 2026, engine)
    assert len(pieces) == 2
    assert max(pieces) < datetime(2026, 10, 19)
    with pytest.raises(ValueError, match="after_explicit_source_clock"):
        signals._pieces(context, 2027, engine)


def test_annual_references_are_bound_to_saved_graph_and_not_aliases() -> None:
    graph = {"nodes": [{"id": "target.yearly", "stem_ten_god": "正印"}]}
    reference = {"kind": "calculation", "node_id": "target.yearly"}
    bound = signals._bind_evidence([reference], graph, "/2026/H~10/pieces/0")[0]
    document = {
        "2026": {"H/0": {"pieces": [{"data": {"p8": {"time_interactions": graph}}}]}}
    }
    value = document
    for part in bound["evidence_paths"][0].split("/")[1:]:
        part = part.replace("~1", "/").replace("~0", "~")
        value = value[int(part)] if isinstance(value, list) else value[part]
    assert value == graph["nodes"][0]
    assert bound["alias_status"] == "unregistered_mainline_alias_required"
    with pytest.raises(ValueError, match="must_bind_to_annual_graph"):
        signals._bind_evidence(
            [{"kind": "rule", "paths": ["/data/p8/natal/0"]}],
            graph,
            "/2026/H0/pieces/0",
        )


def test_invariants_report_only_actual_complete_pillar_values() -> None:
    columns = {
        "A": {"pillars": {"year": "甲子", "month": "乙丑", "hour": "丙寅"}},
        "B": {"pillars": {"year": "甲子", "month": "乙丑", "hour": "丁卯"}},
    }
    result = conclusion_metadata(columns, ("A", "B"))
    assert {row["field"] for row in result["stable_conclusions"]} == {
        "pillars.year",
        "pillars.month",
    }
    assert len(result["conditional_conclusions"]) == 2
    assert all(
        row["field"] == "pillars.hour" for row in result["conditional_conclusions"]
    )
    assert "pillars.day" not in json.dumps(result)
    assert result["interpretation_status"] == "no_interpretive_conclusions_generated"
    assert holdout_ranks([4, 2, 2], True) == [
        {"holdout_rank": 1, "holdout_rank_bounds": [1, 1]},
        {"holdout_rank": 3, "holdout_rank_bounds": [2, 3]},
        {"holdout_rank": 3, "holdout_rank_bounds": [2, 3]},
    ]
    assert holdout_ranks([0, 0], False)[0]["holdout_rank"] is None
