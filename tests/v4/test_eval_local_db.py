"""Prove inherited libpq routing cannot redirect a baseline database connection."""

from unittest.mock import MagicMock

import pytest
from psycopg.conninfo import conninfo_to_dict

from tools.eval.targets.local_db import local_dsn, verify_local_postgres
from tools.eval.targets.v3_target import V3Target


@pytest.mark.parametrize(
    ("host", "address"),
    [("localhost", "127.0.0.1"), ("127.0.0.1", "127.0.0.1"), ("::1", "::1")],
)
def test_inherited_hostaddr_and_port_cannot_override_explicit_test_route(monkeypatch, host, address):
    monkeypatch.delenv("PGSERVICE", raising=False)
    monkeypatch.setenv("PGHOSTADDR", "192.0.2.10")
    monkeypatch.setenv("PGPORT", "65432")
    canonical = local_dsn(f"host={host} port=55480 dbname=core_test user=core_test")
    params = conninfo_to_dict(canonical)
    assert params["hostaddr"] == address
    assert params["port"] == "55480"
    assert conninfo_to_dict(V3Target(dsn=canonical).dsn) == params


def test_inherited_port_cannot_supply_an_unspecified_test_port(monkeypatch):
    monkeypatch.delenv("PGSERVICE", raising=False)
    monkeypatch.setenv("PGPORT", "65432")
    canonical = local_dsn("host=127.0.0.1 dbname=core_test user=core_test")
    assert conninfo_to_dict(canonical)["port"] == "5432"


def test_inherited_service_is_rejected_before_opening_any_connection(monkeypatch):
    monkeypatch.setenv("PGSERVICE", "synthetic_remote_service")
    connect = MagicMock(side_effect=AssertionError("must reject before connecting"))
    monkeypatch.setattr("tools.eval.targets.local_db.psycopg.connect", connect)
    with pytest.raises(ValueError, match="service routing"):
        verify_local_postgres("postgresql://core_test@127.0.0.1:55480/core_test")
    connect.assert_not_called()


def test_server_verification_opens_only_the_canonical_loopback_route(monkeypatch):
    monkeypatch.delenv("PGSERVICE", raising=False)
    monkeypatch.setenv("PGHOSTADDR", "192.0.2.10")
    connection = MagicMock()
    connection.__enter__.return_value.execute.return_value.fetchone.return_value = (
        150019,
        "127.0.0.1",
    )
    connect = MagicMock(return_value=connection)
    monkeypatch.setattr("tools.eval.targets.local_db.psycopg.connect", connect)
    verify_local_postgres("postgresql://core_test@localhost:55480/core_test")
    params = conninfo_to_dict(connect.call_args.args[0])
    assert params["hostaddr"] == "127.0.0.1"
    assert params["port"] == "55480"
    assert params["dbname"] == "core_test"
