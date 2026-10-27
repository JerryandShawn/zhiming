"""File-only validation or explicit complete synthetic-source forward; never stage or production."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from tools.first_release_candidate_process import CandidateReplay
from tools.first_release_capture_binding import CaptureBinding
from tools.first_release_contracts import ReleasePin, RestoreContract, RestoreRejected, read_json
from tools.first_release_controller_runtime import ControllerRuntimePin
from tools.first_release_incremental import BackupInputs
from tools.first_release_incremental_forward import (
    ForwardInputs,
    SourceForwardPin,
    SourceForwardStopped,
    execute,
)
from tools.first_release_local_inputs import DumpPin, LocalInputs
from tools.first_release_restore import SafeParser
from tools.first_release_source_backfill_pin import SourceBackfillPin
from tools.first_release_source_process import PHASES, SourceReplayPin
from tools.first_release_target_proof import TargetProofPin

FILE_ARGUMENTS = (
    "pin",
    "contract",
    "dump-pin",
    "dump",
    "pg-restore",
    "capture-inputs",
    "capture-pin",
    "candidate-python",
    "replay-ledger",
    "replay-pin",
    "target-proof-pin",
    "controller-runtime-pin",
    "forward-pin",
    "source-replay-pin",
    "source-backfill-pin",
)
FORWARD_PHASES = frozenset(
    {
        "source_checks",
        "authorized",
        "core_transaction_started",
        "core_transaction_rejected",
        "core_commit_outcome_unknown",
        "core_committed",
        "core_verified",
        "checkpoint_started",
        "checkpoint_completed",
        "grant_started",
        "grant_commit_outcome_unknown",
        "grant_rolled_back",
        "grant_committed",
        "source_forward_completed",
        "source_replay_preflight",
        "ready_ro",
        "source_replay_completed",
        "source_backfill_preflight",
        "backfill_ready_ro",
        "source_backfill_completed",
    }
) | frozenset(PHASES)


def _parser() -> SafeParser:
    parser = SafeParser(description=__doc__, allow_abbrev=False)
    for name in FILE_ARGUMENTS:
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--apply-source-local", action="store_true")
    return parser


def _inputs(args: Any) -> tuple[ForwardInputs, SourceReplayPin, SourceBackfillPin]:
    """Parse independent reviewed files; no serialized witness or success bit is accepted."""
    workspace = Path.cwd()
    source = BackupInputs.parse(read_json(args.capture_inputs), workspace)
    target = LocalInputs(
        ReleasePin.parse(read_json(args.pin)),
        RestoreContract.parse(read_json(args.contract)),
        DumpPin.parse(read_json(args.dump_pin)),
        args.dump,
        args.pg_restore,
        workspace,
    )
    request = ForwardInputs(
        source,
        target,
        CaptureBinding.parse(args.capture_inputs, read_json(args.capture_pin)),
        CandidateReplay.parse(args.candidate_python, args.replay_ledger, read_json(args.replay_pin)),
        TargetProofPin.parse(read_json(args.target_proof_pin)),
        ControllerRuntimePin.parse(read_json(args.controller_runtime_pin)),
        SourceForwardPin.parse(read_json(args.forward_pin)),
    )
    replay = SourceReplayPin.parse(read_json(args.source_replay_pin))
    backfill = SourceBackfillPin.parse(read_json(args.source_backfill_pin))
    return request, replay, backfill


def _blocked(error: Exception, phase: str) -> dict[str, Any]:
    code, restored = "SOURCE_FORWARD_CLI_FAILED_OUTPUTS_RETAINED", False
    if isinstance(error, RestoreRejected):
        observed = str(error)
        if re.fullmatch(r"[A-Z][A-Z0-9_]{0,119}", observed):
            code = observed
    if isinstance(error, SourceForwardStopped):
        observed = error.phase
        if type(observed) is str and (
            observed in FORWARD_PHASES
            or re.fullmatch(r"source_backfill_[1-9][0-9]{0,4}_owner_(started|verified)", observed)
        ):
            phase = observed
        else:
            phase = "execution_outcome_unknown"
        restored = error.session_restored is True
    return dict(status="blocked", code=code, phase=phase, session_restored=restored, automatic_cleanup=False)


def main(argv: list[str] | None = None) -> int:
    phase = "input_validation"
    try:
        args = _parser().parse_args(argv)
        request, replay, backfill = _inputs(args)
        # The old controls stay unchanged. This reviewed CLI only selects the existing complete chain.
        phase = "execution_outcome_unknown" if args.apply_source_local else "file_validation"
        receipt = execute(
            request,
            apply_source=args.apply_source_local,
            source_replay_pin=replay,
            source_backfill_pin=backfill,
        )
        output = json.dumps(receipt, sort_keys=True)
    except Exception as error:
        print(json.dumps(_blocked(error, phase), sort_keys=True))
        return 2
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
