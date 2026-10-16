"""Knowledge contracts are independent of runtime, channels and model providers."""
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class KnowledgeSource(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    source_id: str
    title: str
    creator: str
    kind: Literal["primary_text_transcription", "original_editorial"]
    locator: str
    section: str
    accessed_on: str
    excerpt: str
    scope_note: str
    rights_note: str


class AllowedInterpretation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    interpretation_id: str
    text_template: str
    scope: str


class KnowledgeRule(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    rule_id: str
    system: Literal["bazi", "ziwei", "astro", "tarot"]
    school_id: str
    version: str
    concept_definition: str
    source_refs: list[str] = Field(min_length=1)
    applicable_topics: list[str] = Field(min_length=1)
    time_scales: list[str] = Field(min_length=1)
    required_features: list[str] = Field(min_length=1)
    preconditions: list[str] = Field(min_length=1)
    exceptions: list[str]
    allowed_interpretations: list[AllowedInterpretation] = Field(min_length=1)
    prohibited_inferences: list[str] = Field(min_length=1)
    conflicts_with: list[str]
    supersedes: list[str]
    editorial_status: Literal["machine_structured_unreviewed", "original_editorial_unreviewed", "expert_reviewed"]
    empirical_status: Literal["traditional_not_empirically_validated", "reflection_not_prediction"]
    predicate_id: str
    limitations: list[str] = Field(min_length=1)
    counterexamples: list[dict[str, Any]] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_identifiers(self):
        identifiers = [item.interpretation_id for item in self.allowed_interpretations]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("duplicate interpretation ID")
        if len(self.required_features) != len(set(self.required_features)):
            raise ValueError("duplicate required feature")
        return self
