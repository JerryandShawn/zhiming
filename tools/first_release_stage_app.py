"""F-only health/state/history host: real Core/Agent dependencies, no provider or background execution."""

from __future__ import annotations

import json
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

ROOT = Path(__file__).absolute().parents[1]
if __package__ in {None, ""}:
    if sys.flags.isolated != 1:
        raise SystemExit("STAGE_ISOLATED_ENTRY_REQUIRED")
    sys.path.insert(0, str(ROOT))

from fastapi import FastAPI, Request  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from psycopg.conninfo import conninfo_to_dict  # noqa: E402

from mingjing_core.adapters.web import create_app  # noqa: E402
from mingjing_core.agent.context_k3 import K3EstimatedMeter  # noqa: E402
from mingjing_core.agent.k3_loader import load_k3_counter  # noqa: E402
from mingjing_core.application.agent_runtime import AgentRuntime  # noqa: E402
from mingjing_core.application.consultation import ConsultationService  # noqa: E402
from mingjing_core.domain.consultation import ModelUnavailable  # noqa: E402
from mingjing_core.models.port import ModelPort  # noqa: E402
from mingjing_core.repositories.postgres import PostgresRepository  # noqa: E402
from mingjing_core.runtime import LangGraphRuntime  # noqa: E402
from tools.first_release_contracts import RestoreRejected, ordinary, require  # noqa: E402
from tools.first_release_hermes_entry import _private_read  # noqa: E402
from tools.first_release_native_exchange import Scope  # noqa: E402
from tools.first_release_restore import SafeParser  # noqa: E402
from tools.first_release_writer_fence import file_lock, pg_lock  # noqa: E402


class NoStageModel(ModelPort):
    model = "stage-model-access-disabled"

    def stream(self, messages, **kwargs):
        raise ModelUnavailable("首发副本演练禁止模型请求")

    def generate(self, **kwargs):
        raise ModelUnavailable("首发副本演练禁止模型请求")


def _identity(repo: PostgresRepository, scope: Scope, expected_oid: int) -> None:
    fields = conninfo_to_dict(repo.dsn)
    require(
        set(fields) <= {"host", "port", "dbname", "user", "password", "connect_timeout"}
        and fields.get("dbname") == scope.original
        and fields.get("host") in {"127.0.0.1", "::1"}
        and fields.get("port") in ({"55480", "55481"} if scope.local_drill else {"5432"})
        and fields.get("user") == scope.original + "_writer",
        "STAGE_RUNTIME_DSN_SCOPE",
    )
    with repo.connection() as connection:
        row = connection.execute(
            "SELECT current_database() AS database,current_user AS role,session_user AS login,"
            "host(inet_server_addr()) AS host,inet_server_port() AS port,d.oid,"
            "current_setting('server_version_num')::int AS version,"
            "r.rolsuper,r.rolinherit,r.rolcreatedb,r.rolcreaterole,r.rolreplication,r.rolbypassrls,"
            "EXISTS(SELECT 1 FROM pg_auth_members WHERE member=r.oid) AS member "
            "FROM pg_database d,pg_roles r WHERE d.datname=current_database() AND r.rolname=current_user"
        ).fetchone()
        require(
            row["database"] == scope.original
            and row["role"] == row["login"] == fields["user"]
            and row["host"] == fields["host"]
            and row["port"] == int(fields["port"])
            and row["oid"] == expected_oid
            and 150000 <= row["version"] < 160000
            and not any(
                row[key]
                for key in (
                    "rolsuper",
                    "rolinherit",
                    "rolcreatedb",
                    "rolcreaterole",
                    "rolreplication",
                    "rolbypassrls",
                    "member",
                )
            ),
            "STAGE_RUNTIME_ACTUAL_IDENTITY",
        )
        require(
            not connection.execute(
                "SELECT EXISTS(SELECT 1 FROM mingjing_core.core_runs WHERE status IN ('queued','running')) AS pending"
            ).fetchone()["pending"],
            "STAGE_PENDING_RUNS_REQUIRE_REVIEW",
        )
    repo.verify_schema()


def stage_app(repo: PostgresRepository, scope: Scope, expected_oid: int, workspace: Path, tokenizer: Path) -> FastAPI:
    scope.validate()
    require(scope.local_drill or os.name == "posix", "STAGE_FORMAL_POSIX_REQUIRED")
    ordinary(workspace, directory=True)
    require(
        scope.local_drill or workspace == Path("/root/zhiming-core-fr-stage/operations") / scope.operation,
        "STAGE_DEDICATED_WORKSPACE_REQUIRED",
    )
    app = FastAPI(title="首发副本：无模型健康验证")

    @asynccontextmanager
    async def lifespan(application):
        try:
            with file_lock(workspace / "writer.lock", exclusive=False, existing_only=True):
                require(not os.path.lexists(workspace / "maintenance.json"), "STAGE_MAINTENANCE_CLOSED")
                _identity(repo, scope, expected_oid)
                with repo.pool.connection() as held, pg_lock(held, "fr-stage-runtime", exclusive=False):
                    meter = K3EstimatedMeter(load_k3_counter(tokenizer), model="k3.1-pro")
                    require(meter.live_admissible, "STAGE_PUBLIC_TOKENIZER_REQUIRED")
                    disabled = NoStageModel()
                    agent = AgentRuntime(repo, disabled, meter, offline=False)
                    service = ConsultationService(
                        repo, model=disabled, runtime=LangGraphRuntime(repo, initialize=False), agent_runtime=agent
                    )
                    application.state.service = service
                    # Mounted apps do not run their lifespans: no legacy queue, dispatcher, privacy or report worker.
                    application.mount("/", create_app(service))
                    yield
        finally:
            repo.close()

    app.router.lifespan_context = lifespan

    @app.middleware("http")
    async def restrict(request: Request, call_next):
        if os.path.lexists(workspace / "maintenance.json"):
            return JSONResponse({"detail": "演练维护门已关闭"}, status_code=503)
        if request.method != "GET" or request.url.path not in {"/api/health", "/api/state", "/api/history"}:
            return JSONResponse({"detail": "副本演练仅开放健康、状态和历史读取"}, status_code=403)
        return await call_next(request)

    return app


def main(argv: list[str] | None = None) -> int:
    parser = SafeParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--env-file", type=Path, required=True)
    try:
        args = parser.parse_args(argv)
        require(os.name == "posix" and sys.flags.isolated == 1, "STAGE_FORMAL_ISOLATED_POSIX_REQUIRED")
        value = json.loads(_private_read(args.env_file))
        require(
            set(value) == {"dsn", "token", "operation", "database_oid", "workspace", "tokenizer"},
            "STAGE_RUNTIME_CONFIG_FIELDS",
        )
        require(isinstance(value["token"], str) and len(value["token"]) >= 32, "STAGE_PRIVATE_TOKEN_REQUIRED")
        # Providers, proxies, traces and old application/central configuration never reach the stage process.
        retained = {key: os.environ[key] for key in ("PATH", "HOME", "LANG", "LC_ALL", "TZ") if key in os.environ}
        os.environ.clear()
        os.environ.update(
            retained,
            MINGJING_TOKEN=value["token"],
            MINGJING_OWNER_ID="primary",
            LANGSMITH_TRACING="false",
            LANGCHAIN_TRACING_V2="false",
            OTEL_SDK_DISABLED="true",
            FEISHU_ENABLED="false",
            CORE_FEISHU_ENABLED="false",
        )
        repo = PostgresRepository(value["dsn"], initialize=False, max_size=3, max_running=3)
        app = stage_app(
            repo, Scope(value["operation"]), value["database_oid"], Path(value["workspace"]), Path(value["tokenizer"])
        )
        import uvicorn

        uvicorn.run(app, host="127.0.0.1", port=8788, access_log=False, log_level="warning")
    except RestoreRejected as error:
        print(json.dumps({"status": "blocked", "code": str(error), "automatic_retry": False}))
        return 2
    except Exception:
        print(json.dumps({"status": "blocked", "code": "STAGE_HOST_STOP_PRESERVE_ALL", "automatic_retry": False}))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
