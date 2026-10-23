"""Readiness report without observations: it cannot manufacture a product pass."""

import hashlib
from collections import Counter
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from mingjing_core.timekit.clock import Clock

from .loader import ROOT, MaterialError
from .observe import evaluate_observation


def build_readiness(cases: tuple[dict, ...], *, clock: Clock) -> dict[str, Any]:
    instant = clock.now()
    if not isinstance(instant, datetime) or instant.tzinfo is None or instant.utcoffset() is None:
        raise MaterialError("report_clock_must_be_aware")
    results = [evaluate_observation(case) for case in cases]
    counts = Counter(item.status for item in results)
    return {
        "schema": "eval-material-readiness-v1",
        "generated_at": instant.astimezone(ZoneInfo("Asia/Shanghai")).isoformat(),
        "scope": "material and checker readiness; no product scenario executed",
        "contract": "deterministic-eval-v2.3.0-candidate-material-v1",
        "case_count": len(cases),
        "assertion_count": sum(len(case["assertions"]) for case in cases),
        "counts": {
            key: counts[key] for key in ("unverified", "blocked_decision", "blocked_dependency", "observed_pass")
        },
        "cases": [
            {
                "id": case["id"],
                "status": result.status,
                "blocking_reasons": case["blocking_reasons"],
                "material_only": case["material_only"],
                "dataset_years": case["dataset_years"],
            }
            for case, result in zip(cases, results, strict=True)
        ],
        "source_files": {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(ROOT.iterdir())
            if path.is_file()
        },
        "limits": [
            "No live model/server/PG/HTTP/Feishu requests; no product tool is called",
            "Checker unit tests use synthetic observations and do not establish 59 product passes",
            "Missing or blank evidence stays unverified; fixed decisions and dependencies stay blocked",
            "Artifact hashes bind supplied observation fields only; the checker does not authenticate PG or humans",
            "Text negation support is a conservative lexical rule, not full natural language understanding",
            "Historical v2.1/v2.2 and runners are untouched; no score subtraction across contracts",
            "J01/J02 remain record_only without reviewed human labels; E2 is 2025 only",
        ],
    }
