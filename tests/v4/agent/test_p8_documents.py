"""Real donor documents and strict invocation-bound references, no model I/O."""

from copy import deepcopy
import json
from pathlib import Path

import pytest

from mingjing_core.adapters.charts.tool_evidence import evidence_result
from mingjing_core.application.charts_documents import lifted_pointer, verify_p8_document
from mingjing_core.domain.contracts import EvidenceError, ScopeError
from mingjing_core.knowledge.registry import resolve_pointer

ROOT = Path(__file__).resolve().parents[3] / "docs/v4/contracts/samples"
SOURCES = {"synthetic-worker.py": "a" * 64}
SCOPE = {"owner_user_id": "alice", "subject_id": "self", "revision": 3, "operation_id": "step"}


def tool_payload() -> dict:
    return evidence_result(
        "p8-daily-transit-v1",
        {"observed": {"a/b~c": 7}},
        [
            {
                "met": True,
                "rule_id": "synthetic",
                "school": "synthetic",
                "source": "fixture",
                "evidence_paths": ["/data/observed/a~1b~0c"],
            }
        ],
        [],
        SCOPE,
    )


def verify(payload: dict, kind: str = "daily_transit", **changes: object) -> dict:
    args = {
        "kind": kind,
        "owner": "alice",
        "subject": "self",
        "revision": 3,
        "operation_id": "step",
        "source_sha256": SOURCES,
    }
    return verify_p8_document(payload, **(args | changes))


def test_tool_content_scope_and_references_are_bound_without_copying_alias_names() -> None:
    payload = tool_payload()
    before = deepcopy(payload)
    doc = verify(payload)
    assert doc["document_id"].startswith("doc-") and doc["scope"] == SCOPE
    assert doc["payload"] == before and payload == before
    assert len(doc["references"]) == 2
    assert doc["references"][0]["pointer"] == "/data/observed/a~1b~0c"
    assert all("alias" not in row for row in doc["references"])
    doc["payload"]["data"]["observed"]["a/b~c"] = 99
    assert payload == before


@pytest.mark.parametrize("change", [{"owner": "bob"}, {"subject": "other"}, {"revision": 4}, {"operation_id": "other"}])
def test_other_invocation_is_rejected(change: dict) -> None:
    with pytest.raises(ScopeError):
        verify(tool_payload(), **change)


@pytest.mark.parametrize("mode", ["content", "hash", "version", "nan", "revision_bool", "source"])
def test_forged_or_invalid_document_is_not_accepted(mode: str) -> None:
    payload = tool_payload()
    kwargs = {}
    if mode == "content":
        payload["data"]["observed"]["a/b~c"] = 8
    elif mode == "hash":
        payload["document_id"] = "tool-" + "0" * 64
    elif mode == "version":
        payload["version"] = "unreviewed"
    elif mode == "nan":
        payload["data"]["invalid"] = float("nan")
    elif mode == "revision_bool":
        payload["scope"]["revision"] = True
    else:
        kwargs["source_sha256"] = {}
    with pytest.raises((EvidenceError, ScopeError)):
        verify(payload, **kwargs)


@pytest.mark.parametrize("system", ["bazi", "ziwei", "astro"])
def test_native_time_basis_sample_all_registered_paths_resolve(system: str) -> None:
    preview = json.loads((ROOT / f"ayuan_{system}.json").read_text(encoding="utf-8"))
    native = next(doc["payload"] for doc in preview["documents"] if doc["kind"] == "time_basis")
    scope = preview["scope"]
    doc = verify_p8_document(
        native,
        kind="time_basis",
        owner=scope["owner_user_id"],
        subject=scope["subject_id"],
        revision=scope["revision"],
        operation_id=scope["operation_id"],
        source_sha256=native["source_sha256"],
    )
    assert doc["references"]
    for row in doc["references"]:
        resolve_pointer(native, row["pointer"])
        for path in row.get("evidence_pointers", []):
            resolve_pointer(native, path)
    for index, _ in enumerate(native["charts"]):
        path = f"/charts/{index}/ziwei_column"
        assert lifted_pointer(path, index) == path


def test_missing_path_and_false_rule_are_rejected_even_with_recomputed_native_hash() -> None:
    for hit in (
        {"met": False, "rule_id": "x", "school": "s", "source": "t", "evidence_paths": ["/data/value"]},
        {"met": True, "rule_id": "x", "school": "s", "source": "t", "evidence_paths": ["/data/absent"]},
    ):
        # Native evidence_result itself rejects these; constructing a fresh body
        # checks the consumer independently rather than relying on that producer.
        from mingjing_core.adapters.charts.tool_evidence import content_hash

        root = {
            "version": "p8-daily-transit-v1",
            "scope": SCOPE,
            "data": {"value": 1},
            "rule_hits": [hit],
            "sources": [],
        }
        with pytest.raises(EvidenceError):
            verify(dict(root, document_id="tool-" + content_hash(root)))


def test_almanac_has_no_private_scope_and_synastry_cannot_be_persisted_as_a_chart() -> None:
    payload = json.loads((ROOT / "almanac-20261021.json").read_text(encoding="utf-8"))
    assert verify(payload, kind="almanac")["scope"] == SCOPE
    with pytest.raises(EvidenceError):
        verify(tool_payload(), kind="synastry")
