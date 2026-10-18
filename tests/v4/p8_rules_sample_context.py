"""Synthetic independent-pillar fixtures; never a real birth or a prediction."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from mingjing_core.adapters.charts.interactions_bazi import bazi_interactions
from mingjing_core.adapters.charts.named_bazi import hidden_for, named_ten_gods, options
from mingjing_core.adapters.charts.named_strength import named_patterns, named_scores
from mingjing_core.calculations.bazi.elements import table, validate_pillars

SELECTED = options()
HIDDEN = hidden_for(SELECTED)
CLIMATE = table("climate")["rows"]


def make_data(
    pillars: dict[str, str], layers: dict[str, str] | None = None
) -> dict[str, Any]:
    validate_pillars(pillars)
    strength = named_scores(pillars, HIDDEN)
    graph = (
        bazi_interactions(pillars, layers, hidden_stems=HIDDEN)
        if layers
        else {"relations": []}
    )
    return {
        "pillars": {key: {"ganzhi": value} for key, value in pillars.items()},
        "p8": {
            "ten_gods": named_ten_gods(pillars, HIDDEN, SELECTED),
            "strength": strength,
            "patterns": named_patterns(pillars, HIDDEN, strength),
            "climate": deepcopy(CLIMATE[pillars["day"][0] + pillars["month"][1]]),
            "time_interactions": graph,
        },
    }
