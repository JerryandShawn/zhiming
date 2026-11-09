"""Closed public method and source descriptions; no arbitrary JSON serialization."""

from __future__ import annotations

import re

from .common import need
from .learning_integrity import BOUNDARY_TEXT

BOUNDARY_SCHOOL = "p8-true-solar-day-hour-sect1; physical-UTC+8-exact-jie-year-month"
CHAPTERS = {f"第八、九章；第{number}章专论；第十六章杂气（未完整实现）" for number in (31, 35, 37, 39, 41)}
URLS = {
    "https://zh.wikisource.org/wiki/三命通會/卷二#论人元司事": "《三命通会》卷二·论人元司事",
    "https://docs.iztro.com/posts/palace": "iztro 宫位说明",
    "https://www.astro.com/swisseph/swephprg.htm": "Swiss Ephemeris 官方接口说明",
}


def source_label(value: object) -> dict:
    if type(value) is str and value in URLS:
        return {"title": URLS[value], "url": value, "status": "固定样例登记来源；本线未重新核对原刊。"}
    if value == "docs/v4/evidence/P8/night28-boundary-policy.md":
        return {"title": "项目时辰交界口径与原始资料", "status": "具名交界口径；原刊待核，不授权修正出生时辰。"}
    need(type(value) is dict and set(value) == {"book", "chapter", "url"})
    need(value["book"] == "子平真诠" and value["chapter"] in CHAPTERS)
    need(value["url"] == "https://donglishuzhai.net/chapter/3722.html")
    return {
        "title": "《子平真诠》",
        "locator": value["chapter"],
        "url": value["url"],
        "status": "项目候选条件实现的登记出处；不能把项目模板当古籍原句。",
    }


def school_label(point: dict, system: str) -> str:
    school = point["school"]
    if point["kind"] == "boundary":
        need(school == BOUNDARY_SCHOOL)
        return "真太阳日时（sect1）与物理 UTC+8 节界"
    if point["kind"] == "matched_condition":
        need(school == "子平")
        return "子平 · 项目候选条件实现"
    if system == "bazi":
        need(school == "p8-explicit-multimethod-v1")
        return "八字 · 项目显式多法十神参照"
    if system == "ziwei":
        need(school == "installed-py-iztro-default")
        return "紫微 · 已安装 py-iztro 默认口径"
    need(type(school) is dict and school.get("zodiac") == "tropical")
    need(school.get("coordinates") == "geocentric ecliptic longitude" and school.get("houses") == "Placidus")
    need(school.get("ephemeris") == ["Moshier"])
    return "西占 · 热带黄道、地心黄经、Placidus宫制；Moshier历表，民用UTC近似UT"


def safe_point_text(point: dict, system: str) -> None:
    title, text, kind = point["title"], point["text"], point["kind"]
    if kind == "boundary":
        need(title == "核对临界候选" and text == BOUNDARY_TEXT)
    elif kind == "matched_condition":
        need(
            re.fullmatch(
                r"(?:伤官|偏印|七杀|正官|食神|正印)格候选/(?:月支藏该十神|年月时透该十神|未见本筛选的显性牵制条件)",
                title,
            )
            is not None
        )
        condition = title.split("/", 1)[1]
        need(text == f"这次检查的是“{condition}”。先看下面的实际输入；单项满足还不能跳过另外条件说已成格。")
    elif system == "bazi":
        observed = point["observed"]
        need(type(observed) is dict and set(observed) == {"ganzhi", "gan", "zhi"})
        need(type(observed["gan"]) is str and observed["gan"] in tuple("甲乙丙丁戊己庚辛壬癸"))
        need(type(observed["zhi"]) is str and observed["zhi"] in tuple("子丑寅卯辰巳午未申酉戌亥"))
        need(observed["ganzhi"] == observed["gan"] + observed["zhi"] and title == "先找日主")
    elif system == "ziwei":
        need(title == "分清宫名与地支格")
        need(all(point["observed"][key] in tuple("子丑寅卯辰巳午未申酉戌亥") for key in ("ming_gong", "shen_gong")))
    else:
        need(
            title == "先读计算位置"
            and text == "先从实际行星位置读起，再核相位角距；所用历表、时标和宫制须连同方法栏看。"
        )
