"""Public nested allowlists from mainline events_v1 schema, revision f307231."""

from typing import Literal

from pydantic import Field, model_validator

from .event_nested import Identifier, StrictShape


class PublicReceipt(StrictShape):
    write_status: str
    id: Identifier | None = None
    fact_id: Identifier | None = None
    proposal_id: Identifier | None = None
    draw_id: Identifier | None = None
    kind: str | None = None
    revision: int | None = Field(default=None, ge=1)
    status: str | None = None
    code: str | None = None
    affected_ids: list[Identifier] = Field(default_factory=list, max_length=1024)


class TokenUsage(StrictShape):
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    cache_creation_input_tokens: int | None = Field(default=None, ge=0)
    cache_read_input_tokens: int | None = Field(default=None, ge=0)


class PublicUsage(StrictShape):
    model_steps: int | None = Field(default=None, ge=0)
    model_streams_this_execution: int | None = Field(default=None, ge=0)
    replayed_model_steps: int | None = Field(default=None, ge=0)
    reported_tokens: TokenUsage = Field(default_factory=TokenUsage)
    usage_known: bool = False
    offline: bool | None = None


class StructuralWarning(StrictShape):
    code: str
    count: int = Field(ge=1)


class CoreRun(StrictShape):
    run_id: Identifier
    operation_id: Identifier


class PublicMeta(StrictShape):
    core_run: CoreRun
    subject_id: Identifier
    case_ids: list[Identifier]
    structural_warnings: list[StructuralWarning]


class PublicValidation(StrictShape):
    status: Literal["validated"]
    valid: bool
    schema_name: Literal["core4.0"] = Field(alias="schema")

    @model_validator(mode="after")
    def validated_only(self) -> "PublicValidation":
        if self.valid is not True:
            raise ValueError("validation_must_be_true")
        return self
