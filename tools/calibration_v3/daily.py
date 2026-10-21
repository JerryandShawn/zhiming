"""Clock-based daily opening plans only; no delivery, persistence or human authentication."""

from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from mingjing_core.timekit.clock import Clock

from .batches import BlindBatch, BlindPlan
from .models import CalibrationError, digest, identity

ZONE = ZoneInfo("Asia/Shanghai")


def aware(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise CalibrationError("aware_clock_required")
    return value.astimezone(UTC)


@dataclass(frozen=True)
class BatchOpening:
    batch_id: str
    operation_id: str
    opened_at: datetime

    def __post_init__(self) -> None:
        identity(self.batch_id)
        identity(self.operation_id)
        object.__setattr__(self, "opened_at", aware(self.opened_at))


@dataclass(frozen=True)
class OpeningLedger:
    plan_sha256: str
    entries: tuple[BatchOpening, ...] = ()
    revision: int = 0

    def __post_init__(self) -> None:
        digest(self.plan_sha256)
        if type(self.revision) is not int or self.revision < 0 or not isinstance(self.entries, tuple):
            raise CalibrationError("opening_ledger_invalid")
        if any(not isinstance(entry, BatchOpening) for entry in self.entries):
            raise CalibrationError("opening_entry_invalid")
        if len({entry.batch_id for entry in self.entries}) != len(self.entries) or (
            len({entry.operation_id for entry in self.entries}) != len(self.entries)
        ):
            raise CalibrationError("opening_operation_duplicate")
        days = [entry.opened_at.astimezone(ZONE).date() for entry in self.entries]
        if len(set(days)) != len(days):
            raise CalibrationError("daily_opening_limit_exceeded")
        instants = [entry.opened_at for entry in self.entries]
        if instants != sorted(instants) or self.revision < len(self.entries):
            raise CalibrationError("opening_ledger_regressed")


@dataclass(frozen=True)
class OpeningDecision:
    status: str
    ledger: OpeningLedger
    batch: BlindBatch | None
    next_allowed_at: datetime | None = None


def plan_open_batch(
    plan: BlindPlan, ledger: OpeningLedger, *, clock: Clock, operation_id: str, expected_revision: int
) -> OpeningDecision:
    identity(operation_id)
    now = aware(clock.now())
    if not isinstance(plan, BlindPlan) or not isinstance(ledger, OpeningLedger) or ledger.plan_sha256 != plan.sha256:
        raise CalibrationError("opening_plan_binding_mismatch")
    batch_ids = [batch.id for batch in plan.batches]
    if [entry.batch_id for entry in ledger.entries] != batch_ids[: len(ledger.entries)]:
        raise CalibrationError("opening_order_invalid")
    existing = next((entry for entry in ledger.entries if entry.operation_id == operation_id), None)
    if existing is not None:
        return OpeningDecision("replayed", ledger, plan.batches[batch_ids.index(existing.batch_id)])
    if type(expected_revision) is not int or expected_revision != ledger.revision:
        raise CalibrationError("opening_revision_conflict")
    if ledger.entries and now < ledger.entries[-1].opened_at:
        raise CalibrationError("opening_clock_regressed")
    if len(ledger.entries) == 5:
        return OpeningDecision("complete", ledger, None)
    local = now.astimezone(ZONE)
    if any(entry.opened_at.astimezone(ZONE).date() == local.date() for entry in ledger.entries):
        tomorrow = datetime.combine(local.date() + timedelta(days=1), time(), ZONE).astimezone(UTC)
        return OpeningDecision("deferred", ledger, None, tomorrow)
    batch = plan.batches[len(ledger.entries)]
    updated = OpeningLedger(
        plan.sha256, (*ledger.entries, BatchOpening(batch.id, operation_id, now)), ledger.revision + 1
    )
    return OpeningDecision("opening_intent", updated, batch)
