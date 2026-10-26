"""Neutral availability fallback; no product-specific crisis routing (v29)."""

FALLBACK_TEXT = "我这边暂时没法回答，稍后再试。"


def fallback_text() -> str:
    return FALLBACK_TEXT
