"""Compare every native HTTP frame with the same owner's persisted P3 stream."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from psycopg import sql

from mingjing_core.agent.events import validate_event

RELATED = {"text_delta": "text.delta", "final": "run.completed"}


def persisted(repo: Any, owner: str, run_id: str) -> list[dict[str, Any]]:
    current = repo.fetch_run(owner, run_id)
    if current["owner"] != owner or current["runtime"] != "v4":
        raise ValueError("Offline stream must use its actual owner and v4 run")
    with repo.transaction(owner) as connection:
        rows = connection.execute(
            sql.SQL("SELECT seq,kind,payload FROM {} WHERE owner=%s AND run_id=%s ORDER BY seq").format(
                repo.table("core_run_events")
            ),
            (owner, run_id),
        ).fetchall()
    events = []
    for row in rows:
        value = validate_event(row["kind"], row["payload"])
        if value["seq"] != row["seq"] or value["run_id"] != run_id:
            raise ValueError("Persisted offline SSE native identity is inconsistent")
        events.append({"type": row["kind"], "data": value})
    return events


def fingerprint(event: dict[str, Any]) -> str:
    raw = json.dumps(event, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def check_complete(
    pg: list[dict[str, Any]], initial: list[dict[str, Any]], replay: list[dict[str, Any]], cursor: int
) -> dict[str, Any]:
    if not initial or initial[-1]["data"]["seq"] != cursor or initial[-1]["type"] != "text_delta":
        raise ValueError("Offline disconnect must follow an observed native text fragment")
    ids = [event["data"]["seq"] for event in pg]
    if not ids or ids != list(range(1, len(ids) + 1)):
        raise ValueError("Persisted offline SSE sequence is missing or repeated")
    observed = initial + replay
    if [fingerprint(event) for event in observed] != [fingerprint(event) for event in pg]:
        raise ValueError("Offline HTTP stream differs from its entire persisted native sequence")
    if any(event["data"]["seq"] <= cursor for event in replay):
        raise ValueError("Offline HTTP replay ignored the native Last-Event-ID")
    related = [event for event in pg if event["type"] in RELATED]
    if not related or related[-1]["type"] != "final" or sum(event["type"] == "final" for event in related) != 1:
        raise ValueError("Offline stream has no unique native final event")
    mapping = {event["data"]["seq"]: f"event-{index}" for index, event in enumerate(related, 1)}
    rows = [{"seq": event["data"]["seq"], "kind": event["type"], "sha256": fingerprint(event)} for event in pg]
    return {
        "received_event_ids": [mapping[event["data"]["seq"]] for event in related],
        "replayed_event_ids": [mapping[event["data"]["seq"]] for event in replay if event["type"] in RELATED],
        "native_pg_frames": rows,
        "native_initial_ids": [event["data"]["seq"] for event in initial],
        "native_replay_ids": [event["data"]["seq"] for event in replay],
        "native_last_event_id": cursor,
        "related_native_ids": list(mapping),
        "all_native_frames_verified": True,
        "events": [RELATED[event["type"]] for event in related],
        "scope": "offline real P3 loopback HTTP + PG; no P4 or live model claim",
    }
