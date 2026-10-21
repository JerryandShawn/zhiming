"""A monotonic bounded maintenance schedule reports safe failures and keeps serving."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from typing import Any

from mingjing_core.application.privacy_maintenance import PrivacyMaintenance

LOG = logging.getLogger(__name__)
FAILURE_CODE = "PRIVACY_MAINTENANCE_FAILED"


class PrivacyMaintenanceSchedule:
    def __init__(self, repo: Any, *, monotonic: Callable[[], float] = time.monotonic) -> None:
        self.maintenance = PrivacyMaintenance(repo)
        self.monotonic = monotonic
        self.next_due = 0.0
        self.failures = 0
        self.last_error_code: str | None = None
        self.last_counts: dict[str, int] | None = None
        self.running = False
        self.guard = threading.Lock()

    def tick(self) -> dict[str, Any] | None:
        with self.guard:
            now = self.monotonic()
            if self.running or now < self.next_due:
                return None
            # Reserve the next slot before I/O so concurrent callers cannot
            # start duplicate sweeps, including when the preceding sweep fails.
            self.next_due = now + 60.0
            self.running = True
        try:
            counts = self.maintenance.tick(limit=50)
        except Exception:
            with self.guard:
                self.failures += 1
                self.last_error_code = FAILURE_CODE
                self.running = False
            LOG.warning(FAILURE_CODE)
            return {"status": "failed", "code": FAILURE_CODE}
        with self.guard:
            self.last_error_code = None
            self.last_counts = counts
            self.running = False
        return {"status": "succeeded", "counts": counts}
