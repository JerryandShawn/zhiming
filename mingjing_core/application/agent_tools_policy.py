"""v4 writing policy wraps existing v3 authority; it never changes v3 defaults."""

from __future__ import annotations

import re
from typing import Any

from mingjing_core.application.memory import SECRET, MemoryService
from mingjing_core.application.memory2_consent import categories_granted, consent_live
from mingjing_core.domain.contracts import EvidenceError, ScopeError
from mingjing_core.memory.policy import clause, has_optout, mask_quoted, third_party
from mingjing_core.repositories.postgres import fingerprint

SENSITIVITIES = ("health", "third_party", "money", "identity", "legal")
RULES = {
    "health": re.compile(r"诊断|确诊|复诊|用药|吃药|服药|抑郁|焦虑症|失眠|怀孕|疾病|血压|癌症|创伤|自杀|病历|停药"),
    "money": re.compile(r"存款|欠款|债务|负债|收入|工资|薪水|借款|贷款|\d[\d.,，]*\s*(?:万|元|块|美元|人民币)"),
    "identity": re.compile(r"性取向|同性恋|双性恋|宗教|信教|佛教|基督教|政治立场|党派"),
    "legal": re.compile(r"官司|诉讼|法律纠纷|违法|犯罪|刑事|被捕|拘留"),
}
CREDENTIAL = re.compile(r"卡号|身份证号|访问令牌|sk-[A-Za-z0-9_-]{20,}", re.I)
BIRTH = re.compile(r"出生|生辰|生日.{0,8}\d")
RELATED_PERSON = re.compile(
    r"(?:^|[，,。！？；;\n\s])\s*(?:我的?)?(?:妈妈|爸爸|母亲|父亲|妈|爸|家人|朋友|同事)"
    r"(?=今年|去年|最近|目前|一直|血压|患|确诊|用药|的|是|出生|生日)"
)
KIND_MAP = {"relationship": "background", "habit": "preference"}


def sensitivity(quote: str, source: str, start: int, end: int, reported: str = "normal") -> str:
    local = clause(source, start, end, comma=False)
    if SECRET.search(quote) or CREDENTIAL.search(quote):
        return "secret"
    if third_party(local) or RELATED_PERSON.search(local):
        return "third_party"
    if BIRTH.search(quote):
        return "profile"
    found = next((name for name, pattern in RULES.items() if pattern.search(local)), "normal")
    if third_party(local):
        return "third_party"
    return found if found != "normal" else reported


def sensitivity_categories(quote: str, source: str, start: int, end: int, reported: str = "normal") -> tuple[str, ...]:
    local = clause(source, start, end, comma=False)
    level = sensitivity(quote, source, start, end, reported)
    found = [name for name, pattern in RULES.items() if pattern.search(local)]
    if level in SENSITIVITIES:
        found.append(level)
    return tuple(dict.fromkeys(found))


def source_span(source: dict[str, Any], quote: str, start: int | None, end: int | None) -> tuple[int, int]:
    text = source.get("content", "")
    if not isinstance(quote, str) or not quote or quote not in text:
        raise EvidenceError("原话必须逐字来自指定用户消息")
    if start is None and end is None:
        if text.count(quote) != 1:
            raise EvidenceError("原话区间不唯一，需要确认具体位置")
        start, end = text.index(quote), text.index(quote) + len(quote)
    if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(text):
        raise EvidenceError("原话区间无效")
    if text[start:end] != quote or text.find(quote) != start:
        raise EvidenceError("原话区间不匹配或当前写入路径不能唯一定位")
    return start, end


def source_policy(source: dict[str, Any], subject: str, thread_id: str) -> None:
    policy = source.get("policy", {})
    if source["subject_id"] != subject or source.get("thread_id") != thread_id:
        raise ScopeError("工具来源不属于当前人物和线程")
    if source["status"] != "active" or source.get("role") != "user":
        raise EvidenceError("助手、系统或已撤销消息不能成为用户事实")
    if policy.get("origin") != "current_user" or policy.get("run_context") is not True:
        raise EvidenceError("工具需要当前用户的受信原始来源")


class V4FactMemory(MemoryService):
    def _fact_id(
        self,
        owner: str,
        message_id: str,
        start: int,
        end: int,
        kind: str,
        case_id: str | None,
        field: str | None,
        value: Any,
        authorization_id: str | None,
    ) -> str:
        original = super()._fact_id(owner, message_id, start, end, kind, case_id, field, value, authorization_id)
        if authorization_id:
            proof = self.repo.get(owner, "consent", authorization_id)
            if proof.get("authority") == "p5_proposal":
                return "fact_" + fingerprint([original, authorization_id])[:32]
        return original

    def _third_party_authorized(
        self,
        owner: str,
        subject: str,
        source: dict[str, Any],
        kind: str,
        authorization_id: str | None,
        case_id: str | None,
        quote: str,
    ) -> bool:
        policy = source.get("policy", {})
        if policy.get("origin") != "current_user" or policy.get("run_context") is not True:
            return False
        if authorization_id:
            return self._authorized(owner, subject, source, kind, authorization_id, case_id, quote)
        start = source["content"].find(quote)
        categories = sensitivity_categories(quote, source["content"], start, start + len(quote))
        return "third_party" in categories and categories_granted(self, owner, subject, categories)

    def _authorized(
        self,
        owner: str,
        subject: str,
        source: dict[str, Any],
        kind: str,
        authorization_id: str | None,
        case_id: str | None,
        quote: str,
    ) -> bool:
        if super()._authorized(owner, subject, source, kind, authorization_id, case_id, quote):
            if authorization_id:
                proof = self.repo.get(owner, "consent", authorization_id)
                if proof.get("authority") == "p5_proposal" and not consent_live(self, owner, subject, proof):
                    raise EvidenceError("记忆提案授权已失效")
            return True
        policy = source.get("policy", {})
        if subject != "self" or policy.get("origin") != "current_user" or policy.get("run_context") is not True:
            return False
        start = source["content"].find(quote)
        level = sensitivity(quote, source["content"], start, start + len(quote))
        if level in SENSITIVITIES:
            categories = sensitivity_categories(quote, source["content"], start, start + len(quote))
            return categories_granted(self, owner, subject, categories)
        # The v4 design changes ordinary events/goals to default-save; source,
        # span, opt-out, revoked ranges and secret checks still run in save_fact.
        settings = self.repo.assert_scope(owner, subject)["settings"]
        return level == "normal" and settings.get("auto_save_low_sensitivity", True)


def refusal(source: dict[str, Any], quote: str, start: int, end: int) -> dict[str, Any] | None:
    if has_optout(source["content"]) or "无痕" in source["content"]:
        return {"write_status": "stopped", "code": "source_optout"}
    if not mask_quoted(source["content"])[start:end].strip():
        return {"write_status": "rejected", "code": "quoted_speech"}
    return None
