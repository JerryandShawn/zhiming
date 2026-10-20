"""Real v3 ConsultationService on a disposable, loopback PostgreSQL 15 schema."""

import os
import re
import time
import uuid
from typing import Any

from psycopg import sql

from mingjing_core.adapters.model import ConfiguredModel
from mingjing_core.application.consultation import ConsultationService
from mingjing_core.repositories.postgres import ENTITY_KINDS, PostgresRepository
from tools.eval.quota import ProviderStopped, QuotaGuard

from .base import TurnResult
from .local_db import local_dsn, verify_local_postgres
from .v3_seed import V3Seeder


class TrackingModel:
    def __init__(self, provider: Any) -> None:
        self.provider = QuotaGuard(provider, "target")
        self.calls = 0
        self.failures = 0
        self.last_failure_category = "provider"
        self.usage: dict[str, int] = {}
        self.diagnostics: list[dict[str, Any]] = []

    def generate(self, **kwargs: Any) -> dict[str, Any]:
        self.provider.check_open()
        self.calls += 1
        try:
            result = self.provider.generate(**kwargs)
        except ProviderStopped:
            self.failures += 1
            self.last_failure_category = "provider"
            raise
        except Exception as exc:
            self.failures += 1
            if hasattr(exc, "safe_diagnostic"):
                diagnostic = exc.safe_diagnostic()
                self.diagnostics.append(diagnostic)
                self.last_failure_category = (
                    "business"
                    if diagnostic.get("reason") in {"json", "max_tokens", "tool_count", "tool_input"}
                    else "provider"
                )
            else:
                self.last_failure_category = "provider"
            raise
        for key, count in result.get("usage", {}).items():
            if type(count) is int and count >= 0:
                self.usage[key] = self.usage.get(key, 0) + count
        return result


class V3Target:
    def __init__(self, model: str = "kimi", *, dsn: str | None = None, provider: Any = None) -> None:
        self.dsn = local_dsn(dsn or os.getenv("CORE_TEST_DSN", ""))
        self.model_name = os.getenv("KIMI_MODEL", "kimi-k3") if model == "kimi" else model
        self.provider = provider
        self.repo: PostgresRepository | None = None
        self.service: ConsultationService | None = None
        self.schema = ""
        self.owner = "synthetic-eval-owner"
        self.run_ids: list[str] = []
        self.seed_data: dict[str, Any] = {}

    def reset(self, seed: dict[str, Any]) -> None:
        self.close()
        verify_local_postgres(self.dsn)
        self.seed_data = seed
        self.schema = "eval_p0_" + uuid.uuid4().hex
        self.repo = PostgresRepository(self.dsn, schema=self.schema, max_size=4)
        self.repo.ensure_owner(self.owner, settings={"auto_save_low_sensitivity": True, **seed.get("settings", {})})
        self.model = TrackingModel(self.provider or ConfiguredModel(model=self.model_name))
        self.service = ConsultationService(self.repo, model=self.model)
        self.seeder = V3Seeder(self.service, self.owner, seed.get("_scenario_id", "scenario"))
        self.seeder.seed(seed)

    def send(self, turn: dict[str, Any]) -> TurnResult:
        if self.service is None or self.repo is None:
            raise RuntimeError("Call reset before send")
        started = time.perf_counter()
        calls_before = self.model.calls
        elapsed_before = self.model.provider.elapsed_seconds
        failures_before = self.model.failures
        usage_before = dict(self.model.usage)
        request = self.submit_turn(turn)
        self.run_ids.append(request["id"])
        events: list[str] = []
        result: dict[str, Any] = {}
        error = None
        try:
            result = self.service.execute(self.owner, request["id"], lambda event: events.append(event["type"]))
        except ProviderStopped:
            error = "ProviderStopped"
        except Exception as exc:
            error = type(exc).__name__
        run = self.repo.fetch_run(self.owner, request["id"])
        return TurnResult(
            text=result.get("answer", ""),
            receipts=[
                {**receipt, "status": receipt.get("write_status")} for receipt in result.get("memory_receipts", [])
            ],
            db=self.inspect_db(),
            events=events,
            model_calls=self.model.calls - calls_before,
            elapsed_seconds=round(time.perf_counter() - started, 4),
            usage={key: value - usage_before.get(key, 0) for key, value in self.model.usage.items()},
            error=error,
            metadata={
                "run_status": run["status"],
                "run_id": request["id"],
                "runtime": "v3",
                "model_elapsed_seconds": self.model.provider.elapsed_seconds - elapsed_before,
                "stop_reason": self.model.provider.stop_reason,
                "provider_http_status": self.model.provider.provider_http_status,
                "error_category": self.model.last_failure_category
                if self.model.failures > failures_before
                else "business"
                if error
                else None,
            },
        )

    def submit_turn(self, turn: dict[str, Any]) -> dict[str, Any]:
        # Seed the current original and admit its run atomically. A refused
        # privacy request must not leave an orphaned life-thread original.
        with self.repo.transaction(self.owner):
            return self._submit_turn(turn)

    def _submit_turn(self, turn: dict[str, Any]) -> dict[str, Any]:
        index = turn.get("_index", len(self.run_ids) + 1)
        operation = f"eval:{self.seed_data.get('_scenario_id', 'scenario')}:{index}"
        kind = turn.get("kind", "turn")
        mode = "scheduled_report" if kind in {"brief", "report"} else "chat"
        selection = self.report_selection() if mode == "scheduled_report" else {}
        source = None
        if mode == "chat":
            source = self.seeder.receive(
                {
                    **turn,
                    "content": turn["user"],
                    "role": "user",
                    "topic_id": self.seed_data.get("context", {}).get("topic_id", "shared"),
                },
                operation,
            )
        return self.service.submit(
            owner=self.owner,
            message=turn["user"],
            request_id=operation,
            conversation_id=turn.get(
                "conversation_id", turn.get("topic_id", self.seed_data.get("context", {}).get("topic_id", "shared"))
            ),
            case_ids=self.seeder.case_ids,
            mode=mode,
            depth="standard",
            selection=selection,
            source_message_id=source["id"] if source else None,
        )

    def report_selection(self) -> dict[str, Any]:
        from mingjing_core.application.report_schedules import ReportScheduleService

        service = ReportScheduleService(self.repo)
        service.seed_defaults(self.owner)
        policy = service.effective(self.owner, "daily")
        return {
            "report_schedule_kind": "daily",
            "report_schedule_revision": policy["revision"],
        }

    def inspect_db(self) -> dict[str, Any]:
        if self.repo is None:
            raise RuntimeError("Call reset before inspect_db")
        entities = {
            kind: self.repo.list(self.owner, kind, include_deleted=True)
            for kind in sorted(ENTITY_KINDS)
            if kind not in {"model_call", "runtime_step"}
        }
        flattened = [
            {"id": row["id"], "kind": kind, "status": row["status"], "data": row}
            for kind, rows in entities.items()
            for row in rows
            if kind != "fact" or row["id"] not in self.seeder.profile_fact_ids
        ]
        return {
            "entities": flattened,
            "settings": self.repo.assert_scope(self.owner)["settings"],
            **entities,
            **{kind + "s": rows for kind, rows in entities.items()},
        }

    def close(self) -> None:
        if self.repo is None:
            return
        try:
            if self.service is not None:
                for run_id in self.run_ids:
                    run = self.repo.fetch_run(self.owner, run_id)
                    for epoch in range(run.get("retry_epoch", 0) + 1):
                        self.service.runtime.purge(run_id, epoch)
            if not re.fullmatch(r"eval_p0_[a-f0-9]{32}", self.schema):
                raise ValueError("Refusing to clean an unowned evaluation schema")
            with self.repo.transaction() as connection:
                connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(self.schema)))
        finally:
            self.repo.close()
            self.repo = None
            self.service = None
            self.run_ids = []
