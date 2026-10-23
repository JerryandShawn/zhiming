"""Original forgetting is authorized by actual user wording and unambiguous facts."""

from pathlib import Path

import pytest

from mingjing_core.application.memory import MemoryService
from mingjing_core.application.v4_forget import retire_from_message
from mingjing_core.domain.contracts import EvidenceError
from tools.eval.engine import evaluate_scenario
from tools.eval.schema import load_scenarios
from tools.eval.targets.v4_corpus import execution_overlay

from .test_eval_v4_native_privacy_pg import target as target

__all__ = ["target"]

ROOT = Path(__file__).resolve().parents[3]


def test_f02_original_contract_reads_real_search_and_nonempty_proposal_and_assistant_lineage(target):
    original = next(case for case in load_scenarios(ROOT / "tools/eval/scenarios") if case.id == "F02")
    result = evaluate_scenario(execution_overlay(original), target, target_name="v4")
    assert result["status"] == "passed", result["failed_assertions"]
    observed = target.inspect_db()
    assert observed["run_meta"]["privacy_initial_layers"] == {"proposal": 1}
    assert [step["name"] for step in observed["observed_tools"]] == ["memory_search", "memory_forget"]
    assistant = next(row for row in observed["entities"] if row["id"] == "anxiety-assistant")
    assert assistant["data"]["redacted"] is True and "焦虑症" not in assistant["data"]["content"]


def seed_fact(target, text="我被诊断出焦虑症。", key="anxiety"):
    memory = MemoryService(target.repo)
    source = memory.receive(target.owner, content="请保存" + text, source_id="seed-" + key, channel="web")
    fact = memory.save_fact(target.owner, "self", source["id"], text, "concern")
    assert fact["write_status"] == "saved"
    return memory, fact


@pytest.mark.parametrize(
    "text",
    [
        "别忘了我焦虑症的事",
        "不要忘了我焦虑症的事",
        "不要删除我焦虑症的事",
        "如果我说把焦虑症忘了会怎样",
        "家人说“把焦虑症忘了”",
        "删除那条记忆",
        "把我和妈妈的焦虑症都忘了",
        "把我妈焦虑症的事忘了",
        "他说把焦虑症的事忘了",
        "不是要你忘记焦虑症的事",
        "我之前要求忘记焦虑症的事",
    ],
    ids=[
        "benign_reminder",
        "negative_reminder",
        "negative_delete",
        "hypothetical",
        "quoted",
        "guessed_id",
        "multiple_people",
        "other_person",
        "reported_speech",
        "denied_intent",
        "past_intent",
    ],
)
def test_denied_hypothetical_quoted_guessed_and_other_person_targets_do_not_revoke(target, text):
    target.reset({"synthetic": True, "profile": "empty_profile", "_scenario_id": "forget-negative", "_scripted": []})
    memory, fact = seed_fact(target)
    source = memory.receive(target.owner, content=text, source_id="current", channel="web")
    with pytest.raises(EvidenceError):
        retire_from_message(memory, target.owner, fact["id"], source["id"], "forget")
    assert memory.repo.get(target.owner, "fact", fact["id"])["content"] == fact["content"]
    assert not memory.repo.is_revoked(target.owner, "fact", fact["id"])


def test_multiple_actual_facts_matching_the_same_current_phrase_require_confirmation(target):
    target.reset({"synthetic": True, "profile": "empty_profile", "_scenario_id": "forget-ambiguous", "_scripted": []})
    memory, fact = seed_fact(target)
    _, another = seed_fact(target, "我焦虑症需要随访。", "another")
    source = memory.receive(target.owner, content="把我焦虑症的事忘了", source_id="current", channel="web")
    with pytest.raises(EvidenceError):
        retire_from_message(memory, target.owner, fact["id"], source["id"], "forget")
    assert memory.repo.get(target.owner, "fact", another["id"])["status"] == "active"
    assert memory.repo.get(target.owner, "fact", fact["id"])["status"] == "active"
