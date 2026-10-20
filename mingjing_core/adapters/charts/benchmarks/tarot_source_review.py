"""Review one exact Clock migration without rewriting the historical source."""

from __future__ import annotations

import ast
import hashlib

HISTORICAL_SHA = "603d961da03bc076c3272ffc40350a575ed6423e06716ee01f3db1f0b10b5ee0"
CLOCK_REVIEW_SHA = "742d022d2368420f51870c2df4b7b50e5802966006f671f95a0fd1ce20e8b9ad"
REVIEW_VERSION = "p8-tarot-service-clock-review-v1"
_CLOCK_IMPORT = "from mingjing_core.timekit.clock import get_clock\n"
_DATETIME_IMPORT = "from datetime import datetime, timezone\n"
_OLD_STAMP = "    return datetime.now(timezone.utc).isoformat()\n"
_CLOCK_STAMP = "    return get_clock().now().isoformat()\n"


def lf_sha(text: str) -> str:
    return hashlib.sha256(text.replace("\r\n", "\n").encode("utf8")).hexdigest()


def _replace_once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise ValueError("P8_TAROT_SOURCE_REVIEW_PATCH_MISMATCH")
    return text.replace(old, new, 1)


def historical_source(text: str) -> str:
    """Return exact reviewed history; unknown source versions remain refused."""
    text = text.replace("\r\n", "\n")
    digest = lf_sha(text)
    if digest == HISTORICAL_SHA:
        return text
    if digest != CLOCK_REVIEW_SHA:
        raise ValueError("P8_TAROT_SOURCE_REVIEW_REQUIRED")
    historical = _replace_once(text, _CLOCK_IMPORT, "")
    anchor = "from copy import deepcopy\n"
    historical = _replace_once(historical, anchor, anchor + _DATETIME_IMPORT)
    historical = _replace_once(historical, _CLOCK_STAMP, _OLD_STAMP)
    if lf_sha(historical) != HISTORICAL_SHA:
        raise ValueError("P8_TAROT_HISTORICAL_SOURCE_MISMATCH")
    return historical


def reviewed_clock_source(historical: str) -> str:
    """Reconstruct the fetched Clock blob exactly, for offline review tests."""
    if lf_sha(historical) != HISTORICAL_SHA:
        raise ValueError("P8_TAROT_HISTORICAL_SOURCE_MISMATCH")
    text = _replace_once(historical.replace("\r\n", "\n"), _DATETIME_IMPORT, "")
    anchor = "from psycopg.types.json import Jsonb\n"
    text = _replace_once(text, anchor, anchor + _CLOCK_IMPORT)
    text = _replace_once(text, _OLD_STAMP, _CLOCK_STAMP)
    if lf_sha(text) != CLOCK_REVIEW_SHA:
        raise ValueError("P8_TAROT_CLOCK_SOURCE_MISMATCH")
    return text


def _service_ast(text: str) -> str:
    classes = [
        node
        for node in ast.parse(text).body
        if isinstance(node, ast.ClassDef) and node.name == "TarotService"
    ]
    if len(classes) != 1:
        raise ValueError("P8_TAROT_SERVICE_LOCATOR_MISMATCH")
    return ast.dump(classes[0], include_attributes=False)


def review_service_source(text: str) -> dict:
    """Distinguish original provenance from the separately reviewed checkout."""
    historical = historical_source(text)
    clock = reviewed_clock_source(historical)
    if _service_ast(clock) != _service_ast(historical):
        raise ValueError("P8_TAROT_SERVICE_SEMANTICS_CHANGED")
    historical_checkout = lf_sha(text) == HISTORICAL_SHA
    return {
        "review_version": REVIEW_VERSION,
        "checkout_basis": "historical_source"
        if historical_checkout
        else "reviewed_clock_migration",
        "reviewed_clock_checkout_verified": not historical_checkout,
        "checkout_lf_sha256": lf_sha(text),
        "historical_lf_sha256": HISTORICAL_SHA,
        "reviewed_clock_lf_sha256": CLOCK_REVIEW_SHA,
        "complete_service_ast_unchanged": True,
        "historical_source_reconstructed_exactly": True,
        "runtime_execution_verified": False,
        "clock_dependency_verified": False,
    }
