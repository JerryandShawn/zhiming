"""Pure v4 write policy: source authorization precedes classification and prior consent."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .consent_text import has_storage_optout

if TYPE_CHECKING:
    from mingjing_core.timekit.clock import Clock

    from .contracts import (
        Confirmation,
        MemoryFact,
        MemoryScope,
        MemorySettings,
        MemorySnapshot,
        PolicyDecision,
    )

CATEGORY_PATTERNS = {
    "health": re.compile(
        r"确诊|诊断|病历|病理|医嘱|服用|体检|结节|用药|服药|停药|处方|抑郁|躁郁|精神科|怀孕|疾病|癌症"
        r"|手术|住院|治疗|血压|血糖|糖尿病|肝炎|心理咨询|失眠"
    ),
    "sexual_orientation": re.compile(
        r"同性恋|双性恋|泛性恋|性取向|无性恋|跨性别|同性伴侣|出柜|喜欢同性|伴侣.{0,8}同性"
        r"|我和女朋友.{0,6}女性|我和男朋友.{0,6}男性"
    ),
    "religion": re.compile(
        r"信仰|信奉|宗教(?:立场|身份)|基督徒|佛教徒|穆斯林|天主教徒|无神论|清真寺|礼拜|受洗|皈依|教信徒"
        r"|犹太教.{0,8}习俗"
    ),
    "politics": re.compile(
        r"政治(?:立场|观点|倾向|信仰|信念)|政治上.{0,6}倾向|政党倾向|支持.{0,8}(?:政党|党)|党员|党派|投票给"
        r"|政治组织|政治运动.{0,8}支持"
    ),
    "legal": re.compile(
        r"官司|违法经历|起诉|诉讼|犯罪记录|被拘留|被判刑|纠纷|行政处罚|法院|传票|仲裁|案底|刑事|判决"
        r"|盗窃.{0,8}处罚"
    ),
}
SECRET = re.compile(r"密码|密钥|api.?key|身份证|银行卡|口令|sk-[a-zA-Z0-9_-]{16,}|(?<!\d)\d{17}[\dXx](?!\d)", re.I)
FINANCE = re.compile(
    r"债务|欠款|欠债|贷款|房贷|车贷|欠银行|[一二三四五六七八九十百千万亿两\d]+\s*(?:元|块钱|万元|人民币|美元|日元|港币|欧元)"
    r"|(?:存款|工资|收入|年薪|月薪).{0,10}[一二三四五六七八九十百千万亿两\d]+"
)
OTHER_PERSON = re.compile(
    r"(?:朋友|同事|室友|同学|老板|领导|妈妈|爸爸|母亲|父亲|家人|[表堂]?[哥姐弟妹]|伴侣|老公|老婆|丈夫|妻子|他|她"
    r"|小[\u4e00-\u9fff]{1,3})"
    r".{0,20}(?:病|确诊|收入|工资|年薪|感情|婚|恋|出生|生日|住址|电话|债务|存款)"
)
BIRTH = re.compile(
    r"(?:我|本人)(?:的)?出生|(?:我|本人).{0,16}(?:年出生|清晨出生|凌晨出生|晚上出生|出生时间)"
    r"|我的生日(?:是|为)|出生(?:时间|地点|日期)|生于.{0,12}(?:年|月|日)"
)
INCOGNITO_COMMAND = re.compile(r"(?<!不)(?<!别)(?:开启?|进入|使用|这段|本次|现在).{0,4}无痕")
HINT_ALIASES = {
    "健康": "health",
    "身心": "health",
    "他人隐私": "third_party",
    "金额": "finance",
    "财务": "finance",
    "性取向": "sexual_orientation",
    "宗教": "religion",
    "政治": "politics",
    "法律": "legal",
    "high": "model_sensitive",
    "sensitive": "model_sensitive",
    "敏感": "model_sensitive",
    "credential": "secret",
    "password": "secret",
    "密钥": "secret",
    "密码": "secret",
    "身份证": "secret",
    "银行卡": "secret",
}
KNOWN_CATEGORIES = frozenset({*CATEGORY_PATTERNS, "finance", "third_party", "model_sensitive", "secret"})
BENIGN_HINTS = frozenset({"", "none", "low", "normal", "public", "非敏感", "ordinary"})


@dataclass(frozen=True)
class Sensitivity:
    categories: tuple[str, ...] = ()
    profile_confirmation: bool = False
    secret: bool = False


def _hints(model_hint: object) -> set[str]:
    values = (model_hint,) if isinstance(model_hint, str) else model_hint or ()
    if not isinstance(values, (tuple, list, frozenset, set)):
        return {"model_sensitive"}
    result = set()
    for value in values:
        if not isinstance(value, str):
            result.add("model_sensitive")
            continue
        label = value.strip().casefold()
        if label in BENIGN_HINTS:
            continue
        category = HINT_ALIASES.get(label, label)
        result.add(category if category in KNOWN_CATEGORIES else "model_sensitive")
    return result


def classify_sensitivity(
    text: str, kind: str = "background", model_hint: object = (), subject_role: str = "self"
) -> Sensitivity:
    if not isinstance(text, str) or not isinstance(kind, str) or subject_role not in {"self", "other"}:
        raise ValueError("敏感分类输入无效")
    categories = {name for name, pattern in CATEGORY_PATTERNS.items() if pattern.search(text)} | _hints(model_hint)
    if FINANCE.search(text):
        categories.add("finance")
    other = subject_role == "other" or bool(OTHER_PERSON.search(text))
    if other:
        categories.add("third_party")
    profile = not other and bool(BIRTH.search(text))
    return Sensitivity(tuple(sorted(categories)), profile, bool(SECRET.search(text)) or "secret" in categories)


def quote_fingerprint(quote: str) -> str:
    return hashlib.sha256(quote.encode("utf-8")).hexdigest()


def question_key(fact: MemoryFact, scope: MemoryScope, categories: tuple[str, ...]) -> str:
    anchors = [
        (item.source_id, item.revision, item.start, item.end, quote_fingerprint(item.quote)) for item in fact.anchors
    ]
    raw = json.dumps(
        [scope.owner_id, scope.subject_id, sorted(anchors), sorted(categories)],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return "memory-consent:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _confirmation_matches(
    confirmation: Confirmation, fact: MemoryFact, scope: MemoryScope, categories: tuple[str, ...], clock: Clock
) -> bool:
    if len(fact.anchors) != 1 or confirmation.scope != scope:
        return False
    anchor = fact.anchors[0]
    return (
        confirmation.source_id == anchor.source_id
        and confirmation.source_revision == anchor.revision
        and confirmation.quote_fingerprint == quote_fingerprint(anchor.quote)
        and frozenset(categories) == confirmation.categories
        and fact.said_at <= confirmation.at <= clock.now()
    )


def _explicit_optout(snapshot: MemorySnapshot, incoming: MemoryFact) -> bool:
    sources = [source for source in snapshot.sources if source.id in incoming.source_ids]
    return any(
        source.optout or has_storage_optout(source.text) or INCOGNITO_COMMAND.search(source.text) for source in sources
    )


def _authorize(snapshot: MemorySnapshot, incoming: MemoryFact, scope: MemoryScope) -> PolicyDecision | None:
    from .contracts import PolicyDecision
    from .guards import MemoryGuardError, authorize_fact

    if snapshot.scope != scope or (incoming.owner_id, incoming.subject_id) != (scope.owner_id, scope.subject_id):
        raise MemoryGuardError("scope_mismatch")
    for source_id in incoming.source_ids:
        source = snapshot.source(source_id)
        if source is not None and (source.owner_id, source.subject_id) != (scope.owner_id, scope.subject_id):
            raise MemoryGuardError("source_scope_mismatch")
    try:
        authorize_fact(incoming, snapshot, scope)
    except MemoryGuardError as error:
        sources = [snapshot.source(item) for item in incoming.source_ids]
        if str(error) == "source_storage_forbidden" and _explicit_optout(snapshot, incoming):
            return PolicyDecision("stop", reason="explicit_optout")
        if str(error) == "source_storage_forbidden":
            return PolicyDecision("reject", reason="secret_never_saved")
        if str(error) == "source_unavailable" and any(item and (item.incognito or item.optout) for item in sources):
            return PolicyDecision("stop", reason="source_private_or_optout")
        raise
    return None


def decide_policy(
    snapshot: MemorySnapshot,
    incoming: MemoryFact,
    *,
    scope: MemoryScope,
    clock: Clock,
    settings: MemorySettings | None = None,
    confirmation: Confirmation | None = None,
    model_hint: object = (),
) -> PolicyDecision:
    from .contracts import MemorySettings, PolicyDecision, utc
    from .guards import MemoryGuardError

    now = utc(clock.now())
    if incoming.said_at > now or incoming.recorded_at > now or incoming.recorded_at < incoming.said_at:
        raise MemoryGuardError("fact_time_invalid")
    if any(source.at > now for source in snapshot.sources if source.id in incoming.source_ids):
        raise MemoryGuardError("source_time_invalid")
    blocked = _authorize(snapshot, incoming, scope)
    if blocked is not None:
        return blocked
    if _explicit_optout(snapshot, incoming):
        return PolicyDecision("stop", (), reason="explicit_optout")
    content = "\n".join([incoming.text, *(anchor.quote for anchor in incoming.anchors)])
    sensitive = classify_sensitivity(content, incoming.kind, model_hint)
    if sensitive.secret:
        return PolicyDecision("reject", sensitive.categories, reason="secret_never_saved")
    if sensitive.profile_confirmation:
        return PolicyDecision("profile_confirm", sensitive.categories, reason="own_birth_profile_flow")
    if not sensitive.categories:
        return PolicyDecision("save", (), reason="non_sensitive_default")
    if confirmation is not None and _confirmation_matches(confirmation, incoming, scope, sensitive.categories, clock):
        return PolicyDecision(
            "save" if confirmation.decision == "granted" else "stop",
            sensitive.categories,
            reason="bound_confirmation" if confirmation.decision == "granted" else "confirmation_declined",
        )
    options = settings or MemorySettings()
    if "model_sensitive" not in sensitive.categories and set(sensitive.categories) <= options.auto_save_categories:
        return PolicyDecision("save", sensitive.categories, reason="category_previously_authorized")
    key = question_key(incoming, scope, sensitive.categories)
    return PolicyDecision(
        "proposal",
        sensitive.categories,
        ask_required=key not in snapshot.asked_keys,
        question_key=key,
        reason="sensitive_confirmation_required",
    )
