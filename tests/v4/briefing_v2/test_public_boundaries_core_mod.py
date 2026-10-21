"""Thirty frozen public scenarios; malformed host proofs never justify raw errors or current-source ambiguity."""

import copy
import json
from dataclasses import replace
from datetime import datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from brief_public_support_core_mod import MATRIX, current_items, payload, reissue, resolve, text, values

from mingjing_core.application.briefing_v2 import BriefingError, calendar_snapshot, compose_briefing
from mingjing_core.streaming.json_values import thaw_json


class NaiveClock:
    def now(self) -> datetime:
        return datetime(2026, 10, 21, 7)


def test_bp00_positive_public_p2_and_three_daily_systems_have_bound_basis_and_zero_effects() -> None:
    raw = payload()
    before = copy.deepcopy(raw)
    setup = values(raw)
    result = compose_briefing(**setup)
    section = next(section for section in result.sections if section.id == "transit")
    assert len(section.lines) == 3 and all("12:00" in line.text for line in section.lines)
    assert all(ref.document_id == raw["document_id"] and ref.claim_id for line in section.lines for ref in line.basis)
    assert result.effects.notifications == result.effects.writes == result.effects.model_calls == 0 and raw == before
    term = setup["calendar"].almanac["jieqi"]
    assert term["days_to_next"] == (datetime.fromisoformat(term["next_at"]).date() - setup["calendar"].day).days
    assert len(json.loads(MATRIX.read_bytes())["cases"]) == 30


@pytest.mark.parametrize("case", [f"BC{index:02}" for index in range(1, 12)])
def test_public_calendar_malformed_snapshot_has_a_fixed_domain_error(case: str) -> None:
    setup = values()
    with pytest.raises(BriefingError) as caught:
        malformed_calendar(case, setup)
    assert "Synthetic/NoSuchZone" not in str(caught.value)


def malformed_calendar(case: str, setup: dict[str, Any]) -> Any:
    snapshot = setup["calendar"]
    almanac = thaw_json(snapshot.almanac)
    if case == "BC01":
        return replace(snapshot, day=datetime.combine(snapshot.day, time()))
    if case == "BC02":
        return replace(snapshot, observed_at=snapshot.observed_at + timedelta(days=1))
    if case == "BC03":
        almanac["weekday"] = "weekday-does-not-match"
    elif case == "BC04":
        return replace(snapshot, day_status=replace(snapshot.day_status, is_off=True))
    elif case == "BC05":
        return replace(snapshot, day_status=replace(snapshot.day_status, kind="unknown"))
    elif case == "BC06":
        almanac["festivals"].append(1)
    elif case == "BC07":
        almanac["lunar"].pop("is_leap")
    elif case == "BC08":
        almanac["lunar"]["is_leap"] = "false"
    elif case == "BC09":
        next_day = datetime.fromisoformat(almanac["jieqi"]["next_at"]).astimezone(ZoneInfo(snapshot.timezone)).date()
        almanac["jieqi"]["days_to_next"] = (next_day - snapshot.day).days + 1
    elif case == "BC10":
        return calendar_snapshot(scope=setup["scope"], clock=NaiveClock())
    elif case == "BC11":
        return calendar_snapshot(scope=setup["scope"], clock=setup["clock"], timezone="Synthetic/NoSuchZone")
    return replace(snapshot, almanac=almanac)


@pytest.mark.parametrize("case", [f"BE{index:02}" for index in range(1, 9)])
def test_malformed_p8_document_is_omitted_despite_a_current_binding(case: str) -> None:
    raw = payload()
    if case == "BE01":
        raw["sources"] = raw["sources"][:2]
    elif case == "BE02":
        raw["limits"] = []
    elif case == "BE03":
        raw["rule_hits"] = {}
    elif case == "BE04":
        raw["rule_hits"][0]["undefined_field"] = 1
    elif case == "BE05":
        raw["rule_hits"][0]["source"] = {}
    elif case == "BE06":
        raw["rule_hits"][0]["context"]["system"] = "unsupported-system"
    elif case == "BE07":
        raw["rule_hits"][0]["evidence_paths"].append(raw["rule_hits"][0]["evidence_paths"][0])
    elif case == "BE08":
        raw["rule_hits"][0]["evidence_paths"] = ["/scope/revision"]
    raw = reissue(raw)
    result = compose_briefing(**values(raw))
    assert result.warnings and any(section.id == "calendar" for section in result.sections)
    assert all(ref.document_id != raw["document_id"] for ref in result.basis)
    assert result.effects.notifications == result.effects.writes == 0


@pytest.mark.parametrize("case", [f"BT{index:02}" for index in range(1, 9)])
def test_bad_or_unsupported_rule_never_renders_a_claim_or_raises_an_uncontrolled_error(case: str) -> None:
    raw = malformed_rule(case)
    bad_claim = raw["aliases"]["r"][0]["claim_id"]
    try:
        result = compose_briefing(**values(raw))
    except BriefingError:
        return
    assert all(ref.claim_id != bad_claim for ref in result.basis)
    assert result.warnings and result.effects.notifications == result.effects.writes == 0


def malformed_rule(case: str) -> dict[str, Any]:
    kind = {"BT01": "ten_god", "BT02": "relation", "BT03": "ten_god", "BT04": "ziwei", "BT05": "ziwei"}
    raw = payload(kind.get(case, "astro"))
    hit = raw["rule_hits"][0]
    context = hit["context"]
    evidence = resolve(raw, hit["evidence_paths"][0])
    if case == "BT01":
        raw["data"]["bazi"]["snapshot"]["day"] = 7
    elif case == "BT02":
        context["complete"] = evidence["complete"] = "false"
    elif case == "BT03":
        context["layer"] = "natal"
    elif case in {"BT04", "BT05"}:
        links = raw["data"]["ziwei"]["transformations"]["daily"]["links"]
        link = next(link for link in links if link["mutagen"] == context["mutagen"])
        if case == "BT04":
            link["status"] = "unresolved"
        else:
            context["palace_index"] = (context["palace_index"] + 1) % 12
    elif case == "BT06":
        context["orb_degrees"] = evidence["orb_degrees"] = False
    elif case == "BT07":
        evidence["angle"] += 1
    elif case == "BT08":
        raw["data"]["astro"]["orb_limit_degrees"] = context["orb_limit"] + 1
    return reissue(raw)


@pytest.mark.parametrize("case", ["BS01", "BS02"])
def test_one_batch_cannot_use_contradictory_current_states_for_one_source(case: str) -> None:
    setup = values()
    entries = current_items(case, setup["scope"])
    try:
        result = compose_briefing(**dict(setup, items=entries))
    except BriefingError as error:
        assert all(item.request.candidate.text not in str(error) for item in entries)
        return
    assert all(ref.source_id != "synthetic-shared-source" for ref in result.basis)
    assert all(item.request.candidate.text not in text(result) for item in entries)
