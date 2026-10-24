"""Create a real pending proposal when a model omitted sensitive memory submission."""

from __future__ import annotations

import re
from dataclasses import replace
from typing import TYPE_CHECKING

from psycopg import sql

from mingjing_core.application.agent_tools_policy import CREDENTIAL, RULES, SECRET, sensitivity
from mingjing_core.memory.policy import has_optout, hypothetical, mask_quoted
from mingjing_core.models.port import ToolCall

if TYPE_CHECKING:
    from mingjing_core.agent.loop_cycle import LoopCycle, LoopOutcome


def _model_submitted(cycle: LoopCycle) -> bool:
    repo, run = cycle.registry.service.repo, cycle.run
    with repo.transaction(run["owner"]) as connection:
        rows = connection.execute(
            sql.SQL(
                "SELECT output FROM {} WHERE owner=%s AND run_id=%s AND epoch=%s "
                "AND kind='model' AND status='completed'"
            ).format(repo.table("core_run_steps")),
            (run["owner"], run["id"], run["retry_epoch"]),
        ).fetchall()
    return any(
        call.get("name") == "memory_write"
        for row in rows
        for call in (row["output"] or {}).get("assistant", {}).get("tool_calls", [])
    )


def _sensitive_span(text: str) -> tuple[str, int, int] | None:
    if has_optout(text) or "无痕" in text or SECRET.search(text) or CREDENTIAL.search(text):
        return None
    plain = re.sub(r"‘[^’\n]*’", lambda match: " " * len(match.group()), mask_quoted(text))
    for match in re.finditer(r"[^。！？!?；;\n]+[。！？!?；;]?", plain):
        start, end = match.span()
        start += len(text[start:end]) - len(text[start:end].lstrip())
        end = start + len(text[start:end].rstrip())
        if not start < end or end - start > 1000 or hypothetical(plain, start, end):
            continue
        quote = plain[start:end]
        if quote != text[start:end]:
            continue
        level = sensitivity(quote, plain, start, end)
        if level == "money" and not re.search(r"\d[\d.,，]*\s*(?:万|元|块|美元|人民币)", quote):
            continue
        if level == "third_party" and not (
            RULES["health"].search(quote) or re.search(r"隐私|住址|婚姻|离婚|出轨|出生|生辰|性取向", quote)
        ):
            continue
        if level in {"health", "third_party", "money"} and quote.strip():
            return level, start, end
    return None


def ensure_sensitive_pending(cycle: LoopCycle, outcome: LoopOutcome) -> LoopOutcome:
    from mingjing_core.agent.loop_batch import ToolBatch

    if (
        cycle.incognito
        or cycle.crisis
        or outcome.stop_reason not in {"completed", "asked"}
        or "memory_write" not in cycle.exposed
        or _model_submitted(cycle)
    ):
        return outcome
    service = cycle.registry.service
    for ident in cycle.current_sources:
        source = service.source(cycle._context(), ident)
        selected = _sensitive_span(source["content"])
        if selected is None:
            continue
        level, start, end = selected
        quote = source["content"][start:end]
        result, _ = ToolBatch(cycle).serial(
            ToolCall(
                "system-sensitive-pending",
                "memory_write",
                {
                    "message_id": ident,
                    "quote": quote,
                    "summary": quote,
                    "start": start,
                    "end": end,
                    "kind": "background",
                    "sensitivity": level,
                },
            )
        )
        if result.receipt and result.receipt.get("write_status") == "pending_confirmation":
            cycle.usage["sensitive_pending_fallback"] = True
        return replace(
            outcome,
            receipts=tuple(cycle.receipts),
            alias_map=dict(cycle.aliases),
            versions=dict(cycle.versions),
            usage=dict(cycle.usage),
        )
    return outcome
