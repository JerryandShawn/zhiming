"Copied v3 warning rules: regex values and denial semantics are preserved."

import re
from typing import Any

_V3_001 = "(?:不是|并非|不能说|不意味着|不代表|不能|不可|无法|不可能|不|未)\\s*[“\"‘\\'「『`]?\\s*$"
_V3_002 = (
    "(?:^|[，,]|但(?:是)?|然而|不过|可是|事实上|实际上)(?:同时|仍|然后|现在|还是)?(?"
    ":你)?(?:建议(?:你)?|可以|允许|应当)(?:先)?(?:接受|尝试)(?:该|此|上述|这个)(?"
    ":例外|夜班安排|安排)"
)
_V3_003 = "(?:不是|并非|不能说|不意味着|不代表|不能保证|不能|不可|无法|不可能|不|未)\\s*[“\"‘\\'「『`]?\\s*$"
_V3_004 = "(?:不是|并非|不能说|不意味着|不代表|不能保证|不能|不可|无法|不可能|不|未)\\s*[“\"‘\\'「『`]?\\s*$"
_V3_005 = (
    "(?:每月|每周|偶尔|破例|例外|可以尝试|可以接受).{0,"
    "16}(?:一次|[一二三四五六七八九十\\d]+次|夜班)|(?"
    ":破例|例外).{0,12}夜班"
)
_V3_006 = (
    "(?:关系|流程)(?:[、和与](?:关系|流程))?(?:都)?(?:已(?:经)?)?熟悉(?!程度)|"
    "(?:你|我).{0,4}熟悉.{0,16}(?:任务|岗位|关系|流程)"
)


def night_exception_is_asserted(text: str, clause: str, occurrence: re.Match[str]) -> bool:
    before, after = (clause[: occurrence.start()], clause[occurrence.end() :])
    local = re.split("[，,：:]|但(?:是)?|然而|不过|可是|事实上|实际上", before)[-1]
    denial = re.search("(?:不建议|不能建议|不应建议|不允许|不接受|拒绝)(?:任何)?$", local)
    double_denial = denial and re.search(_V3_001, local[: denial.start()])
    term = occurrence.group()
    if re.search(_V3_002, after):
        return True
    if (
        denial
        and (not double_denial)
        and re.fullmatch("少量(?:晚间|夜班)|夜班(?:例外(?:或放宽|、少量放宽)?|放宽)", term)
    ):
        return False
    if re.fullmatch("夜班[”\"’\\'」』`]?不设例外(?:或放宽)?", term):
        denied_refusal = re.search(_V3_003, local)
        refusal = re.search("(?:不能上|不接受|不排)$", local)
        if refusal and re.search(_V3_004, local[: refusal.start()]):
            denied_refusal = True
        return bool(denied_refusal)
    if term == "夜班例外" and re.search("不能上夜班|不接受夜班|不排夜班", text):
        start = re.sub("^(?:-\\s*|(?:收益|代价|风险|可逆性|第一步)：)", "", before.strip())
        end = after.strip()
        if re.fullmatch("(?:今天)?向A发出班次与", start) and re.fullmatch(
            "书面问题(?:，并标注希望回复(?:期限|的截止期限))?", end
        ):
            return False
        if re.fullmatch("在收到A书面班次/", start) and re.fullmatch("答复(?:、B书面费用与退出条款)?后复盘", end):
            return False
        if re.fullmatch("(?:制作(?:一张)?A/B对照表，)?只填已核实项与未知项[（：]班次、", start) and re.fullmatch(
            "、费用、退出、通勤、学习时段、休息承受度(?:），未知栏保持空白，不用牌面或命盘补空)?", end
        ):
            return False
        if re.fullmatch("A班次、", start) and re.fullmatch("、轮班/顶班、报名截止与退出条件未知", end):
            return False
    return True


def decision_issues(
    text: str,
    final: dict[str, Any],
    facts: dict[str, dict[str, Any]],
    claims: dict[str, dict[str, Any]],
    plan: dict[str, Any],
    run_request: dict[str, Any],
) -> tuple[list[str], str]:
    issues = []
    if plan["decision"] and (not final["decision_options"] or not final["actions"]):
        issues.append("现实决策缺少选择代价或行动")
    if plan["decision"] and len(final["decision_options"]) < 2:
        issues.append("现实决策需要至少两个可行选择，可包含暂缓与核实")
    if plan["decision"] and facts and (not final["cited_fact_ids"]):
        issues.append("已有现实资料时，决策必须引用本轮有效事实依据")
    factual = (
        "\n".join(
            str(f.get("content", ""))
            for f in facts.values()
            if not f.get("context_only") and f.get("kind") not in ("hypothesis", "hearsay", "concern")
        )
        + "\n"
        + run_request["message"]
    )
    clauses = re.split("[。；;\\n]", text)
    night_exception = any(
        night_exception_is_asserted(text, clause, occurrence)
        for clause in clauses
        for occurrence in re.finditer("少量(?:晚间|夜班)|夜班.{0,6}(?:例外|放宽)", clause)
    ) or any("夜班" in clause and re.search(_V3_005, clause) for clause in clauses)
    if re.search("不能.{0,6}夜班|不接受.{0,6}夜班", factual) and night_exception:
        issues.append("用户明确不能上夜班，未授权修改时不能建议少量例外或次数放宽")
    cost_pattern = "协商成本低|B\\s*成本低"
    familiarity_pattern = _V3_006
    if (
        re.search(cost_pattern, text)
        and (not re.search("协商成本低", factual))
        or (re.search(familiarity_pattern, text) and (not re.search(familiarity_pattern, factual)))
    ):
        issues.append("熟悉关系、流程或协商成本低没有已授权现实来源，不可作为推荐理由")
    return (issues, factual)


def completion_issues(final: dict[str, Any], claims: dict[str, dict[str, Any]], plan: dict[str, Any]) -> list[str]:
    issues = []
    if plan["mode"] in ("support", "urgent_support") and len(final["actions"]) > 1:
        issues.append("支持模式只给最多一个低负担行动")
    if plan["systems"] and claims and (not final["cited_claim_ids"]):
        issues.append("专业结果缺少经过核验的声明引用")
    return issues
