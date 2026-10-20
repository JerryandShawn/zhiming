"""Nested shapes frozen by brain document 28, section 3, contract v1."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Identifier = Annotated[str, Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")]


class StrictShape(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, allow_inf_nan=False, hide_input_in_errors=True)


class AskOption(StrictShape):
    id: Identifier
    label: str = Field(repr=False, min_length=1, max_length=200)


class AskUserPayload(StrictShape):
    ask_id: Identifier
    question: str = Field(repr=False, min_length=1, max_length=500)
    options: list[AskOption] = Field(repr=False, max_length=4)
    allow_free_text: bool
    multi: bool
    why: str = Field(repr=False, min_length=1, max_length=500)

    @model_validator(mode="after")
    def unique_options(self) -> "AskUserPayload":
        if len({item.id for item in self.options}) != len(self.options):
            raise ValueError("duplicate_option_id")
        return self


class DecisionOption(StrictShape):
    id: Identifier
    title: str = Field(repr=False, min_length=1, max_length=120)
    benefit: str = Field(repr=False, max_length=500)
    cost: str = Field(repr=False, max_length=500)
    risk: str = Field(repr=False, max_length=500)
    reversibility: Literal["easy", "partial", "hard", "unknown"]
    first_step: str = Field(repr=False, max_length=500)
    unknowns: list[str] = Field(repr=False, max_length=20)


class PresentOptionsPayload(StrictShape):
    options_id: Identifier
    prompt: str | None = Field(default=None, repr=False, max_length=500)
    options: list[DecisionOption] = Field(min_length=2, max_length=4, repr=False)

    @model_validator(mode="after")
    def unique_options(self) -> "PresentOptionsPayload":
        if len({item.id for item in self.options}) != len(self.options):
            raise ValueError("duplicate_option_id")
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


class ReviewReason(StrictShape):
    code: ReviewCode
    severity: int = Field(ge=1, le=5)


class ReviewPayload(StrictShape):
    state: Literal["pending", "passed", "revised", "skipped"]
    reasons: list[ReviewReason]
    revision_id: Identifier | None = None


class MemoryReceiptPayload(StrictShape):
    fact_id: Identifier | None = None
    proposal_id: Identifier | None = None
    write_status: Literal["saved", "pending_confirm", "undone", "rejected"]
    summary: str = Field(repr=False, min_length=1, max_length=160)
    undo_token: str | None = Field(default=None, repr=False, max_length=1024)
    sensitive: bool

    @model_validator(mode="after")
    def one_target(self) -> "MemoryReceiptPayload":
        if bool(self.fact_id) == bool(self.proposal_id):
            raise ValueError("exactly_one_receipt_target")
        return self
