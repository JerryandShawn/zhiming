"Copied v3 warning rules: regex values and denial semantics are preserved."

import re

from .legacy_guarantee_denials import (
    explicit_denial,
    finite_guarantee_denial,
    finite_inference_is_asserted,
    guarantee_pattern,
)

_V3_001 = (
    '^[，,]本轮已更正为(?:"不产生付款承诺但消耗不可收回的时间与机会成本，不能视为零成本或完全无损失"|“不'
    "产生付款承诺但消耗不可收回的时间与机会成本，不能视为零成本或完全无损失”)"
)
_V3_002 = (
    '^修正为(?:"可停止但已投入时间不可收回、承诺后可逆性取决于未知退出条件"|'
    "“可停止但已投入时间不可收回、承诺后可逆性取决于未知退出条件”)"
)
_V3_003 = "(?:撤回|收回|否定|纠正|更正|修正)(?:上一轮|先前|之前|此前|原先)?(?:的|将|关于|对)?\\s*$"
_V3_004 = (
    "^\\s*[，,：:]?\\s*(?:这(?:一(?:说法|判断|承诺))?(?:属于|是)|该(?:说法|判断|"
    "承诺)(?:属于|是)|(?:属于|是))?\\s*(?:过度承诺|过于绝对|错误|不成立|不准确|没有依据|缺"
    "乏依据|已(?:经)?撤回|现(?:在)?撤回|应当撤回|需要撤回|需(?:要)?修正|予以修正)"
)
_V3_005 = "^\\s*[，,:：]?\\s*(?:此|该)(?:断语|表述|说法|判断|承诺)\\s*(?:依据不足|缺乏依据|没有依据|不成立)"
_V3_006 = "已(?:经)?(?:修复|纠正|更正|修正)(?:上(?:一)?轮|先前|之前|此前|原先)(?:错误|过度(?:断语|承诺))"
_V3_007 = (
    "^[”\"’\\'」』`]?\\s*(?:(?:的|这个|这一)?(?:说法|判断|承诺|结论)(?:在条款确认前都"
    ")?)?\\s*(?:不成立|不能成立|没有依据|缺乏依据|尚无依据|并无依据|属于过度承诺|是过度承诺|应当撤"
    "回|已经撤回|不能保证|不能承诺)"
)
_V3_008 = "^、未强调损失可能，现已在各选项的reversibility字段中明确[—-]+退出条件、费用和风险条件均未经确认"
_V3_009 = (
    "是否|能否|可否|吗|么|[？?]|不要|请避免|别(?:说|承诺|保证)|不排除|不能否认|不可否认|未排除"
    "|可能|或许|也许|据说|有人说|撤回|收回|修复|修正|纠正|更正|上一轮|此前|之前|先前"
)


def _closed_repair(local_history: str, withdrawal: str, quoted_terms: str) -> bool:
    old_pause = re.search("上一轮将(?:\"暂缓决定\"|“暂缓决定”|\\'暂缓决定\\'|‘暂缓决定’)描述为$", local_history)
    if (
        old_pause
        and quoted_terms == "完全可逆"
        and (
            not re.search(
                "(?:不是|并非|没有|未曾|尚未|不会|不能|不|未)\\s*[“\"‘\\'「『`]?\\s*$",
                local_history[: old_pause.start()],
            )
        )
        and re.match(_V3_001, withdrawal)
    ):
        return True
    revised_from = re.search("已将decision_options中所有reversibility表述从$", local_history)
    if (
        revised_from
        and (
            not re.search(
                "(?:不是|并非|没有|未曾|尚未|不会|不能|不|未)\\s*[“\"‘\\'「『`]?\\s*$",
                local_history[: revised_from.start()],
            )
        )
        and re.match(_V3_002, withdrawal)
    ):
        return True
    return bool(
        explicit_denial(local_history, withdrawal)
        and re.fullmatch(
            "(?:" + guarantee_pattern + ")(?:(?:、|,|，|或|和|及|与)(?:" + guarantee_pattern + "))*", quoted_terms
        )
    )


def _withdrawal_signal(history: str, local_history: str, withdrawal: str) -> bool:
    withdrawn = False
    retraction = re.search(_V3_003, local_history)
    if retraction and (
        not re.search(
            "(?:不是|并非|未曾|尚未|没有|不会|不能|无需|不必|不|未)\\s*$", local_history[: retraction.start()]
        )
    ):
        withdrawn = True
    if re.search(
        "(?:修复|修正|纠正|更正)了?(?:上一轮|先前|之前|此前|原先)?(?:对|关于)?\\s*$", local_history
    ) and re.match("^\\s*的(?:过度(?:断语|承诺)|错误(?:断语|判断|说法))", withdrawal):
        withdrawn = True
    if (
        re.search("上一轮|先前|之前|此前|原先|原来的|原本|旧(?:说法|答复|判断)", history)
        and re.search("描述|表述|称|说|判断|写|承诺", history)
        and re.match(_V3_004, withdrawal)
    ):
        withdrawn = True
    if (
        re.search("上一轮|先前|之前|此前|原先|原来的|原本|旧(?:说法|答复|判断)", history)
        and re.search("描述|表述|称|说|判断|写|承诺", history)
        and re.match(_V3_005, withdrawal)
    ):
        withdrawn = True
    prior_repair = re.search(_V3_006, history)
    deleted_wording = re.search("删除了\\s*$", local_history)
    if (
        prior_repair
        and deleted_wording
        and (not re.search("(?:不是|并非|未曾|尚未|没有|不会|不能|不|未)\\s*$", history[: prior_repair.start()]))
        and (
            not re.search("(?:不是|并非|未曾|尚未|没有|不会|不能|不|未)\\s*$", local_history[: deleted_wording.start()])
        )
    ):
        withdrawn = True
    return withdrawn


def _not_withdrawn(clause: str, assertion: re.Match[str]) -> bool:
    withdrawn = False
    for opening, closing in (("“", "”"), ('"', '"'), ("‘", "’"), ("'", "'"), ("「", "」"), ("『", "』"), ("`", "`")):
        for quoted in re.finditer(
            re.escape(opening) + "[^" + re.escape(closing) + "]{0,160}" + re.escape(closing), clause
        ):
            if not (quoted.start() < assertion.start() and assertion.end() < quoted.end()):
                continue
            history = clause[max(0, quoted.start() - 160) : quoted.start()]
            withdrawal = clause[quoted.end() : quoted.end() + 90]
            local_history = re.split("[，,：:]|但(?:是(?!否))?|然而|不过|可是|事实上|实际上|反而|却", history)[-1]
            quoted_terms = quoted.group()[1:-1]
            if _closed_repair(local_history, withdrawal, quoted_terms):
                return False
            if _withdrawal_signal(history, local_history, withdrawal):
                withdrawn = True
    return not withdrawn


def guarantee_is_asserted(clause: str, assertion: re.Match[str], context: str, source: bool = False) -> bool:
    before, after = (clause[: assertion.start()], clause[assertion.end() :])
    local = re.split("[，,：:]|但(?:是(?!否))?|然而|不过|可是|事实上|实际上|反而|却", before)[-1]
    inference = finite_inference_is_asserted(clause, assertion, local, after, context, source)
    if inference is not None:
        return inference
    if re.search("不能(?:(?:从牌面)?推断为|当作)", local):
        start = assertion.start() - len(local)
        if re.search("(?:不是|并非|不能说|不意味着|不代表|不能|不可|无法|不可能|不|未)\\s*[：:]\\s*$", clause[:start]):
            return not source
        for opening, closing in (
            ("“", "”"),
            ('"', '"'),
            ("‘", "’"),
            ("'", "'"),
            ("「", "」"),
            ("『", "』"),
            ("`", "`"),
        ):
            for quoted in re.finditer(
                re.escape(opening) + "[^" + re.escape(closing) + "]*" + re.escape(closing), context
            ):
                for occurrence in re.finditer(re.escape(clause), context):
                    if (
                        quoted.start() < occurrence.start() + assertion.start()
                        and occurrence.start() + assertion.end() < quoted.end()
                    ):
                        return not source
    if explicit_denial(local, after):
        return False
    if finite_guarantee_denial(clause, assertion, local, after, context):
        return False
    if assertion.group() == "零损失" and local == "退出是否" and re.fullmatch("也取决于尚未确认的具体条款", after):
        return False
    if re.search("(?:是否|能否|可否)[“\"‘\\'「『`]?$", local) and re.match(
        "^[”\"’\\'」』`]?(?:(?:、|或)(?:是否|能否|可否)?(?:"
        + guarantee_pattern
        + "|零成本))*\\s*(?:尚未|还未|未经|未)(?:确认|核实|验证)",
        after,
    ):
        return False
    if re.match(_V3_007, after):
        return False
    old_inquiry = re.search("(?:此前|上一轮|先前|之前|原先)将(?:\"询问\"|“询问”|\\'询问\\'|‘询问’)表述为$", local)
    if (
        old_inquiry
        and (
            not re.search(
                "(?:不是|并非|没有|未曾|尚未|不会|不能|不|未)\\s*[“\"‘\\'「『`]?\\s*$", local[: old_inquiry.start()]
            )
        )
        and re.match(_V3_008, after)
    ):
        return False
    return _not_withdrawn(clause, assertion)


def guarantee_kind(assertion: re.Match[str]) -> str:
    value = assertion.group()
    if value in ("没有任何损失", "无损失", "零损失"):
        return "无损失"
    if value.startswith("随时"):
        return "随时退款" if value.endswith("退款") else "随时退出"
    return value


def guarantee_issues(text: str, factual: str) -> list[str]:
    issues = []
    clauses = re.split("[。；;\\n]", text)
    supported_guarantees = set()
    for source_clause in re.split("[。；;\\n]", factual):
        if re.search(_V3_009, source_clause):
            continue
        for source_assertion in re.finditer(guarantee_pattern, source_clause):
            if guarantee_is_asserted(source_clause, source_assertion, factual, source=True):
                supported_guarantees.add(guarantee_kind(source_assertion))
    if any(
        guarantee_kind(assertion) not in supported_guarantees and guarantee_is_asserted(clause, assertion, text)
        for clause in clauses
        for assertion in re.finditer(guarantee_pattern, clause)
    ):
        issues.append("费用、退出和风险条件未经确认，不能承诺完全可逆或无损失")
    return issues
