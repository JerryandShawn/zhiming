"""Synthetic-only packet tests; native cases use the existing isolated PG driver."""

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools.eval.engine import evaluate_scenario
from tools.eval.judge_context import judge_payload
from tools.eval.judge_packet import serialized
from tools.eval.judges import ModelJudge
from tools.eval.targets.base import TurnResult
from tools.eval.targets.v4_core30 import load_core30
from tools.eval.targets.v4_target import V4Target


def scenario(identity):
    return next(row for row in load_core30() if row.id == identity)


def test_packet_resolves_profile_and_excludes_replay_answers():
    packet = judge_payload(scenario("T10"), 1, TurnResult(text="合成回答"))
    assert packet["packet_version"] == "judge-packet-v2"
    assert packet["seed_profile"]["name"] == packet["resolved_profile"]["name"] == "阿远"
    assert packet["seed_profile"]["birth"]
    assert "scripted" not in serialized(packet) and "gold" not in serialized(packet)
    assert packet["reference_ids"] == ["REF-ZI-01", "REF-JQ-01", "REF-HOL-01"]


def test_native_tombstones_win_and_old_effects_are_never_truncated():
    case = scenario("F01")
    metadata = {
        "judge_evidence": {
            "seed_bindings": {"interview": "native-interview"},
            "memories": [
                {"id": "native-interview", "status": "deleted", "content": None},
            ],
        },
        "prior_turns": [
            {
                "turn": i,
                "user_gist": "合成" * 100,
                "receipts": [
                    {"kind": "fact", "fact_id": "native-interview", "write_status": "deleted"},
                ],
                "effects": ["followup native-followup → cancelled"],
            }
            for i in range(1, 6)
        ],
    }
    before = deepcopy(metadata)
    packet = judge_payload(case, 2, TurnResult(text="没有已知安排", metadata=metadata))
    memory = next(row for row in packet["memories"] if row["id"] == "native-interview")
    assert memory["status"] == "revoked@turn5"
    assert all(row["effects"] == ["followup native-followup → cancelled"] for row in packet["prior_turns"])
    assert "user_gist" not in packet["prior_turns"][0]
    assert len(packet["prior_turns"][-1]["user_gist"]) <= 60
    assert metadata == before


def test_packet_limits_count_drops_and_keep_answer_and_cards_whole():
    evidence = {"memories": [{"id": "fact-" + str(i), "content": "合成" * 100, "status": "active"} for i in range(30)]}
    answer = "〔fact-29〕〔c11〕" + "答复" * 10000
    evidence["chart_claims"] = [{"alias": "c" + str(i), "text": "合成计算证据"} for i in range(12)]
    cards = {"present_options": [{"label": "A", "benefit": "合成收益", "risk": "待核实", "first_step": "询问"}]}
    packet = judge_payload(
        scenario("D01"),
        1,
        TurnResult(
            text=answer,
            metadata={
                "judge_evidence": evidence,
                "tool_effects": cards,
            },
        ),
    )
    assert packet["answer"] == answer and packet["this_turn"]["cards"] == cards
    assert len(packet["memories"]) <= 12 and all(len(row["text"]) <= 80 for row in packet["memories"])
    assert packet["truncation"]["memories_dropped"] >= 18 and packet["packet_chars"] <= 6000
    assert any(row["alias"] == "fact-29" for row in packet["memories"])
    assert any(row["alias"] == "c11" for row in packet["chart_claims"])
    assert len(packet["packet_sha256"]) == 64


def test_required_data_overflow_refuses_before_any_judge_request():
    with pytest.raises(ValueError, match="required_budget"):
        judge_payload(scenario("D01"), 1, TurnResult(text="合成", metadata={"tool_effects": {"card": "字" * 3000}}))


@pytest.mark.parametrize("identity", ["T10", "D01", "F01"])
def test_native_judge_packet_preserves_now_cards_and_withdrawal(identity):
    packets = []

    def generate(**kwargs):
        packets.append(kwargs["payload"])
        return {
            "output": {
                "score": 1,
                "verdict": "pass",
                "issues": [],
                "reason": "synthetic",
                "deductions": [],
                "expected_clauses": [],
            }
        }

    judge = ModelJudge("synthetic", Path("tools/eval/rubric_v1.md"), SimpleNamespace(generate=generate))
    target = V4Target()
    try:
        case = evaluate_scenario(scenario(identity), target, target_name="v4", judge=judge)
        assert case["status"] == "passed", (case.get("error_code"), case["failed_assertions"])
        assert packets and packets[-1]["now"] and packets[-1]["packet_chars"] <= 6000
        assert case["judge_metadata"]["model"] == "synthetic"
        assert case["judge_metadata"]["rubric_path"].endswith("rubric_v1.md")
        assert len(case["judge_metadata"]["rubric_sha256"]) == 64
        assert case["private_evidence"][-1]["packet"]["packet_sha256"] == packets[-1]["packet_sha256"]
        if identity == "D01":
            assert packets[-1]["this_turn"]["cards"]["present_options"]
        if identity == "F01":
            assert any(row["status"].startswith("revoked@turn1") for row in packets[-1]["memories"])
            assert any("cancelled" in effect for row in packets[-1]["prior_turns"] for effect in row["effects"])
    finally:
        target.close()
