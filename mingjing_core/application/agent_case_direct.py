"""Recognize an unversioned trusted tool component without granting own-write credit."""

from __future__ import annotations

from typing import Any

from psycopg import sql


def unversioned_direct_component(repo: Any, connection: Any, run: dict) -> bool:
    # A real Runtime keeps at least one of these independent witnesses. Deleted
    # snapshots and older epochs still count; losing a model proof cannot opt out.
    if run["state_version"] or "agent_runtime" in run["usage"]:
        return False
    model = connection.execute(
        sql.SQL("SELECT 1 FROM {} WHERE owner=%s AND run_id=%s AND kind='model' LIMIT 1").format(
            repo.table("core_run_steps")
        ),
        (run["owner"], run["id"]),
    ).fetchone()
    snapshot = connection.execute(
        sql.SQL(
            "SELECT 1 FROM {} WHERE owner=%s AND kind='runtime_step' AND data->>'run_id'=%s "
            "AND (data->>'stage' IN ('agent_initial_context','agent_model_request') "
            "OR data->>'schema' IN ('agent-initial-context-v1','agent-model-request-v1')) LIMIT 1"
        ).format(repo.table("core_entities")),
        (run["owner"], run["id"]),
    ).fetchone()
    return model is None and snapshot is None
