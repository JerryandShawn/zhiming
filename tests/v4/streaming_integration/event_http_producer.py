"""A fresh Python process executes the actual leased M1 event writer, not the hub."""

from __future__ import annotations

import json
import sys

from psycopg import sql

from mingjing_core.application.agent_runtime_events import RuntimeEvents
from mingjing_core.repositories.postgres import PostgresRepository
from tools.eval.targets.local_db import local_dsn, verify_local_postgres


def main() -> None:
    value = json.load(sys.stdin)
    dsn = local_dsn(value["dsn"])
    verify_local_postgres(dsn)
    assert value["schema"].startswith("p2_test_") and len(value["schema"]) == 40
    repo = PostgresRepository(dsn, schema=value["schema"], initialize=False)
    try:
        run = repo.fetch_run(value["owner"], value["ident"])
        assert run["runtime"] == "v4" and run["status"] == "running"
        events = RuntimeEvents(repo, run, None)
        with repo.transaction(run["owner"]):
            events.send(
                "started",
                dict(
                    thread_id=run["thread_id"],
                    message_id=run["request"]["source_message_id"],
                    incognito=False,
                ),
            )
            events.send("text_delta", {"text": value["text"]})
        with repo.transaction(run["owner"]) as connection:
            rows = connection.execute(
                sql.SQL(
                    "SELECT seq FROM {} WHERE owner=%s AND run_id=%s ORDER BY seq"
                ).format(repo.table("core_run_events")),
                (run["owner"], run["id"]),
            ).fetchall()
        print(
            json.dumps(
                {
                    "seqs": [row["seq"] for row in rows],
                    "producer": "actual-leased-runtime-events",
                }
            )
        )
    finally:
        repo.close()


if __name__ == "__main__":
    main()
