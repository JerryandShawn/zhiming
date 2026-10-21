"""A batch cannot use one source as both current and withdrawn, even across content categories."""

from collections.abc import Mapping, Sequence

from mingjing_core.application.briefing_v2.contracts import BriefSourceState
from mingjing_core.application.followups_contracts import FollowupScope

from .contracts import DailyTransitInput, ReportError, ReportRecord, SyntheticSymbolicInput


def validate_batch_manifest(
    records: Sequence[ReportRecord],
    transits: Sequence[DailyTransitInput],
    synthetic: Sequence[SyntheticSymbolicInput],
    scope: FollowupScope,
) -> None:
    groups = ((records, ReportRecord), (transits, DailyTransitInput), (synthetic, SyntheticSymbolicInput))
    for rows, kind in groups:
        if not isinstance(rows, (list, tuple)) or any(not isinstance(row, kind) for row in rows):
            raise ReportError("typed_batch_inputs_required")
    if any(row.scope != scope for row in (*records, *synthetic)):
        raise ReportError("batch_scope_mismatch")
    for row in transits:
        identity = row.payload.get("scope")
        if isinstance(identity, Mapping):
            actual = (identity.get("owner_user_id"), identity.get("subject_id"))
            if all(type(value) is str for value in actual) and actual != (scope.owner_id, scope.subject_id):
                raise ReportError("transit_scope_mismatch")
    states = [state for row in (*records, *synthetic) for state in row.source_states]
    states.extend(row.current_state for row in transits if row.current_state is not None)
    known: dict[str, BriefSourceState] = {}
    for state in states:
        if state.source_id in known and known[state.source_id] != state:
            raise ReportError("contradictory_current_source_manifest")
        known[state.source_id] = state
