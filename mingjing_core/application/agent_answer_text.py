"""Remove only a leading history-format metadata line from an answer."""

import re

HISTORY_HEADER = re.compile(
    r"\A[ \t]*\[\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?"
    r"(?:Z|[+-]\d{2}:\d{2})? (?:web|feishu)\][ \t]*(?:\r?\n|\Z)"
)


def without_history_header(text: str) -> str:
    return HISTORY_HEADER.sub("", text, count=1)
