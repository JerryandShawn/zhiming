"""Real native proposals/receipts with text-only model output, never fake DB effects."""

from datetime import datetime

import pytest

from mingjing_core.timekit.clock import FrozenClock, get_clock, set_clock

from mingjing_core.application.agent_finalization import AgentFinalizer
from mingjing_core.application.agent_sensitive_pending import _sensitive_span
from tools.eval.engine import evaluate_scenario
from tools.eval.schema import Scenario, load_scenario
from tools.eval.targets.v4_corpus import execution_overlay
from tools.eval.targets.v4_target import V4Target

TEXT = "听起来最近不容易。治疗和用药请跟医生商量；这条信息要记住吗？"


def scenario(user="我被诊断出焦虑症了，最近在吃药", level="health", *, incognito=False):
    value = execution_overlay(
        load_scenario("tools/eval/scenarios/M05.yaml")
    ).model_dump(mode="json")
    value["turns"][0]["user"] = user
    value["seed"]["incognito"] = incognito
    value["turns"][0]["expect"]["db"][0]["where"] = {"data.sensitivity": level}
    value["scripted"] = [{"turn": 1, "model": [{"text": TEXT}]}]
    return Scenario.model_validate(value)


@pytest.mark.parametrize(
    "user,level",
    [
        ("我被诊断出焦虑症了，最近在吃药", "health"),
        ("我妈妈确诊了糖尿病", "third_party"),
        ("我的工资是12000元", "money"),
    ],
)
def test_text_only_model_creates_native_pending_once_and_keeps_answer(user, level):
    target = V4Target()
    try:
        result = evaluate_scenario(scenario(user, level), target, target_name="v4")
        assert result["status"] == "passed", result["failed_assertions"]
        run = target.repo.fetch_run(target.owner, target.run_ids[-1])
        assert run["result"]["text"] == TEXT
        assert run["result"]["receipts"][0]["write_status"] == "pending_confirmation"
        proposals = target.repo.list(target.owner, "proposal")
        assert len(proposals) == 1 and proposals[0]["sensitivity"] == level
        assert proposals[0]["source_refs"][0]["quote"] == user
        source_id = proposals[0]["source_refs"][0]["message_id"]
        assert not any(
            source_id in fact.get("source_ids", [])
            for fact in target.repo.list(target.owner, "fact")
        )
        # A repeated completed run reads the same committed result, no extra proposal.
        again = target.runtime.execute(
            target.service, target.owner, run["id"], "old-token"
        )
        assert (
            again == run["result"]
            and len(target.repo.list(target.owner, "proposal")) == 1
        )
    finally:
        target.close()


@pytest.mark.parametrize(
    "text",
    [
        "不要保存，我被诊断出焦虑症",
        "假如我被诊断出焦虑症怎么办",
        "朋友说：‘我确诊了焦虑症’",
        "这本书写着“诊断焦虑症”",
        "收入可能会增加",
        "我同事今天去上班",
        "我的密码是abcdef，最近吃药",
    ],
)
def test_sensitive_span_refuses_optout_hypothetical_quotes_and_unrelated(text):
    assert _sensitive_span(text) is None


def test_incognito_never_creates_pending():
    target = V4Target()
    try:
        evaluate_scenario(scenario(incognito=True), target, target_name="v4")
        assert not target.repo.list(target.owner, "proposal")
    finally:
        target.close()


def test_original_model_write_does_not_add_system_duplicate():
    target = V4Target()
    try:
        case = execution_overlay(load_scenario("tools/eval/scenarios/M05.yaml"))
        result = evaluate_scenario(case, target, target_name="v4")
        assert result["status"] == "passed", result["failed_assertions"]
        assert len(target.repo.list(target.owner, "proposal")) == 1
        run = target.repo.fetch_run(target.owner, target.run_ids[-1])
        assert not run["result"]["usage"].get("sensitive_pending_fallback")
    finally:
        target.close()


def test_pending_before_finalization_replays_without_duplicate_effect(monkeypatch):
    target = V4Target()
    original = AgentFinalizer.finalize
    seen = []

    def crash_once(self, *args, **kwargs):
        seen.append(True)
        if len(seen) == 1:
            raise RuntimeError("synthetic-after-tool-crash")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(AgentFinalizer, "finalize", crash_once)
    try:
        result = evaluate_scenario(scenario(), target, target_name="v4")
        assert result.get("target_error_code") == "RuntimeError"
        run = target.repo.fetch_run(target.owner, target.run_ids[-1])
        assert len(target.repo.list(target.owner, "proposal")) == 1
        previous = get_clock()
        try:
            set_clock(FrozenClock(datetime.fromisoformat(scenario().clock)))
            envelope = target.runtime.execute(
                target.service, target.owner, run["id"], run["lease_token"]
            )
        finally:
            set_clock(previous)
        assert envelope["text"] == TEXT
        assert (
            len(envelope["receipts"]) == 1
            and len(target.repo.list(target.owner, "proposal")) == 1
        )
    finally:
        target.close()


@pytest.mark.parametrize(
    "user",
    [
        "不要保存，我被诊断出焦虑症",
        "假如我被诊断出焦虑症怎么办",
        "朋友说：‘我确诊了焦虑症’",
    ],
)
def test_actual_pg_privacy_refusals_remain_without_pending(user):
    target = V4Target()
    try:
        evaluate_scenario(scenario(user), target, target_name="v4")
        assert not target.repo.list(target.owner, "proposal")
        run = target.repo.fetch_run(target.owner, target.run_ids[-1])
        assert not run["result"]["receipts"]
        assert run["result"]["text"] == TEXT
    finally:
        target.close()


def test_native_forget_does_not_repropose_deleted_health():
    target = V4Target()
    try:
        case = execution_overlay(load_scenario("tools/eval/scenarios/F02.yaml"))
        result = evaluate_scenario(case, target, target_name="v4")
        assert result["status"] == "passed", result["failed_assertions"]
        assert not target.repo.list(target.owner, "proposal")
        run = target.repo.fetch_run(target.owner, target.run_ids[-1])
        assert not run["result"]["usage"].get("sensitive_pending_fallback")
    finally:
        target.close()


def test_text_only_forget_does_not_create_pending():
    target = V4Target()
    try:
        evaluate_scenario(scenario("把我焦虑症的事忘了"), target, target_name="v4")
        assert not target.repo.list(target.owner, "proposal")
        run = target.repo.fetch_run(target.owner, target.run_ids[-1])
        assert not run["result"]["receipts"]
        assert run["result"]["text"] == TEXT
    finally:
        target.close()
