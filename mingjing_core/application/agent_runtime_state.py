"""Small authoritative state helpers for the injected v4 runtime."""

from __future__ import annotations

import hashlib
from typing import Any

from psycopg import sql
from psycopg.types.json import Jsonb

from mingjing_core.agent.prompts import PromptBundle
from mingjing_core.application.agent_case_capability import pin_case_effect_capability
from mingjing_core.application.agent_regeneration import lease_hash
from mingjing_core.application.agent_thread_scope import assert_thread
from mingjing_core.domain.contracts import LeaseConflict, ScopeError
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.timekit.clock import get_clock


class RuntimeState:
    def __init__(self, repo: PostgresRepository) -> None:
        self.repo = repo

    def authority(self, owner: str, ident: str, token: str) -> dict[str, Any]:
        with self.repo.transaction(owner) as connection:
            row = self.repo._run(self.repo._leased(connection, owner, ident, token))
            if row["runtime"] != "v4" or row["owner_user_id"] != owner:
                raise ScopeError("运行版本或所有者不符")
            if row["cancel_requested_at"] is not None:
                raise LeaseConflict("本轮已请求取消")
            if row["deadline_at"] is not None and row["deadline_at"] <= get_clock().now():
                raise LeaseConflict("本轮已超过执行时限")
            self.repo.assert_scope(owner, row["subject"])
            assert_thread(self.repo, row)
            return row

    def metadata(self, run: dict[str, Any], **values: Any) -> None:
        with self.repo.transaction(run["owner"]) as connection:
            row = self.repo._leased(connection, run["owner"], run["id"], run["lease_token"])
            if row["retry_epoch"] != run["retry_epoch"]:
                raise LeaseConflict("运行记录不属于当前批次")
            usage = dict(row["usage"])
            usage["agent_runtime"] = dict(usage.get("agent_runtime", {}), **values)
            connection.execute(
                sql.SQL("UPDATE {} SET usage=%s WHERE owner=%s AND id=%s").format(self.repo.table("core_runs")),
                (Jsonb(usage), run["owner"], run["id"]),
            )

    def pin(self, run: dict[str, Any], prompts: PromptBundle, system: str, *, crisis: bool) -> None:
        pin_case_effect_capability(self.repo, run)
        provenance = {
            name: {key: row[key] for key in ("version", "sha256")} for name, row in prompts.manifest["files"].items()
        }
        self.metadata(
            run,
            executor_lease_sha256=lease_hash(run["lease_token"]),
            prompt_versions=provenance,
            rendered_system_sha256=hashlib.sha256(system.encode()).hexdigest(),
            crisis=crisis,
        )

    def onboarding(self, run: dict[str, Any]) -> bool:
        with self.repo.transaction(run["owner"]) as connection:
            rows = connection.execute(
                sql.SQL(
                    "SELECT count(*) AS n FROM {} WHERE owner=%s AND kind='message' AND subject=%s "
                    "AND status='active' AND data->>'role'='user'"
                ).format(self.repo.table("core_entities")),
                (run["owner"], run["subject"]),
            ).fetchone()
        return rows["n"] <= 3
