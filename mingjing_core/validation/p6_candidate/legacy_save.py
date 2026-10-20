"Copied v3 warning rules: regex values and denial semantics are preserved."

import re

_V3_001 = "(?:不是|并非|不能说|不意味着|不代表|不能保证|不能|不可|无法|不可能|不|未)\\s*[“\"‘\\'「『`]?\\s*$"
_V3_002 = (
    "(?:已|已经|我会|已为你)[^。；;！？!?\\n，,：:]{0,8}?(?:记住|保存|记录到|更新.{0"
    ",4}(?:记忆|档案)|删除.{0,4}(?:记忆|资料))"
)
_V3_003 = (
    "(?:(?:不(?:能|会|应)?|未)(?:声称|宣称|表示|"
    "说|承诺|暗示)(?:任何资料|本轮内容)?|并未|尚未|没有|"
    "未曾|未)[“\"‘\\'「『`]?$"
)
_V3_004 = "(?:不是|并非|不能说|不意味着|不代表|不能保证|不能|不可|无法|不可能|不|未)\\s*[“\"‘\\'「『`]?\\s*$"


def save_issues(text: str) -> list[str]:
    issues = []
    unsupported_save = False
    denied_status_lists = []
    for opening, closing in (("“", "”"), ('"', '"'), ("‘", "’"), ("'", "'"), ("「", "」"), ("『", "』"), ("`", "`")):
        for quoted in re.finditer(
            re.escape(opening) + "已记住/已保存/已更新/已删除" + re.escape(closing) + "状态的声称", text
        ):
            local = re.split("[。；;\\n，,：:]|但(?:是)?|然而|不过|可是|事实上|实际上", text[: quoted.start()])[-1]
            denial = re.search("不包含任何$", local)
            double_denial = denial and re.search(_V3_001, local[: denial.start()])
            if denial and (not double_denial):
                denied_status_lists.append((quoted.start(), quoted.end()))
    for assertion in re.finditer(_V3_002, text):
        if any((start < assertion.start() and assertion.end() < end for start, end in denied_status_lists)):
            continue
        prefix = re.split("[。；;\\n，,：:]|但(?:是)?|然而|不过|可是|事实上|实际上", text[: assertion.start()])[-1]
        denial = re.search(_V3_003, prefix)
        double_denial = denial and re.search(_V3_004, prefix[: denial.start()])
        if not denial or double_denial:
            unsupported_save = True
    if unsupported_save:
        issues.append("保存或删除提示必须由实际程序回执生成")
    return issues
