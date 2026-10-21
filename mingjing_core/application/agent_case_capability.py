"""Pin the new Case writer only before a fresh Runtime epoch has any frozen work."""

from typing import Any

from psycopg import sql
from psycopg.types.json import Jsonb

from mingjing_core.agent.journal import Journal
from mingjing_core.domain.case_effects import SCHEMA
from mingjing_core.domain.contracts import EvidenceError
from mingjing_core.repositories.postgres import fingerprint

KEY = "case_effect_capabilities"
CAPABILITY_SCHEMA = "agent-case-capability-v1"


def _identity(run: dict, epoch: int) -> dict[str, Any]:
    return {
        "schema": CAPABILITY_SCHEMA,
        "protocol": SCHEMA,
        "owner": run["owner"],
        "run_id": run["id"],
        "subject": run["subject"],
        "thread_id": run["thread_id"] or "life:" + run["subject"],
        "epoch": epoch,
    }


def case_effect_capability(run: dict) -> bool:
    meta = run["usage"].get("agent_runtime", {})
    if not isinstance(meta, dict):
        raise EvidenceError("事项写入能力元数据无效")
    pins = meta.get(KEY, {})
    if not isinstance(pins, dict):
        raise EvidenceError("事项写入能力凭据结构无效")
    for key, value in pins.items():
        if not isinstance(key, str) or not key.isdecimal() or str(int(key)) != key or int(key) > run["retry_epoch"]:
            raise EvidenceError("事项写入能力周期无效")
        expected = _identity(run, int(key))
        if not isinstance(value, dict) or fingerprint(value) != fingerprint(
            dict(expected, pin_sha256=fingerprint(expected))
        ):
            raise EvidenceError("事项写入能力凭据与受信身份不符")
    return str(run["retry_epoch"]) in pins


def _has_frozen_work(repo: Any, connection: Any, run: dict) -> bool:
    if run["state_version"]:
        return True
    step = connection.execute(
        sql.SQL("SELECT 1 FROM {} WHERE owner=%s AND run_id=%s AND epoch=%s LIMIT 1").format(
            repo.table("core_run_steps")
        ),
        (run["owner"], run["id"], run["retry_epoch"]),
    ).fetchone()
    snapshot = connection.execute(
        sql.SQL(
            "SELECT 1 FROM {} WHERE owner=%s AND kind='runtime_step' AND data->>'run_id'=%s "
            "AND data->>'epoch'=%s AND (data->>'stage' IN ('agent_initial_context','agent_model_request') "
            "OR data->>'schema' IN ('agent-initial-context-v1','agent-model-request-v1')) LIMIT 1"
        ).format(repo.table("core_entities")),
        (run["owner"], run["id"], str(run["retry_epoch"])),
    ).fetchone()
    return step is not None or snapshot is not None


def pin_case_effect_capability(repo: Any, run: dict) -> None:
    with repo.transaction(run["owner"]) as connection:
        current = repo._run(Journal(repo, run["owner"])._leased(connection, run))
        if case_effect_capability(current) or _has_frozen_work(repo, connection, current):
            return
        usage = dict(current["usage"])
        meta = dict(usage.get("agent_runtime", {}))
        value = _identity(current, current["retry_epoch"])
        pins = dict(meta.get(KEY, {}), **{str(current["retry_epoch"]): dict(value, pin_sha256=fingerprint(value))})
        usage["agent_runtime"] = dict(meta, **{KEY: pins})
        connection.execute(
            sql.SQL("UPDATE {} SET usage=%s WHERE owner=%s AND id=%s").format(repo.table("core_runs")),
            (Jsonb(usage), current["owner"], current["id"]),
        )
