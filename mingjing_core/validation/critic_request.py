"""Allowlisted request descriptions only: this module has no model or transport dependency."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Literal, get_args

from .critic_contracts import CRITIC_PROMPT_VERSION, ProgramIssue

ReceiptStatus = Literal[
    "saved", "updated", "pending_confirmation", "stopped", "deleted", "rejected", "skipped", "denied", "failed"
]
RECEIPT_STATUSES = frozenset(get_args(ReceiptStatus))


@dataclass(frozen=True)
class EvidenceSummary:
    id: str
    summary: str = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id.strip() or len(self.id) > 200:
            raise ValueError("evidence summary requires a bounded reference id")
        if not isinstance(self.summary, str) or not self.summary.strip():
            raise ValueError("evidence summary cannot be blank")


@dataclass(frozen=True)
class ReceiptSummary:
    id: str
    status: ReceiptStatus
    summary: str = field(repr=False)

    def __post_init__(self) -> None:
        EvidenceSummary(self.id, self.summary)
        if self.status not in RECEIPT_STATUSES:
            raise ValueError("receipt status is not a recognized program result")


@dataclass(frozen=True)
class CriticMaterials:
    user_message: str = field(repr=False)
    now_block: str = field(repr=False)
    draft: str = field(repr=False)
    memory_summaries: tuple[EvidenceSummary, ...] = field(default=(), repr=False)
    chart_summaries: tuple[EvidenceSummary, ...] = field(default=(), repr=False)
    profile_summaries: tuple[EvidenceSummary, ...] = field(default=(), repr=False)
    receipts: tuple[ReceiptSummary, ...] = field(default=(), repr=False)
    program_issues: tuple[ProgramIssue, ...] = field(default=(), repr=False)

    def __post_init__(self) -> None:
        if any(not isinstance(value, str) for value in (self.user_message, self.now_block, self.draft)):
            raise ValueError("critic materials require explicit text projections")
        for name in ("memory_summaries", "chart_summaries", "profile_summaries", "receipts", "program_issues"):
            values = tuple(getattr(self, name))
            required = (
                ProgramIssue if name == "program_issues" else ReceiptSummary if name == "receipts" else EvidenceSummary
            )
            if any(not isinstance(value, required) for value in values):
                raise ValueError("critic materials accept typed summaries, not raw run records")
            object.__setattr__(self, name, values)
        refs = [
            row.id for row in (*self.memory_summaries, *self.chart_summaries, *self.profile_summaries, *self.receipts)
        ]
        reserved = self._builtin_evidence_ids()
        if len(refs) != len(set(refs)) or set(refs) & reserved:
            raise ValueError("evidence references must be unique and cannot replace reserved references")
        for issue in self.program_issues:
            if issue.quote not in self.draft or issue.evidence not in self.evidence_ids:
                raise ValueError("program findings must bind to this draft and its actual evidence projection")

    def _builtin_evidence_ids(self) -> set[str]:
        refs = {"receipts"}
        if self.user_message.strip():
            refs.add("user:current")
        if self.now_block.strip():
            refs.add("now")
        refs.update(f"now:{index + 1}" for index, line in enumerate(self.now_block.splitlines()) if line.strip())
        return refs

    @property
    def evidence_ids(self) -> frozenset[str]:
        rows = (*self.memory_summaries, *self.chart_summaries, *self.profile_summaries, *self.receipts)
        return frozenset(self._builtin_evidence_ids() | {row.id for row in rows})

    def payload(self) -> dict[str, object]:
        return {
            "user_message": self.user_message,
            "now_block": self.now_block,
            "draft": self.draft,
            "memory_summaries": [{"id": row.id, "summary": row.summary} for row in self.memory_summaries],
            "chart_summaries": [{"id": row.id, "summary": row.summary} for row in self.chart_summaries],
            "profile_summaries": [{"id": row.id, "summary": row.summary} for row in self.profile_summaries],
            "receipts": [{"id": row.id, "status": row.status, "summary": row.summary} for row in self.receipts],
            "program_issues": [
                {
                    "item": row.item,
                    "quote": row.quote,
                    "rule": row.rule,
                    "evidence": row.evidence,
                    "fix_hint": row.fix_hint,
                    "resolved": row.resolved,
                }
                for row in self.program_issues
            ],
            "evidence_reference_ids": sorted(self.evidence_ids),
        }


@dataclass(frozen=True)
class CriticRequest:
    prompt: str = field(repr=False)
    payload_json: str = field(repr=False)

    def as_dict(self) -> dict[str, object]:
        return {
            "role": "critic",
            "model": "k3-256k",
            "effort": "high",
            "new_session": True,
            "messages": [{"role": "system", "content": self.prompt}, {"role": "user", "content": self.payload_json}],
        }


def build_critic_request(materials: CriticMaterials, *, critic_prompt: str) -> CriticRequest:
    marker = f"<!-- prompt: critic v{CRITIC_PROMPT_VERSION} -->"
    if (
        not isinstance(materials, CriticMaterials)
        or not isinstance(critic_prompt, str)
        or not critic_prompt.startswith(marker)
    ):
        raise ValueError("an independent versioned critic prompt and typed materials are required")
    return CriticRequest(critic_prompt, json.dumps(materials.payload(), ensure_ascii=False, separators=(",", ":")))
