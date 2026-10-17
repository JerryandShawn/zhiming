"""P2 integration fixtures always use an explicit disposable loopback database."""

from __future__ import annotations

import os
import uuid
from typing import TYPE_CHECKING

import psycopg
import pytest
from psycopg import sql

from mingjing_core.repositories.postgres import PostgresRepository
from tools.eval.targets.local_db import local_dsn, verify_local_postgres

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture
def p2_repo() -> Iterator[PostgresRepository]:
    configured = os.getenv("CORE_TEST_DSN")
    if not configured:
        pytest.skip("requires disposable PostgreSQL 15")
    dsn = local_dsn(configured)
    verify_local_postgres(dsn)
    schema = "p2_test_" + uuid.uuid4().hex
    repo = PostgresRepository(dsn, schema=schema)
    repo.ensure_owner("alice")
    repo.ensure_owner("bob")
    try:
        yield repo
    finally:
        repo.close()
        assert schema.startswith("p2_test_") and len(schema) == 40
        with psycopg.connect(dsn) as connection:
            connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
