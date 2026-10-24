"""Full native rows for same-run quota continuation regression assertions."""

from models.test_quota_http_pg import rows as quota_rows
from psycopg import sql

from mingjing_core.repositories.postgres import fingerprint


def rows(value, name):
    target = value.target
    with target.repo.transaction(target.owner) as connection:
        return connection.execute(
            sql.SQL('SELECT t.* FROM {} t ORDER BY to_jsonb(t)::text COLLATE "C"').format(target.repo.table(name))
        ).fetchall()


def core_state(value):
    names = (
        "core_runs",
        "core_entities",
        "core_run_steps",
        "core_run_events",
        "core_operations",
        "core_mutation_requests",
        "core_revocations",
        "core_versions",
        "core_owners",
        "core_subjects",
    )
    return fingerprint([rows(value, name) for name in names])


def assert_clear_without_post_or_new_epoch(value, *, withdrawn=False):
    with value.live.guard.store.connect() as connection:
        account = value.live.guard.store.verify(connection)
    assert account["stop_kind"] is account["stopped_at"] is account["resume_at"] is None
    assert account["clear_authorization"] is not None
    assert quota_rows(value.live.guard) == value.old_usage and len(value.live.sent) == 3
    runs = rows(value, "core_runs")
    assert len(runs) == 1 and runs[0]["id"] == value.run["id"] and runs[0]["retry_epoch"] == value.run["retry_epoch"]
    if withdrawn:
        assert runs[0]["status"] == "revoked" and runs[0]["request"] == {} and runs[0]["result"] is None
        assert runs[0]["lease_token"] is runs[0]["lease_until"] is None and runs[0]["checkpoint"] == {}
        ids = {row["id"] for row in value.original["private"]}
        private = [row for row in rows(value, "core_entities") if row["id"] in ids]
        assert len(private) == len(ids) and all(row["status"] == "deleted" and row["data"] == {} for row in private)
        native = rows(value, "core_run_steps")
        assert sorted(row["seq"] for row in native) == [1, 2, 3, 4, 5]
        assert all(row["output"] is None and row["error_code"] == "SOURCE_REVOKED" for row in native)
        assert all(row["payload"] == {} for row in rows(value, "core_run_events"))
    else:
        assert runs[0]["request"] == value.run["request"]
    assert runs[0]["usage"]["agent_runtime"]["limit_epochs"] == value.old_pin
    assert value.control.load(value.session, value.binding, value.live.guard) == value.old_record
