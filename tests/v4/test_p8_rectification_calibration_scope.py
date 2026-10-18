"""Regression tests for threshold/shape scope and frozen follow-up cache binding."""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from typing import Any, cast

import pytest

from mingjing_core.adapters.charts.rectification_workbench import statistics
from mingjing_core.adapters.charts.rectification_workbench.contracts import (
    AnnualSignalCache,
    rules_identity,
)
from mingjing_core.adapters.charts.rectification_workbench.evaluation import (
    generated_events,
    session,
    synthetic_cache,
)
from mingjing_core.adapters.charts.rectification_workbench.sessions import freeze_round2
from mingjing_core.adapters.charts.rectification_workbench.statistics import (
    _passes,
    calibrate,
    evaluate,
    round2_prompt,
)


def null_records(
    group: str, *, round_no: int = 1, shape: tuple[int, int] = (12, 16)
) -> list[dict[str, Any]]:
    version, rule_hash = rules_identity()
    return [
        {
            "session_fingerprint": f"{group}-{index}",
            "events_hash": f"events-{index}",
            "annual_cache_hash": f"cache-{index}",
            "signal_provenance": "artificial_independent_binary_signals_not_real_charts",
            "candidate_count": shape[0],
            "event_count": shape[1],
            "rules_version": version,
            "rules_hash": rule_hash,
            "round": round_no,
            "alpha": 0.05 if round_no == 1 else 0.025,
            "p_value": 1.0,
            "holdout": {"supported": True},
            "unique_leader": False,
            "margin": 0,
        }
        for index in range(200)
    ]


@pytest.mark.parametrize(("round_no", "alpha"), [(1, 0.05), (2, 0.025)])
def test_independent_calibration_is_bound_to_one_round_and_alpha(
    round_no: int, alpha: float
) -> None:
    records = null_records("cal", round_no=round_no)
    calibration = calibrate(records, null_records("val", round_no=round_no))
    assert calibration.usable and calibration.covers(records[0])
    assert (calibration.round_no, calibration.alpha) == (round_no, alpha)
    other_round = null_records("other", round_no=3 - round_no)[0]
    assert not calibration.covers(other_round)
    assert not calibration.covers(dict(records[0], alpha=0.01))
    assert not calibration.covers(dict(records[0], round=True))
    incomplete = dict(records[0])
    incomplete.pop("round")
    assert not calibration.covers(incomplete)


@pytest.mark.parametrize("batch", ["calibration", "validation"])
def test_mixed_rounds_are_rejected_in_either_batch(batch: str) -> None:
    calibration, validation = null_records("cal"), null_records("val")
    changed = calibration if batch == "calibration" else validation
    changed[-1].update(round=2, alpha=0.025)
    with pytest.raises(ValueError, match="mixed_calibration_rounds"):
        calibrate(calibration, validation)


@pytest.mark.parametrize("batch", ["calibration", "validation"])
@pytest.mark.parametrize(
    ("round_no", "alpha"),
    [
        (1, 0.025),
        (2, 0.05),
        (3, 0.05),
        (True, 0.05),
        (1.0, 0.05),
        (1, True),
        (1, float("nan")),
        (1, float("inf")),
    ],
)
def test_invalid_threshold_pair_is_rejected(
    batch: str, round_no: Any, alpha: Any
) -> None:
    calibration, validation = null_records("cal"), null_records("val")
    changed = calibration if batch == "calibration" else validation
    changed[0].update(round=round_no, alpha=alpha)
    with pytest.raises(ValueError, match="invalid_calibration_round_alpha_pair"):
        calibrate(calibration, validation)


@pytest.mark.parametrize("field", ["round", "alpha"])
def test_missing_threshold_metadata_cannot_restore_unbound_calibration(
    field: str,
) -> None:
    calibration = null_records("cal")
    calibration[0].pop(field)
    with pytest.raises(ValueError, match="invalid_calibration_round_alpha_pair"):
        calibrate(calibration, null_records("val"))


@pytest.mark.parametrize("shape", [(12, 8), (24, 16)])
def test_shape_mixture_cannot_hide_one_shapes_false_positives(
    shape: tuple[int, int],
) -> None:
    calibration, validation = null_records("cal"), null_records("val")
    for rows in (calibration, validation):
        for row in rows[-10:]:
            row.update(
                candidate_count=shape[0],
                event_count=shape[1],
                p_value=0.01,
                unique_leader=True,
                margin=1,
            )
        assert sum(_passes(row, 0) for row in rows) / len(rows) == 0.05
    with pytest.raises(ValueError, match="mixed_calibration_shapes"):
        calibrate(calibration, validation)


def test_direct_calibration_objects_also_reject_multiple_shapes_and_wrong_alpha() -> (
    None
):
    calibration = calibrate(null_records("cal"), null_records("val"))
    with pytest.raises(ValueError, match="mixed_calibration_shapes"):
        replace(calibration, supported_shapes=((12, 16), (12, 8)))
    with pytest.raises(ValueError, match="invalid_calibration_round_alpha_pair"):
        replace(calibration, alpha=0.025)
    other = calibrate(null_records("cal", round_no=2), null_records("val", round_no=2))
    assert calibration.dataset_hash != other.dataset_hash
    assert calibration.fingerprint != other.fingerprint


def test_round_two_abstains_until_its_own_independent_calibration_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache = synthetic_cache(1, "threshold-binding")
    dominant = replace(
        cache,
        values=tuple(
            tuple((int(index == 0),) * len(cache.signal_ids) for index in range(12))
            for _ in cache.years
        ),
    )
    rows = generated_events(dominant, known=None, seed_value=42)
    frozen = freeze_round2(
        session(dominant, rows, "round-two-binding"),
        [{"id": "extra", "type": "career", "year": 2000, "added_in_round": 2}],
        user_confirmed=True,
    )
    monkeypatch.setattr(statistics, "_null_distribution", lambda *args: [0] * 1000)
    shape = (12, len(rows) + 1)
    first = calibrate(
        null_records("cal", shape=shape), null_records("val", shape=shape)
    )
    rejected = evaluate(frozen, dominant, first, 2)
    assert _passes(rejected, first.delta)
    assert rejected["calibration_usable"] is False
    assert rejected["distinguishable"] is False
    assert rejected["selected_candidate"] is None
    assert rejected["conclusion"] == "分不出来"
    second = calibrate(
        null_records("r2-cal", round_no=2, shape=shape),
        null_records("r2-val", round_no=2, shape=shape),
    )
    accepted = evaluate(frozen, dominant, second, 2)
    assert accepted["calibration_usable"] and accepted["distinguishable"]


@pytest.mark.parametrize(
    "field", ["birth_year", "as_of_year", "scope", "rules_hash", "rules_version"]
)
def test_round_two_prompt_rejects_cache_outside_frozen_bindings(field: str) -> None:
    cache = synthetic_cache(1, "followup-binding")
    frozen = session(
        cache, generated_events(cache, known=None, seed_value=42), "prompt"
    )
    if field == "birth_year":
        mismatched = replace(
            cache,
            birth_year=1979,
            years=(1985, *cache.years),
            values=(cache.values[0], *cache.values),
        )
    elif field == "as_of_year":
        mismatched = replace(
            cache, as_of_year=2025, years=cache.years[:-1], values=cache.values[:-1]
        )
    elif field == "scope":
        mismatched = replace(cache, scope=(cache.scope[0], "another-subject", 1))
    else:
        # A loaded old cache may outlive the rules; no binary-vector work is needed to reject it.
        mismatched = cast(
            AnnualSignalCache, SimpleNamespace(**{**vars(cache), field: "stale"})
        )
    with pytest.raises(
        ValueError, match="scope_or_years_mismatch|rule_version_mismatch"
    ):
        round2_prompt(frozen, mismatched)
