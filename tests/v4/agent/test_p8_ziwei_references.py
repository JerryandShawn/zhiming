"""Declared flying tables bind native facts, never manufacture rule hits."""

import pytest

from mingjing_core.adapters.charts.tool_evidence import content_hash
from mingjing_core.domain.contracts import EvidenceError
from mingjing_core.knowledge.registry import resolve_pointer

from .test_p8_documents import boundary_document, verify_boundary


def test_native_flying_is_bound_to_column_without_rule_or_alias_invention() -> None:
    payload = boundary_document()
    doc = verify_boundary(payload)
    flying_rows = [row for row in doc["references"] if "ziwei_column" in row["pointer"]]
    assert len(flying_rows) == len(payload["charts"]) * 2
    for row in flying_rows:
        assert row["kind"] == "chart" and "alias" not in row
        assert row["value_sha256"] == content_hash(resolve_pointer(payload, row["pointer"]))
    for chart in payload["charts"]:
        flying = chart["ziwei_column"]["p8_flying_transformations"]
        assert all(not value["links"] for value in flying["temporal_layers"].values())
        # Unavailable native layers stay unavailable instead of being promoted
        # to an interpretation merely because a chart reference exists.
        assert all(value["status"] == "unavailable" for value in flying["temporal_layers"].values())


@pytest.mark.parametrize(
    "mode", ["hash", "school", "edge", "missing_star", "other_column", "double_lift", "missing_path", "fake_layer"]
)
def test_flying_provenance_or_pointer_tampering_is_rejected(mode: str) -> None:
    payload = boundary_document()
    flying = payload["charts"][0]["ziwei_column"]["p8_flying_transformations"]
    if mode == "hash":
        flying["table_sha256"] = "0" * 64
    elif mode == "school":
        flying["table_id"] = "unapproved"
    elif mode == "edge":
        flying["edges"][0]["star"] = "invented"
    elif mode == "missing_star":
        flying["edges"][0]["status"] = "resolved"
        flying["edges"][0]["locations"] = []
    elif mode == "fake_layer":
        flying["temporal_layers"]["yearly"]["status"] = "resolved"
    else:
        path = flying["edges"][0]["evidence_paths"][0]
        replacement = {
            "other_column": path.replace("/charts/0/", "/charts/1/"),
            "double_lift": "/charts/0" + path,
            "missing_path": "/charts/0/ziwei_column/absent",
        }[mode]
        flying["edges"][0]["evidence_paths"][0] = replacement
    with pytest.raises(EvidenceError):
        verify_boundary(payload)
