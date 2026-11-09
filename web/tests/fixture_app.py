"""Local frontend fixture: real v3 services/PG, scripted model, no delivery."""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from urllib.parse import urlparse

import uvicorn
from fastapi import Request
from fastapi.responses import StreamingResponse
from psycopg import sql
from psycopg.types.json import Jsonb

from mingjing_core.adapters.model import ConfiguredModel
from mingjing_core.adapters.web import create_app
from mingjing_core.application.consultation import ConsultationService
from mingjing_core.application.report_schedules import ReportScheduleService
from mingjing_core.repositories.postgres import PostgresRepository
from tests.test_core_pg_channels import FixtureModel
from web.tests.fixture_events import V2_EVENTS, V2_STARTED

DSN = os.environ.get(
    "FRONTEND_TEST_DSN", "postgresql://core_test@127.0.0.1:55480/core_test_fe"
)
parsed = urlparse(DSN)
if (
    parsed.hostname != "127.0.0.1"
    or parsed.port not in (55480, 55481)
    or parsed.path != "/core_test_fe"
):
    raise RuntimeError("Frontend fixtures require the isolated core_test_fe database")


def reject_real_model(*args, **kwargs):
    raise RuntimeError("Real model calls are forbidden in frontend fixtures")


ConfiguredModel.generate = reject_real_model


class FrontendModel(FixtureModel):
    def __init__(self):
        super().__init__()
        self.failures = 0
        self.delay = 0.0
        self.lock = threading.Lock()

    def generate(self, **kwargs):
        with self.lock:
            should_fail = (
                kwargs["purpose"] in ("synthesis", "repair") and self.failures > 0
            )
            if should_fail:
                self.failures -= 1
            delay = self.delay
        if delay:
            time.sleep(delay)
        if should_fail:
            raise TimeoutError("Scripted frontend fixture interruption")
        result = super().generate(**kwargs)
        if kwargs["purpose"] == "intake":
            text = kwargs["payload"]["reference_data"]["message"]
            if "喜欢" in text:
                result["output"]["proposals"] = [{"quote": text, "category": "偏好"}]
        return result


schema = "test_frontend_" + uuid.uuid4().hex[:16]
repo = PostgresRepository(DSN, schema=schema, max_size=4)
model = FrontendModel()
service = ConsultationService(repo, model=model)


def seed_owner(owner: str) -> None:
    """Give every browser test its own real, synthetic business scope."""
    repo.ensure_owner(owner)
    target = "ou_synthetic_" + owner.replace("-", "_")
    jobs = [
        {
            "id": "fixture-" + owner + "-" + kind,
            "kind": kind,
            "channel": "feishu",
            "target": target,
        }
        for kind in ("daily", "weekly", "monthly", "quarterly")
    ]
    with repo.transaction(owner) as connection:
        settings = repo.assert_scope(owner)["settings"]
        settings["report_pipeline"] = {
            "enabled": False,
            "jobs": jobs,
            "start_at": "2026-10-11T00:00:00+08:00",
        }
        connection.execute(
            sql.SQL("UPDATE {} SET settings=%s WHERE id=%s").format(
                repo.table("core_owners")
            ),
            (Jsonb(settings), owner),
        )
    for job in jobs:
        repo.bind_channel(owner, "report", job["id"], binding_kind="task")
    repo.bind_channel(owner, "feishu", target, binding_kind="user")
    ReportScheduleService(repo).seed_defaults(owner)

    source = service.memory.receive(
        owner,
        content="我喜欢清晨阅读，请记住",
        channel="synthetic",
        source_id="fixture-preference",
    )
    service.memory.save_fact(
        owner,
        "self",
        source["id"],
        source["content"],
        operation_id="fixture-preference",
    )
    service.memory.receive(
        owner,
        content="这是飞书上的合成历史。",
        channel="feishu",
        external_id=target,
        source_id="fixture-history",
        conversation_id="shared",
        at="2026-10-17T08:00:00+08:00",
    )


for owner in ("frontend-owner", "frontend-other"):
    seed_owner(owner)

app = create_app(service)
mock_connections = 0
mock_cursors: list[str] = []
token_owners_lock = threading.Lock()


@app.post("/__test__/owner")
async def new_test_owner():
    ident = uuid.uuid4().hex
    owner = "frontend-case-" + ident
    token = "synthetic-frontend-" + ident
    seed_owner(owner)
    with token_owners_lock:
        mappings = json.loads(os.environ.get("ZHIMING_TOKEN_OWNERS", "{}"))
        mappings[token] = owner
        os.environ["ZHIMING_TOKEN_OWNERS"] = json.dumps(mappings)
    return {"token": token}


@app.get("/__test__/metrics")
async def metrics():
    return {
        "database": "core_test_fe",
        "schema_prefix": "test_frontend_",
        "model": "scripted-only",
        "provider_calls": len(model.requests),
        "real_model_calls": 0,
        "v2_connections": mock_connections,
        "v2_cursors": mock_cursors,
    }


@app.post("/__test__/model-control")
async def model_control(request: Request):
    data = await request.json()
    with model.lock:
        model.failures = max(0, min(100, int(data.get("failures", 0))))
        model.delay = max(0, min(10, float(data.get("delay", 0))))
    return {"ok": True}


@app.get("/__test__/v2/runs/{ident}")
async def v2_run(ident: str):
    return {"id": ident, "status": "running"}


@app.get("/__test__/v2/runs/{ident}/events")
async def v2_events(ident: str, request: Request):
    global mock_connections
    mock_connections += 1
    cursor = request.headers.get("Last-Event-ID", "")
    mock_cursors.append(cursor)
    events = [("started", {"run_id": ident, **V2_STARTED}), *V2_EVENTS]
    start = int(cursor) if cursor.isdigit() else 0
    # Reconnect repeats the last event after the first stream ends early.
    chosen = (
        list(enumerate(events, 1))[max(0, start - 1) :]
        if start
        else list(enumerate(events, 1))[:4]
    )

    async def stream():
        for seq, (event, data) in chosen:
            payload = json.dumps(data, ensure_ascii=False)
            frame = f"id: {seq}\r\nevent: {event}\r\ndata: {payload}\r\n\r\n"
            encoded = frame.encode()
            middle = len(encoded) // 2
            yield encoded[:middle]
            yield encoded[middle:]

    return StreamingResponse(stream(), media_type="text/event-stream")


def serve():
    print(
        "Frontend fixture ready: localhost:8002 / core_test_fe / scripted model only",
        flush=True,
    )
    uvicorn.run(app, host="127.0.0.1", port=8002, log_level="warning", access_log=False)
