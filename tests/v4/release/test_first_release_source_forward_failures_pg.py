"""Native source-forward failures preserve control flow and recheck live SDK SQL."""

from __future__ import annotations

import inspect
import json

import psycopg
import pytest
from langgraph.checkpoint import postgres
from psycopg import sql
from test_first_release_incremental_backup_pg import state
from test_first_release_incremental_forward_pg import archive_fixture as shared_archive
from test_first_release_incremental_forward_pg import materials, prefix, source_rows
from test_first_release_incremental_forward_pg import proposal as shared_proposal
from test_first_release_incremental_forward_pg import source_fixture as shared_existing

from tools import first_release_incremental_forward as forward
from tools import first_release_incremental_scope as scopes
from tools.first_release_contracts import RestoreRejected


@pytest.fixture(scope="module", name="archive")
def archive_fixture():
    return shared_archive.__wrapped__()


@pytest.fixture(name="existing")
def source_fixture(request, archive):
    yield from shared_existing.__wrapped__(request, archive)


@pytest.fixture
def proposal(existing):
    yield from shared_proposal.__wrapped__(existing)


def observed_forward(request, **kwargs):
    try:
        return forward.execute(request, **kwargs)
    except forward.SourceForwardStopped as error:
        diagnostic = forward._session_diagnostic(error)
        if diagnostic is not None:
            try:
                print(json.dumps(diagnostic, sort_keys=True), flush=True)
            except Exception:  # noqa: BLE001 - Diagnostics cannot replace the selected source failure.
                raise error from None
        raise


def sdk_setup_on_stack():
    frame = inspect.currentframe()
    try:
        while frame is not None:
            if frame.f_code is postgres.PostgresSaver.setup.__code__:
                return True
            frame = frame.f_back
    finally:
        del frame
    return False


def closing_spies(value, monkeypatch, interrupt):
    execute, cursor = psycopg.Connection.execute, psycopg.Connection.cursor
    observed = {"sdk_errors": [], "cleanup_errors": []}
    database = value.request.source.source.database

    def actual_cursor(connection, *args, **kwargs):
        try:
            return cursor(connection, *args, **kwargs)
        except psycopg.OperationalError as error:
            if connection is observed.get("owner") and sdk_setup_on_stack():
                observed["sdk_errors"].append(error)
            raise

    def actual_execute(connection, query, *args, **kwargs):
        try:
            result = execute(connection, query, *args, **kwargs)
        except psycopg.Error as error:
            if connection is observed.get("owner") and connection.closed:
                if query == "SET default_transaction_read_only=on":
                    observed["restore_error"] = error
                    # The original closed-connection error happened before this control fault.
                    raise interrupt from None
                observed["cleanup_errors"].append(error)
            raise
        if query == "SET search_path=public" and connection.info.dbname == database:
            observed["owner"] = connection
            connection.close()
            observed["closed_after_public"] = True
        return result

    monkeypatch.setattr(psycopg.Connection, "cursor", actual_cursor)
    monkeypatch.setattr(psycopg.Connection, "execute", actual_execute)
    return observed


def test_native_sdk_failure_then_restore_control_preserves_same_interrupt_over_cleanup(
    proposal, monkeypatch, record_property
):
    before_rows = source_rows(proposal)
    old_versions = len(before_rows["public.checkpoint_migrations"])
    interrupt = KeyboardInterrupt("synthetic-control-during-session-restoration")
    observed = closing_spies(proposal, monkeypatch, interrupt)
    with pytest.raises(KeyboardInterrupt) as stopped:
        forward.execute(proposal.request, apply_source=True)
    assert stopped.value is interrupt
    assert observed["closed_after_public"] and observed["owner"].closed
    assert observed["sdk_errors"] and all(
        isinstance(error, psycopg.OperationalError) for error in observed["sdk_errors"]
    )
    assert isinstance(observed["restore_error"], psycopg.OperationalError)
    assert observed["cleanup_errors"] and all(isinstance(error, psycopg.Error) for error in observed["cleanup_errors"])
    assert all(error is not interrupt for error in observed["sdk_errors"] + observed["cleanup_errors"])
    assert prefix(proposal) == 8 and source_rows(proposal, old_versions) == before_rows
    assert materials(proposal.case) == proposal.material
    assert not scopes._SCOPES and not scopes._WITNESSES
    record_property("fault", "native-sdk-closed-source-cursor-then-restore-control")
    record_property("sdk_setup_entered_native_cursor_failure", True)
    record_property("sdk_pending_ddl_executed", False)
    record_property("same_control_exception_propagated", True)


def post_setup_spies(value, monkeypatch):
    verified = scopes.verified_saver
    cursor, execute = psycopg.Connection.cursor, psycopg.Connection.execute
    database = value.request.source.source.database
    observed = {"sdk_cursor_seen": False, "post_setup_hook": False, "source_grant_attempted": False}

    def actual_cursor(connection, *args, **kwargs):
        result = cursor(connection, *args, **kwargs)
        if connection.info.dbname == database and sdk_setup_on_stack():
            observed["sdk_cursor_seen"] = True
        return result

    def actual_execute(connection, query, *args, **kwargs):
        if connection.info.dbname == database:
            text = query.as_string(connection) if isinstance(query, sql.Composable) else query
            if isinstance(text, str) and text.lstrip().upper().startswith(("GRANT ", "REVOKE ")):
                observed["source_grant_attempted"] = True
        return execute(connection, query, *args, **kwargs)

    def changed_live_sql(runtime):
        matching = [scope for scope in scopes._SCOPES.values() if scope.request is value.request]
        if matching and matching[0].phase == "checkpoint_started":
            assert observed["sdk_cursor_seen"] and not sdk_setup_on_stack(), "FAULT_MUST_FOLLOW_ACTUAL_SDK_SETUP"
            observed["post_setup_hook"] = True
            migrations = postgres.PostgresSaver.MIGRATIONS
            original = migrations[0]
            migrations[0] = original + "\n-- SYNTHETIC_POST_SETUP_SQL_DRIFT"
            try:
                return verified(runtime)
            finally:
                migrations[0] = original
        return verified(runtime)

    monkeypatch.setattr(psycopg.Connection, "cursor", actual_cursor)
    monkeypatch.setattr(psycopg.Connection, "execute", actual_execute)
    monkeypatch.setattr(scopes, "verified_saver", changed_live_sql)
    return observed


def test_real_post_setup_live_sql_drift_stops_before_grants_and_preserves_source(
    proposal, monkeypatch, record_property
):
    before_rows = source_rows(proposal)
    old_versions = len(before_rows["public.checkpoint_migrations"])
    original_migrations = list(postgres.PostgresSaver.MIGRATIONS)
    observed = post_setup_spies(proposal, monkeypatch)
    with pytest.raises(forward.SourceForwardStopped, match="^CONTROLLER_SAVER_SQL_CHANGED$") as stopped:
        observed_forward(proposal.request, apply_source=True)
    assert observed["sdk_cursor_seen"] and observed["post_setup_hook"]
    assert observed["source_grant_attempted"] is False
    assert stopped.value.phase == "checkpoint_started" and stopped.value.session_restored is True
    assert original_migrations == postgres.PostgresSaver.MIGRATIONS
    assert prefix(proposal) == 8 and source_rows(proposal, old_versions) == before_rows
    assert materials(proposal.case) == proposal.material
    assert not scopes._SCOPES and not scopes._WITNESSES
    after_versions = len(source_rows(proposal)["public.checkpoint_migrations"])
    record_property("fault", "live-saver-sql-drift-only-at-real-post-setup-audit")
    record_property("sdk_versions_before", old_versions)
    record_property("sdk_versions_after", after_versions)
    record_property("sdk_new_versions", after_versions - old_versions)
    record_property("source_grant_attempted", False)


def annotate_actual_session_failure(monkeypatch):
    original, observed = scopes.guard.sessions, {}

    def actual_gate(connection, allowed):
        try:
            return original(connection, allowed)
        except RestoreRejected as error:
            if str(error) == "INCREMENTAL_OTHER_SOURCE_SESSION":
                diagnostic = error.session_diagnostic
                diagnostic["unreviewed_field"] = "SYNTHETIC_UNREVIEWED_FIELD"
                diagnostic["actual_backends"][0]["query"] = "SYNTHETIC_UNREVIEWED_QUERY"
                error.add_note("SYNTHETIC_UNREVIEWED_NOTE")
                observed["failure"] = error
            raise

    monkeypatch.setattr(scopes.guard, "sessions", actual_gate)
    return observed


def test_actual_foreign_session_diagnostic_survives_public_forward_stop_without_source_changes(
    proposal, monkeypatch, capsys, record_property
):
    before = state(proposal.case.source)
    controls = materials(proposal.case)
    observed = annotate_actual_session_failure(monkeypatch)
    with psycopg.connect(proposal.case.source.environment["FIRST_INCREMENTAL_OWNER_DSN"]) as foreign:
        with pytest.raises(forward.SourceForwardStopped, match="^INCREMENTAL_OTHER_SOURCE_SESSION$") as stopped:
            observed_forward(proposal.request, apply_source=True)
        original, public = observed["failure"], stopped.value
        diagnostic = public.session_diagnostic
        assert str(original) == str(public) == "INCREMENTAL_OTHER_SOURCE_SESSION"
        assert diagnostic["schema"] == "source-session-set-v1" and diagnostic["observation"] == "at_failed_gate"
        assert set(diagnostic) == {
            "schema",
            "observation",
            "allowed_pids",
            "allowed_count",
            "actual_backends",
            "actual_count",
            "truncated",
        }
        assert all(set(row) == {"pid", "backend_type"} for row in diagnostic["actual_backends"])
        actual = {row["pid"]: row["backend_type"] for row in diagnostic["actual_backends"]}
        assert actual[foreign.info.backend_pid] == "client backend"
        assert foreign.info.backend_pid not in diagnostic["allowed_pids"]
        assert diagnostic is not original.session_diagnostic
        assert diagnostic["allowed_pids"] is not original.session_diagnostic["allowed_pids"]
        assert diagnostic["actual_backends"][0] is not original.session_diagnostic["actual_backends"][0]
        assert not getattr(public, "__notes__", ()) and not public.automatic_cleanup
        assert public.phase == "source_checks" and public.session_restored is True
    captured = capsys.readouterr().out
    assert json.loads(captured) == diagnostic and "SYNTHETIC_UNREVIEWED" not in captured
    assert state(proposal.case.source) == before and materials(proposal.case) == controls
    assert not scopes._SCOPES and not scopes._WITNESSES
    record_property("session_observation", "at_failed_gate")
    record_property("actual_foreign_session_preserved", True)
    record_property("unreviewed_diagnostic_fields_and_notes_dropped", True)
