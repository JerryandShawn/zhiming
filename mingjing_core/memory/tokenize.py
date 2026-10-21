"""Chinese lexical search stays local; tokens never grant fact authority."""

import logging
import re
from collections.abc import Iterator
from functools import lru_cache

import jieba

from .private import is_private

TERMS = [
    "日主",
    "喜用神",
    "大运",
    "流年",
    "流月",
    "流日",
    "十神",
    "正官",
    "七杀",
    "食神",
    "伤官",
    "正财",
    "偏财",
    "正印",
    "偏印",
    "比肩",
    "劫财",
    "化禄",
    "化权",
    "化科",
    "化忌",
    "命宫",
    "身宫",
    "上升",
    "月亮",
    "太阳",
    "相位",
    "合盘",
    "逆位",
    "夜班",
    "考研",
]
SEARCHABLE = frozenset({"fact", "note", "episode", "message", "profile_doc", "thread_summary", "case"})
LONG_RUN = 4096
WINDOW = 512
OVERLAP = 32


@lru_cache(maxsize=1)
def tokenizer() -> jieba.Tokenizer:
    jieba.setLogLevel(logging.ERROR)
    instance = jieba.Tokenizer()
    for term in TERMS:
        instance.add_word(term)
    return instance


def tokenize(text: str) -> list[str]:
    return list(dict.fromkeys(word.lower() for word in bounded_words(text) if re.search(r"[\w\u3400-\u9fff]", word)))


def bounded_words(text: str) -> Iterator[str]:
    # Jieba's HMM copies growing paths for a long unknown Han run. This bounds
    # only derived lexical work; original text and source offsets never change.
    if len(text) <= LONG_RUN:
        yield from tokenizer().cut(text)
        return
    for block in jieba.re_han_default.split(text):
        if len(block) <= LONG_RUN:
            yield from tokenizer().cut(block)
        else:
            for start in range(0, len(block), WINDOW - OVERLAP):
                yield from tokenizer().cut(block[start : start + WINDOW])


def searchable_data(kind: str, data: dict) -> dict:
    result = dict(data)
    if kind in SEARCHABLE and result:
        if is_private(result):
            return dict(result, search_tokens="")
        text = "\n".join(str(result.get(key, "")) for key in ("content", "text", "title", "summary", "answer"))
        result["search_tokens"] = " ".join(tokenize(text))
    return result
