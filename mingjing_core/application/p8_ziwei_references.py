"""Native flying calculations are chart facts, not invented rule hits."""

from __future__ import annotations

from typing import Any

from mingjing_core.adapters.charts.time_basis_readout import rebase_column_evidence
from mingjing_core.adapters.charts.tool_evidence import content_hash
from mingjing_core.adapters.charts.ziwei_flying import palace_flying_transformations
from mingjing_core.domain.contracts import EvidenceError
from mingjing_core.knowledge.registry import resolve_pointer


def _pointers(value: Any, root: dict[str, Any], prefix: str) -> None:
    if isinstance(value, list):
        for item in value:
            _pointers(item, root, prefix)
    elif isinstance(value, dict):
        for key, item in value.items():
            paths = item if key == "evidence_paths" else [item] if key.endswith("_pointer") else None
            if paths is None:
                _pointers(item, root, prefix)
                continue
            if not isinstance(paths, list):
                raise EvidenceError("紫微飞化依据列表无效")
            for path in paths:
                if not isinstance(path, str) or not path.startswith(prefix + "/"):
                    raise EvidenceError("紫微飞化依据不属于当前盘面")
                resolve_pointer(root, path)


def ziwei_reference_rows(payload: dict[str, Any], document_id: str) -> list[dict[str, Any]]:
    rows = []
    for index, chart in enumerate(payload["charts"]):
        prefix = f"/charts/{index}/ziwei_column"
        column = chart["ziwei_column"]
        flying = column["p8_flying_transformations"]
        # Reproduce the declared table against actual native stars/palaces;
        # missing/ambiguous stars and unavailable layers remain unresolved.
        expected = {"p8_flying_transformations": palace_flying_transformations(column, school=flying["table_id"])}
        rebase_column_evidence(expected, prefix)
        if content_hash(expected["p8_flying_transformations"]) != content_hash(flying):
            raise EvidenceError("紫微飞化与本盘星曜、具名表或来源不符")
        _pointers(flying, payload, prefix)
        for path in (prefix, prefix + "/p8_flying_transformations"):
            rows.append(
                {
                    "kind": "chart",
                    "document_id": document_id,
                    "pointer": path,
                    "value_sha256": content_hash(resolve_pointer(payload, path)),
                }
            )
    return rows
