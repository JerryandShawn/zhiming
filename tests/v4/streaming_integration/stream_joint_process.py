"""Fresh process executes one real offline Runtime; no credentials enter stdout."""

from __future__ import annotations

import json
import os
import re
import sys
import traceback
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from mingjing_core.application.run_event_stream_worker import StreamWorker
from mingjing_core.repositories.postgres import PostgresRepository
from tests.v4.streaming_integration.stream_joint_http_support import JointPort, joint_service
from tools.eval.targets.local_db import local_dsn, verify_local_postgres

PHASE = "input"
ACTOR_FAILURES = []


def main() -> None:
    global PHASE
    value = json.load(sys.stdin)
    if set(value) != {"dsn", "schema", "ident", "provider"} or not re.fullmatch(
        r"p2_test_[0-9a-f]{32}", value["schema"]
    ):
        raise ValueError("invalid isolated joint input")
    url = urlsplit(value["provider"])
    if url.scheme != "http" or url.hostname != "127.0.0.1" or not url.port or url.username or url.password:
        raise ValueError("invalid synthetic provider target")
    if url.path not in {"", "/"} or url.query or url.fragment:
        raise ValueError("invalid synthetic provider path")
    if any(name.startswith("PG") or name.upper().endswith("_PROXY") for name in os.environ):
        raise ValueError("implicit routing is forbidden")
    dsn = local_dsn(value["dsn"])
    PHASE = "verify_db"
    verify_local_postgres(dsn)
    original_init, original_send = httpx.Client.__init__, httpx.Client.send

    def direct(self, *args, **kwargs):
        kwargs["trust_env"] = False
        original_init(self, *args, **kwargs)

    def local_only(self, request, *args, **kwargs):
        if request.url.host != "127.0.0.1" or request.url.scheme != "http":
            raise AssertionError("synthetic process permits only loopback HTTP")
        return original_send(self, request, *args, **kwargs)

    httpx.Client.__init__, httpx.Client.send = direct, local_only
    original_fail = StreamWorker._fail

    def failed(worker):
        error = sys.exception()
        if error is not None:
            ACTOR_FAILURES.append(
                {
                    "type": type(error).__name__,
                    "frames": [
                        (Path(row.filename).name, row.name, row.lineno)
                        for row in traceback.extract_tb(error.__traceback__)
                    ],
                }
            )
        original_fail(worker)

    StreamWorker._fail = failed
    PHASE = "repository"
    repo = PostgresRepository(dsn, schema=value["schema"], initialize=False)
    try:
        run = repo.fetch_run("alice", value["ident"])
        if run["runtime"] != "v4" or run["status"] != "queued":
            raise ValueError("child requires its isolated queued v4 run")
        port = JointPort(value["provider"])
        PHASE = "assembly"
        service = joint_service(repo, port)
        PHASE = "execute"
        result = service.execute("alice", run["id"])
        print(json.dumps({"succeeded": result["schema_version"] == "core4.0", "physical_requests": port.request_count}))
    finally:
        repo.close()


if __name__ == "__main__":
    try:
        main()
    except BaseException as error:
        print(
            json.dumps({"failed": True, "phase": PHASE, "error_type": type(error).__name__, "actors": ACTOR_FAILURES})
        )
        raise SystemExit(1) from None
