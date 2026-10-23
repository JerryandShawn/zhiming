"""Trusted execution identities and body-safe results for first-batch tools."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from mingjing_core.domain.contracts import EvidenceError

if TYPE_CHECKING:
    from mingjing_core.agent.journal import JournalStep


def tool_input_fingerprint(name: str, arguments: dict[str, Any], source_versions: dict[str, int] | None = None) -> str:
    from mingjing_core.agent.journal import input_fingerprint

    return input_fingerprint("tool", name, {"arguments": arguments, "source_versions": source_versions or {}})


@dataclass(frozen=True)
class ToolContext:
    owner: str
    run_id: str
    subject: str
    epoch: int
    seq: int
    lease_token: str = field(repr=False)
    name: str
    input_fp: str
    thread_id: str
    source_ids: tuple[str, ...] = ()
    case_ids: tuple[str, ...] = ()
    crisis: bool = False
    incognito: bool = False
    at: datetime | None = None
    source_versions: dict[str, int] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        values = (
            self.owner,
            self.run_id,
            self.subject,
            self.lease_token,
            self.thread_id,
        )
        if any(not isinstance(value, str) or not 1 <= len(value) <= 200 for value in values):
            raise EvidenceError("工具需要完整的受信运行身份")
        if type(self.epoch) is not int or self.epoch < 0 or type(self.seq) is not int or self.seq < 1:
            raise EvidenceError("工具步骤身份无效")
        if not isinstance(self.input_fp, str) or re.fullmatch("[0-9a-f]{64}", self.input_fp) is None:
            raise EvidenceError("工具步骤指纹无效")
        if len(self.source_ids) > 100 or len(self.case_ids) > 8:
            raise EvidenceError("工具来源范围超过上限")
        if not isinstance(self.source_versions, dict) or any(
            not isinstance(key, str) or type(value) is not int or value < 1
            for key, value in self.source_versions.items()
        ):
            raise EvidenceError("工具来源版本无效")
        if self.at is not None and (self.at.tzinfo is None or self.at.utcoffset() is None):
            raise EvidenceError("工具时刻必须带时区")

    @classmethod
    def from_step(
        cls,
        step: JournalStep,
        *,
        thread_id: str,
        source_ids: tuple[str, ...] = (),
        case_ids: tuple[str, ...] = (),
        crisis: bool = False,
        incognito: bool = False,
        at: datetime | None = None,
        source_versions: dict[str, int] | None = None,
    ) -> ToolContext:
        return cls(
            step.owner,
            step.run_id,
            step.subject,
            step.epoch,
            step.seq,
            step.lease_token,
            step.name,
            step.input_fp,
            thread_id,
            tuple(source_ids),
            tuple(case_ids),
            crisis,
            incognito,
            at,
            dict(source_versions or {}),
        )

    @property
    def operation_id(self) -> str:
        return f"run:{self.run_id}:e{self.epoch}:s{self.seq}"

    @property
    def private(self) -> bool:
        return self.incognito or self.thread_id.startswith("incognito:")


class ToolResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ok: bool = Field(strict=True)
    data: dict[str, Any] = Field(default_factory=dict, repr=False)
    receipt: dict[str, Any] | None = Field(default=None, repr=False)
    ends_turn: bool = Field(default=False, strict=True)
    summary: str = Field(max_length=160)


@dataclass(frozen=True)
class DateResolution:
    status: Literal["resolved", "not_date", "needs_confirmation"]
    event_at: str | None = None
    expression: str | None = None
    candidates: tuple[str, ...] = ()
    reason: str = ""


class RelativeDateParser(Protocol):
    def resolve(self, text: str, *, said_at: datetime, timezone: str) -> DateResolution: ...
