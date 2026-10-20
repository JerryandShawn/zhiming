"""Measure complete fenced pure-state lifecycles, including JSON restore and source checks."""

import argparse
import hashlib
import sys
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mingjing_core.adapters.channels.cardkit_official_v3 import (  # noqa: E402
    OfficialError,
    recover_expired,
    restore_state,
    state_metadata,
)
from mingjing_core.timekit.clock import SystemClock  # noqa: E402
from tools.mod_week.official_synthetic_fixture import (  # noqa: E402
    TEXT,
    acknowledge,
    dispatch,
    fixture,
    open_stream,
    prepare,
)
from tools.mod_week.performance import measure, write_report  # noqa: E402


def complete_lifecycles() -> int:
    for _ in range(100):
        context = fixture()
        state = open_stream(context)
        operations = [("update", TEXT[:6]), ("finalize", context.artifact.final_card), ("close_streaming", None)]
        for kind, payload in operations:
            state = acknowledge(dispatch(prepare(state, context, kind, payload), context), context)
            state = restore_state(state_metadata(state), scope=context.scope)
        assert state.close_acked and state.finalize_acked and state.stage == "closed"
        assert state.last_acked_sequence == 3
    return 100


def crash_and_expiry_lifecycles() -> int:
    for index in range(200):
        context = fixture()
        state = dispatch(prepare(open_stream(context), context, "update", TEXT), context)
        if index % 2:
            context.clock.advance(timedelta(seconds=31))
            state = recover_expired(state, clock=context.clock, expected_revision=state.revision)
        state = restore_state(state_metadata(state), scope=context.scope)
        assert state.phase == "uncertain" and state.card_id == "synthetic_card"
        try:
            prepare(state, context, "update", TEXT)
        except OfficialError:
            continue
        raise AssertionError("unknown_operation_became_resendable")
    return 200


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    destination = parser.parse_args().output.resolve()
    if not destination.is_relative_to(ROOT) or destination.exists() or not destination.parent.is_dir():
        raise ValueError("new_workspace_report_required")
    sources = [
        *ROOT.glob("mingjing_core/adapters/channels/cardkit_official_v3/*.py"),
        *ROOT.glob("mingjing_core/adapters/channels/cards_official_v3/*.py"),
        *ROOT.glob("mingjing_core/adapters/channels/stream_outbox_v2/*.py"),
        ROOT / "mingjing_core/adapters/channels/card_limits_official_v3.py",
        ROOT / "tools/mod_week/official_synthetic_fixture.py",
        Path(__file__),
    ]
    before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in sources}
    cases = [
        measure(
            "100 complete five-request acknowledged lifecycles with three restores", complete_lifecycles, repeats=3
        ),
        measure(
            "200 complete create/send/update crash or lease-expiry restores, all deny resend",
            crash_and_expiry_lifecycles,
            repeats=3,
        ),
    ]
    if before != {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in sources}:
        raise ValueError("benchmark_source_changed")
    report = write_report(destination, cases, sources, clock=SystemClock())
    for case in report["cases"]:
        print(case["name"], case["median_seconds"], case["separate_tracemalloc_peak_bytes"])


if __name__ == "__main__":
    main()
