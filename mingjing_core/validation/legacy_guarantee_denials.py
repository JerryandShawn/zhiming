"Copied v3 warning rules: regex values and denial semantics are preserved."

import re

guarantee_pattern = "零风险|完全可逆|没有任何损失|无损失|零损失|零成本退出|随时.{0,3}(?:退出|退款)"
_V3_001 = (
    "(?:(?:不能|无法|不应|不可|不宜|不再|尚不能|不可能|不要|不|未)(?:据此|因此|预先|直接|单"
    "独|事先)?(?:保证|承诺|认定|断言|声称|宣称|认为|说|称为|视为|视作|确定|(?:被)?推断)|未"
    "推断为|不该被当作|不能把未知当成|不能推定退出|不再对任何方案或动作宣称|(?:没有|缺乏|尚无|并无)依据"
    "(?:保证|承诺|认定|断言|认为)|(?:避免|不要|不能|不应|不)(?:被)?(?:默认|假设|假定|当"
    "作|当成|视为|预设)|(?:并非|不是)(?:保证|承诺)?|(?<!除)非|未必|不等于|不)(?:(?:"
    "任何(?:报名|选项|路径|方案|一步|后续步骤)|任一(?:方|选项)|正式报名|该课程|这项安排|这个选择"
    '|此路径|核实行动|等待|中途退出|退出|其|它|A|B)(?:是|可|为)?|任何|是|可|为)?[“"‘\\'
    "'「『`]?(?:完全)?$"
)
_V3_002 = "[”\"’\\'」』`]?)*\\s*处理[”\"’\\'」』`]?(?=$|[，,]|但(?:是)?|然而|不过|可是|事实上|实际上)"
_V3_003 = (
    "(?:不是|并非|(?<!除)非|不能说|不意味着|不代表|不能"
    '保证|不能|不可|无法|不可能|不|没有|未曾|未)\\s*[“"'
    "‘\\'「『`]?\\s*$"
)
_V3_004 = (
    "(?:零风险|完全可逆|没有任何损失|无损失|零损失|零成本退出|随时(?:可无损|无损|可)?退出|随时(?"
    ":可)?退款|零成本|低成本|零代价|无风险|可逆|可承受|可退款|低价|可无损退出|可退出|零费用|免费|可"
    "逆性|签约后可逆)"
)
_V3_005 = "(?:的)?(?:推断|假设)(?=$|[，,”\"’\\'」』`]|但(?:是)?|然而|不过|可是|事实上|实际上|反而|却)"
_V3_006 = (
    "(?:不是|并非|(?<!除)非|不能说|不意味着|不代表|不能保证|不能|不可|无法|不可能|不会|不应|不"
    "|没有|未曾|尚未|未)\\s*(?:[：:]\\s*)?[“\"‘\\'「『`]?\\s*$"
)


def explicit_denial(prefix: str, suffix: str = "") -> bool:
    finite_term = (
        "(?:"
        + guarantee_pattern
        + "|零成本|低成本|零代价|无风险|可逆|可承受|可退款|低价|可无损退出|可退出|零费用|免费)"
    )
    joined = finite_term + "[”\"’\\'」』`]?(?:或|、|和|及|与)\\s*[“\"‘\\'「『`]?(?:付款后)?(?:完全)?$"
    while re.search(joined, prefix):
        prefix = re.sub(joined, "", prefix)
    denial = re.search(_V3_001, prefix)
    if denial is None and re.fullmatch("(?:(?:、|或|和|及|与)" + finite_term + ")*", suffix):
        denial = re.fullmatch("(?:(?:均)?保持待核实而)?非推断为", prefix)
    if denial is None and re.match(
        "^(?:(?:、|或|和|及|与)"
        + finite_term
        + ")*(?:或可忽略)?(?=$|[，,]|——|但(?:是)?|然而|不过|可是|事实上|实际上|反而|却)",
        suffix,
    ):
        denial = re.search("不能(?:(?:从牌面)?推断为|当作)$", prefix)
    if denial is None:
        denial = re.search("(?:不是|并非)[“\"‘\\'「『`]零代价$", prefix)
    if denial is None and re.match("^处理", suffix):
        denial = re.search("不按$", prefix)
    if denial is None and re.match(
        "^[”\"’\\'」』`]?(?:(?:、|或|和|及|与)[“\"‘\\'「『`]?" + finite_term + _V3_002, suffix
    ):
        denial = re.search("(?:不能|不可|不应|不宜|不要|不)按[“\"‘\\'「『`]?$", prefix)
    if denial is None and re.match(
        "^(?:(?:、|或|和|及|与)(?:" + guarantee_pattern + "))*[”\"’\\'」』`]?\\s*(?:的)?(?:承诺|保证)", suffix
    ):
        denial = re.search("(?:不作|不做)\\s*[“\"‘\\'「『`]?$", prefix)
    double_denial = denial and re.search(_V3_003, prefix[: denial.start()])
    return bool(denial and (not double_denial))


def finite_inference_is_asserted(
    clause: str, assertion: re.Match[str], local: str, after: str, context: str, source: bool
) -> bool | None:
    term = _V3_004
    pairs = (("“", "”"), ('"', '"'), ("‘", "’"), ("'", "'"), ("「", "」"), ("『", "』"), ("`", "`"))
    quoted_term = "(?:" + term + "|" + "|".join((re.escape(o) + term + re.escape(c) for o, c in pairs)) + ")"
    terms = quoted_term + "(?:(?:、|或|和|及|与)" + quoted_term + ")*"
    enumeration = "(?:" + terms + "|" + "|".join((re.escape(o) + terms + re.escape(c) for o, c in pairs)) + ")"
    scope = local + assertion.group() + after
    denial = re.search("未(?:作|做)(?:任何)?" + enumeration + _V3_005, scope)
    if not denial or not (denial.start() <= len(local) and len(local) + len(assertion.group()) <= denial.end()):
        if source and re.search("未(?:作|做)(?:任何)?", local):
            return False
        return None
    start = assertion.start() - len(local) + denial.start()
    double = _V3_006
    if re.search(double, clause[:start]):
        return not source
    for opening, closing in pairs:
        for occurrence in re.finditer(re.escape(clause), context):
            prefix = context[: occurrence.start() + start]
            if prefix.count(opening) % 2 if opening == closing else prefix.rfind(opening) > prefix.rfind(closing):
                return not source
        for quoted in re.finditer(re.escape(opening) + "[^" + re.escape(closing) + "]*" + re.escape(closing), context):
            for occurrence in re.finditer(re.escape(clause), context):
                if quoted.start() < occurrence.start() + start and occurrence.start() + assertion.end() < quoted.end():
                    return not source
    if re.match("^[”\"’\\'」』`]", scope[denial.end() :]):
        return not source
    return False


def finite_guarantee_denial(clause: str, assertion: re.Match[str], local: str, after: str, context: str) -> bool:
    scope = local + assertion.group() + after
    finite = (
        "(?:也)?(?:不要|不能)假设(?:付费后)?可以无损失退出",
        "不能推断为零费用、免费退出或无损失",
        "(?:两条都)?不能被描述为完全可逆或无损失",
        "未对任何费用、退出或可逆性做零成本、完全可逆或无损失的假设",
        "两方案是否允许无损失退出、是否有答复时限或名额限制均待核实",
    )
    comparison_finite = (
        "不能认定(?:之后可以|选择B可)无损失退出",
        "不能承诺选择B之后完全可逆或无损失",
        "若B费用不可接受能否无损失退出，取决于B的退出条件，待核实",
        "因此不存在零成本、零风险或完全可逆的路径",
        "不把未知退出条件解释为无损失退出",
        "未把未知班次、费用、退出条件或时限推断为有利、零成本、零风险或完全可逆",
        "不能假设费用可接受或退出无损失",
        "不能把这些未知项当作零损失",
        "不能承诺该选项可逆或无损失",
    )
    boundary = "(?=$|[，,]|但(?:是)?|然而|不过|可是|事实上|实际上|反而|却)"
    denial = re.match("(?:" + "|".join(finite + comparison_finite) + ")" + boundary, scope)
    if not denial or len(local) + len(assertion.group()) > denial.end():
        return False
    start = assertion.start() - len(local)
    comparison_denial = re.match("(?:" + "|".join(comparison_finite) + ")" + boundary, scope)
    if comparison_denial and re.search(
        "(?:不是|并非|不能说|不意味着|不代表|不能|不可|无法|不可能|不|未)\\s*[：:]\\s*$", clause[:start]
    ):
        return False
    for opening, closing in (("“", "”"), ('"', '"'), ("‘", "’"), ("'", "'"), ("「", "」"), ("『", "』"), ("`", "`")):
        for quoted in re.finditer(re.escape(opening) + "[^" + re.escape(closing) + "]*" + re.escape(closing), clause):
            if quoted.start() < start and assertion.end() < quoted.end():
                return False
        if comparison_denial:
            for quoted in re.finditer(
                re.escape(opening) + "[^" + re.escape(closing) + "]*" + re.escape(closing), context
            ):
                for occurrence in re.finditer(re.escape(clause), context):
                    if (
                        quoted.start() < occurrence.start() + assertion.start()
                        and occurrence.start() + assertion.end() < quoted.end()
                    ):
                        return False
    return True
