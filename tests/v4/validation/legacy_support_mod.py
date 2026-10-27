"""Pure synthetic snapshots and an oracle that never invokes a repository or model."""

from copy import deepcopy
from types import SimpleNamespace
from typing import Any

from mingjing_core.application.consultation import ConsultationService
from mingjing_core.domain.consultation import render_answer
from mingjing_core.validation.legacy_lint import LintContext


def eligible(calculation: dict[str, Any], claims: list[dict[str, Any]], tarot_provenance: Any) -> dict[str, Any]:
    return {"eligible": True}


def final_answer(text: str = "先核实条件，再选一个小行动。") -> dict[str, Any]:
    return {
        "plain_summary": text,
        "explanation": "",
        "actions": [],
        "decision_options": [],
        "follow_up": "",
        "professional_appendix": "",
        "cited_fact_ids": [],
        "cited_claim_ids": [],
        "caveats": [],
    }


def context(final: dict[str, Any] | None = None) -> LintContext:
    return LintContext(
        snapshot={"facts": [{"id": "f1", "content": "我不能上夜班", "kind": "constraint"}]},
        calculation={"claims": [{"claim_id": "c1"}], "calculation": {}, "tarot_provenance": None},
        plan={"decision": False, "mode": "conversation", "systems": []},
        run_request={"message": "请先帮我核实选择。"},
        final_answer=final,
        revalidator=eligible,
    )


def rendered(final: dict[str, Any]) -> str:
    return render_answer(final) + "\n" + final["professional_appendix"]


def original_warnings(final: dict[str, Any], ctx: LintContext) -> list[str]:
    """Exercise only the actual old rule function with released in-memory inputs."""
    service = object.__new__(ConsultationService)
    service._snapshot = lambda owner, run: deepcopy(ctx.snapshot)
    service._record = lambda owner, identity, stage: deepcopy(ctx.calculation if stage == "calculation" else ctx.plan)
    service.knowledge = SimpleNamespace(revalidate_claims=ctx.revalidator)
    run = {"id": "synthetic-run", "request": deepcopy(ctx.run_request)}
    return service._validate("synthetic-owner", run, deepcopy(final))
