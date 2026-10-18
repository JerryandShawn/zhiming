"""Cross-check skill JSON Pointers against actual chart engines and public draw serialization."""

from __future__ import annotations

import importlib.resources
import importlib.util
import os
from copy import deepcopy
from typing import Any

import pytest

from hermes.tarot_deck import DECK_VERSION, MEANING_VERSION, SPREADS, card
from mingjing_core.adapters.charts.p8_adapter import P8ChartAdapter
from mingjing_core.adapters.charts.profile_draft import profile_proposal
from mingjing_core.adapters.tarot import TarotService
from mingjing_core.skills import SkillLibrary


def pointer(value: Any, path: str) -> Any:
    for part in path.split("/")[1:]:
        key = part.replace("~1", "/").replace("~0", "~")
        value = value[int(key)] if isinstance(value, list) else value[key]
    return value


def sample_archive() -> dict[str, Any]:
    return {
        "owner_user_id": "synthetic-skills-owner",
        "subject_id": "synthetic-skills-subject",
        "user": {
            "gender": "男",
            "birth": {
                "solar_datetime": "2000-06-15 10:30",
                "timezone_offset": 8,
                "time_precision": "exact",
                "location": {"lng": 120, "lat": 30},
            },
        },
    }


@pytest.mark.parametrize("system", ["bazi", "ziwei", "astro"])
def test_artifact_pointer_requirements_exist_in_real_isolated_engine_output(
    system: str,
) -> None:
    adapter = P8ChartAdapter(
        "synthetic-skills-owner", python=os.environ["CHART_PYTHON"]
    )
    result = adapter.calculate(
        sample_archive(), "2026-10-18", [system], 1, "synthetic-skills-subject"
    )
    assert not result["errors"], result["errors"]
    artifact = next(iter(result["artifacts"].values()))
    for chapter in SkillLibrary().chapters(system):
        if chapter["artifact_root"] == "CalculationArtifact":
            for path in chapter["required_fields"]:
                pointer(artifact, path)
    if system == "bazi":
        proposed = profile_proposal(
            result, "synthetic-skills-owner", "synthetic-skills-subject", 1
        )
        for chapter in SkillLibrary().chapters("bazi"):
            for interface in chapter.get("additional_interfaces", []):
                for path in interface["paths"]:
                    pointer(proposed, path)
        assert proposed["status"] == "calculation_proposal_not_persisted"
        assert proposed["writes"] == 0


def test_optional_transit_skill_paths_match_explicit_interval_artifact() -> None:
    adapter = P8ChartAdapter(
        "synthetic-skills-owner",
        python=os.environ["CHART_PYTHON"],
        transit_period={
            "start_at": "2026-06-12T00:00:00+08:00",
            "end_at": "2026-06-18T00:00:00+08:00",
            "moving_bodies": ["太阳"],
        },
    )
    result = adapter.calculate(
        sample_archive(), "2026-06-15", ["astro"], 1, "synthetic-skills-subject"
    )
    assert not result["errors"], result["errors"]
    artifact = next(iter(result["artifacts"].values()))
    chapter = next(
        row
        for row in SkillLibrary().chapters("astro")
        if row["topic"] == "transits-progressions"
    )
    for capability in chapter["conditional_fields"]:
        for path in capability["paths"]:
            pointer(artifact, path)
    assert artifact["data"]["p8_transit_windows"]["windows"]
    assert any(
        item["feature_key"] == "astro.p8_transit_windows"
        and item["time_scale"] == "transit_interval"
        for item in result["features"].values()
    )


def test_tarot_pointer_requirements_match_actual_public_view_serializer() -> None:
    # Only the real pure serializer is exercised: no substitute database/service.
    selected = {
        "position": 1,
        "label": SPREADS["focus1"]["positions"][0],
        "back_id": "opaque-synthetic-back",
        "revealed": True,
        "card_id": "cups-11",
        "orientation": "upright",
        "card_snapshot": card("cups-11"),
    }
    payload = {
        "question": "合成的行动反思",
        "spread": deepcopy(SPREADS["focus1"]),
        "deck_version": DECK_VERSION,
        "meaning_version": MEANING_VERSION,
        "draw_source": "auto",
        "reversals": True,
        "status": "ready",
        "context_snapshot": {},
        "selected": [selected],
        "revision": 1,
        "previous_draw_id": None,
    }
    row = {
        "id": "synthetic-draw",
        "subject": "synthetic-subject",
        "case_id": "case",
        "stage": "open",
    }
    row.update(payload=payload, private_deck=[selected])
    public = TarotService(None)._viewer(row)
    for chapter in SkillLibrary().chapters("tarot"):
        for path in chapter["required_fields"]:
            pointer(public, path)


def test_time_basis_pointer_requirements_match_real_read_only_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A test-only bridge to the locked Core tzdata; no production fallback/install.
    if importlib.util.find_spec("tzdata"):
        monkeypatch.setenv(
            "PYTHONTZPATH", str(importlib.resources.files("tzdata.zoneinfo"))
        )
    request = {
        "owner_user_id": "synthetic-skills-owner",
        "subject_id": "synthetic-skills-subject",
        "operation_id": "skills-time-basis-interface-check",
        "revision": 1,
        "as_of_date": "2026-10-18",
        "birth": {
            "date": "2000-06-15",
            "reported_time": "10:30",
            "precision": "reported",
            "clock_basis": "clock",
            "gender": "男",
            "place": {"tz": "Asia/Shanghai", "lon": 120, "lat": 30},
        },
    }
    adapter = P8ChartAdapter(
        "synthetic-skills-owner", python=os.environ["CHART_PYTHON"]
    )
    result = adapter.time_basis(request)
    for chapter in SkillLibrary().chapters("bazi"):
        if chapter["artifact_root"] == "P8ChartAdapter.time_basis read-only envelope":
            for path in chapter["required_fields"]:
                pointer(result, path)
    assert result["version"] == "p8-time-basis-readonly-v1"
    assert result["profile_update_allowed"] is False
    assert result["life_event_scoring_performed"] is False
    assert result["writes"] == result["model_calls"] == 0
    assert result["time_basis"]["items"] and result["charts"]
