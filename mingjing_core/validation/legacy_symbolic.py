"Copied v3 warning rules: regex values and denial semantics are preserved."

import re

_V3_001 = "(?:不是|并非|不能说|不意味着|不代表|不能|不可|无法|不可能|不|未)\\s*[“\"‘\\'「『`]?\\s*$"
_V3_002 = "(?:不是|并非|不能说|不意味着|不代表|不能|不可|无法|不可能|不|未)\\s*[“\"‘\\'「『`]?\\s*$"
_V3_003 = "(?:命盘|八字|星盘|塔罗|牌面).{0,28}?(证明|保证|一定会|必然会|成功率\\s*\\d|\\d+\\s*%)"
_V3_004 = (
    "(?:不能|无法|不应|不会|并非|不是|不|无从)(?:据此|因此|直接|单独|可靠地|用于|用来|作为|被"
    "用于|被用来|给出|做出|提供)?$|没有依据(?:可以|能够)?$"
)
_V3_005 = "(?:不是|并非|不能说|不意味着|不代表|不能|不可|无法|不可能|不|未)\\s*[“\"‘\\'「『`]?\\s*$"


def symbolic_limit_is_denied(
    denial: re.Match[str], prefix: str, clause: str, assertion: re.Match[str], *, reject_quoted: bool = False
) -> bool:
    double = _V3_001
    if re.search(double, prefix[: denial.start()]) or re.search(double, clause[: assertion.start()]):
        return True
    for opening, closing in (("“", "”"), ('"', '"'), ("‘", "’"), ("'", "'"), ("「", "」"), ("『", "』"), ("`", "`")):
        if reject_quoted:
            before = clause[: assertion.start() + denial.start()]
            if before.count(opening) % 2 if opening == closing else before.rfind(opening) > before.rfind(closing):
                return True
        for quoted in re.finditer(
            re.escape(opening) + "[^" + re.escape(closing) + "]{0,360}" + re.escape(closing), clause
        ):
            if assertion.end() < quoted.end():
                if quoted.start() < assertion.start() and re.search(double, clause[: quoted.start()]):
                    return True
                if reject_quoted and quoted.start() < assertion.start() + denial.start() < quoted.end():
                    return True
    return False


def symbolic_expression_is_quoted(text: str, clause: str, assertion: re.Match[str]) -> bool:
    for occurrence in re.finditer(re.escape(clause), text):
        leading = text[: occurrence.start() + assertion.start()]
        for opening, closing in (
            ("“", "”"),
            ('"', '"'),
            ("‘", "’"),
            ("'", "'"),
            ("「", "」"),
            ("『", "』"),
            ("`", "`"),
        ):
            if leading.count(opening) % 2 if opening == closing else leading.rfind(opening) > leading.rfind(closing):
                return True
    return False


def _guarantee_denial(
    clause: str, assertion: re.Match[str], prefix: str, denial: re.Match[str] | None
) -> re.Match[str] | None:
    finite_object = "(?:学习(?:效果|成效|成果)|成绩|他人动机)"
    limited_denial = re.search(
        "(?:不|不能)构成(?:对)?" + finite_object + "(?:(?:、|或|和|及|与)" + finite_object + ")*(?:的)?(?:任何)?$",
        prefix,
    )
    if (
        limited_denial
        and re.fullmatch("\\s*[”\"’\\'」』`]?\\s*", clause[assertion.end() :])
        and (not re.search("(?:不会|不应|没有|未曾)\\s*$", prefix[: limited_denial.start()]))
        and (not symbolic_limit_is_denied(limited_denial, prefix, clause, assertion, reject_quoted=True))
    ):
        denial = limited_denial
    limited_denial = re.search("(?:不能|无法|不应|不会|不)提供吉凶$|不产生任何概率或吉凶$", prefix)
    double_denial = limited_denial and re.search(_V3_002, prefix[: limited_denial.start()])
    if limited_denial and limited_denial.group() == "不产生任何概率或吉凶":
        double_denial = symbolic_limit_is_denied(limited_denial, prefix, clause, assertion)
    if limited_denial and (not double_denial):
        denial = limited_denial
    return denial


def _proof_denial(
    text: str, clause: str, assertion: re.Match[str], prefix: str, denial: re.Match[str] | None
) -> re.Match[str] | None:
    local = re.split("[，,：:]|但(?:是)?|然而|不过|可是|事实上|实际上", clause[: assertion.start()])[-1]
    before_subject = re.search("(?:不能|不可|不应|不要)(?:把|将)$", local)
    proof_object = "(?:结果|对方态度|顺利程度)"
    finite_proof = re.fullmatch(
        "(?:命盘|八字|星盘|塔罗|牌面)(?:当作|视为)" + proof_object + "(?:(?:、|或|和|及|与)" + proof_object + ")*的",
        prefix,
    )
    closed_tail = re.fullmatch("(?:[，,]也不能给出成败概率)?\\s*", clause[assertion.end() :])
    if (
        before_subject
        and finite_proof
        and closed_tail
        and not symbolic_expression_is_quoted(text, clause, assertion)
        and not symbolic_limit_is_denied(before_subject, local, clause, assertion, reject_quoted=True)
    ):
        denial = before_subject
    before_subject = re.search("(?:没有|不存在)(?:任何)?$", local)
    proof_subject = "(?:命盘|八字|星盘|塔罗|牌面)"
    existential_proof = re.fullmatch(
        proof_subject + "(?:(?:或|和|及|与)(?:命盘|八字|星盘|塔罗|牌面|算法))*(?:能|能够|可以)", prefix
    )
    renewed = False
    for tail in re.split(
        "[，,]|但(?:是)?|然而|不过|可是|事实上|实际上|反而|却|并且|同时|且", clause[assertion.end() :]
    ):
        for claim in re.finditer("证明|保证|一定会|必然会|成功率\\s*\\d|\\d+\\s*%", tail):
            denied = re.search("(?:不能|无法|不应|不会|并非|不是|不|无从)$", tail[: claim.start()])
            if not denied or re.search(
                "(?:不是|并非|不能说|不意味着|不代表|不能|不可|无法|不可能|不|未)\\s*$", tail[: denied.start()]
            ):
                renewed = True
    if (
        not denial
        and before_subject
        and existential_proof
        and (not renewed)
        and (not symbolic_expression_is_quoted(text, clause, assertion))
        and (not symbolic_limit_is_denied(before_subject, local, clause, assertion, reject_quoted=True))
    ):
        denial = before_subject
    snapshot_limit = re.fullmatch("八字仅(?:采用)?正午快照[，,]未", prefix)
    if (
        snapshot_limit
        and re.fullmatch("整日不(?:更)?换日柱\\s*", clause[assertion.end() :])
        and (not symbolic_limit_is_denied(snapshot_limit, prefix, clause, assertion, reject_quoted=True))
    ):
        denial = snapshot_limit
    limited_denial = re.search("不能摘取单一相位$", prefix)
    if limited_denial and (not symbolic_limit_is_denied(limited_denial, prefix, clause, assertion)):
        denial = limited_denial
    return denial


def symbolic_issues(text: str) -> list[str]:
    issues = []
    certainty = False
    for clause in re.split("[。；;\\n]", text):
        for assertion in re.finditer(_V3_003, clause):
            prefix = clause[assertion.start() : assertion.start(1)]
            denial = re.search(_V3_004, prefix)
            if not denial and assertion.group(1) == "保证":
                denial = _guarantee_denial(clause, assertion, prefix, denial)
            if not denial and assertion.group(1) == "证明":
                denial = _proof_denial(text, clause, assertion, prefix, denial)
            if not denial and assertion.group() == "牌面证明":
                local = re.split("[，,：:]|但(?:是)?|然而|不过|可是|事实上|实际上", clause[: assertion.start()])[-1]
                before_subject = re.search("不由$", local)
                double_denial = before_subject and re.search(_V3_005, local[: before_subject.start()])
                if before_subject and (not double_denial):
                    denial = before_subject
            if not denial and assertion.group() == "牌面保证":
                local = re.split("[，,：:]|但(?:是)?|然而|不过|可是|事实上|实际上", clause[: assertion.start()])[-1]
                before_subject = re.fullmatch("\\s*不能由", local)
                if (
                    before_subject
                    and re.fullmatch("\\s*", clause[assertion.end() :])
                    and (not symbolic_limit_is_denied(before_subject, prefix, clause, assertion, reject_quoted=True))
                ):
                    denial = before_subject
            if not denial:
                certainty = True
    if certainty:
        issues.append("象征解释被提升为现实确定性或概率")
    return issues
