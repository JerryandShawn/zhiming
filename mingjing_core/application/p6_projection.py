"""Trusted owner-scoped projections for the isolated P6 candidate; never model assertions."""

from __future__ import annotations

from typing import Any

from mingjing_core.agent.loop_cycle import LoopOutcome
from mingjing_core.application.agent_commit_versions import persisted_receipts
from mingjing_core.application.agent_options import load_options
from mingjing_core.domain.contracts import EvidenceError
from mingjing_core.repositories.dependencies import entity_dependency
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.validation.p6_candidate.legacy_lint import LintContext
from mingjing_core.validation.structural import check_structure


def trusted_records(repo: PostgresRepository, run: dict[str, Any], outcome: LoopOutcome) -> dict[str, dict]:
    result = {}
    for alias, value in outcome.alias_map.items():
        kind, ident = value["kind"], value["id"]
        if entity_dependency(kind, ident) not in outcome.versions:
            continue
        row = repo.get(run["owner"], kind, ident)
        if row["subject_id"] != run["subject"] or row["status"] not in {"active", "open", "pending"}:
            raise EvidenceError("P6材料不属于当前有效人物")
        if row["revision"] != outcome.versions[entity_dependency(kind, ident)] or repo.is_revoked(
            run["owner"], kind, ident
        ):
            raise EvidenceError("P6材料来源版本已失效")
        result[alias] = dict(row, entity_kind=kind)
    return result


def receipt_projection(repo: PostgresRepository, run: dict[str, Any], records: dict[str, dict]) -> tuple[dict, ...]:
    result = []
    for receipt in persisted_receipts(repo, run):
        ident = receipt.get("id", receipt.get("fact_id"))
        match = next(
            (
                (alias, row)
                for alias, row in records.items()
                if row["id"] == ident and row["entity_kind"] == receipt.get("kind")
            ),
            None,
        )
        if match is None:
            continue
        alias, row = match
        result.append(
            dict(
                write_status=receipt.get("write_status"),
                alias=alias,
                summary=row.get("content", row.get("text", row.get("title", ""))),
            )
        )
    return tuple(result)


def lint_context(
    repo: PostgresRepository, run: dict[str, Any], outcome: LoopOutcome, records: dict[str, dict]
) -> LintContext:
    checked = check_structure(outcome.text, outcome.alias_map)
    selected = load_options(repo, run)
    choices = selected.value["options"] if selected else []
    final = {
        "plain_summary": outcome.text[:6000] or "本轮回答待整理",
        "explanation": "",
        "actions": [row["first_step"] for row in choices],
        "decision_options": [
            dict(
                option=row["title"],
                **{key: row[key] for key in ("benefit", "cost", "risk", "reversibility", "first_step")},
            )
            for row in choices
        ],
        "follow_up": "",
        "professional_appendix": "",
        "cited_fact_ids": list(checked.used_fact_ids),
        "cited_claim_ids": list(checked.used_claim_ids),
        "caveats": [],
    }
    facts = [row for row in records.values() if row["entity_kind"] == "fact"]
    claims = [dict(row, claim_id=row["id"]) for row in records.values() if row["entity_kind"] == "interpretive_claim"]
    return LintContext(
        snapshot={"facts": facts},
        calculation={"claims": claims, "calculation": {}},
        plan={"decision": bool(choices), "mode": "conversation", "systems": []},
        run_request=dict(run["request"]),
        final_answer=final,
        revalidator=None,
    )
