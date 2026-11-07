"""Frozen public v1 payloads; provider/private protocol data have no fields here."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from mingjing_core.domain.json_values import ensure_finite_json

Ident = Annotated[str, Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")]
Text = Annotated[str, Field(min_length=1, max_length=200_000)]


class PublicModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, serialize_by_alias=True)

    @model_validator(mode="before")
    @classmethod
    def finite_json(cls, value: Any) -> Any:
        ensure_finite_json(value)
        return value


class PublicReceipt(PublicModel):
    write_status: str
    id: Ident | None = None
    fact_id: Ident | None = None
    proposal_id: Ident | None = None
    draw_id: Ident | None = None
    kind: str | None = None
    revision: int | None = Field(default=None, ge=1)
    status: str | None = None
    code: str | None = None
    affected_ids: list[Ident] = Field(default_factory=list, max_length=1024)
    ids: list[Ident] = Field(default_factory=list, max_length=1024)
    summary: str | None = Field(default=None, max_length=160)


class AskOption(PublicModel):
    id: Ident
    label: str = Field(min_length=1, max_length=200)


class Asked(PublicModel):
    ask_id: Ident
    question: str = Field(min_length=1, max_length=500)
    options: list[AskOption] = Field(max_length=4)
    allow_free_text: bool
    multi: bool
    why: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def unique_ids(self) -> Asked:
        if len({item.id for item in self.options}) != len(self.options):
            raise ValueError("选项标识重复")
        return self


class Decision(PublicModel):
    id: Ident
    title: str = Field(min_length=1, max_length=120)
    benefit: str = Field(max_length=500)
    cost: str = Field(max_length=500)
    risk: str = Field(max_length=500)
    reversibility: Literal["easy", "partial", "hard", "unknown"]
    first_step: str = Field(max_length=500)
    unknowns: list[str] = Field(max_length=20)


class Options(PublicModel):
    options_id: Ident
    prompt: str | None = Field(default=None, max_length=500)
    options: list[Decision] = Field(min_length=2, max_length=4)

    @model_validator(mode="after")
    def unique_ids(self) -> Options:
        if len({item.id for item in self.options}) != len(self.options):
            raise ValueError("选项标识重复")
        return self


ReviewCode = Literal[
    "off_topic",
    "time_error",
    "memory_error",
    "false_receipt",
    "unsupported_chart",
    "fatalism",
    "unsafe_advice",
    "crisis_missed",
    "over_asking",
    "overpromise",
    "tone",
    "fabrication",
    "generic_barnum",
    "sycophancy",
    "chart_inconsistency",
]


class ReviewReason(PublicModel):
    code: ReviewCode
    severity: int = Field(ge=1, le=5)


class Review(PublicModel):
    state: Literal["pending", "passed", "revised", "skipped"]
    reasons: list[ReviewReason]
    revision_id: Ident | None = None


class TokenUsage(PublicModel):
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    cache_creation_input_tokens: int | None = Field(default=None, ge=0)
    cache_read_input_tokens: int | None = Field(default=None, ge=0)


class PublicUsage(PublicModel):
    model_steps: int | None = Field(default=None, ge=0)
    model_streams_this_execution: int | None = Field(default=None, ge=0)
    replayed_model_steps: int | None = Field(default=None, ge=0)
    reported_tokens: TokenUsage = Field(default_factory=TokenUsage)
    usage_known: bool = False
    offline: bool | None = None


class Validation(PublicModel):
    status: Literal["validated"]
    valid: Literal[True]
    schema_: Literal["core4.0"] = Field(alias="schema")


class CoreRun(PublicModel):
    run_id: Ident
    operation_id: Ident


class StructuralWarning(PublicModel):
    code: str
    count: int = Field(ge=1)


class PublicMeta(PublicModel):
    core_run: CoreRun
    subject_id: Ident
    case_ids: list[Ident]
    structural_warnings: list[StructuralWarning]


class EnvelopeV1(PublicModel):
    schema_: Literal["core4.0"] = Field(alias="schema")
    message_id: Ident
    text: Text
    receipts: list[PublicReceipt]
    used_fact_ids: list[Ident]
    used_claim_ids: list[Ident]
    asked: Asked | None
    options: Options | None
    review: Review
    usage: PublicUsage
    # Existing core3 readers use these optional projections during migration.
    schema_version: Literal["core4.0"] | None = None
    answer: str | None = None
    validation: Validation | None = None
    meta: PublicMeta | None = None

    @model_validator(mode="after")
    def same_text(self) -> EnvelopeV1:
        if self.answer is not None and self.answer != self.text:
            raise ValueError("兼容回答与正文不符")
        return self


class EventData(PublicModel):
    v: Literal[1]
    run_id: Ident
    seq: int = Field(ge=1)
    ts: str = Field(
        pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?\+08:00$",
        json_schema_extra={"format": "date-time"},
    )

    @field_validator("v", mode="before")
    @classmethod
    def exact_version(cls, value: Any) -> Any:
        if type(value) is not int:
            raise ValueError("事件版本必须为整数")
        return value

    @field_validator("ts")
    @classmethod
    def beijing_instant(cls, value: str) -> str:
        if datetime.fromisoformat(value).utcoffset() != timedelta(hours=8):
            raise ValueError("事件时间必须为北京时间")
        return value


class Started(EventData):
    thread_id: Ident
    message_id: Ident
    area_id: Ident | None = None
    topic_id: Ident | None = None
    incognito: bool


class Status(EventData):
    text: str = Field(min_length=1, max_length=160)
    phase: Literal["thinking", "tool", "writing", "reviewing"]


class ToolCallEvent(EventData):
    call_id: Ident
    name: str = Field(pattern=r"^[a-z][a-z0-9_]{0,79}$")
    summary: str = Field(min_length=1, max_length=160)

    @field_validator("summary")
    @classmethod
    def no_credentials(cls, value: str) -> str:
        if re.search(r"sk-[A-Za-z0-9_-]{20,}|-----BEGIN .*PRIVATE KEY-----", value):
            raise ValueError("安全摘要含凭据")
        return value


class ToolResultEvent(ToolCallEvent):
    ok: bool
    receipt: PublicReceipt | None = None


class TextDelta(EventData):
    text: str = Field(min_length=1, max_length=200_000)


class TextReset(EventData):
    text: str = Field(max_length=200_000)
    reason: Literal["revised", "resumed"]
    revision_id: Ident | None = None


class MemoryReceipt(EventData):
    model_config = ConfigDict(
        json_schema_extra={
            "oneOf": [
                {
                    "required": ["fact_id"],
                    "properties": {"fact_id": {"type": "string"}, "proposal_id": {"type": "null"}},
                },
                {
                    "required": ["proposal_id"],
                    "properties": {"proposal_id": {"type": "string"}, "fact_id": {"type": "null"}},
                },
            ]
        }
    )
    fact_id: Ident | None = None
    proposal_id: Ident | None = None
    write_status: Literal["saved", "updated", "pending_confirm", "undone", "rejected"]
    summary: str = Field(min_length=1, max_length=160)
    undo_token: str | None = Field(default=None, max_length=1024)
    sensitive: bool

    @model_validator(mode="after")
    def one_entity(self) -> MemoryReceipt:
        if (self.fact_id is None) == (self.proposal_id is None):
            raise ValueError("记忆回执须指定一个事实或提议")
        return self


class AskUserEvent(EventData, Asked):
    """The same question object terminates this turn and appears in core4.0."""


class PresentOptionsEvent(EventData, Options):
    """Decision options are identical in the event and final envelope."""


class ReviewEvent(EventData, Review):
    """Only reason codes and severity, never critic quotes or private trace."""


class Final(EventData):
    message_id: Ident
    envelope: EnvelopeV1

    @model_validator(mode="after")
    def matching_message(self) -> Final:
        if self.message_id != self.envelope.message_id:
            raise ValueError("最终消息标识不一致")
        return self


class Error(EventData):
    code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,79}$")
    message: str = Field(min_length=1, max_length=500)
    retryable: bool
