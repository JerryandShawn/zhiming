"""Exact provenance bridge; changed owner/cards/ready or unknown edits fail."""

from __future__ import annotations

import ast
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from mingjing_core.adapters.charts.benchmarks.tarot_source_review import (
    CLOCK_REVIEW_SHA,
    HISTORICAL_SHA,
    REVIEW_VERSION,
    historical_source,
    lf_sha,
    review_service_source,
    reviewed_clock_source,
)
from mingjing_core.timekit.clock import FrozenClock

ROOT = Path(__file__).resolve().parents[2]
CHECKOUT = (ROOT / "mingjing_core/adapters/tarot.py").read_text(encoding="utf8")
HISTORICAL = historical_source(CHECKOUT)
CLOCK_SOURCE = reviewed_clock_source(HISTORICAL)


def test_historical_asset_is_unchanged_and_current_review_is_separate() -> None:
    asset = json.loads(
        (ROOT / "mingjing_core/knowledge/p8_tarot/spreads_v1.json").read_bytes()
    )
    source = next(
        row for row in asset["sources"] if row["source_id"] == "runtime-service"
    )
    assert source["sha256"] == lf_sha(HISTORICAL) == HISTORICAL_SHA
    review = json.loads(
        (
            ROOT / "mingjing_core/knowledge/p8_tarot/service_clock_review_v1.json"
        ).read_bytes()
    )
    assert review["version"] == REVIEW_VERSION
    assert review["historical"]["lf_sha256"] == HISTORICAL_SHA
    assert (
        review["reviewed_clock"]["lf_sha256"]
        == lf_sha(CLOCK_SOURCE)
        == CLOCK_REVIEW_SHA
    )
    assert (
        review["reviewed_clock"]["blob_sha1"]
        == "66600110660608840d8182474ee6752f0204613c"
    )
    assert len(review["exact_changes"]) == 3


@pytest.mark.parametrize(
    "text", [HISTORICAL, CLOCK_SOURCE, CLOCK_SOURCE.replace("\n", "\r\n")]
)
def test_exact_history_and_reviewed_migration_are_not_conflated(text: str) -> None:
    result = review_service_source(text)
    assert result["complete_service_ast_unchanged"] is True
    assert result["historical_source_reconstructed_exactly"] is True
    assert result["runtime_execution_verified"] is False
    assert result["clock_dependency_verified"] is False
    assert result["reviewed_clock_checkout_verified"] is (
        lf_sha(text) == CLOCK_REVIEW_SHA
    )
    assert result["checkout_basis"] == (
        "historical_source"
        if lf_sha(text) == HISTORICAL_SHA
        else "reviewed_clock_migration"
    )
    assert historical_source(text) == HISTORICAL


MUTATIONS = [
    ("draw['status']!='ready'", "draw['status']=='ready'"),
    ("if ident in seen", "if False and ident in seen"),
    ("if options['A']==options['B']", "if options['A']!=options['B']"),
    (
        "self.repo.assert_scope(owner,subject_id)",
        "self.repo.assert_scope(owner,'self')",
    ),
    ("position=i+1", "position=i+2"),
    ("not explicit_new", "explicit_new"),
    (
        "get_clock().now().isoformat()",
        "get_clock().now().replace(tzinfo=None).isoformat()",
    ),
    ("TarotDrawService = TarotService", "TarotDrawService = None"),
    (
        "from mingjing_core.timekit.clock import get_clock",
        "from another.clock import get_clock",
    ),
    ("models never shuffle", "models may shuffle"),
]


@pytest.mark.parametrize("old,new", MUTATIONS)
def test_unknown_behavior_provenance_or_even_comment_change_requires_review(
    old: str, new: str
) -> None:
    assert old in CLOCK_SOURCE
    with pytest.raises(ValueError, match="P8_TAROT_SOURCE_REVIEW_REQUIRED"):
        review_service_source(CLOCK_SOURCE.replace(old, new))


def test_historical_source_cannot_be_replaced_by_a_resigned_unknown_version() -> None:
    with pytest.raises(ValueError, match="P8_TAROT_HISTORICAL_SOURCE_MISMATCH"):
        reviewed_clock_source(HISTORICAL + "\n")


def test_reviewed_stamp_uses_real_frozen_utc_clock_without_running_service() -> None:
    stamp = next(
        node
        for node in ast.parse(CLOCK_SOURCE).body
        if isinstance(node, ast.FunctionDef) and node.name == "_stamp"
    )
    frozen = FrozenClock(datetime(2026, 10, 21, 0, 0, tzinfo=UTC))
    scope = {"get_clock": lambda: frozen}
    exec(
        compile(ast.Module(body=[stamp], type_ignores=[]), "reviewed_stamp", "exec"),
        scope,
    )
    assert scope["_stamp"]() == frozen.now().isoformat()
    assert scope["_stamp"]().endswith("+00:00")
