"""Sparse character n-grams provide partial lexical overlap without a downloaded model."""

import math
import re
import unicodedata
from collections import Counter
from collections.abc import Mapping

_STOP = frozenset(
    [
        "我想",
        "我们",
        "这个",
        "那个",
        "一个",
        "现在",
        "今天",
        "明天",
        "昨天",
        "最近",
        "怎么",
        "什么",
        "可以",
        "觉得",
        "然后",
        "因为",
        "所以",
        "已经",
        "自己",
        "没有",
        "不是",
        "还是",
        "这样",
        "那样",
        "一下",
        "一点",
        "准备",
        "还有",
        "刚才",
        "前面",
        "这次",
        "那次",
        "希望",
        "好像",
        "不知道",
    ]
)


def normalize(text: str) -> str:
    return unicodedata.normalize("NFKC", text).casefold()


def char_ngrams(text: str) -> dict[str, float]:
    result = Counter()
    for token in re.findall(r"[\u3400-\u9fff]+|[a-z0-9_]+", normalize(text)):
        if token.isascii():
            result["w:" + token] += 1
            continue
        for size in (2, 3):
            for index in range(len(token) - size + 1):
                gram = token[index : index + size]
                if gram not in _STOP:
                    result[gram] += 1 / size
    return {key: 1 + math.log(value) if value >= 1 else value for key, value in result.items()}


def cosine(left: Mapping[str, float], right: Mapping[str, float]) -> float:
    divisor = math.sqrt(sum(value * value for value in left.values()) * sum(value * value for value in right.values()))
    return sum(value * right.get(key, 0) for key, value in left.items()) / divisor if divisor else 0.0
