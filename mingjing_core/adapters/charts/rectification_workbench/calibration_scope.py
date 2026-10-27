"""Calibration applies to one frozen test threshold and one candidate/event shape."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .contracts import digest, rules


def valid_round_alpha(round_no: Any, alpha: Any) -> bool:
    return (
        type(round_no) is int
        and round_no in (1, 2)
        and type(alpha) in (int, float)
        and alpha == rules()["alpha"][str(round_no)]
    )


@dataclass(frozen=True)
class CalibrationScope:
    round_no: int
    alpha: float
    signal_provenance: str
    shape: tuple[int, int]


def calibration_scope(rows: list[dict[str, Any]]) -> CalibrationScope:
    if any(not valid_round_alpha(row.get("round"), row.get("alpha")) for row in rows):
        raise ValueError("invalid_calibration_round_alpha_pair")
    thresholds = {(row["round"], row["alpha"]) for row in rows}
    if len(thresholds) != 1:
        raise ValueError("mixed_calibration_rounds_or_alpha")
    provenance = {row["signal_provenance"] for row in rows}
    if len(provenance) != 1:
        raise ValueError("mixed_calibration_signal_families")
    shapes = {(row["candidate_count"], row["event_count"]) for row in rows}
    if len(shapes) != 1:
        raise ValueError("mixed_calibration_shapes")
    round_no, alpha = next(iter(thresholds))
    return CalibrationScope(round_no, alpha, next(iter(provenance)), next(iter(shapes)))


def calibration_dataset_hash(rows: list[dict[str, Any]]) -> str:
    keys = (
        "session_fingerprint",
        "events_hash",
        "annual_cache_hash",
        "p_value",
        "margin",
        "holdout",
        "round",
        "alpha",
        "signal_provenance",
        "candidate_count",
        "event_count",
    )
    return digest([{key: row[key] for key in keys} for row in rows])
