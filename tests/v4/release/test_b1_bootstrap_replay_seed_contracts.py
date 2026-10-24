from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from tools.b1_bootstrap_replay_fixture import DSN_ENV, SeedBlocked, SeedRequest
from tools.b1_bootstrap_replay_seed import environment, main, run_worker


def request() -> SeedRequest:
    return SeedRequest("b1-seed-synthetic-operation", "seed", Path.cwd(), Path(sys.executable).resolve())


def test_default_is_pure_plan_without_database_or_candidate(monkeypatch, capsys):
    monkeypatch.delenv(DSN_ENV, raising=False)
    monkeypatch.setattr("psycopg.connect", lambda *args, **kwargs: pytest.fail("default must not connect"))
    assert main([]) == 0
    value = json.loads(capsys.readouterr().out)
    assert value["database_connections"] == value["models"] == value["sends"] == 0
    assert value["admissible"] is False


@pytest.mark.parametrize(
    "field,value,code",
    [
        ("operation_id", "wrong", "SEED_OPERATION_ID"),
        ("phase", "migrate", "SEED_PHASE"),
        ("candidate_source", Path("relative"), "SEED_ABSOLUTE_PATH"),
    ],
)
def test_bad_static_request_does_not_connect(field, value, code):
    with pytest.raises(SeedBlocked, match=code):
        replace(request(), **{field: value}).validate()


@pytest.mark.parametrize(
    "change,code",
    [
        ({"host": "example.invalid"}, "LOOPBACK"),
        ({"hostaddr": "127.0.0.2"}, "HOSTADDR"),
        ({"dbname": "zhiming_core_stage"}, "RANDOM_DATABASE"),
        ({"user": "postgres"}, "ROLE"),
        ({"port": "5432"}, "PORT"),
        ({"options": "-c search_path=public"}, "OPTIONS"),
        ({"passfile": "/arbitrary"}, "OPTIONS"),
    ],
)
def test_dsn_scope_is_explicit_random_and_local(monkeypatch, change, code):
    from psycopg.conninfo import make_conninfo

    fields = {
        "host": "127.0.0.1",
        "port": "55480",
        "dbname": "b1_application_" + "a" * 32,
        "user": "b1_application_" + "a" * 32 + "_owner",
    }
    monkeypatch.setenv(DSN_ENV, make_conninfo(**dict(fields, **change)))
    with pytest.raises(SeedBlocked, match=code):
        request().dsn()


def test_environment_drops_provider_credentials_and_implicit_pg(monkeypatch):
    database = "b1_application_" + "a" * 32
    monkeypatch.setenv(DSN_ENV, f"host=127.0.0.1 port=55480 dbname={database} user={database}_owner")
    monkeypatch.setenv("KIMI_API_KEY", "synthetic-never-send")
    monkeypatch.setenv("MINGJING_TOKEN", "synthetic-never-send")
    values = environment(request())
    assert "KIMI_API_KEY" not in values and "MINGJING_TOKEN" not in values
    assert values["LANGSMITH_TRACING"] == values["CORE_FEISHU_ENABLED"] == "false"
    monkeypatch.setenv("PGHOSTADDR", "127.0.0.2")
    with pytest.raises(SeedBlocked, match="IMPLICIT_PG_ENV"):
        request().dsn()


def test_module_cli_default_no_ambient_pg_or_source(tmp_path):
    env = {key: os.environ[key] for key in ("PATH", "SystemRoot", "WINDIR", "TEMP", "TMP") if key in os.environ}
    root = Path(__file__).resolve().parents[3]
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            "-X",
            "pycache_prefix=" + os.path.abspath(os.devnull),
            "-m",
            "tools.b1_bootstrap_replay_seed",
        ],
        cwd=root,
        env=env,
        capture_output=True,
        check=False,
        encoding="utf-8",
        timeout=15,
    )
    assert result.returncode == 0
    assert json.loads(result.stdout)["database_connections"] == 0


def test_worker_has_isolation_and_no_readable_candidate_bytecode_prefix(monkeypatch):
    database = "b1_application_" + "a" * 32
    monkeypatch.setenv(DSN_ENV, f"host=127.0.0.1 port=55480 dbname={database} user={database}_owner")
    monkeypatch.setattr("tools.b1_bootstrap_replay_seed.verify_candidate", lambda source: None)
    captured = {}

    def denied_process(arguments, **options):
        captured.update(arguments=arguments, options=options)
        return subprocess.CompletedProcess(arguments, 2, "", '{"code":"SEED_SYNTHETIC_STOP"}')

    monkeypatch.setattr("tools.b1_bootstrap_replay_seed.subprocess.run", denied_process)
    with pytest.raises(SeedBlocked, match="SYNTHETIC_STOP"):
        run_worker(request())
    assert captured["arguments"][1:5] == ["-I", "-B", "-X", "pycache_prefix=" + os.path.abspath(os.devnull)]
    assert "KIMI_API_KEY" not in captured["options"]["env"]
