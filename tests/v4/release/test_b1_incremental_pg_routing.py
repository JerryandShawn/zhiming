"""Pre-connect libpq routing contracts; physical PG and child processes are forbidden."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from tools import core_incremental_pg as pg
from tools.core_incremental_contracts import EXPECTED_MANIFEST, STAGE_UNITS, Request, UpgradeRejected


@dataclass
class Boundary:
    calls: list[tuple[list[str], dict[str, Any]]] = field(default_factory=list)
    connections: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    def run(self, args: list[str], **kwargs: Any) -> bytes:
        self.calls.append((args, kwargs))
        return b"{}"

    def connect(self, dsn: str, **kwargs: Any) -> object:
        self.connections.append((dsn, kwargs))
        return object()


@pytest.fixture
def controlled(monkeypatch: pytest.MonkeyPatch) -> tuple[Request, Boundary]:
    for key in pg.IMPLICIT_PG_ENV:
        monkeypatch.delenv(key, raising=False)
    request = Request(
        "b1-controlled-routing",
        "stage",
        "synthetic-host",
        EXPECTED_MANIFEST,
        "a" * 64,
        ("primary",),
        8 * 1024**3,
        dict.fromkeys(STAGE_UNITS, "a" * 64),
        "",
    )
    for role in ("owner", "writer"):
        monkeypatch.setenv("CORE_INCREMENTAL_" + role.upper() + "_DSN", dsn(request, role))
    for name in ("tools.core_incremental_pg.connect", "subprocess.run", "socket.create_connection"):
        monkeypatch.setattr(name, lambda *args, **kwargs: pytest.fail("physical boundary escaped"))
    return request, Boundary()


def dsn(request: Request, role: str, **changes: str) -> str:
    return make_conninfo(host="127.0.0.1", dbname=request.database, user=request.database + "_" + role, **changes)


def port(controlled: tuple[Request, Boundary]) -> pg.PostgresPort:
    request, boundary = controlled
    return pg.PostgresPort(request, boundary, connector=boundary.connect)


@pytest.mark.parametrize("key", pg.IMPLICIT_PG_ENV)
def test_ambient_route_is_rejected_before_initial_connector_or_runner(
    controlled: tuple[Request, Boundary],
    monkeypatch: pytest.MonkeyPatch,
    key: str,
) -> None:
    monkeypatch.setenv(key, "SYNTHETIC_UNTRUSTED_VALUE")
    with pytest.raises(UpgradeRejected, match="IMPLICIT_PG_ENVIRONMENT"):
        port(controlled)
    assert controlled[1].connections == [] and controlled[1].calls == []


@pytest.mark.parametrize("key", pg.IMPLICIT_PG_ENV)
@pytest.mark.parametrize("action", ["connect", "candidate", "dump"])
def test_ambient_changes_after_construction_are_rejected_at_execution(
    controlled: tuple[Request, Boundary],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    key: str,
    action: str,
) -> None:
    candidate = port(controlled)
    monkeypatch.setenv(key, "SYNTHETIC_UNTRUSTED_VALUE")
    with pytest.raises(UpgradeRejected, match="IMPLICIT_PG_ENVIRONMENT"):
        if action == "connect":
            candidate._connection("owner")
        elif action == "candidate":
            candidate.candidate("print('{}')")
        else:
            candidate.dump(tmp_path / "not-written.dump")
    assert controlled[1].connections == [] and controlled[1].calls == []


@pytest.mark.parametrize(
    "field,value,code",
    [
        ("hostaddr", "203.0.113.1", "LOOPBACK_ONLY"),
        ("host", "127.0.0.1,203.0.113.1", "LOOPBACK_ONLY"),
        ("service", "synthetic-service", "PG_DSN_FIELDS"),
        ("options", "-csearch_path=untrusted", "PG_DSN_OPTIONS"),
        ("connect_timeout", "60", "PG_DSN_OPTIONS"),
        ("port", "5433", "DATABASE_IDENTITY"),
        ("dbname", "zhiming_core_live", "DATABASE_IDENTITY"),
        ("user", "postgres", "SEPARATE_DATABASE_ROLES"),
        ("sslmode", "allow", "PG_DSN_FIELDS"),
        ("passfile", "relative-password-file", "PASSFILE_ABSOLUTE"),
    ],
    ids=["hostaddr", "host-list", "service", "options", "timeout", "port", "database", "role", "ssl", "passfile"],
)
def test_bad_explicit_route_is_rejected_without_physical_effects(
    controlled: tuple[Request, Boundary],
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: str,
    code: str,
) -> None:
    request, boundary = controlled
    fields = conninfo_to_dict(dsn(request, "writer"))
    fields[field] = value
    monkeypatch.setenv("CORE_INCREMENTAL_WRITER_DSN", make_conninfo(**fields))
    with pytest.raises(UpgradeRejected, match=code):
        port(controlled)
    assert boundary.connections == [] and boundary.calls == []


def test_invalid_conninfo_error_does_not_echo_synthetic_secret(
    controlled: tuple[Request, Boundary],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    secret = "SYNTHETIC_DSN_SECRET"
    monkeypatch.setenv("CORE_INCREMENTAL_OWNER_DSN", "password='" + secret)
    with pytest.raises(UpgradeRejected, match="PG_DSN_INVALID") as rejected:
        port(controlled)
    assert secret not in str(rejected.value) and capsys.readouterr() == ("", "")
    assert controlled[1].connections == [] and controlled[1].calls == []


def test_different_loopback_servers_are_rejected_before_first_connection(
    controlled: tuple[Request, Boundary],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request, boundary = controlled
    fields = conninfo_to_dict(dsn(request, "writer"))
    fields["host"] = "::1"
    monkeypatch.setenv("CORE_INCREMENTAL_WRITER_DSN", make_conninfo(**fields))
    with pytest.raises(UpgradeRejected, match="PG_SERVER_MISMATCH"):
        port(controlled)
    assert boundary.connections == [] and boundary.calls == []


def test_canonical_connection_explicit_password_and_no_home_passfile(
    controlled: tuple[Request, Boundary],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request, boundary = controlled
    monkeypatch.setenv("CORE_INCREMENTAL_OWNER_DSN", dsn(request, "owner", password="SYNTHETIC_EXPLICIT_SECRET"))
    candidate = port(controlled)
    candidate._connection("owner")
    fields = conninfo_to_dict(boundary.connections[0][0])
    assert fields == {
        "host": "127.0.0.1",
        "hostaddr": "127.0.0.1",
        "port": "5432",
        "dbname": request.database,
        "user": request.database + "_owner",
        "password": "SYNTHETIC_EXPLICIT_SECRET",
        "options": "",
        "passfile": os.path.abspath(os.devnull),
        "connect_timeout": "5",
    }
    assert boundary.connections[0][1]["connect_timeout"] == 5 and boundary.calls == []


def test_explicit_private_passfile_is_guarded_again_before_execution(
    controlled: tuple[Request, Boundary],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    request, boundary = controlled
    path = tmp_path / "synthetic-reviewed-password-file"
    observed: list[tuple[Path, bool]] = []

    def protected(value: Path, *, private: bool = False) -> None:
        observed.append((value, private))

    # This proves the protection call and pass-through ABI, not Linux mode bits on Windows.
    monkeypatch.setattr(pg, "regular", protected)
    monkeypatch.setenv("CORE_INCREMENTAL_OWNER_DSN", dsn(request, "owner", passfile=str(path)))
    candidate = port(controlled)
    assert observed == [(path, True)]
    candidate._connection("owner")
    assert observed == [(path, True), (path, True)]
    assert conninfo_to_dict(boundary.connections[0][0])["passfile"] == str(path)


def test_unprotected_file_is_rejected_without_reading_it(
    controlled: tuple[Request, Boundary],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    request, boundary = controlled
    path = tmp_path / "unprotected-password-file"
    path.write_bytes(b"SYNTHETIC_PASSWORD_FILE_MUST_NOT_BE_READ")
    path.chmod(0o666)
    monkeypatch.setenv("CORE_INCREMENTAL_OWNER_DSN", dsn(request, "owner", passfile=str(path)))
    monkeypatch.setattr(Path, "read_bytes", lambda self: pytest.fail("password file contents read"))
    monkeypatch.setattr(Path, "read_text", lambda self, **kwargs: pytest.fail("password file contents read"))
    with pytest.raises(UpgradeRejected, match="PRIVATE_FILE_MODE"):
        port(controlled)
    assert boundary.connections == [] and boundary.calls == []


def test_passfile_protection_change_after_construction_stops_connection(
    controlled: tuple[Request, Boundary],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    request, boundary = controlled
    path = tmp_path / "reviewed-password-file"
    monkeypatch.setenv("CORE_INCREMENTAL_OWNER_DSN", dsn(request, "owner", passfile=str(path)))
    monkeypatch.setattr(pg, "regular", lambda *args, **kwargs: None)
    candidate = port(controlled)

    def rejected(*args: Any, **kwargs: Any) -> None:
        raise UpgradeRejected("PRIVATE_FILE_MODE")

    monkeypatch.setattr(pg, "regular", rejected)
    with pytest.raises(UpgradeRejected, match="PRIVATE_FILE_MODE"):
        candidate._connection("owner")
    assert boundary.connections == [] and boundary.calls == []


def test_dump_explicitly_carries_controlled_libpq_environment(
    controlled: tuple[Request, Boundary],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    request, boundary = controlled
    monkeypatch.setenv("CORE_INCREMENTAL_OWNER_DSN", dsn(request, "owner", password="SYNTHETIC_EXPLICIT_SECRET"))
    monkeypatch.setenv("KIMI_API_KEY", "SYNTHETIC_PROVIDER_SECRET")
    candidate = port(controlled)
    candidate.dump(tmp_path / "not-written.dump")
    args, options = boundary.calls[0]
    assert args == ["pg_dump", "--format=custom", "--no-owner", "--no-acl"]
    assert {key: options["env"][key] for key in ("PGHOST", "PGHOSTADDR", "PGPORT", "PGDATABASE", "PGUSER")} == {
        "PGHOST": "127.0.0.1",
        "PGHOSTADDR": "127.0.0.1",
        "PGPORT": "5432",
        "PGDATABASE": request.database,
        "PGUSER": request.database + "_owner",
    }
    assert options["env"]["PGPASSWORD"] == "SYNTHETIC_EXPLICIT_SECRET"
    assert options["env"]["PGPASSFILE"] == os.path.abspath(os.devnull) and options["env"]["PGOPTIONS"] == ""
    assert "KIMI_API_KEY" not in options["env"] and boundary.connections == []


def test_candidate_child_dsns_are_canonical_and_no_provider_secret(
    controlled: tuple[Request, Boundary],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("KIMI_API_KEY", "SYNTHETIC_PROVIDER_SECRET")
    candidate = port(controlled)
    candidate.candidate("print('{}')")
    child = controlled[1].calls[0][1]["env"]
    for role in ("owner", "writer"):
        fields = conninfo_to_dict(child["CORE_INCREMENTAL_" + role.upper() + "_DSN"])
        assert fields["hostaddr"] == "127.0.0.1" and fields["passfile"] == os.path.abspath(os.devnull)
        assert fields["options"] == "" and fields["connect_timeout"] == "5"
    assert "KIMI_API_KEY" not in child and controlled[1].connections == []
