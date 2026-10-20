"""One independent critic request and at most one text-only primary revision."""

from __future__ import annotations

import json
from dataclasses import asdict, replace
from typing import Any

from pydantic import ValidationError

from mingjing_core.agent.context_tokens import apply_token_budget
from mingjing_core.agent.context_types import BudgetResult, ContextItem, ContextLayer
from mingjing_core.agent.journal import JournalStep, input_fingerprint
from mingjing_core.agent.loop_codec import ObservedPort, assistant_from, assistant_output
from mingjing_core.agent.loop_cycle import LoopCycle, LoopOutcome
from mingjing_core.agent.options import review_material
from mingjing_core.agent.prompts import PromptBundle
from mingjing_core.agent.review import CriticVerdict, TrustedReviewReceipt
from mingjing_core.application.agent_model_calls import RequestLedger
from mingjing_core.application.agent_options import load_options
from mingjing_core.application.agent_review_proofs import ReviewProofStore
from mingjing_core.domain.contracts import EvidenceError, LeaseConflict, RevisionConflict, ScopeError
from mingjing_core.models.errors import ModelUnavailable
from mingjing_core.models.port import ChatMessage, ModelPort
from mingjing_core.validation.structural import check_structure


class AgentReviewer:
    def __init__(self, port: ModelPort | None, ledger: RequestLedger, prompts: PromptBundle, *, offline: bool) -> None:
        self.port, self.ledger, self.prompts, self.offline = port, ledger, prompts, offline

    def _budget(self, cycle: LoopCycle, outcome: LoopOutcome) -> BudgetResult:
        material = {
            "user_message": cycle.run["request"]["message"],
            "draft": outcome.text,
            "options": (selected.value if (selected := load_options(self.ledger.repo, cycle.run)) else None),
            "context": [
                message.content
                for layer in cycle.frozen.budget.layers
                if layer.name in {"L1", "L2", "L3_STABLE", "L4"}
                for item in layer.items
                for message in item.messages
            ],
            "receipts": list(outcome.receipts),
            "aliases": outcome.alias_map,
        }
        layers = (
            ContextLayer(
                "L0", (ContextItem("critic-system", (ChatMessage("system", self.prompts.render("critic")),), True),)
            ),
            ContextLayer(
                "L6",
                (ContextItem("critic-input", (ChatMessage("user", json.dumps(material, ensure_ascii=False)),), True),),
            ),
        )
        return apply_token_budget(layers, (), meter=self.ledger.meter(cycle.run), policy=cycle.budget_policy)

    def _call(self, cycle: LoopCycle, outcome: LoopOutcome) -> tuple[str, JournalStep, bool]:
        if self.port is None or self.offline and getattr(self.port, "offline", False) is not True:
            raise EvidenceError("独立评审端口未配置")
        cached = self.ledger.restore_next(cycle.journal, cycle.run, role="critic", name="critic")
        budget = cached.budget if cached else self._budget(cycle, outcome)
        versions = cached.versions if cached else outcome.versions
        identity = {
            "messages": [asdict(row) for row in budget.messages],
            "tools": [],
            "tool_choice": "auto",
            "source_versions": versions,
        }
        step = cycle.journal.next_or_replay(
            cycle.run, kind="model", name="critic", input_fp=input_fingerprint("model", "critic", identity)
        )
        replayed = step.completed
        if replayed:
            response = assistant_from(step.output or {})
        else:
            self.ledger.reserve(step, cycle.frozen, budget, "auto", versions, role="critic")
            with cycle.control.monitor():
                response = ObservedPort(self.port, cycle.control, lambda text: None).complete(
                    list(budget.messages),
                    tools=[],
                    tool_choice="auto",
                    role="critic",
                    cancel_event=cycle.control.cancel_event,
                )
            if response.tool_calls:
                raise EvidenceError("评审不允许调用工具")
            step = cycle.journal.complete(step, assistant_output(response), response.usage)
        self.ledger.completed(step)
        return response.text, step, replayed

    def review(self, cycle: LoopCycle, outcome: LoopOutcome) -> tuple[LoopOutcome, TrustedReviewReceipt | None]:
        if self.port is None or outcome.asked or outcome.stop_reason != "completed" or cycle.last_step is None:
            return outcome, None
        # Sanitization precedes publication. A changed draft is not secretly
        # substituted for the model row that a critic proof must actually bind.
        if check_structure(outcome.text, outcome.alias_map, outcome.receipts).text != outcome.text:
            return outcome, None
        draft = cycle.last_step
        critic, replayed = None, False
        if cycle.emit:
            cycle.emit("status", {"text": "我再仔细看一遍", "phase": "reviewing"})
            cycle.emit("review", {"state": "pending", "reasons": []})
        try:
            raw, critic, replayed = self._call(cycle, outcome)
            selected = load_options(self.ledger.repo, cycle.run)
            verdict = CriticVerdict.parse(raw, review_material(outcome.text, selected.value if selected else None))
            revision = None
            if verdict.verdict == "revise":
                outcome = cycle.revise(verdict.instructions())
                revision = cycle.last_step
            receipt = ReviewProofStore(self.ledger.repo).save(
                cycle.run,
                draft=draft,
                critic=critic,
                revision=revision,
                final=outcome.text,
                versions=outcome.versions,
                prompt_sha256=self.prompts.manifest["files"]["critic"]["sha256"],
            )
            usage = self._usage(outcome.usage, critic, replayed)
            outcome = replace(outcome, usage=usage)
            if cycle.emit:
                if revision:
                    cycle.emit(
                        "text_reset",
                        {"text": outcome.text, "reason": "revised", "revision_id": receipt.public()["revision_id"]},
                    )
                cycle.emit("review", receipt.public())
            return outcome, receipt
        except (LeaseConflict, RevisionConflict, ScopeError):
            raise
        except (ModelUnavailable, ValidationError, ValueError, EvidenceError):
            if cycle.emit:
                cycle.emit("review", {"state": "skipped", "reasons": []})
            return replace(outcome, usage=self._usage(outcome.usage, critic, replayed)) if critic else outcome, None

    @staticmethod
    def _usage(usage: dict[str, Any], step: JournalStep, replayed: bool) -> dict[str, Any]:
        result = dict(usage)
        result["model_steps"] += 1
        key = "replayed_model_steps" if replayed else "model_streams_this_execution"
        result[key] += 1
        tokens = dict(result["reported_tokens"])
        for name, value in step.usage.items():
            if type(value) is int and value >= 0:
                tokens[name] = tokens.get(name, 0) + value
        result["reported_tokens"] = tokens
        return result
