"""Seeded implementation/null experiments on explicitly artificial signal matrices."""

from __future__ import annotations

import argparse
import json
import random
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .contracts import AnnualSignalCache, canonical, rules, rules_identity
from .sessions import FrozenSession, freeze_round1
from .statistics import DeltaCalibration, _passes, assess_statistics, calibrate, wilson

DISCLAIMER = "本评测衡量的是程序的一致性与防误报能力，不证明命理方法本身的效度。"


def synthetic_cache(index: int, group: str) -> AnnualSignalCache:
    """Independent Bernoulli features are software fixtures, not computed Bazi."""
    from .sessions import seed

    rng = random.Random(seed(group, f"artificial-matrix-{index}"))
    candidates = tuple(f"H{number:02d}" for number in range(12))
    signals = tuple(
        sorted(
            {row["signal"] for rows in rules()["event_rules"].values() for row in rows}
        )
    )
    years = tuple(range(1986, 2027))
    values = tuple(
        tuple(tuple(int(rng.random() < 0.12) for _ in signals) for _ in candidates)
        for _ in years
    )
    columns = {
        ident: {
            "label": ident,
            "ziwei_column": {"status": "not_computed_in_artificial_matrix_fixture"},
        }
        for ident in candidates
    }
    version, rules_hash = rules_identity()
    return AnnualSignalCache(
        candidates,
        years,
        signals,
        values,
        canonical(columns),
        "{}",
        ("synthetic-owner", f"{group}-{index}", 1),
        version,
        rules_hash,
        1980,
        2026,
        "artificial_independent_binary_signals_not_real_charts",
    )


def generated_events(
    cache: AnnualSignalCache, *, known: int | None, seed_value: int
) -> list[dict[str, Any]]:
    rng, rows = random.Random(seed_value), []
    tables = cache.score_tables()
    for kind, (lower, upper) in rules()["age_intervals"].items():
        years = list(range(max(1986, 1980 + lower), min(2026, 1980 + upper) + 1))
        rng.shuffle(years)
        if known is not None:
            years.sort(key=lambda year: -tables[kind][year - cache.years[0]][known])
        for year in years[:2]:
            ident = f"synthetic-{len(rows):02d}"
            rows.append(
                {
                    "id": ident,
                    "type": kind,
                    "year": year,
                    "certainty": "sure",
                    "source_fact_id": ident,
                    "added_in_round": 1,
                }
            )
    return rows


def session(
    cache: AnnualSignalCache, rows: list[dict[str, Any]], ident: str
) -> FrozenSession:
    return freeze_round1(
        ident,
        rows,
        owner_user_id=cache.scope[0],
        subject_id=cache.scope[1],
        revision=cache.scope[2],
        birth_year=cache.birth_year,
        as_of_year=cache.as_of_year,
        user_confirmed=True,
    )


def _null_set(group: str, count: int) -> list[dict[str, Any]]:
    results = []
    for index in range(count):
        cache = synthetic_cache(index, group)
        events = generated_events(cache, known=None, seed_value=100000 + index)
        result = assess_statistics(session(cache, events, f"{group}-{index}"), cache)
        results.append(result)
    return results


def _noise(
    events: list[dict[str, Any]],
    cache: AnnualSignalCache,
    error: float,
    missing: float,
    unrelated: float,
    seed_value: int,
) -> list[dict[str, Any]]:
    rng, output = random.Random(seed_value), []
    for event in events:
        if rng.random() < missing:
            continue
        row = dict(event)
        if rng.random() < error:
            lower, upper = rules()["age_intervals"][row["type"]]
            changed = row["year"] + rng.choice((-1, 1))
            row["year"] = min(
                cache.as_of_year, 1980 + upper, max(1980 + lower, changed)
            )
        output.append(row)
    additions = generated_events(cache, known=None, seed_value=seed_value + 999)
    for number, row in enumerate(additions[: round(len(events) * unrelated)]):
        output.append(
            dict(row, id=f"unrelated-{number}", source_fact_id=f"unrelated-{number}")
        )
    return output or events[:1]


def _known_cases() -> list[tuple[AnnualSignalCache, list[dict[str, Any]], int]]:
    return [
        (
            cache,
            generated_events(cache, known=index % 12, seed_value=30000 + index),
            index % 12,
        )
        for index in range(12)
        for cache in [synthetic_cache(index, "consistency")]
    ]


def run_experiments() -> dict[str, Any]:
    calibration, validation = (
        _null_set("null-calibration", 200),
        _null_set("null-validation", 200),
    )
    delta = calibrate(calibration, validation)
    known, first, grid = _known_cases(), [], []
    for index, (cache, events, truth) in enumerate(known):
        result = assess_statistics(session(cache, events, f"known-{index}"), cache)
        first.append(
            {
                "correct": result["unique_leader"] and result["leader_index"] == truth,
                "confidence_wrong": delta.covers(result)
                and _passes(result, delta.delta)
                and result["leader_index"] != truth,
                "distinguishable": delta.covers(result)
                and _passes(result, delta.delta),
            }
        )
    for error in (0, 0.2, 0.4):
        for missing in (0, 0.3):
            for unrelated in (0, 0.3):
                grid.append(_grid_cell(known, delta, error, missing, unrelated))
    fpr = delta.validation_false_positives / delta.validation_count
    return {
        "disclaimer": DISCLAIMER,
        "model_calls": 0,
        "writes_to_user_profiles": 0,
        "fixture_scope": "artificial_binary_signals_not_real_U2_or_life_events",
        "generator": "12 persons;16 events/person;known-only generation;no filtering",
        "E_R1": {
            "subjects": len(first),
            "first_place_hit_rate": sum(row["correct"] for row in first) / len(first),
            "passed_95_percent": sum(row["correct"] for row in first) / len(first)
            >= 0.95,
            "confidence_wrong_rate": sum(row["confidence_wrong"] for row in first)
            / len(first),
        },
        "calibration": asdict(delta) | {"usable": delta.usable},
        "E_R2_null_validation": {
            "subjects": 200,
            "false_positive_rate": fpr,
            "wilson_95": wilson(delta.validation_false_positives, 200),
            "passed_point_estimate_5_percent": fpr <= 0.05,
        },
        "noise_grid": grid,
        "max_1000_permutation_seconds": max(
            row["null_seconds"] for row in calibration + validation
        ),
        "permutation_performance_under_ten_seconds": all(
            row["null_seconds"] < 10 for row in calibration + validation
        ),
        "external_validity": "not_tested_no_external_person_data_downloaded",
        "limits": [
            "矩阵信号是软件测试输入，不是实际命理盘；不能把本表成绩归于传统规则。",
            "δ仅在本次人工矩阵零样本上标定，真实Charts信号需另做独立标定，不授权生产倾向结论。",
        ],
    }


def _grid_cell(
    known: list[Any],
    delta: DeltaCalibration,
    error: float,
    missing: float,
    unrelated: float,
) -> dict[str, Any]:
    records = []
    for index, (cache, events, truth) in enumerate(known):
        changed = _noise(events, cache, error, missing, unrelated, 40000 + index)
        result = assess_statistics(
            session(cache, changed, f"noise-{error}-{missing}-{unrelated}-{index}"),
            cache,
        )
        scores = result["train_scores"]
        rank_worst = sum(value >= scores[truth] for value in scores)
        covered = delta.covers(result)
        raw_pass = _passes(result, delta.delta)
        records.append(
            (
                rank_worst <= 3,
                covered and raw_pass,
                covered and raw_pass and result["leader_index"] != truth,
                covered,
                raw_pass,
            )
        )
    return {
        "year_error_fraction": error,
        "missing_fraction": missing,
        "unrelated_fraction": unrelated,
        "subjects": len(records),
        "top_three_hit_rate_diagnostic_only": sum(row[0] for row in records)
        / len(records),
        "distinguishable_rate": sum(row[1] for row in records) / len(records),
        "confidence_wrong_rate": sum(row[2] for row in records) / len(records),
        "covered_by_calibration_rate": sum(row[3] for row in records) / len(records),
        "raw_delta_pass_rate_diagnostic_only": sum(row[4] for row in records)
        / len(records),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Offline artificial-matrix consistency/null experiments, no models"
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run_experiments()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(
        json.dumps(
            {
                "E_R1": result["E_R1"],
                "E_R2_null_validation": result["E_R2_null_validation"],
                "model_calls": 0,
                "max_1000_permutation_seconds": result["max_1000_permutation_seconds"],
            }
        )
    )


if __name__ == "__main__":
    main()
