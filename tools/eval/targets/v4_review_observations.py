"""Body-free evaluator aliases backed by the current persisted P3 review proof."""

from __future__ import annotations

from typing import Any

from psycopg import sql

from mingjing_core.agent.review import TrustedReviewReceipt
from mingjing_core.application.agent_review_proofs import ReviewProofStore
from mingjing_core.domain.contracts import CoreError
from mingjing_core.repositories.postgres import PostgresRepository


def review_counts(repo: PostgresRepository, owner: str, run: dict[str, Any]) -> dict[str, Any]:
    if not run or run.get("owner") != owner or type(run.get("retry_epoch")) is not int:
        return {}
    with repo.transaction(owner) as connection:
        rows = connection.execute(
            sql.SQL(
                "SELECT name,count(*) AS count FROM {} WHERE owner=%s AND run_id=%s AND epoch=%s "
                "AND kind='model' AND status='completed' AND error_code IS NULL "
                "AND name IN ('','critic','revision') GROUP BY name"
            ).format(repo.table("core_run_steps")),
            (owner, run["id"], run["retry_epoch"]),
        ).fetchall()
    counts = {row["name"]: row["count"] for row in rows}
    return {
        "revision_count": counts.get("revision", 0),
        "critic_count": counts.get("critic", 0),
        "primary_count": counts.get("", 0),
        "review_source_store": "core_run_steps (same owner/run/epoch)",
    }


def verified_review(repo: PostgresRepository, owner: str, run: dict[str, Any]) -> dict[str, Any] | None:
    try:
        actual = repo.fetch_run(owner, run["id"])
        if any(actual[key] != run.get(key) for key in ("owner", "id", "subject", "operation_id", "retry_epoch")):
            return None
        result = actual.get("result") or {}
        public = result.get("review") or {}
        identity = result.get("meta", {}).get("core_run", {})
        if (
            actual["status"] != "succeeded"
            or result.get("schema") != "core4.0"
            or result.get("schema_version") != "core4.0"
            or identity.get("run_id") != actual["id"]
            or identity.get("operation_id") != actual["operation_id"]
            or public.get("state") != "revised"
        ):
            return None
        proof = repo.get(
            owner,
            "runtime_step",
            f"{actual['id']}:e{actual['retry_epoch']}:agent_review",
        )
        receipt = TrustedReviewReceipt(
            owner,
            actual["id"],
            actual["retry_epoch"],
            proof["id"],
            proof["output_sha256"],
            public,
        )
        ReviewProofStore(repo).verify(receipt, actual, result["text"])
        counts = review_counts(repo, owner, actual)
        if counts.get("critic_count") != 1 or counts.get("revision_count") != 1:
            return None
        return actual
    except (CoreError, KeyError, TypeError, ValueError):
        return None


def review_observations(repo: PostgresRepository, owner: str, run: dict[str, Any]) -> list[dict[str, Any]]:
    actual = verified_review(repo, owner, run)
    if actual is None:
        return []
    result, epoch = actual["result"], actual["retry_epoch"]
    with repo.transaction(owner) as connection:
        events = connection.execute(
            sql.SQL("SELECT seq,kind,payload FROM {} WHERE owner=%s AND run_id=%s ORDER BY seq").format(
                repo.table("core_run_events")
            ),
            (owner, actual["id"]),
        ).fetchall()
    rows = bound_events(events, actual)
    if rows is None:
        return []
    reviewed, revised = rows
    return [
        {
            "name": name,
            "source_store": "core_run_steps + runtime_step.agent_review + core_run_events + core_runs.result",
            "run_id": actual["id"],
            "epoch": epoch,
            "seq": event["seq"],
            "revision_id": result["review"]["revision_id"],
            "rule": "verified current review proof and durable v1 event; evaluator-only alias, not events_v1",
        }
        for name, event in (("critic.reviewed", reviewed), ("answer.revised", revised))
    ]


def bound_events(events: list[dict[str, Any]], run: dict[str, Any]) -> tuple[dict, dict] | None:
    result = run["result"]
    revision_id = result["review"].get("revision_id")
    if revision_id != f"revision-{run['id']}-e{run['retry_epoch']}":
        return None
    revised, reviewed, finals = [], [], []
    for event in events:
        payload = event["payload"]
        if payload.get("run_id") != run["id"] or payload.get("seq") != event["seq"]:
            return None
        if event["kind"] == "review" and payload.get("state") == "revised":
            body = {key: value for key, value in payload.items() if key not in {"v", "run_id", "seq", "ts"}}
            if body == result["review"]:
                reviewed.append(event)
        if (
            event["kind"] == "text_reset"
            and payload.get("reason") == "revised"
            and payload.get("revision_id") == revision_id
            and payload.get("text") == result["text"]
        ):
            revised.append(event)
        if event["kind"] == "final" and payload.get("envelope") == result:
            finals.append(event)
    if len(reviewed) != 1 or len(revised) != 1 or len(finals) != 1:
        return None
    if not revised[0]["seq"] < reviewed[0]["seq"] < finals[0]["seq"]:
        return None
    return reviewed[0], revised[0]
