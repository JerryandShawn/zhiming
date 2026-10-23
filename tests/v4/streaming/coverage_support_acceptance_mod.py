"""Independent synthetic row-port inputs; no database or real runtime is exercised."""

import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Any

from mingjing_core.streaming.event_models import RunEvent, RunScope, make_event
from mingjing_core.streaming.store_contracts import EventColumns, StoredOperation

AT = datetime(2026, 10, 21, 0, 52, tzinfo=UTC)
SCOPE = RunScope("boundary-owner", "boundary-run")
COLUMNS = EventColumns()


def sample(kind: str) -> dict[str, Any]:
    path = Path(__file__).parent / "fixtures/event_samples_main_v1_mod.json"
    return next(item["payload"] for item in json.loads(path.read_bytes())["samples"] if item["type"] == kind)


def event(kind: str, seq: int = 1, payload: Mapping[str, Any] | None = None) -> RunEvent:
    return make_event(
        run_id=SCOPE.run_id, seq=seq, ts=AT, type=kind, payload=sample(kind) if payload is None else payload
    )


def row(seq: int = 1) -> dict[str, Any]:
    return {
        "owner": SCOPE.owner_id,
        "run_id": SCOPE.run_id,
        "seq": seq,
        "kind": "text_delta",
        "created_at": AT,
        "payload": {"v": 1, "run_id": SCOPE.run_id, "seq": seq, "ts": "2026-10-21T08:52:00+08:00", "text": "虚构行"},
    }


class RowPort:
    """Fault-injection port deliberately returns supplied rows without pretending to run SQL."""

    def __init__(
        self,
        rows: Sequence[Mapping[str, object]] = (),
        *,
        cursor: Mapping[str, object] | None = None,
        prior: StoredOperation | None = None,
        allocated: int = 10,
        previous: int = 0,
    ) -> None:
        self.rows, self.cursor, self.prior = rows, cursor, prior
        self.allocated, self.previous = allocated, previous
        self.calls: list[str] = []

    def __call__(self, scope: RunScope) -> "RowPort":
        self.calls.append("transaction")
        return self

    def __enter__(self) -> "RowPort":
        return self

    def __exit__(
        self, kind: type[BaseException] | None, value: BaseException | None, traceback: TracebackType | None
    ) -> bool:
        return False

    def lock_scope(self, scope: RunScope) -> None:
        self.calls.append("lock")

    def assert_run(self, scope: RunScope) -> None:
        self.calls.append("authorize")

    def find_operation(self, scope: RunScope, operation_id: str) -> StoredOperation | None:
        self.calls.append("find")
        return self.prior

    def last_sequence(self, scope: RunScope) -> int:
        return self.previous

    def next_sequence(self, scope: RunScope) -> int:
        self.calls.append("allocate")
        return self.allocated

    def read_event(self, scope: RunScope, seq: int, columns: EventColumns) -> Mapping[str, object] | None:
        return self.cursor

    def read_rows(
        self, scope: RunScope, after_seq: int, limit: int, columns: EventColumns
    ) -> Sequence[Mapping[str, object]]:
        return self.rows

    def insert_row(self, columns: EventColumns, value: Mapping[str, object]) -> None:
        self.calls.append("insert")

    def record_operation(self, scope: RunScope, operation_id: str, fingerprint: str, seq: int) -> None:
        self.calls.append("record")

    def notify(self, channel: str, payload: str) -> None:
        self.calls.append("notify")
