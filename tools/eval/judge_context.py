"""Private judge context resolved from the same fixtures and native committed turns."""

from copy import deepcopy
from typing import Any
from tools.eval.schema import Scenario
from tools.eval.targets.base import TurnResult

from tools.eval.targets.v3_seed import V3Seeder
from tools.eval.judge_packet import bounded_packet, memories, references


def judge_payload(scenario: Scenario, index: int, result: TurnResult) -> dict[str, Any]:
    turn = scenario.turns[index - 1]
    seed = scenario.seed.model_dump(mode="json")
    profile = V3Seeder.load_profile(seed)
    evidence = deepcopy(result.metadata.get("judge_evidence", {}))
    prior = deepcopy(result.metadata.get("prior_turns", []))
    for number, row in enumerate(prior, 1):
        row.setdefault("turn", number)
        row.setdefault("user_gist", "")
        row.setdefault("effects", row.get("tool_effects", {}).get("effects", []))
    evidence["prior_turns"] = prior
    ids, rules, decisions = references(scenario.category)
    effects = deepcopy(result.metadata.get("tool_effects", {}))
    packet = {
        "packet_version": "judge-packet-v2",
        "scenario": {
            "id": scenario.id,
            "category": scenario.category,
            "turn": index,
            "turns_total": len(scenario.turns),
        },
        "scenario_id": scenario.id,
        "user": turn.user,
        "clock": turn.at or scenario.clock,
        "seed_profile": {key: deepcopy(value) for key, value in profile.items() if key not in {"scripted", "controls"}},
        "resolved_profile": {
            key: deepcopy(profile[key]) for key in ("name", "occupation", "goals", "birth") if key in profile
        },
        "memories": memories(seed, evidence, result.text),
        "now": evidence.get("now", ""),
        "chart_claims": deepcopy(evidence.get("chart_claims", [])),
        "missing_evidence": [] if evidence.get("now") else ["now"],
        "prior_turns": prior,
        "tool_effects": effects,
        "this_turn": {
            "user": turn.user,
            "tools_called": result.tools_called,
            "receipts": result.receipts,
            "cards": effects,
        },
        "receipts": result.receipts,
        "tools_called": result.tools_called,
        "criterion": [{"id": "legacy-criterion", "kind": "must", "text": turn.expect.judge}]
        if turn.expect.judge
        else [],
        "criterion_status": "legacy_only_pending_brain_review_of_expanded_clauses",
        "product_decisions": decisions,
        "reference_ids": ids,
        "reference": rules,
        "answer": result.text,
    }
    return bounded_packet(packet)
