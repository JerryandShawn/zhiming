"""Bounds from design 26's official review; no platform request or real identifier lookup."""

import hashlib
import re

SAFE_CARD_BYTES = 28_000
MAX_WIRE_BYTES = 30_000
MAX_COMPONENTS = 200
MAX_SEQUENCE = 2_147_483_647


def validate_element_id(value: str) -> str:
    # 已核实（26转录）：https://open.feishu.cn/document/feishu-cards/card-json-v2-structure (2025-06-23).
    if type(value) is not str or re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,19}", value) is None:
        raise ValueError("cardkit_element_id_invalid")
    return value


def validate_card_id(value: str) -> str:
    # 已核实（26转录）：https://open.feishu.cn/document/cardkit-v1/card-element/content (2025-08-22).
    # The documented bound is length, not a claimed platform character-set specification.
    if type(value) is not str or not 1 <= len(value) <= 20 or any(ord(char) < 32 for char in value):
        raise ValueError("cardkit_card_id_invalid")
    return value


def validate_sequence(value: int) -> int:
    # 已核实（26转录）：https://open.feishu.cn/document/cardkit-v1/card-element/content (2025-08-22).
    if type(value) is not int or value < 1:
        raise ValueError("cardkit_sequence_invalid")
    if value > MAX_SEQUENCE:
        raise ValueError("cardkit_sequence_exhausted")
    return value


def wire_uuid(operation_id: str) -> str:
    # 项目派生策略；≤50 satisfies message UUID and ≤64 CardKit UUID bounds in 26 §8.2.
    if type(operation_id) is not str or not operation_id.strip():
        raise ValueError("cardkit_operation_id_required")
    return hashlib.sha256(operation_id.encode("utf-8")).hexdigest()[:40]
