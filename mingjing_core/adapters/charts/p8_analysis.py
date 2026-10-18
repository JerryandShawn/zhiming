"""Attach program-ordered time interactions and condition hits to one P8 chart."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .interactions_bazi import bazi_interactions
from .named_bazi import hidden_for, options
from .rules import evaluate_rules


def attach_analysis(data: dict[str, Any]) -> None:
    p8 = data["p8"]
    snapshot = p8["calendar_layers"]["day"]
    layers = {label: snapshot[key]["ganzhi"] for key, label in (("year", "yearly"), ("month", "monthly"))}
    layers["daily"] = snapshot["day"]["ganzhi"]
    sample = datetime.fromisoformat(snapshot["sample_at"])
    decade = next(
        (
            row
            for row in p8["decade_luck"]["decades"]
            if datetime.fromisoformat(row["nominal_start_at"])
            <= sample
            < datetime.fromisoformat(row["nominal_end_exclusive"])
        ),
        None,
    )
    if decade:
        layers["decadal"] = decade["ganzhi"]
    selected = {key: value for key, value in p8["selected_schools"].items() if key != "hidden_order"}
    p8["time_interactions"] = bazi_interactions(
        {key: row["ganzhi"] for key, row in data["pillars"].items()},
        layers,
        hidden_stems=hidden_for(options(selected)),
    )
    evaluated = evaluate_rules(data, graph=p8["time_interactions"])
    p8.update(
        rule_hits=evaluated["rule_hits"], rule_assessments=evaluated["assessments"], rules_version=evaluated["version"]
    )
