"""Fixed 1000-year randomization and conservative holdout gates; no chart calls."""

from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass
from time import perf_counter
from typing import Any

from .calibration_scope import (
    calibration_dataset_hash,
    calibration_scope,
    valid_round_alpha,
)
from .contracts import AnnualSignalCache, digest, rules, rules_identity
from .sessions import FrozenSession, seed, split_events

PERMUTATIONS = 1000


def wilson(successes: int, total: int) -> tuple[float, float]:
    if (
        type(total) is not int
        or total <= 0
        or type(successes) is not int
        or not 0 <= successes <= total
    ):
        raise ValueError("invalid_binomial_counts")
    z, proportion = 1.959963984540054, successes / total
    denominator = 1 + z * z / total
    center = (proportion + z * z / (2 * total)) / denominator
    radius = (
        z
        * math.sqrt(proportion * (1 - proportion) / total + z * z / (4 * total * total))
        / denominator
    )
    return max(0, center - radius), min(1, center + radius)


def _totals(
    rows: list[dict[str, Any]], tables: dict[str, Any], first_year: int, count: int
) -> list[int]:
    totals = [0] * count
    for event in rows:
        vector = tables[event["type"]][event["year"] - first_year]
        for index, score in enumerate(vector):
            totals[index] += score
    return totals


def _null_distribution(
    rows: list[dict[str, Any]],
    tables: dict[str, Any],
    cache: AnnualSignalCache,
    session: FrozenSession,
    round_no: int,
) -> list[int]:
    intervals, pools = rules()["age_intervals"], []
    for event in rows:
        lower, upper = intervals[event["type"]]
        start = max(cache.years[0], cache.birth_year + lower) - cache.years[0]
        end = min(cache.as_of_year, cache.birth_year + upper) - cache.years[0] + 1
        pool = tables[event["type"]][start:end]
        if not pool:
            raise ValueError("empty_type_specific_permutation_year_pool")
        pools.append(pool)
    rng = random.Random(
        seed(session.session_id, f"year-randomization-round-{round_no}")
    )
    distribution = []
    for _ in range(PERMUTATIONS):
        totals = [0] * len(cache.candidate_ids)
        for pool in pools:
            vector = pool[rng.randrange(len(pool))]
            for index, value in enumerate(vector):
                totals[index] += value
        distribution.append(max(totals))
    return distribution


def _validate_bindings(session: FrozenSession, cache: AnnualSignalCache) -> None:
    session.verify()
    if session.scope != cache.scope or (session.birth_year, session.as_of_year) != (
        cache.birth_year,
        cache.as_of_year,
    ):
        raise ValueError("session_and_annual_cache_scope_or_years_mismatch")
    if (cache.rules_version, cache.rules_hash) != (
        session.rules_version,
        session.rules_hash,
    ):
        raise ValueError("session_and_cache_rule_version_mismatch")


def assess_statistics(
    session: FrozenSession, cache: AnnualSignalCache, round_no: int = 1
) -> dict[str, Any]:
    _validate_bindings(session, cache)
    train, heldout = split_events(session, round_no)
    rows, tables, count = (
        session.event_rows(round_no),
        cache.score_tables(),
        len(cache.candidate_ids),
    )
    trained = _totals(train, tables, cache.years[0], count)
    held = _totals(heldout, tables, cache.years[0], count)
    full = _totals(rows, tables, cache.years[0], count)
    ordered = sorted(
        range(count), key=lambda index: (-trained[index], cache.candidate_ids[index])
    )
    leader = ordered[0]
    margin = trained[leader] - trained[ordered[1]]
    rank_best = 1 + sum(value > held[leader] for value in held)
    rank_worst = sum(value >= held[leader] for value in held)
    start = perf_counter()
    null = _null_distribution(rows, tables, cache, session, round_no)
    duration = perf_counter() - start
    exceedances = sum(value >= full[leader] for value in null)
    return {
        "session_fingerprint": digest(session.session_id),
        "events_hash": session.events_hash,
        "round2_hash": session.round2_hash if round_no == 2 else None,
        "round": round_no,
        "alpha": 0.05 if round_no == 1 else 0.025,
        "rules_version": cache.rules_version,
        "rules_hash": cache.rules_hash,
        "annual_cache_hash": cache.fingerprint,
        "signal_provenance": cache.provenance,
        "candidate_count": count,
        "event_count": len(rows),
        "p_value": (1 + exceedances) / 1001,
        "null_exceedances": exceedances,
        "permutations": PERMUTATIONS,
        "null_seconds": duration,
        "margin": margin,
        "unique_leader": margin > 0,
        "training_leader": cache.candidate_ids[leader],
        "leader_index": leader,
        "train_scores": trained,
        "holdout_scores": held,
        "full_scores": full,
        "holdout": {
            "used": bool(heldout),
            "leader_rank": rank_worst,
            "rank_bounds": [rank_best, rank_worst],
            "supported": bool(heldout) and rank_worst <= 2,
            "event_ids": [row["id"] for row in heldout],
        },
        "statistic": "training_leader_full_score_vs_null_best_full_candidate",
        "null_method": "independent_uniform_year_replacement_in_type_age_range",
        "month_policy": "year_only_test_month_metadata_preserved_not_scored",
    }


@dataclass(frozen=True)
class DeltaCalibration:
    delta: int
    sample_count: int
    validation_count: int
    calibration_false_positives: int
    validation_false_positives: int
    dataset_hash: str
    rules_version: str
    rules_hash: str
    signal_provenance: str
    supported_shapes: tuple[tuple[int, int], ...]
    round_no: int
    alpha: float

    def __post_init__(self) -> None:
        if type(self.delta) is not int or self.delta < 0:
            raise ValueError("invalid_calibration_delta")
        for count, false in (
            (self.sample_count, self.calibration_false_positives),
            (self.validation_count, self.validation_false_positives),
        ):
            if (
                type(count) is not int
                or type(false) is not int
                or not 0 <= false <= count
            ):
                raise ValueError("invalid_calibration_binomial_counts")
        if not self.signal_provenance or not self.supported_shapes:
            raise ValueError("calibration_requires_signal_family_and_shapes")
        if len(self.supported_shapes) != 1:
            raise ValueError("mixed_calibration_shapes")
        if not valid_round_alpha(self.round_no, self.alpha):
            raise ValueError("invalid_calibration_round_alpha_pair")

    @property
    def usable(self) -> bool:
        return (
            type(self.delta) is int
            and self.delta >= 0
            and self.sample_count >= 200
            and self.validation_count >= 200
            and self.calibration_false_positives / self.sample_count <= 0.05
            and self.validation_false_positives / self.validation_count <= 0.05
            and (self.rules_version, self.rules_hash) == rules_identity()
        )

    @property
    def fingerprint(self) -> str:
        return digest(self.__dict__)

    def covers(self, result: dict[str, Any]) -> bool:
        return (
            self.usable
            and valid_round_alpha(result.get("round"), result.get("alpha"))
            and (result["round"], result["alpha"]) == (self.round_no, self.alpha)
            and result["signal_provenance"] == self.signal_provenance
            and (result["candidate_count"], result["event_count"])
            in self.supported_shapes
        )


def _passes(result: dict[str, Any], delta: int) -> bool:
    return (
        result["p_value"] <= result["alpha"]
        and result["holdout"]["supported"]
        and result["unique_leader"]
        and result["margin"] >= delta
    )


def calibrate(
    calibration: list[dict[str, Any]], validation: list[dict[str, Any]]
) -> DeltaCalibration:
    if len(calibration) < 200 or len(validation) < 200:
        raise ValueError(
            "need_200_calibration_and_200_independent_validation_null_datasets"
        )
    identities = [row["session_fingerprint"] for row in calibration + validation]
    if len(set(identities)) != len(identities):
        raise ValueError("calibration_validation_overlap_or_duplicate_dataset")
    version, rule_hash = rules_identity()
    if any(
        (row["rules_version"], row["rules_hash"]) != (version, rule_hash)
        for row in calibration + validation
    ):
        raise ValueError("calibration_rules_mismatch")
    scope = calibration_scope(calibration + validation)
    choices = range(max(row["margin"] for row in calibration) + 2)
    delta = next(
        value
        for value in choices
        if sum(_passes(row, value) for row in calibration) / len(calibration) <= 0.05
    )
    return DeltaCalibration(
        delta=delta,
        sample_count=len(calibration),
        validation_count=len(validation),
        calibration_false_positives=sum(_passes(row, delta) for row in calibration),
        validation_false_positives=sum(_passes(row, delta) for row in validation),
        dataset_hash=calibration_dataset_hash(calibration + validation),
        rules_version=version,
        rules_hash=rule_hash,
        signal_provenance=scope.signal_provenance,
        supported_shapes=(scope.shape,),
        round_no=scope.round_no,
        alpha=scope.alpha,
    )


def evaluate(
    session: FrozenSession,
    cache: AnnualSignalCache,
    calibration: DeltaCalibration,
    round_no: int = 1,
) -> dict[str, Any]:
    from .envelope import conclusion_metadata, holdout_ranks
    from .signals import event_evidence

    result = assess_statistics(session, cache, round_no)
    covered = calibration.covers(result)
    passes = covered and _passes(result, calibration.delta)
    columns, events = json.loads(cache.columns_json), session.event_rows(round_no)
    ranks = holdout_ranks(result["holdout_scores"], result["holdout"]["used"])
    candidates = []
    for index, ident in enumerate(cache.candidate_ids):
        candidates.append(
            {
                "id": ident,
                **columns[ident],
                "train_score": result["train_scores"][index],
                "holdout_score": result["holdout_scores"][index],
                **ranks[index],
                "evidence": [
                    event_evidence(cache, index, event, result["annual_cache_hash"])
                    for event in events
                ],
            }
        )
    return dict(
        result,
        distinguishable=passes,
        conclusion="更倾向（推断，不是确认）" if passes else "分不出来",
        selected_candidate=result["training_leader"] if passes else None,
        candidates=candidates,
        **conclusion_metadata(columns, cache.candidate_ids),
        delta=calibration.delta,
        calibration_hash=calibration.fingerprint,
        calibration_usable=covered,
        model_calls=0,
        writes=0,
        method="rectification_rules v1",
        limits=[
            "只检验项目规则内的年份配合，不证明命理效度。",
            "少于6件不满足留出闸门；并列按最坏名次；第二轮已见过第一轮，不能当作独立外部验证。",
        ],
    )


def round2_prompt(session: FrozenSession, cache: AnnualSignalCache) -> dict[str, Any]:
    _validate_bindings(session, cache)
    if session.second:
        raise ValueError("maximum_two_rounds_no_more_followup")
    divergences = []
    for index, year in enumerate(cache.years):
        amount = sum(
            len({candidate[signal] for candidate in cache.values[index]}) - 1
            for signal in range(len(cache.signal_ids))
        )
        divergences.append((amount, -year))
    year = -max(divergences)[1]
    age = year - cache.birth_year
    lower, upper = max(6, age - 2), min(cache.as_of_year - cache.birth_year, age + 2)
    return {
        "round": 2,
        "age_range": [lower, upper],
        "selection": "maximum_precomputed_signal_disagreement",
        "question": (
            f"你在{lower}到{upper}岁这段时间，记得哪些事情、分别是哪一年？"
            "记得不确定也可以说。"
        ),
        "no_event_type_or_candidate_in_question": True,
    }
