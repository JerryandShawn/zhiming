"""Synthetic action driver exercises real P3 authority instead of declared script DB state."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from pathlib import Path

import pytest

from mingjing_core.application.memory2_consent import consent_live
from mingjing_core.domain.contracts import EvidenceError
from mingjing_core.timekit.clock import FrozenClock, get_clock, set_clock
from tools.eval.contracts import scenario_contract_hash
from tools.eval.schema import load_scenarios
from tools.eval.targets.v4_corpus import execution_overlay
from tools.eval.targets.v4_target import V4Target

from .test_eval_v4_pg import target as base_target


@pytest.fixture(name="target")
def action_target(monkeypatch: pytest.MonkeyPatch):
    yield from base_target.__wrapped__(monkeypatch)


@pytest.fixture
def pending_target(target: V4Target):
    original = next(c for c in load_scenarios(Path("tools/eval/scenarios")) if c.id == "M08")
    case = execution_overlay(original)
    assert scenario_contract_hash(original) == scenario_contract_hash(case)
    previous = get_clock()
    set_clock(FrozenClock(datetime.fromisoformat(case.clock)))
    seed = case.seed.model_dump(mode="json")
    seed.update(
        _scenario_id=case.id, _clock=case.clock, _scripted=[s.model_dump(exclude_none=True) for s in case.scripted]
    )
    try:
        target.reset(seed)
        payload = case.turns[0].model_dump(mode="json", exclude={"expect"}, exclude_none=True)
        yield target, {**payload, "_index": 1}
    finally:
        set_clock(previous)


def test_category_action_preserves_real_approval_and_replays_without_writes(pending_target: tuple) -> None:
    target, turn = pending_target
    assert target.memory_actions.setup_calls == 2
    assert target.repo.list(target.owner, "fact")
    ident = target.memory_actions.ids["health-proposal"]
    proposal = target.repo.get(target.owner, "proposal", ident)
    assert proposal["status"] == "pending"
    source_id = proposal["source_refs"][0]["message_id"]
    assert source_id == target.seeder.ids["health-source"]
    result = target.send(turn)
    receipt = result.receipts[0]
    fact = target.repo.get(target.owner, "fact", receipt["fact_id"])
    proof = target.repo.get(target.owner, "consent", fact["approval_consent_id"])
    assert consent_live(target.service.memory, target.owner, "self", proof)
    assert fact["source_refs"][0]["message_id"] == source_id
    assert fact["source_refs"][1]["quote"] == turn["user"] == "以后这类都记"
    assert result.model_calls == 0
    assert result.events == ["consent.category_updated"]
    before = target.repo.get_revision(target.owner)
    assert target.send(turn).receipts == result.receipts
    assert target.repo.get_revision(target.owner) == before
    db = target.inspect_db()
    assert db["owner_settings"] == db["settings"]
    assert db["owner_settings"]["auto_save_categories"] == ["health"]


@pytest.mark.parametrize("change", ["category", "proposal", "phrase"])
def test_actions_cannot_expand_selected_proposal_authority(pending_target: tuple, change: str) -> None:
    target, original = pending_target
    turn = deepcopy(original)
    if change == "category":
        turn["action"]["auto_save_category"] = "money"
    elif change == "proposal":
        turn["action"]["proposal_id"] = "unselected"
    else:
        turn["user"] = "也许以后再说"
    before = len(target.repo.list(target.owner, "fact"))
    with pytest.raises((ValueError, EvidenceError)) as caught:
        target.send(turn)
    assert type(caught.value).__name__ in {"ValueError", "EvidenceError"}
    assert target.repo.assert_scope(target.owner)["settings"].get("auto_save_categories", []) == []
    assert len(target.repo.list(target.owner, "fact")) == before
    assert target.repo.list(target.owner, "consent") == []
