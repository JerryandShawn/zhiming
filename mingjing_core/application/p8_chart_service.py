"""Explicit trusted-worker calculation route, without model or persistence effects."""

from __future__ import annotations

from copy import deepcopy
from subprocess import TimeoutExpired
from typing import Any

from mingjing_core.adapters.charts.p8_adapter import P8ChartAdapter
from mingjing_core.adapters.charts.p8_worker import source_hashes
from mingjing_core.application.charts_documents import verify_p8_document
from mingjing_core.application.charts_natal import natal_request
from mingjing_core.domain.contracts import CoreError, EvidenceError


class P8CalculationUnavailable(EvidenceError):
    code = "CALCULATION_ERROR"


def evaluate_time_basis(
    owner: str,
    subject: str,
    snapshot: dict[str, Any],
    target: str,
    operation_id: str,
    *,
    factory: Any = None,
) -> dict[str, Any]:
    """Caller must prepare/recheck the native snapshot outside calculation I/O."""
    request = natal_request(snapshot, owner=owner, subject=subject, operation_id=operation_id, as_of=target)
    sources = source_hashes()
    try:
        # The adapter owns a bounded isolated Charts subprocess; this service
        # neither imports its calculation dependencies nor holds a PG lock.
        adapter = (factory or P8ChartAdapter)(owner)
        payload = adapter.time_basis(request)
    except CoreError:
        raise
    except (OSError, RuntimeError, ValueError, TypeError, TimeoutExpired):
        raise P8CalculationUnavailable("本次时间口径计算未完成，未采用未经验证的盘面") from None
    document = verify_p8_document(
        payload,
        kind="time_basis",
        owner=owner,
        subject=subject,
        revision=snapshot["revision"],
        operation_id=operation_id,
        source_sha256=sources,
    )
    return {
        "calculation": deepcopy(payload),
        "documents": [document],
        "adapter_mode": "p8_v1_1",
        "boundary_alerts": deepcopy(payload.get("boundary_alerts", [])),
        "physical_instant_confirmation_required": payload["time_basis"]["requires_confirmation"],
        "unsupported_capabilities": ["western_timing", "transit_interval_search"],
    }
