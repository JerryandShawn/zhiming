"""A deliberately narrow Chinese assertion grammar, not a semantic truth judge."""

from __future__ import annotations

import re
from collections.abc import Iterator

STEMS = "甲乙丙丁戊己庚辛壬癸"
BRANCHES = "子丑寅卯辰巳午未申酉戌亥"
PATTERNS = "正官格|七杀格|正印格|偏印格|正财格|偏财格|食神格|伤官格"
SIGNS = "白羊|金牛|双子|巨蟹|狮子|处女|天秤|天蝎|射手|摩羯|水瓶|双鱼"
PLANETS = "太阳|月亮|水星|金星|火星|木星|土星|天王星?|海王星?|冥王星?"
STARS = "紫微|天机|太阳|武曲|天同|廉贞|天府|太阴|贪狼|巨门|天相|天梁|七杀|破军"
PALACES = "命宫|兄弟宫|夫妻宫|子女宫|财帛宫|疾厄宫|迁移宫|仆役宫|交友宫|官禄宫|田宅宫|福德宫|父母宫"
OP = r"(?P<op>不是|并非|是|为|=|：|:)"
ALIASES = re.compile(r"〔([cr][1-9][0-9]*)〕")
TOPIC = re.compile(
    r"日主|日干|格局|成格|格.*筛选|用神|候选天干|大运|主星|空宫|本命|行运|太阳|月亮|"
    + PATTERNS
)


def segments(
    text: str, display_name: str = ""
) -> Iterator[tuple[int, int, str, str | None]]:
    """Guards apply before commas are split, so an 'if' protects its whole sentence."""
    protected = _quote_ranges(text)
    carried, previous_end = None, 0
    for sentence in re.finditer(r"[^。！？!?\n；;]+[。！？!?\n；;]?", text):
        body = sentence.group()
        if "\n\n" in text[previous_end : sentence.start() + 1].replace("\r", ""):
            carried = None
        if re.fullmatch(r"\s*(?:以下为)?本盘真太阳时主盘[：:。]?\s*", body):
            carried = None
        own_guard = _guard(body)
        carried = _heading_guard(body, own_guard, display_name) or carried
        guard = own_guard or carried
        previous_end = sentence.end() - (1 if body.endswith("\n") else 0)
        if any(
            left < sentence.end() and sentence.start() < right
            for left, right in protected
        ):
            guard = "quoted_or_reported"
        for clause in re.finditer(r"[^，,。！？!?\n；;]+", body):
            raw = clause.group()
            left = len(raw) - len(raw.lstrip())
            right = len(raw.rstrip())
            if left == right:
                continue
            start = sentence.start() + clause.start() + left
            end = sentence.start() + clause.start() + right
            yield start, end, raw.strip(), guard


def _heading_guard(body: str, guard: str | None, display_name: str) -> str | None:
    stripped = body.strip()
    if not re.search(
        r"(?:如下|命盘|盘面|结果|资料|案例|示例|口径|假设)[：:。]?\s*$", stripped
    ):
        return None
    if guard in (
        "other_subject",
        "comparison_basis",
        "other_layer",
        "quoted_or_reported",
        "hypothetical",
    ):
        return guard
    match = re.fullmatch(
        r"(?:#+\s*)?(.{1,30}?)的?(?:命盘|盘面|出生资料)(?:如下)?[：:。]?", stripped
    )
    if match and match[1].removesuffix("的") not in (
        "你",
        "我",
        "本盘",
        "此盘",
        "该盘",
        display_name,
    ):
        return "other_subject"
    return None


def _quote_ranges(text: str) -> list[tuple[int, int]]:
    pairs = {"“": "”", "‘": "’", "「": "」", "『": "』", '"': '"', "`": "`"}
    ranges, opened = [], None
    for index, char in enumerate(text):
        if opened is None and char in pairs:
            opened = (index, pairs[char])
        elif opened is not None and char == opened[1]:
            ranges.append((opened[0], index + 1))
            opened = None
    if opened is not None:
        ranges.append((opened[0], len(text)))
    return ranges


def _guard(text: str) -> str | None:
    groups = (
        (
            r'[“”‘’「」『』"`]|^\s*>|(?:别人|书里|书中|文中|原文|他说|她说|转述|引用|据说|示例|假设案例|有人说|原话|你曾说|你说|我说|声称|记载|写着)',
            "quoted_or_reported",
        ),
        (
            r"如果|假如|假设|倘若|若是|若日|即使|要是|假定|设想|当.*(?:时|时候)",
            "hypothetical",
        ),
        (
            r"[？?]|是否|是不是|难道|何以|为啥|怎么|为何|吗(?:[，。\s]|$)|呢(?:[，。\s]|$)",
            "question",
        ),
        (
            r"不是不|并非不|没有不|不能说不|不一定|未必|不排除|不无|不是.*而是|不能.*(?:认定|确定)|"
            r"不成立|不正确|说错|误写|有误|不对|应撤回|作废|不是事实|才怪|才不是|开玩笑|瞎说|搞错|错了|错误",
            "complex_negation",
        ),
        (
            r"可能|也许|大概|或许|似乎|推测|不确定|待核|未评估|尚未判断|说不准|尚不清楚|未确认",
            "uncertain",
        ),
        (
            r"北京时间|北京时|钟表时|比较盘|比较口径|另一口径|真太阳时.*(?:和|与).*北京",
            "comparison_basis",
        ),
        (
            r"他人|对方|小禾|张三|李四|朋友的|母亲|父亲|前任|妻子|丈夫|她的|他的|另一人|合盘",
            "other_subject",
        ),
        (
            r"行运|流年|流月|流日|推运|次限|太阳回归|旧盘|上一张|修订前|上一版|借星|三方四正",
            "other_layer",
        ),
    )
    for pattern, reason in groups:
        if re.search(pattern, text):
            return reason
    return None


def _number(value: str) -> int:
    if value.isascii() and value.isdecimal():
        return int(value)
    return {
        "一": 1,
        "二": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
        "十": 10,
        "十一": 11,
        "十二": 12,
    }.get(value, -1)


def _simple(body: str) -> dict | None:
    match = re.fullmatch(
        rf"日(?:主|干){OP}(?P<value>[{STEMS}])(?P<element>[木火土金水])?", body
    )
    if match:
        row = match.groupdict()
        if (
            row["element"]
            and row["element"] != "木木火火土土金金水水"[STEMS.index(row["value"])]
        ):
            return {"reason": "invalid_stem_element"}
        return {
            "field": "day_master",
            "value": row["value"],
            "negative": row["op"] in ("不是", "并非"),
        }
    match = re.fullmatch(
        rf"(?:格局候选)?(?P<key>{PATTERNS})(?:候选)?筛选(?P<state>通过|未通过|不通过)",
        body,
    )
    if match:
        return {
            "field": "pattern_screen",
            "key": match["key"],
            "value": match["state"] == "通过",
        }
    match = re.fullmatch(
        rf"(?P<method>扶抑|调候|格局)(?:\[(?P<qualifier>[^\]]{{1,64}})\])?候选天干"
        rf"(?P<op>不包括|不包含|不含|没有|包括|包含|含有|含)(?P<value>[{STEMS}])",
        body,
    )
    if match:
        return {
            "field": "useful",
            "key": match["method"] + ":" + (match["qualifier"] or ""),
            "value": match["value"],
            "negative": match["op"].startswith(("不", "没")),
        }
    return None


def _decade(body: str) -> dict | None:
    prefix = (
        r"(?:第(?P<index>[1-9][0-9]?|[一二三四五六七八九十]+)步|"
        r"(?P<date>[0-9]{4}-[0-9]{2}-[0-9]{2})的?)大运"
    )
    match = re.fullmatch(prefix + OP + rf"(?P<value>[{STEMS}][{BRANCHES}])", body)
    if not match:
        return None
    value = match["value"]
    if STEMS.index(value[0]) % 2 != BRANCHES.index(value[1]) % 2:
        return {"reason": "invalid_ganzhi"}
    return {
        "field": "decade",
        "key": str(_number(match["index"])) if match["index"] else "",
        "date": match["date"],
        "value": value,
        "negative": match["op"] in ("不是", "并非"),
    }


def _ziwei(body: str) -> dict | None:
    match = re.fullmatch(
        rf"(?P<key>{PALACES})(?:的)?主星(?P<op>不包括|不包含|不含|没有|包含|包括|含|有|是|为)(?P<value>{STARS})",
        body,
    )
    if match:
        return {
            "field": "ziwei_stars",
            "key": match["key"].replace("交友", "仆役"),
            "value": match["value"],
            "negative": match["op"].startswith(("不", "没")),
        }
    match = re.fullmatch(rf"(?P<key>{PALACES})(?P<op>不是|并非|是|为)空宫", body)
    if match:
        return {
            "field": "ziwei_stars",
            "key": match["key"].replace("交友", "仆役"),
            "value": "空宫",
            "negative": match["op"] in ("不是", "并非"),
        }
    return None


def _astro(body: str) -> dict | None:
    prefix = rf"本命(?P<key>{PLANETS})(?P<op>不在|位于|落在|在)"
    match = re.fullmatch(
        prefix
        + rf"(?P<sign>{SIGNS})座?(?:(?P<degree>[0-9]{{1,2}}(?:\.[0-9]{{1,6}})?)度)?",
        body,
    )
    if match:
        degree = match["degree"]
        if degree is not None and not 0 <= float(degree) < 30:
            return {"reason": "invalid_degree"}
        return {
            "field": "planet",
            "key": match["key"].replace("王星", "王"),
            "component": "position",
            "value": {
                "sign": match["sign"],
                "degree": float(degree) if degree else None,
                "tolerance": 0.5
                * 10 ** (-len(degree.split(".")[1]) if "." in degree else 0)
                if degree
                else None,
            },
            "negative": match["op"] == "不在",
        }
    match = re.fullmatch(
        prefix + r"第?(?P<house>[0-9]{1,2}|[一二三四五六七八九十]+)宫", body
    )
    if match:
        house = _number(match["house"])
        if not 1 <= house <= 12:
            return {"reason": "invalid_house"}
        return {
            "field": "planet",
            "key": match["key"].replace("王星", "王"),
            "component": "house",
            "value": house,
            "negative": match["op"] == "不在",
        }
    match = re.fullmatch(rf"本命(?P<key>{PLANETS})(?P<state>逆行|顺行)", body)
    if match:
        return {
            "field": "planet",
            "key": match["key"].replace("王星", "王"),
            "component": "retrograde",
            "value": match["state"] == "逆行",
        }
    return None


def parse_clause(text: str, display_name: str) -> tuple[dict | None, list[str]]:
    names = ALIASES.findall(text)
    body = ALIASES.sub("", text).strip()
    prefix = r"^(?:你的|你|本盘的|本盘|此盘的|此盘|该盘的|该盘|我的|我)"
    if display_name:
        prefix = (
            prefix[:-1]
            + "|"
            + re.escape(display_name)
            + "的?|"
            + re.escape(display_name)
            + ")"
        )
    body = re.sub(prefix, "", body).strip().lstrip("：:").strip()
    for parser in (_simple, _decade, _ziwei, _astro):
        query = parser(body)
        if query:
            return query, names
    if re.search(PATTERNS, body) or re.search(
        r"(?:已|已经|确定|成立|成了|就是|定为|唯一).*(?:格|用神)|(?:格|用神).*(?:成立|已定|确定|唯一)|"
        r"格局(?:是|为)|用神(?:是|为)|候选天干|格.*筛选|(?:日主|日干|大运|主星|本命)",
        body,
    ):
        return {"reason": "unsupported_or_nonfinal_assertion"}, names
    return None, names
