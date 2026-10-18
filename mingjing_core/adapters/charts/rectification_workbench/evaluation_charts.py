"""Offline actual-chart signal experiments, explicitly separate from matrix tests."""

from __future__ import annotations

import argparse
import itertools
import json
import random
from dataclasses import asdict
from pathlib import Path
from time import perf_counter
from typing import Any

from .contracts import AnnualSignalCache, rules
from .sessions import freeze_round1, seed
from .statistics import assess_statistics, calibrate, evaluate, wilson

DISCLAIMER = "本评测衡量的是程序的一致性与防误报能力，不证明命理方法本身的效度。"


def _years(cache: AnnualSignalCache, kind: str) -> list[int]:
    lower, upper = rules()["age_intervals"][kind]
    return list(
        range(
            max(cache.years[0], cache.birth_year + lower),
            min(cache.as_of_year, cache.birth_year + upper) + 1,
        )
    )


def _event(identity: str, kind: str, year: int) -> dict[str, Any]:
    return {
        "id": identity,
        "type": kind,
        "year": year,
        "certainty": "sure",
        "source_id": "synthetic:" + identity,
    }


def null_events(
    cache: AnnualSignalCache, identity: str, count: int
) -> list[dict[str, Any]]:
    rng = random.Random(seed(identity, "actual-chart-independent-null-years"))
    kinds = sorted(rules()["event_rules"])
    rows = []
    for index in range(count):
        kind = rng.choice(kinds)
        rows.append(
            _event(f"{identity}-{index}", kind, rng.choice(_years(cache, kind)))
        )
    return rows


def known_events(
    cache: AnnualSignalCache, known: int, identity: str
) -> list[dict[str, Any]]:
    """Only inspect known candidate; this deliberately circular test proves no validity."""
    tables, events = cache.score_tables(), []
    rng = random.Random(seed(identity, "known-chart-year-ties"))
    for kind in sorted(rules()["event_rules"]):
        years = _years(cache, kind)
        rng.shuffle(years)
        year = max(years, key=lambda value: tables[kind][value - cache.years[0]][known])
        events.append(_event(f"{identity}-{kind}", kind, year))
    return events


def _session(
    cache: AnnualSignalCache, identity: str, events: list[dict[str, Any]]
) -> Any:
    owner, subject, revision = cache.scope
    return freeze_round1(
        identity,
        events,
        owner_user_id=owner,
        subject_id=subject,
        revision=revision,
        birth_year=cache.birth_year,
        as_of_year=cache.as_of_year,
        user_confirmed=True,
    )


def _calibration(
    caches: list[AnnualSignalCache], count: int
) -> tuple[Any, dict[str, Any]]:
    batches = {}
    for group in ("calibration", "validation"):
        batch = []
        for index in range(200):
            cache = caches[index % len(caches)]
            identity = f"actual-charts-{group}-events{count}-{index}"
            session = _session(cache, identity, null_events(cache, identity, count))
            batch.append(assess_statistics(session, cache))
        batches[group] = batch
    calibration = calibrate(batches["calibration"], batches["validation"])
    return calibration, {
        **asdict(calibration),
        "calibration_wilson_95": wilson(calibration.calibration_false_positives, 200),
        "validation_wilson_95": wilson(calibration.validation_false_positives, 200),
        "max_1000_permutation_seconds": max(
            row["null_seconds"] for rows in batches.values() for row in rows
        ),
        "independence": "200 independent event datasets per split over 10 fixed synthetic birth charts; "
        "no shared session seeds",
    }


def _noise(
    cache: AnnualSignalCache,
    events: list[dict[str, Any]],
    identity: str,
    cell: tuple[float, float, float],
) -> list[dict[str, Any]]:
    error, missing, contamination = cell
    rng = random.Random(seed(identity, "noise-grid"))
    rows = [dict(row) for row in events]
    omitted = set(rng.sample(range(len(rows)), round(missing * len(rows))))
    rows = [row for index, row in enumerate(rows) if index not in omitted]
    for index in rng.sample(range(len(rows)), round(error * len(rows))):
        allowed = _years(cache, rows[index]["type"])
        rows[index]["year"] = min(
            max(rows[index]["year"] + rng.choice((-1, 1)), allowed[0]), allowed[-1]
        )
    added = round(contamination * len(events))
    return rows + null_events(cache, identity + "-unrelated", added)


def _retrieval(raw: dict[str, Any], known: int) -> dict[str, Any]:
    values = raw["train_scores"]
    better = sum(value > values[known] for value in values)
    tied = sum(value == values[known] for value in values)
    return {
        "unique_first_hit": better == 0 and tied == 1,
        "stable_first_hit": raw["leader_index"] == known,
        "tie_count": tied,
        "rank_bounds": [better + 1, better + tied],
        "tie_aware_top_three_expected": min(1.0, max(0.0, (3 - better) / tied)),
    }


def run_actual_charts(caches: list[AnnualSignalCache]) -> dict[str, Any]:
    if len(caches) < 10 or any(
        cache.provenance != "real_charts_U2_U12_precompute_no_model_calls"
        for cache in caches
    ):
        raise ValueError("need_ten_actual_program_chart_caches_not_artificial_matrix")
    cells = list(itertools.product((0.0, 0.2, 0.4), (0.0, 0.3), (0.0, 0.3)))
    counts = sorted(
        {8 - round(missing * 8) + round(mixed * 8) for _, missing, mixed in cells}
    )
    calibrations, summaries = {}, {}
    for count in counts:
        calibrations[count], summaries[str(count)] = _calibration(caches, count)
    cases, grid = [], []
    for index, cache in enumerate(caches):
        known = (index * 5 + 1) % len(cache.candidate_ids)
        identity = f"actual-charts-er1-{index}"
        events = known_events(cache, known, identity)
        result = evaluate(
            _session(cache, identity, events), cache, calibrations[len(events)]
        )
        cases.append(
            {
                "id": identity,
                "known_index": known,
                "candidate_count": len(cache.candidate_ids),
                **_retrieval(result, known),
                "distinguishable": result["distinguishable"],
                "confident_wrong": result["distinguishable"]
                and result["leader_index"] != known,
                "p_value": result["p_value"],
                "margin": result["margin"],
                "holdout": result["holdout"],
            }
        )
        for cell in cells:
            changed = _noise(cache, events, identity + str(cell), cell)
            session = _session(cache, identity + str(cell), changed)
            result = evaluate(session, cache, calibrations[len(changed)])
            grid.append(
                {
                    "case": index,
                    "year_error": cell[0],
                    "omission": cell[1],
                    "contamination": cell[2],
                    "event_count": len(changed),
                    "noise_applied": _applied_noise(events, changed),
                    **_retrieval(result, known),
                    "distinguishable": result["distinguishable"],
                    "confident_wrong": result["distinguishable"]
                    and result["leader_index"] != known,
                }
            )
    return _report(caches, cases, grid, summaries)


def _applied_noise(
    original: list[dict[str, Any]], changed: list[dict[str, Any]]
) -> dict[str, int]:
    before = {row["id"]: row["year"] for row in original}
    after = {row["id"]: row["year"] for row in changed}
    return {
        "original_count": len(before),
        "omitted_count": len(before.keys() - after.keys()),
        "added_count": len(after.keys() - before.keys()),
        "year_changed_count": sum(
            before[key] != after[key] for key in before.keys() & after.keys()
        ),
    }


def _report(
    caches: list[AnnualSignalCache],
    cases: list[dict[str, Any]],
    grid: list[dict[str, Any]],
    summaries: dict[str, Any],
) -> dict[str, Any]:
    return {
        "disclaimer": DISCLAIMER,
        "experiment": "actual_program_charts_synthetic_people_not_external_validity",
        "people": len(cases),
        "cases": cases,
        "noise_grid": grid,
        "calibrations_by_event_count": summaries,
        "unique_first_rate": sum(row["unique_first_hit"] for row in cases) / len(cases),
        "stable_first_rate": sum(row["stable_first_hit"] for row in cases) / len(cases),
        "er1_95_percent_gate_passed": sum(row["unique_first_hit"] for row in cases)
        / len(cases)
        >= 0.95,
        "confident_wrong_rate": sum(row["confident_wrong"] for row in cases)
        / len(cases),
        "confident_wrong_wilson_95": wilson(
            sum(row["confident_wrong"] for row in cases), len(cases)
        ),
        "cache_fingerprints": [cache.fingerprint for cache in caches],
        "model_calls": 0,
        "writes": 0,
        "limits": [
            "12标准钟表中点，不代表连续未知时间覆盖；真实用户未走此网格。",
            "事件从同一已知盘的最高年份生成，存在循环性；不看竞争候选，不回滚挑人物。",
            "200+200独立事件集仅复用10种出生盘，不冒称200种独立盘面或外部名人效度。",
            "首名严格要求唯一；稳定ID解并列另报；前三仅离线噪声曲线，产品不输出前三。",
        ],
    }


def main() -> None:
    from .chart_grid import synthetic_chart_grid
    from .contracts import digest
    from .evaluation_cases import fixture_requests
    from .signals import precompute

    parser = argparse.ArgumentParser(
        description="Actual synthetic Charts only; no model or external corpus"
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    requests, caches, timings = fixture_requests(), [], []
    for request in requests:
        start = perf_counter()
        contexts = synthetic_chart_grid(request, basis="standard")
        cache = precompute(
            contexts,
            birth_year=int(request["birth"]["date"][:4]),
            as_of_year=2026,
            scope=(
                request["owner_user_id"],
                request["subject_id"],
                request["revision"],
            ),
        )
        caches.append(cache)
        timings.append(
            {
                "id": request["subject_id"],
                "seconds": perf_counter() - start,
                "cache_hash": cache.fingerprint,
                "candidates": len(cache.candidate_ids),
                "signals": len(cache.signal_ids),
            }
        )
    report = run_actual_charts(caches)
    report.update(fixed_fixture_hash=digest(requests), precomputations=timings)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(
        json.dumps(
            {
                "people": report["people"],
                "er1_gate_passed": report["er1_95_percent_gate_passed"],
                "model_calls": 0,
            }
        )
    )


if __name__ == "__main__":
    main()
