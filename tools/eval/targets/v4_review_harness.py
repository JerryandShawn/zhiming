"""Offline X01 model responses exercise existing P3 review scheduling only."""

from __future__ import annotations

import json
from typing import Any

from mingjing_core.agent.review import CriticVerdict
from tools.eval.targets.v4_review_observations import review_counts

DRAFT = "跳槽一定成功。先核对岗位成长、收入与生活节奏。"
VERDICTS = ["revise", "revise"]


def prepare_review_model(identity: str, turn: int, actions: list[dict], controls: dict[str, Any]) -> None:
    if identity != "X01":
        return
    if controls.get("critic_verdicts") != VERDICTS or turn != 1:
        raise ValueError("X01 needs its original two-revise scheduling control")
    if not actions or any(set(action) != {"text"} for action in actions):
        raise ValueError("X01 review harness requires declared primary model text only")
    if actions[0]["text"] != DRAFT:
        actions.insert(0, {"text": DRAFT})
    if len(actions) != 2:
        raise ValueError("X01 must declare one draft and one possible revision")


def critic_script(seed: dict[str, Any]) -> list[dict[str, Any]]:
    controls = seed.get("controls", {})
    if seed.get("_scenario_id") != "X01":
        return controls.get("critic_scripted", [])
    if controls.get("critic_verdicts") != VERDICTS or controls.get("critic_scripted"):
        raise ValueError("X01 must preserve its original critic controls")
    steps = seed.get("_scripted", [])
    if len(steps) != 1 or steps[0]["turn"] != 1:
        raise ValueError("X01 needs one original scripted user turn")
    actions = steps[0]["model"]
    if len(actions) != 2 or actions[0] != {"text": DRAFT} or set(actions[1]) != {"text"}:
        raise ValueError("X01 requires its explicit primary draft/revision overlay")
    draft, revised = (action["text"] for action in actions)
    first = verdict("fatalism", "一定成功", "说明不确定性并提供可以验证的小步骤")
    # The second legal response is prepared, never requested. A second review
    # would therefore be visible as an extra actual model row, not a fake event.
    second = verdict("generic_barnum", revised, "说明具体的岗位成长标准")
    CriticVerdict.parse(first, draft)
    CriticVerdict.parse(second, revised)
    return [{"turn": 1, "model": [{"text": first}, {"text": second}]}]


def verdict(code: str, quote: str, hint: str) -> str:
    return json.dumps(
        {
            "verdict": "revise",
            "issues": [{"type": code, "quote": quote, "severity": 4, "fix_hint": hint}],
        },
        ensure_ascii=False,
    )


def harness_evidence(target: Any) -> dict[str, Any]:
    if target.seed.get("_scenario_id") != "X01" or target.critic is None:
        return {}
    if getattr(target.port, "offline", False) is not True or getattr(target.critic, "offline", False) is not True:
        raise ValueError("X01 scheduling harness cannot attach to a live model port")
    run = target.repo.fetch_run(target.owner, target.run_ids[-1])
    counts = review_counts(target.repo, target.owner, run)
    return {
        "review_harness": {
            "scope": "offline P3 review harness",
            "production_internal_critic": False,
            "completed_primary_steps": counts["primary_count"] + counts["revision_count"],
            "completed_critic_steps": counts["critic_count"],
            "source_store": counts["review_source_store"],
        }
    }
