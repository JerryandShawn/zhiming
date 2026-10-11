"""Typed execution and presentation contracts, free of provider/runtime imports."""
from typing import Any, Literal, Protocol
from enum import Enum
import math
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
    plain_summary: str = Field(min_length=1, max_length=6000, description="用两至四句先回答本轮问题。现实依据和专业细节分别填写explanation/professional_appendix。")
    explanation: str = Field(default="", max_length=18000, description="说明目标、现实约束、证据、选择代价与待核实条件。不能把象征或旧预测当成已发生事实。")
    actions: list[str] = Field(max_length=5, description="独立填写可执行行动，不能仅写在plain_summary。decision=true时至少一项；支持模式最多一项。无行动时明确返回[]。")
    decision_options: list[DecisionOption] = Field(max_length=4, description="decision=true时至少两个可行选项，可包括暂缓核实。每项独立填写真实收益、代价、风险、可逆性、第一步；未知条件明示待确认。其他模式可返回[]。")
    follow_up: str = ""
    professional_appendix: str = Field(default="", max_length=30000)
    cited_fact_ids: list[str] = Field(description="必须独立填写本答复实际使用的reference_data.facts[].id。正文或附录中的ID不能替代此数组。只选本轮有效事实；没有引用时返回[]。")
    cited_claim_ids: list[str] = Field(description="必须独立填写本答复实际使用的reference_data.claims[].claim_id。存在专业声明时至少引用一项；只把ID写进professional_appendix仍不合格。无专业声明时返回[]。")
    caveats: list[str] = Field(default_factory=list, max_length=12)


class SpecialistAnswer(Contract):
    system: Literal["bazi", "ziwei", "astro", "tarot"]
    claim_ids: list[str] = Field(description="独立填写discussion实际采用的reference_data.claims[].claim_id，不可仅在文字中列ID，不可编造。")
    discussion: str = Field(default="", max_length=10000, description="围绕问题解释选中声明的字段、规则、允许意义与反例，约1500字以内；无须复制整个计算产物。完整可核验字段由程序另行展示。")
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


class ModelFailureReason(str, Enum):
    UNKNOWN = "unknown"
    CONFIGURATION = "configuration"
    HTTP = "http"
    NETWORK = "network"
    JSON = "json"
    MAX_TOKENS = "max_tokens"
    TOOL_COUNT = "tool_count"
    TOOL_INPUT = "tool_input"


class ModelUnavailable(CoreError):
    """Provider failure metadata contains fixed categories and token counts only."""
    code = "MODEL_UNAVAILABLE"
    _token_fields = frozenset({'input_tokens', 'output_tokens', 'cache_creation_input_tokens', 'cache_read_input_tokens'})
    _stop_reasons = frozenset({'end_turn', 'max_tokens', 'stop_sequence', 'tool_use', 'pause_turn', 'refusal'})

    def __init__(self, message="模型调用尚未完成，请查询原请求状态", *, reason=ModelFailureReason.UNKNOWN,
                 provider_http_status=None, usage=None, latency_seconds=None, stop_reason=None, tool_count=None):
        super().__init__(message)
        try:self.reason = ModelFailureReason(reason).value
        except (ValueError, TypeError):self.reason = ModelFailureReason.UNKNOWN.value
        self.failure_code = 'MODEL_' + self.reason.upper()
        self.provider_http_status = provider_http_status if type(provider_http_status) is int and 100 <= provider_http_status <= 599 else None
        self.usage = {key:value for key,value in (usage.items() if isinstance(usage,dict) else ())
                      if key in self._token_fields and type(value) is int and 0 <= value <= 2**63 - 1}
        self.usage_known = bool(self.usage)
        self.latency_seconds = round(latency_seconds, 3) if type(latency_seconds) in (int,float) and math.isfinite(latency_seconds) and latency_seconds >= 0 else None
        self.stop_reason = stop_reason if isinstance(stop_reason,str) and stop_reason in self._stop_reasons else 'unknown' if stop_reason is not None else None
        self.tool_count = tool_count if type(tool_count) is int and 0 <= tool_count <= 100000 else None

    def safe_diagnostic(self):
        result = {'code':self.code, 'reason':self.reason, 'failure_code':self.failure_code,
                  'usage':dict(self.usage), 'usage_known':self.usage_known}
        for name in ('provider_http_status', 'latency_seconds', 'stop_reason', 'tool_count'):
            value=getattr(self,name)
            if value is not None:result[name]=value
        return result


def render_answer(final: dict) -> str:
    paragraphs = [final["plain_summary"], final.get("explanation", "")]
    options = final.get("decision_options", [])
    if options:
        paragraphs.append("\n\n".join(f"**{o['option']}**\n\n收益：{o['benefit']}\n\n代价：{o['cost']}；风险：{o['risk']}\n\n可逆性：{o['reversibility']}\n\n第一步：{o['first_step']}" for o in options))
    if final.get("actions"):
        paragraphs.append("\n".join("- " + action for action in final["actions"]))
    paragraphs.extend([final.get("follow_up", ""), "\n".join(final.get("caveats", []))])
    return "\n\n".join(p for p in paragraphs if p)
