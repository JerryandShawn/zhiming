"""Historical reply fixtures are produced by a real runtime, with original timestamps."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from mingjing_core.application.agent_tools_policy import sensitivity
from mingjing_core.timekit.clock import FrozenClock, get_clock, set_clock
from mingjing_core.timekit.timestamps import history_instant


def pending_source_label(seed: dict[str, Any], fixture: dict[str, Any]) -> str | None:
    if fixture["kind"] != "proposal" or not fixture["data"].get("sensitivity"):
        return None
    if fixture["data"].get("source_message_id"):
        return fixture["data"]["source_message_id"]
    sources = {
        f["source_message_id"]
        for f in seed.get("facts", [])
        if f.get("source_message_id") and f.get("sensitivity") == fixture["data"]["sensitivity"]
    }
    if len(sources) != 1:
        raise ValueError("Declared sensitive proposal needs one unambiguous initial source")
    return next(iter(sources))


def declared_reply(seed: dict[str, Any], source_label: str) -> dict[str, Any] | None:
    previous, candidates = None, []
    for row in seed.get("thread", []):
        if row.get("role") == "user":
            previous = row.get("id")
        elif row.get("role") == "assistant" and previous == source_label:
            candidates.append(row)
    if len(candidates) > 1:
        raise ValueError("Synthetic pending setup cannot choose among multiple historical replies")
    if candidates:
        source = next(row for row in seed["thread"] if row.get("id") == source_label)
        before, after = history_instant(source.get("at")), history_instant(candidates[0].get("at"))
        if before is None or after is None or after < before:
            raise ValueError("Declared assistant reply cannot precede its original user message")
    return candidates[0] if candidates else None


def seed_memory_sources(target: Any) -> None:
    seed = deepcopy(target.seed)
    deferred = [
        reply
        for f in seed.get("entities", [])
        if (label := pending_source_label(seed, f)) and (reply := declared_reply(seed, label))
    ]
    labels = {r["id"] for r in deferred}
    seed["thread"] = [row for row in seed.get("thread", []) if row.get("id") not in labels]
    if deferred:
        seed["entities"] = [f for f in seed.get("entities", []) if pending_source_label(seed, f) is None]
    previous = get_clock()
    try:
        if deferred:
            times = [history_instant(row.get("at")) for row in seed["thread"]]
            if not times or any(at is None for at in times):
                raise ValueError("Historical memory fixtures require original aware timestamps")
            set_clock(FrozenClock(min(times)))
        target.seeder.seed(seed)
        if deferred:
            _declared_sensitivities(target, seed)
    finally:
        set_clock(previous)


def execute_historical(target: Any, run: dict[str, Any], provider: Any, reply: dict[str, Any] | None) -> dict[str, Any]:
    previous = get_clock()
    try:
        if reply is not None:
            at = history_instant(reply.get("at"))
            if at is None:
                raise ValueError("Historical assistant fixture requires an aware timestamp")
            set_clock(FrozenClock(at))
        target.port.start(provider, 1, {})
        return target.runtime.execute(target.service, target.owner, run["id"], run["lease_token"], lambda event: None)
    finally:
        set_clock(previous)


def memory_ingress_needed(seed: dict[str, Any], turn: dict[str, Any]) -> bool:
    if seed.get("controls", {}).get("revoke_after_context"):
        return True
    step = next((s for s in seed.get("_scripted", []) if s["turn"] == turn["_index"]), {})
    return any(a.get("tool_call", {}).get("name") == "memory_forget" for a in step.get("model", []))


def _declared_sensitivities(target: Any, seed: dict[str, Any]) -> None:
    for fixture in seed.get("facts", []):
        if not fixture.get("sensitivity") or not fixture.get("source_message_id"):
            continue
        source = target.service.memory.get_source(target.owner, target.seeder.ids[fixture["source_message_id"]])
        quote = fixture["quote"]
        start = source["content"].index(quote)
        level = sensitivity(quote, source["content"], start, start + len(quote), "normal")
        if level != fixture["sensitivity"]:
            raise ValueError("Historical sensitive fact fixture must match the actual source classifier")
        fact = target.repo.get(target.owner, "fact", fixture["id"])
        target.repo.update(target.owner, "fact", fact["id"], {"sensitivity": level}, expected_revision=fact["revision"])
