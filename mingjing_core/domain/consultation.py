"""Typed execution and presentation contracts, free of provider/runtime imports."""
from typing import Any, Literal, Protocol
from pydantic import BaseModel, ConfigDict, Field


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class ConsultationPlan(Contract):
    mode: Literal["conversation", "support", "urgent_support", "memory", "chart", "tarot", "decision", "report"] = "conversation"
    topic: Literal["general", "study", "career", "relationships", "finance", "family", "home", "health"] = "general"
    systems: list[Literal["bazi", "ziwei", "astro", "tarot"]] = Field(default_factory=list, max_length=4)
    target_date: str
    time_scale: Literal["natal", "daily", "monthly", "yearly"] = "natal"
    decision: bool = False
    rationale: str = ""
    missing_inputs: list[str] = Field(default_factory=list)


class MemoryProposal(Contract):
    quote: str = Field(min_length=1, max_length=4000)
    category: str = "背景"
    case_id: str | None = None
    field: str | None = None
    value: Any = None
    supersedes: str | None = None


class Intake(Contract):
    plan: ConsultationPlan
    proposals: list[MemoryProposal] = Field(default_factory=list, max_length=12)
    retire_fact_ids: list[str] = Field(default_factory=list, max_length=8)
    attachment_observations: list[str] = Field(default_factory=list, max_length=12)


class DecisionOption(Contract):
    option: str
    benefit: str
    cost: str
    risk: str
    reversibility: str
    first_step: str


class FinalAnswer(Contract):
    plain_summary: str = Field(min_length=1, max_length=6000)
    explanation: str = Field(default="", max_length=18000)
    actions: list[str] = Field(default_factory=list, max_length=5)
    decision_options: list[DecisionOption] = Field(default_factory=list, max_length=4)
    follow_up: str = ""
    professional_appendix: str = Field(default="", max_length=30000)
    cited_fact_ids: list[str] = Field(default_factory=list)
    cited_claim_ids: list[str] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list, max_length=12)


class SpecialistAnswer(Contract):
    system: Literal["bazi", "ziwei", "astro", "tarot"]
    claim_ids: list[str] = Field(default_factory=list)
    discussion: str = Field(default="", max_length=10000)
    uncertainties: list[str] = Field(default_factory=list)


class ModelPort(Protocol):
    def generate(self, *, system: str, payload: dict, schema: dict, purpose: str) -> dict: ...


class RuntimePort(Protocol):
    def execute(self, service: Any, owner: str, run_id: str, lease_token: str, emit: Any = None) -> dict: ...


class CoreError(RuntimeError):
    code = "SERVICE_ERROR"
    http_status = 503


class MissingInput(CoreError):
    code = "MISSING_INPUT"
    http_status = 422


class InvalidAnswer(CoreError):
    code = "REFERENCE_ERROR"
    http_status = 422


class ModelUnavailable(CoreError):
    code = "MODEL_UNAVAILABLE"


def render_answer(final: dict) -> str:
    paragraphs = [final["plain_summary"], final.get("explanation", "")]
    options = final.get("decision_options", [])
    if options:
        paragraphs.append("\n\n".join(f"**{o['option']}**\n\n收益：{o['benefit']}\n\n代价：{o['cost']}；风险：{o['risk']}\n\n可逆性：{o['reversibility']}\n\n第一步：{o['first_step']}" for o in options))
    if final.get("actions"):
        paragraphs.append("\n".join("- " + action for action in final["actions"]))
    paragraphs.extend([final.get("follow_up", ""), "\n".join(final.get("caveats", []))])
    return "\n\n".join(p for p in paragraphs if p)
