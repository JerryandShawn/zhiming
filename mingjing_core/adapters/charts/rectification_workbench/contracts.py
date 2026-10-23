"""Versioned rules and immutable annual signal caches for the evidence workbench."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Any

RULE_PATH = (
    Path(__file__).resolve().parents[3] / "knowledge/rectification_rules_v1.json"
)


def canonical(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def rules() -> dict[str, Any]:
    value = json.loads(RULE_PATH.read_text(encoding="utf-8"))
    if (
        value["system"] != "bazi"
        or value["permutations"] != 1000
        or value["alpha"] != {"1": 0.05, "2": 0.025}
    ):
        raise ValueError("invalid_frozen_statistical_rules")
    for kind, mappings in value["event_rules"].items():
        if kind not in value["age_intervals"] or not mappings:
            raise ValueError("missing_event_age_interval_or_mapping")
        for item in mappings:
            if (
                item["system"] != "bazi"
                or type(item["weight"]) is not int
                or item["weight"] < 0
            ):
                raise ValueError("cross_system_or_invalid_weight")
    return value


def rules_identity() -> tuple[str, str]:
    value = rules()
    return value["version"], digest(value)


@dataclass(frozen=True)
class AnnualSignalCache:
    candidate_ids: tuple[str, ...]
    years: tuple[int, ...]
    signal_ids: tuple[str, ...]
    values: tuple[tuple[tuple[int, ...], ...], ...]
    columns_json: str
    evidence_json: str
    scope: tuple[str, str, int]
    rules_version: str
    rules_hash: str
    birth_year: int
    as_of_year: int
    provenance: str

    def __post_init__(self) -> None:
        if (
            len(set(self.candidate_ids)) != len(self.candidate_ids)
            or len(self.candidate_ids) < 2
        ):
            raise ValueError("need_two_or_more_unique_candidates")
        expected = tuple(range(self.birth_year + 6, self.as_of_year + 1))
        if not expected or self.years != expected or len(self.values) != len(expected):
            raise ValueError("annual_cache_must_cover_birth_plus_six_through_asof")
        if len(set(self.signal_ids)) != len(self.signal_ids):
            raise ValueError("duplicate_signal_id")
        for year in self.values:
            if len(year) != len(self.candidate_ids):
                raise ValueError("candidate_vector_shape_mismatch")
            for row in year:
                if len(row) != len(self.signal_ids) or any(
                    type(x) is not int or x not in (0, 1) for x in row
                ):
                    raise ValueError("signal_vectors_must_be_binary")
        if (self.rules_version, self.rules_hash) != rules_identity():
            raise ValueError("annual_cache_rules_version_mismatch")

    @cached_property
    def fingerprint(self) -> str:
        return digest(
            [
                self.candidate_ids,
                self.years,
                self.signal_ids,
                self.values,
                self.columns_json,
                self.evidence_json,
                self.scope,
                self.rules_hash,
                self.provenance,
            ]
        )

    def score_tables(self) -> dict[str, tuple[tuple[int, ...], ...]]:
        indices = {name: index for index, name in enumerate(self.signal_ids)}
        result: dict[str, tuple[tuple[int, ...], ...]] = {}
        for kind, items in rules()["event_rules"].items():
            if any(item["signal"] not in indices for item in items):
                raise ValueError("cache_missing_required_rule_signals")
            weights = [(indices[item["signal"]], item["weight"]) for item in items]
            result[kind] = tuple(
                tuple(sum(row[i] * weight for i, weight in weights) for row in year)
                for year in self.values
            )
        return result
