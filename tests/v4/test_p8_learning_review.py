"""Independent review cases: rehashed input still obeys native chart boundaries."""

from __future__ import annotations

import json
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path

import pytest

from mingjing_core.adapters.charts.benchmarks.handoff_refs import claim_id, document_id
from mingjing_core.adapters.charts.tool_evidence import content_hash, pointer
from mingjing_core.skills.learning import learning_outline

ROOT = Path(__file__).resolve().parents[2]


def _preview() -> dict:
    path = ROOT / "docs/v4/contracts/samples/ayuan_bazi.json"
    return json.loads(path.read_text(encoding="utf8"))


def _rehash(source: dict) -> None:
    """Model a caller who can recompute content hashes; they are not signatures."""
    mapping = {}
    for doc in source["documents"]:
        old = doc["document_id"]
        new = document_id(
            source["scope"], doc["kind"], doc["source_sha256"], doc["payload"]
        )
        mapping[old] = new
        doc["document_id"] = new
    references = [ref for refs in source["view"].values() for ref in refs]
    references.extend(source.get("boundary_alerts", []))
    for ref in references:
        ref["document_id"] = mapping.get(ref["document_id"], ref["document_id"])
    documents = {row["document_id"]: row["payload"] for row in source["documents"]}
    for rows in source["aliases"].values():
        for row in rows:
            ref = row["ref"]
            ref["document_id"] = mapping.get(ref["document_id"], ref["document_id"])
            row["value_sha256"] = content_hash(
                pointer(documents[ref["document_id"]], ref["path"])
            )
            row["claim_id"] = claim_id(row)


def _foreign_c_branch(source: dict) -> None:
    alias = learning_outline(source, limit=1)["points"][0]["c_aliases"][0]
    row = next(row for row in source["aliases"]["c"] if row["alias"] == alias)
    row.update(branch_id="foreign-branch", basis="actual_UTC")
    row["claim_id"] = claim_id(row)


def _promote_diagnostic(source: dict) -> None:
    source["view"]["primary"] = [deepcopy(source["view"]["diagnostics"][0])]


def _null_rule_details_with_valid_hashes(source: dict) -> None:
    row = source["aliases"]["r"][0]
    documents = {row["document_id"]: row["payload"] for row in source["documents"]}
    hit = pointer(documents[row["ref"]["document_id"]], row["ref"]["path"])
    hit["details"] = None
    _rehash(source)


def _missing_request(source: dict) -> None:
    source.pop("request")


def _null_request(source: dict) -> None:
    source["request"] = None


def _boolean_native_revision(source: dict) -> None:
    source["documents"][0]["payload"]["revision"] = bool(source["scope"]["revision"])
    _rehash(source)


def _boolean_alias_revision(source: dict) -> None:
    row = source["aliases"]["c"][0]
    row["scope"]["revision"] = bool(source["scope"]["revision"])
    row["claim_id"] = claim_id(row)


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        (_foreign_c_branch, "learning_alias_branch_invalid"),
        (_promote_diagnostic, "learning_primary_view_invalid"),
        (_null_rule_details_with_valid_hashes, "learning_input_invalid"),
        (_missing_request, "learning_input_invalid"),
        (_null_request, "learning_input_invalid"),
        (_boolean_native_revision, "learning_document_scope_invalid"),
        (_boolean_alias_revision, "learning_alias_content_invalid"),
    ],
    ids=[
        "rehashed-c-foreign-branch-basis",
        "diagnostic-cannot-be-primary",
        "null-details-rehashed-documents-and-claims",
        "request-missing",
        "request-null",
        "native-bool-revision-cannot-equal-integer",
        "alias-bool-revision-cannot-equal-integer",
    ],
)
def test_reviewed_invalid_projection_is_rejected(
    mutation: Callable[[dict], None], expected: str
) -> None:
    source = _preview()
    mutation(source)
    with pytest.raises(ValueError, match="^" + expected + "$"):
        learning_outline(source)
