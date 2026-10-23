"""Command and pinning contracts only; these tests do not establish Linux PG success."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools.b1_linux_drill import MIGRATION8_SHA256, ledger_compatibility, plan, restore
from tools.b1_linux_drill_sql import migrations
from tools.b1_linux_drill_transport import (
    CONTAINER,
    CONTEXT,
    LABEL,
    PIPE,
    PORT,
    VOLUMES,
    DrillBlocked,
    LocalDocker,
)
from tools.core_incremental_contracts import MIGRATIONS, TARGET


def response(value: object, code: int = 0) -> SimpleNamespace:
    return SimpleNamespace(
        returncode=code, stdout=json.dumps(value).encode(), stderr=b"private-value"
    )


def test_plan_does_not_use_a_docker_runner(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("plan must not create a transport")

    monkeypatch.setattr(subprocess, "run", forbidden)
    value = plan()
    assert value["target"] == TARGET and value["b1_migrations"] == list(range(1, 8))
    assert (
        value["model_calls"]
        == value["server_connections"]
        == value["external_sends"]
        == 0
    )
    assert value["ledger_0008"] == "separate-compatibility-only-not-in-B1"


@pytest.mark.parametrize("endpoint", ["ssh://server", "tcp://127.0.0.1:2375"])
def test_nonlocal_context_is_rejected(endpoint: str) -> None:
    calls = []

    def runner(command: list[str], **kwargs: object) -> SimpleNamespace:
        calls.append(command)
        return response([{"Endpoints": {"docker": {"Host": endpoint}}}])

    docker = LocalDocker(runner)
    with pytest.raises(DrillBlocked, match="DOCKER_CONTEXT_NOT_LOCAL"):
        docker.verify_local()
    assert len(calls) == 1 and not docker.ready
    assert calls[0] == ["docker", "--host", PIPE, "context", "inspect", CONTEXT]


@pytest.mark.parametrize("server", [None, {"Os": "windows", "Version": "29"}])
def test_no_linux_server_is_not_a_pass(server: object) -> None:
    replies = iter(
        [response([{"Endpoints": {"docker": {"Host": PIPE}}}]), response(server)]
    )
    docker = LocalDocker(lambda *args, **kwargs: next(replies))
    with pytest.raises(DrillBlocked, match="LINUX_ENGINE_REQUIRED"):
        docker.verify_local()
    assert not docker.ready


def test_runner_is_fixed_to_local_pipe_and_strips_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("KIMI_API_KEY", "private-value")
    monkeypatch.setenv("DATABASE_URL", "private-value")
    captured = {}

    def runner(command: list[str], **kwargs: object) -> SimpleNamespace:
        captured.update(command=command, **kwargs)
        return response({}, 1)

    with pytest.raises(DrillBlocked) as caught:
        LocalDocker(runner).call(["version"])
    assert str(caught.value) == "DOCKER_COMMAND_FAILED"
    assert (
        "KIMI_API_KEY" not in captured["env"] and "DATABASE_URL" not in captured["env"]
    )
    assert captured["env"]["LANGSMITH_TRACING"] == "false"
    assert captured["command"][:3] == ["docker", "--host", PIPE]


def test_timeout_does_not_print_private_output() -> None:
    def runner(*args: object, **kwargs: object) -> None:
        raise subprocess.TimeoutExpired("docker", 3, output=b"private-value")

    with pytest.raises(DrillBlocked, match="^DOCKER_COMMAND_TIMEOUT$"):
        LocalDocker(runner).call(["version"])


@pytest.mark.parametrize(
    "digest", [[], ["postgres@sha256:abc"], ["other@sha256:" + "a" * 64]]
)
def test_official_image_requires_exact_digest(digest: list[str]) -> None:
    docker = LocalDocker(
        lambda *args, **kwargs: response(
            [{"RepoDigests": digest, "Os": "linux", "Id": "id"}]
        )
    )
    docker.ready = True
    with pytest.raises(DrillBlocked, match="POSTGRES_IMAGE_DIGEST_REQUIRED"):
        docker.image(pull=False)


def test_unknown_existing_resource_is_retained() -> None:
    calls = []

    def runner(command: list[str], **kwargs: object) -> SimpleNamespace:
        calls.append(command)
        if "ls" in command:
            return SimpleNamespace(returncode=0, stdout=CONTAINER.encode())
        return response([{"Config": {"Labels": {LABEL: "someone-else"}}}])

    with pytest.raises(DrillBlocked, match="EXISTING_RESOURCE_NOT_OWNED"):
        LocalDocker(runner).inspect_optional("container", CONTAINER)
    assert len(calls) == 2 and all(
        "rm" not in call and "stop" not in call for call in calls
    )


@pytest.mark.parametrize(
    "database,role",
    [("zhiming_core_live", "b1_drill_admin"), ("core_test_b1", "postgres")],
)
def test_sql_rejects_out_of_scope_target_before_runner(
    database: str, role: str
) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("transport must not execute")

    with pytest.raises(DrillBlocked):
        LocalDocker(forbidden).sql(database, "SELECT 1", role=role)


def test_psql_runs_inside_private_container_with_no_dsn() -> None:
    captured = {}

    def runner(command: list[str], **kwargs: object) -> SimpleNamespace:
        captured.update(command=command, **kwargs)
        return SimpleNamespace(returncode=0, stdout=b"15\n")

    docker = LocalDocker(runner)
    docker.ready = True
    assert docker.sql("b1_drill_control", "SELECT 15") == "15"
    assert (
        "--host=127.0.0.1" in captured["command"] and CONTAINER in captured["command"]
    )
    assert (
        "--set=ON_ERROR_STOP=1" in captured["command"]
        and captured["input"] == b"SELECT 15"
    )
    assert not any("postgresql://" in argument for argument in captured["command"])


def test_readiness_is_bounded_and_does_not_restart_container() -> None:
    calls = []
    docker = LocalDocker(
        lambda command, **kwargs: (calls.append(command), response({}, 1))[1]
    )
    docker.ready = True
    sleeps = []
    with pytest.raises(DrillBlocked, match="POSTGRES_STARTUP_NOT_READY"):
        docker.wait_postgres(sleeps.append)
    assert len(calls) == 10 and sleeps == [1] * 9
    assert all(
        "pg_isready" in command and "restart" not in command for command in calls
    )


def test_b1_git_source_is_exactly_seven_pinned_migrations() -> None:
    rows = migrations(Path(__file__).resolve().parents[1])
    assert {str(row["number"]): row["sha256"] for row in rows} == MIGRATIONS
    assert all("core_model_usage" not in row["source"] for row in rows)


def test_changed_p1b_0008_is_rejected_before_sql(tmp_path: Path) -> None:
    source = tmp_path / "0008_model_usage.sql"
    source.write_text("SELECT 1;", encoding="utf-8")
    assert len(MIGRATION8_SHA256) == 64
    with pytest.raises(DrillBlocked, match="P1B_LEDGER_HASH_MISMATCH"):
        ledger_compatibility(None, source)  # type: ignore[arg-type]


def test_restore_cannot_target_live() -> None:
    with pytest.raises(DrillBlocked, match="RESTORE_TARGET_NOT_ISOLATED"):
        restore(None, "zhiming_core_live", "/b1/synthetic.dump")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "change,code",
    [
        ({"Image": "other"}, "DRILL_CONTAINER_IMAGE_CHANGED"),
        ({"Mounts": []}, "DRILL_VOLUME_MOUNTS_CHANGED"),
        ({"State": {"Running": False}}, "DRILL_CONTAINER_NOT_RUNNING"),
        ({"HostConfig": {"PortBindings": {}}}, "LOOPBACK_PORT_REQUIRED"),
    ],
)
def test_retained_container_cannot_change_scope(change: dict, code: str) -> None:
    value = {
        "State": {"Running": True},
        "Image": "expected",
        "HostConfig": {
            "PortBindings": {
                "5432/tcp": [{"HostIp": "127.0.0.1", "HostPort": str(PORT)}]
            },
            "Privileged": False,
            "NetworkMode": "bridge",
        },
        "Mounts": [
            {
                "Type": "volume",
                "Name": VOLUMES[0],
                "Destination": "/var/lib/postgresql/data",
            },
            {"Type": "volume", "Name": VOLUMES[1], "Destination": "/b1"},
        ],
    }
    value.update(change)
    with pytest.raises(DrillBlocked, match=code):
        LocalDocker.validate_container(value, {"id": "expected"})
