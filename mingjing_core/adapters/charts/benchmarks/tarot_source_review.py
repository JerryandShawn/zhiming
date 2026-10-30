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
    if digest == CORE4_REVIEW_SHA:
        review_core4_checkout(text)
        text = _undo_core4(text)
        digest = lf_sha(text)
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

# R-review (10-31): main-lane core4 lineage edits to TarotService, reviewed as exactly two methods.
CORE4_REVIEW_SHA = "1388a06427f959a0abfb4a18a5e6b8ee51d7cdcae29cfda533fc56eb049dec18"
CORE4_REVIEW_VERSION = "p8-tarot-service-core4-lineage-review-v1"
CORE4_REVIEWED_METHODS = ("cancel", "finish_reading")
_CORE4_IMPORT = '        from ..application.tarot import invalidate_cancelled_draw\n'
_CORE4_CANCEL_CALL = '            invalidate_cancelled_draw(self.repo,conn,owner,draw_id)\n'
_CORE4_SNAPSHOT_NEW = "            if error is None:\n                # core4 keeps authoritative source versions on the run rather\n                # than copying private dependency metadata into its envelope.\n                p['execution_snapshot']={\n                    'run_id':run['id'],'revision':result['meta'].get('revision'),\n                    'dependencies':deepcopy(run['dependencies'])}\n"
_CORE4_SNAPSHOT_OLD = "            if result and result.get('meta'):\n                core=result['meta']['core_run'];p['execution_snapshot']={'run_id':core['run_id'],'revision':result['meta'].get('revision'),'dependencies':core['dependencies']}\n"


def _undo_core4(text: str) -> str:
    text = _replace_once(text, _CORE4_IMPORT, "")
    text = _replace_once(text, _CORE4_CANCEL_CALL, "")
    return _replace_once(text, _CORE4_SNAPSHOT_NEW, _CORE4_SNAPSHOT_OLD)


def _service_ast_without(text: str, skipped: tuple[str, ...]) -> str:
    classes = [n for n in ast.parse(text).body if isinstance(n, ast.ClassDef) and n.name == "TarotService"]
    if len(classes) != 1:
        raise ValueError("P8_TAROT_SERVICE_LOCATOR_MISMATCH")
    kept = [n for n in classes[0].body if not (isinstance(n, ast.FunctionDef) and n.name in skipped)]
    return chr(10).join(ast.dump(n, include_attributes=False) for n in kept)


def review_core4_checkout(text: str) -> dict:
    """The checkout may differ from the Clock review only by the two reviewed core4 hunks.

    Every other TarotService member (owner, choice5, manual, order, ready, shuffle) must keep an identical AST.
    """
    text = text.replace(chr(13) + chr(10), chr(10))
    if lf_sha(text) != CORE4_REVIEW_SHA:
        raise ValueError("P8_TAROT_SOURCE_REVIEW_REQUIRED")
    clock = _undo_core4(text)
    if lf_sha(clock) != CLOCK_REVIEW_SHA:
        raise ValueError("P8_TAROT_CLOCK_SOURCE_MISMATCH")
    if _service_ast_without(text, CORE4_REVIEWED_METHODS) != _service_ast_without(clock, CORE4_REVIEWED_METHODS):
        raise ValueError("P8_TAROT_SERVICE_SEMANTICS_CHANGED")
    return {
        "review_version": CORE4_REVIEW_VERSION,
        "checkout_basis": "reviewed_core4_lineage_migration",
        "checkout_lf_sha256": lf_sha(text),
        "reviewed_clock_lf_sha256": CLOCK_REVIEW_SHA,
        "reviewed_methods": list(CORE4_REVIEWED_METHODS),
        "other_service_members_ast_unchanged": True,
        "runtime_execution_verified": False,
    }
