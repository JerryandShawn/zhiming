"""Independent B1 failure promotion and buffered-output probes; no sampling."""

from __future__ import annotations

import io
import sys
from contextlib import suppress
from copy import deepcopy
from types import SimpleNamespace

import pytest

from mingjing_core.adapters.charts.benchmarks import (
    line_coverage_core_boundary as boundary,
)
from mingjing_core.adapters.charts.benchmarks import (
    line_coverage_core_reports as reports,
)
from mingjing_core.adapters.charts.benchmarks import line_coverage_core_run as run
from mingjing_core.adapters.charts.benchmarks.line_coverage_manifest import digest
from mingjing_core.adapters.charts.benchmarks.line_coverage_own_plan import CANDIDATES

NODE = next(node for node, runtime in CANDIDATES.items() if runtime == "core")


def _witness(failed_call: bool) -> reports.Witness:
    value = reports.Witness(NODE)
    value.pytest_collection_modifyitems(
        None, None, [SimpleNamespace(nodeid=NODE, fixturenames=[])]
    )
    for phase in ("setup", "call", "teardown"):
        value.pytest_runtest_logreport(
            SimpleNamespace(
                nodeid=NODE,
                when=phase,
                outcome="failed" if failed_call and phase == "call" else "passed",
            )
        )
    value.pytest_sessionfinish(None, int(failed_call))
    return value


@pytest.mark.parametrize("reason", ["caught_guard", "failed_call", "postflight"])
def test_actual_failed_receipt_cannot_be_promoted_by_two_fields_and_resigning(reason):
    inventory = {
        "commit": "a" * 40,
        "inventory_sha256": "b" * 64,
        "files": [],
    }
    gate = boundary.Gate(set(), boundary.ROOT / "private/tmp/independent-unused")
    if reason == "caught_guard":
        with suppress(ValueError):
            gate.process("synthetic-no-process-created")
    row = run._receipt(
        inventory,
        {"plan_sha256": "c" * 64},
        NODE,
        "trace",
        _witness(reason == "failed_call"),
        (int(reason == "failed_call"), "completed", 0.001, {}),
        gate,
        reason != "postflight",
    )
    source = {"files": {}, "git_configuration": {}, "raw_sha256": {}}
    runtime = {"synthetic_unit_fixture": True}
    runtime["runtime_sha256"] = digest(runtime)
    row.update(
        source_before=source,
        source_after=deepcopy(source),
        runtime_before=runtime,
        runtime_after=deepcopy(runtime),
        postflight_error_code="b1_postflight_fingerprint_failed"
        if reason == "postflight"
        else None,
    )
    assert row["status"] == "failed" and row["eligible_for_union"] is False
    row.update(status="completed", eligible_for_union=True)
    row["receipt_sha256"] = digest(
        {key: value for key, value in row.items() if key != "receipt_sha256"}
    )
    with pytest.raises(ValueError, match="b1_receipt_(guard|lifecycle)_not_successful"):
        reports.validate_receipt(inventory, row)


@pytest.mark.parametrize("descriptor,attribute", [(1, "__stdout__"), (2, "__stderr__")])
def test_held_original_buffer_cannot_flush_marker_after_descriptors_restore(
    capfd, monkeypatch, descriptor, attribute
):
    marker = "SYNTHETIC_B1_BUFFERED_PRIVATE_MARKER"
    held = io.TextIOWrapper(
        io.BufferedWriter(io.FileIO(descriptor, "w", closefd=False)),
        encoding="utf-8",
        line_buffering=False,
        write_through=False,
    )
    gate = boundary.Gate(set(), boundary.ROOT / "private/tmp/independent-unused")
    try:
        with monkeypatch.context() as scope:
            scope.setattr(sys, attribute, held)
            with boundary.boundaries(gate):
                gate.active = True
                getattr(sys, attribute).write(marker + "_CURRENT")
                held.write(marker + "_HELD")
            held.flush()
            captured = capfd.readouterr()
            assert marker not in captured.out and marker not in captured.err
            assert not gate.blocked
    finally:
        held.close()
