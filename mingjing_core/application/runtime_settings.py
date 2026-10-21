"""Change routing only, under the same owner lock used by run submission."""

from __future__ import annotations

import re
from typing import Any

from psycopg import sql
from psycopg.types.json import Jsonb

from mingjing_core.application.thread_queue import owner_runtime
from mingjing_core.domain.contracts import EvidenceError, RevisionConflict, ScopeError

OPERATION = "runtime-settings-v1"


def verify_local_identity(repo: Any, expected: dict[str, str]) -> None:
    with repo.transaction() as connection:
        row = connection.execute(
            "SELECT current_setting('server_version_num')::int AS version, "
            "host(inet_server_addr()) AS address, inet_server_port() AS port, "
            "current_database() AS database, current_user AS role"
        ).fetchone()
    if (
        not 150000 <= row["version"] < 160000
        or row["address"] not in {"127.0.0.1", "::1"}
        or row["database"] != expected["dbname"]
        or row["role"] != expected["user"]
        or row["port"] != int(expected["port"])
    ):
        raise EvidenceError("实际数据库身份不符合本机隔离 PostgreSQL 15 约束")
    repo.verify_schema()


class RuntimeSettingsService:
    def __init__(self, repo: Any) -> None:
        self.repo = repo

    def preview(self, owner: str, runtime: str) -> dict[str, Any]:
        self._validate(owner, runtime)
        with self.repo.transaction() as connection:
            connection.execute(
                "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
            )
            settings = self._settings(connection, owner)
            current = owner_runtime(settings)
        return self._receipt(
            current,
            runtime,
            mode="dry-run",
            changed=False,
            would_change=current != runtime,
            original_changed=False,
            replayed=False,
            current_runtime=current,
        )

    def apply(
        self, owner: str, runtime: str, *, expected_runtime: str, request_id: str
    ) -> dict[str, Any]:
        self._validate(owner, runtime)
        if not isinstance(expected_runtime, str) or expected_runtime not in {
            "v3",
            "v4",
        }:
            raise EvidenceError("必须指定有效的旧运行时")
        if (
            not isinstance(request_id, str)
            or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,199}", request_id) is None
        ):
            raise EvidenceError("必须指定有效的稳定请求标识")
        payload = {"runtime": runtime, "expected_runtime": expected_runtime}
        with self.repo.transaction(owner) as connection:
            current = owner_runtime(self._settings(connection, owner, lock=True))
            previous = connection.execute(
                sql.SQL(
                    "SELECT 1 FROM {} WHERE owner=%s "
                    "AND operation=%s AND request_key=%s"
                ).format(self.repo.table("core_mutation_requests")),
                (owner, OPERATION, request_id),
            ).fetchone()
            stored = self.repo.mutation_request(
                owner,
                OPERATION,
                request_id,
                payload,
                lambda: self._change(connection, owner, runtime, expected_runtime),
            )
        before, after = stored["ids"]
        return self._receipt(
            before,
            after,
            mode="apply",
            changed=stored["enabled"] and not previous,
            original_changed=stored["enabled"],
            replayed=bool(previous),
            current_runtime=current if previous else after,
        )

    def _change(
        self, connection: Any, owner: str, runtime: str, expected: str
    ) -> dict[str, Any]:
        current = owner_runtime(self._settings(connection, owner, lock=True))
        if current != expected:
            raise RevisionConflict("运行时旧值已改变，请重新预览")
        changed = current != runtime
        if changed:
            connection.execute(
                sql.SQL(
                    "UPDATE {} SET "
                    "settings=jsonb_set(settings,ARRAY['runtime'],%s,true) "
                    "WHERE id=%s"
                ).format(self.repo.table("core_owners")),
                (Jsonb(runtime), owner),
            )
        return {
            "status": "updated" if changed else "unchanged",
            "ids": [current, runtime],
            "enabled": changed,
        }

    def _settings(
        self, connection: Any, owner: str, *, lock: bool = False
    ) -> dict[str, Any]:
        query = sql.SQL(
            "SELECT o.settings FROM {} o JOIN {} s ON s.owner=o.id "
            "WHERE o.id=%s AND s.id='self' AND s.consent='granted'"
        ).format(self.repo.table("core_owners"), self.repo.table("core_subjects"))
        if lock:
            query += sql.SQL(" FOR UPDATE OF o")
        row = connection.execute(query, (owner,)).fetchone()
        if row is None:
            raise ScopeError("目标用户不存在或未获授权")
        settings = row["settings"]
        if not isinstance(settings, dict):
            raise EvidenceError("持久用户设置无效")
        return settings

    @staticmethod
    def _validate(owner: str, runtime: str) -> None:
        if not isinstance(owner, str) or not owner.strip() or len(owner) > 200:
            raise ScopeError("必须指定有效的用户标识")
        if not isinstance(runtime, str) or runtime not in {"v3", "v4"}:
            raise EvidenceError("运行时只允许 v3 或 v4")

    @staticmethod
    def _receipt(before: str, after: str, **fields: Any) -> dict[str, Any]:
        return {
            "schema_version": "runtime-switch-v1",
            "old_runtime": before,
            "new_runtime": after,
            **fields,
        }
