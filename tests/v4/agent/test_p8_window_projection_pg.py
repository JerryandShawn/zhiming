"""R54: a full 31-day window_search page stays within the context budget, honestly truncated."""

from __future__ import annotations

import json
from pathlib import Path

from mingjing_core.agent.context_types import BudgetPolicy
from mingjing_core.agent.loop_codec import extend_aliases, tool_message
from mingjing_core.application.agent_p8_charts import WINDOW_HITS_PER_SIDE, tool_projection

from .test_p8_agent_charts_pg import repository  # noqa: F401
from .test_p8_date_tools_pg import begin

EVIDENCE = Path(__file__).resolve().parents[3] / "docs/v4/evidence/P8/window-projection-31day-20261030.json"
ARGS = {"start_date": "2026-10-21", "end_date": "2026-11-20", "purpose": "面试", "limit": 31}


def size(value) -> int:
    return len(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def test_thirty_one_day_page_projection_is_bounded_ordered_and_honest(repo):
    h, step, ctx = begin(repo, "window_search", "择日安排面试", ARGS)
    result = h.registry.execute("window_search", ARGS, ctx)
    assert result.ok
    h.journal.complete(step, result.model_dump())
    native = result.data["calculation"]["data"]
    assert native["pagination"]["returned"] == 31 and len(native["candidates"]) == 31

    projected = tool_projection(result.data)
    tool_data = projected["tool_data"]
    message = tool_message("window", result, "cycle", aliases=extend_aliases({}, [])).content

    # Nothing is re-scored or reordered; same days, same ranks and scores, same pagination.
    assert [(c["date"], c["rank"], c["score"]) for c in tool_data["candidates"]] == [
        (c["date"], c["rank"], c["score"]) for c in native["candidates"]
    ]
    assert tool_data["pagination"] == native["pagination"] and tool_data["range"] == native["range"]
    assert projected["limits"] and projected["arguments"] == ARGS | {"offset": 0} and projected["reference_views"]
    assert tool_data["method"]["election_hours_searched"] is False and tool_data["method"]["sample_clock"]

    truncated = False
    for source, kept in zip(native["candidates"], tool_data["candidates"], strict=True):
        assert len(kept["positive_hits"]) <= WINDOW_HITS_PER_SIDE and len(kept["negative_hits"]) <= WINDOW_HITS_PER_SIDE
        # Negative evidence is never dropped silently when it exists.
        assert bool(kept["negative_hits"]) == bool(source["negative_hits"])
        worst = sorted(source["negative_hits"], key=lambda hit: (hit["contribution"], hit["rule_hit_index"]))
        assert kept["negative_hits"] == worst[: len(kept["negative_hits"])]
        best = sorted(source["positive_hits"], key=lambda hit: (-hit["contribution"], hit["rule_hit_index"]))
        assert kept["positive_hits"] == best[: len(kept["positive_hits"])]
        assert kept["omitted"] == {
            "positive_hits": max(0, len(source["positive_hits"]) - WINDOW_HITS_PER_SIDE),
            "negative_hits": max(0, len(source["negative_hits"]) - WINDOW_HITS_PER_SIDE),
            "neutral_hits": len(source["neutral_hits"]),
        }
        truncated = truncated or any(kept["omitted"].values())
    assert truncated and tool_data["projection_truncated"] is True and tool_data["omitted_observations"] > 0

    # Only hits that survive in the projection can be referenced from it.
    visible = {hit["rule_hit_index"] for day in tool_data["candidates"] for key in ("positive_hits", "negative_hits") for hit in day[key]}
    all_hits = {hit["rule_hit_index"] for day in native["candidates"] for key in ("positive_hits", "negative_hits", "neutral_hits") for hit in day[key]}
    assert visible < all_hits
    dropped = all_hits - visible
    assert not any(f'"rule_hit_index":{index},' in json.dumps(tool_data, ensure_ascii=False, separators=(",", ":")) for index in dropped)

    hard_max = BudgetPolicy().hard_max
    before, after = size(native), size(tool_data)
    full_message = size(json.loads(message))
    assert after < before / 10 and full_message < hard_max
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(
        json.dumps(
            {
                "range": native["range"],
                "pagination": native["pagination"],
                "native_tool_data_bytes": before,
                "projected_tool_data_bytes": after,
                "tool_message_bytes": full_message,
                "policy_units_equal_serialized_bytes": True,
                "hard_max": hard_max,
                "target": BudgetPolicy().target,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
