"""Small deterministic number grammar, shared by calendar and natural-language rules."""

import re

DIGITS = dict(zip("零〇一二两三四五六七八九", (0, 0, 1, 2, 2, 3, 4, 5, 6, 7, 8, 9), strict=True))
NUMBER = r"[0-9零〇一二两三四五六七八九十百千廿卅]+"


def parse_number(text: str) -> int:
    if not isinstance(text, str) or not text or len(text) > 12:
        raise ValueError("数词无效")
    if re.fullmatch(r"[0-9]+", text):
        return int(text)
    text = text.replace("廿", "二十").replace("卅", "三十")
    if all(char in DIGITS for char in text):
        return int("".join(str(DIGITS[char]) for char in text))
    total, current = 0, 0
    for char in text:
        if char in DIGITS:
            current = DIGITS[char]
        elif char in "十百千":
            total += (current or 1) * {"十": 10, "百": 100, "千": 1000}[char]
            current = 0
        else:
            raise ValueError("数词无效")
    return total + current


parse_cn_number = parse_number
