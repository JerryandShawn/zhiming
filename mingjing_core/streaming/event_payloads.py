"""Per-type v1 payload validation, independent of stream sequencing or storage."""

from typing import Literal

from pydantic import Field, model_validator

from .event_nested import (
    AskUserPayload,
    Identifier,
    MemoryReceiptPayload,
    PresentOptionsPayload,
    ReviewPayload,
    StrictShape,
)
from .public_shapes import PublicMeta, PublicReceipt, PublicUsage, PublicValidation


class StartedPayload(StrictShape):
    thread_id: Identifier
    message_id: Identifier
    area_id: Identifier | None = None
    topic_id: Identifier | None = None
    incognito: bool


class StatusPayload(StrictShape):
    text: str = Field(repr=False, min_length=1, max_length=160)
    phase: Literal["thinking", "tool", "writing", "reviewing"]


class ToolCallPayload(StrictShape):
    call_id: Identifier
    name: str = Field(pattern=r"^[a-z][a-z0-9_]{0,79}$")
    summary: str = Field(repr=False, min_length=1, max_length=160)


class ToolResultPayload(ToolCallPayload):
    ok: bool
    receipt: PublicReceipt | None = Field(default=None, repr=False)


class TextDeltaPayload(StrictShape):
    text: str = Field(repr=False, min_length=1, max_length=200000)


class TextResetPayload(TextDeltaPayload):
    text: str = Field(repr=False, max_length=200000)
    reason: Literal["revised", "resumed"]
    revision_id: Identifier | None = None


class Core4Envelope(StrictShape):
    schema_name: Literal["core4.0"] = Field(alias="schema")
    message_id: Identifier
    text: str = Field(repr=False, min_length=1, max_length=200000)
    receipts: list[PublicReceipt] = Field(repr=False)
    used_fact_ids: list[Identifier]
    used_claim_ids: list[Identifier]
    asked: AskUserPayload | None = Field(repr=False)
    options: PresentOptionsPayload | None = Field(repr=False)
    review: ReviewPayload
    usage: PublicUsage = Field(repr=False)
    schema_version: Literal["core4.0"] | None = None
    answer: str | None = Field(default=None, repr=False)
    validation: PublicValidation | None = None
    meta: PublicMeta | None = None


class FinalPayload(StrictShape):
    message_id: Identifier
    envelope: Core4Envelope = Field(repr=False)

    @model_validator(mode="after")
    def same_message(self) -> "FinalPayload":
        if self.message_id != self.envelope.message_id:
            raise ValueError("message_id_mismatch")
        return self


class ErrorPayload(StrictShape):
    code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,79}$")
    message: str = Field(repr=False, min_length=1, max_length=500)
    retryable: bool


PAYLOAD_MODELS = {
    "started": StartedPayload,
    "status": StatusPayload,
    "tool_call": ToolCallPayload,
    "tool_result": ToolResultPayload,
    "text_delta": TextDeltaPayload,
    "text_reset": TextResetPayload,
    "memory_receipt": MemoryReceiptPayload,
    "ask_user": AskUserPayload,
    "present_options": PresentOptionsPayload,
    "review": ReviewPayload,
    "final": FinalPayload,
    "error": ErrorPayload,
}
