"""Batch 3 review_mode: off never calls the critic, risk routes by 44 §2, always keeps P3 behavior."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from mingjing_core.application import agent_review
from mingjing_core.application.agent_review import AgentReviewer
from mingjing_core.application.release_switches import load_switches, validate_switches
from mingjing_core.domain.contracts import EvidenceError


class ExplodingPort:
    offline = True

    def complete(self, *args, **kwargs):
        raise AssertionError("critic must not be called")


def reviewer(mode: str) -> AgentReviewer:
    ledger = SimpleNamespace(repo=object())
    return AgentReviewer(ExplodingPort(), ledger, SimpleNamespace(), offline=True, review_mode=mode)


def outcome(text: str, *, aliases=None, receipts=()):
    return SimpleNamespace(
        text=text, alias_map=aliases or {}, receipts=receipts, asked=None, stop_reason="completed"
    )


def cycle():
    return SimpleNamespace(run={}, last_step=object(), emit=None)


@pytest.fixture(autouse=True)
def no_options(monkeypatch):
    monkeypatch.setattr(agent_review, "load_options", lambda repo, run: None)


def test_unknown_mode_is_rejected():
    with pytest.raises(EvidenceError):
        reviewer("sometimes")


def test_off_never_wants_and_review_returns_untouched_without_calling_critic():
    r = reviewer("off")
    draft = outcome("这是一个很长的回答。" * 100, aliases={"c1": {}})
    assert r._wanted(cycle(), draft) is False
    result, receipt = r.review(cycle(), draft)
    assert result is draft and receipt is None


def test_always_wants_everything():
    assert reviewer("always")._wanted(cycle(), outcome("你好")) is True


@pytest.mark.parametrize(
    "text, kwargs, expected",
    [
        ("你好，今天过得怎么样？", {}, False),
        ("明天 2026-11-02 适合开会。", {}, True),  # concrete date
        ("你的八字显示日主偏弱。", {}, True),  # chart words
        ("好的。", {"aliases": {"c1": {"kind": "claim"}}}, True),  # evidence aliases
        ("好的。", {"receipts": ({"write_status": "saved"},)}, True),  # memory write
        ("好的。", {"receipts": ({"kind": "chart"},)}, False),  # a receipt without a write
        ("请遵医嘱调整用药。", {}, True),  # health
        ("字" * 401, {}, True),  # long answer
        ("字" * 400, {}, False),
    ],
)
def test_risk_routes_by_reviewable_risk(text, kwargs, expected):
    assert reviewer("risk")._wanted(cycle(), outcome(text, **kwargs)) is expected


def test_risk_reviews_decision_cards(monkeypatch):
    monkeypatch.setattr(agent_review, "load_options", lambda repo, run: SimpleNamespace(value={"options": []}))
    assert reviewer("risk")._wanted(cycle(), outcome("好的。")) is True


def test_checked_in_switches_default_to_streaming_on_review_off_proactive_off():
    switches = load_switches()
    assert (switches.streaming_v2, switches.review_mode, switches.proactive) == (True, "off", False)


@pytest.mark.parametrize(
    "value",
    [
        {"version": 1, "streaming_v2": "yes", "review_mode": "off", "proactive": False},
        {"version": 1, "streaming_v2": True, "review_mode": "maybe", "proactive": False},
        {"version": 1, "streaming_v2": True, "review_mode": "off", "proactive": False, "extra": 1},
        {"version": 2, "streaming_v2": True, "review_mode": "off", "proactive": False},
    ],
)
def test_switches_reject_loose_or_unknown_values(value):
    with pytest.raises(EvidenceError):
        validate_switches(value)
