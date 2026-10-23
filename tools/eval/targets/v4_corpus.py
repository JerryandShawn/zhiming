"""Keep 46 original contracts and apply the explicitly approved R3 channel split."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

from tools.eval.contracts import scenario_contract_hash
from tools.eval.schema import Scenario, load_scenarios
from tools.eval.targets.v4_review_harness import prepare_review_model

REQUIRED_IDS = frozenset(
    [f"T{i:02}" for i in range(1, 15)]
    + [f"M{i:02}" for i in (1, 2, 3, 4, 9, 10, 11, 13)]
    + [f"R{i:02}" for i in range(1, 10)]
    + [f"Q{i:02}" for i in range(1, 8)]
    + ["TA01", "TA02", "TA03", "D01", "S01", "X03a", "X03b", "X04", "X05", "L01"]
)
R3_IDS = frozenset({"X03a", "X03b"})


def split_recovery_contract(scenario: Scenario) -> list[Scenario]:
    """35 R3 supersedes X03's mixed web/Feishu expectations, not its replay safety."""
    if scenario.id != "X03":
        raise ValueError("Only the approved X03 recovery contract may be split")
    cases = []
    for identity, channel in (("X03a", "web"), ("X03b", "feishu")):
        data = scenario.model_dump(mode="json", exclude_none=True)
        data["id"] = identity
        data["title"] = f"{channel}发起的崩溃恢复不重复写入或跨渠道回复"
        data["notes"] = "35号R3批准的渠道拆分；替换原X03混合契约，不与旧47题分数直接比较。"
        for index, turn in enumerate(data["turns"]):
            turn["channel"] = channel
            finished = index == 1
            outbox = {"kind": "outbox", "count": int(finished and channel == "feishu")}
            if finished and channel == "feishu":
                outbox["status"] = "sent"
            turn["expect"]["db"] = [
                {"kind": "fact", "count": 1},
                outbox,
                {
                    "kind": "message",
                    "where": {"data.channel": channel, "data.role": "assistant"},
                    "count": int(finished),
                },
            ]
            if finished:
                turn["expect"]["events"] = [
                    "run.resumed",
                    *(["delivery.sent"] if channel == "feishu" else []),
                    "run.completed",
                ]
        cases.append(Scenario.model_validate(data))
    return cases


def execution_overlay(scenario: Scenario) -> Scenario:
    data = scenario.model_dump(mode="json", exclude_none=True)
    for step in data["scripted"]:
        actions = []
        for action in step["model"]:
            action = {key: deepcopy(value) for key, value in action.items() if key in {"text", "tool_call"}}
            if action:
                actions.append(action)
        step["model"] = actions
        prepare_review_model(scenario.id, step["turn"], actions, data["seed"].get("controls", {}))
        migrate_forget_query(actions, step["turn"])
        if scenario.id == "C03" and not any(
            action.get("tool_call", {}).get("name") == "chart_compute" for action in actions
        ):
            # The old script supplied an unbound c1. Obtain a real scoped
            # artifact before its prose; the original scoring contract stays.
            actions.insert(
                0,
                {
                    "tool_call": {
                        "name": "chart_compute",
                        "arguments": {
                            "system": "bazi",
                            "target": data["clock"][:10],
                            "scale": "natal",
                        },
                    }
                },
            )
        for action in actions:
            call = action.get("tool_call", {})
            args: dict[str, Any] = call.get("arguments", {})
            if call.get("name") == "schedule_followup":
                prior = next(
                    (
                        a["tool_call"]["arguments"]
                        for a in actions
                        if a.get("tool_call", {}).get("name") == "memory_write"
                    ),
                    None,
                )
                args.update(
                    message_id=f"turn-{step['turn']}",
                    quote=prior["quote"] if prior else data["turns"][step["turn"] - 1]["user"],
                )
                if args.get("source_fact_id"):
                    args["source_fact_id"] = "$last_receipt.id"
            if call.get("name") == "tarot_start":
                args.update(message_id=f"turn-{step['turn']}", draw_source="pick")
                original = data["turns"][step["turn"] - 1]["user"]
                if args["question"] not in original:
                    args["question"] = original
    result = Scenario.model_validate(data)
    if scenario_contract_hash(result) != scenario_contract_hash(scenario):
        raise ValueError("Execution overlay changed the scoring contract")
    return result


def migrate_forget_query(actions: list[dict[str, Any]], turn: int) -> None:
    for action in list(actions):
        call = action.get("tool_call", {})
        arguments = call.get("arguments", {})
        if call.get("name") != "memory_forget" or "query" not in arguments:
            continue
        query = arguments["query"]
        index = actions.index(action)
        call["arguments"] = {"fact_id": "$unique_memory_fact", "message_id": f"turn-{turn}"}
        actions.insert(
            index,
            {
                "tool_call": {
                    "name": "memory_search",
                    "arguments": {
                        "query": query,
                        "kinds": ["fact"],
                        "limit": 20,
                    },
                }
            },
        )


def write_corpus(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    source_ids = REQUIRED_IDS - R3_IDS | {"X03"}
    originals = [case for case in load_scenarios(source) if case.id in source_ids]
    cases = [split for case in originals for split in (split_recovery_contract(case) if case.id == "X03" else [case])]
    if {case.id for case in cases} != REQUIRED_IDS:
        raise ValueError("P3 corpus is incomplete")
    for case in cases:
        data = execution_overlay(case).model_dump(mode="json", exclude_defaults=True, exclude_none=True)
        path = destination / (case.id + ".yaml")
        path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    (destination / "X03.yaml").unlink(missing_ok=True)


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    write_corpus(root / "scenarios", root / "scenarios_v4")
