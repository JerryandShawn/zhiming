"""R46: real-library alert window is distinct from exact-jie calculation."""

from __future__ import annotations

import copy
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mingjing_core.adapters.charts.boundary_alerts import boundary_alerts  # noqa: E402
from mingjing_core.adapters.charts.time_basis import time_basis_candidates  # noqa: E402


def run() -> list[dict]:
    # Same fixed native-jie instant as the unchanged 12-case boundary regression.
    jie = datetime(2026, 2, 4, 4, 2, 8)
    observations = []
    for offset in (-7260, -7140, 7140, 7260):
        civil = jie + timedelta(seconds=offset)
        original = time_basis_candidates(
            civil.date().isoformat(),
            civil.time().isoformat(),
            {"tz": "Asia/Shanghai", "lon": 87.625},
            "clock",
            include_beijing=True,
        )
        before = copy.deepcopy(original)
        rows = [
            r for r in boundary_alerts(original) if r["boundary_kind"] == "jie_month"
        ]
        assert original == before
        expected = abs(offset) == 7140
        assert bool(rows) is expected
        if rows:
            assert len(rows) == 1
            row = rows[0]
            assert row["distance_seconds"] == abs(offset)
            assert row["threshold_seconds"] == 7200
            assert row["boundary_basis"] == "physical_UTC+8"
            assert row["jie"] == "立春"
            left, right = row["alternatives"]
            assert left["pillars"]["month"] != right["pillars"]["month"]
            assert (left["pillars"]["year"], right["pillars"]["year"]) == (
                "乙巳",
                "丙午",
            )
            assert all(not r["is_birth_fact"] for r in row["alternatives"])
        observations.append({"offset_seconds": offset, "alert": bool(rows)})
    return observations


if __name__ == "__main__":
    print(json.dumps({"cases": run(), "real_model_calls": 0}))
