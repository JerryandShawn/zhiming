"""Raw header/query syntax is checked before real socket SSE headers or subscriptions."""

from __future__ import annotations

import httpx
import pytest
from psycopg import sql

from mingjing_core.adapters.web import create_app
from mingjing_core.application.run_event_read import RunEventReader
from tests.v4.agent.legacy_dom_http_support import local_app
from tests.v4.agent.test_runtime_assembly_pg import service
from tests.v4.streaming_integration.event_http_support import (
    HEADERS,
    decoded,
    isolate,
    until,
)
from tests.v4.streaming_integration.test_event_cursor_pg import seeded
from tests.v4.streaming_integration.test_event_notify_pg import stored


@pytest.fixture
def http_repo(p2_repo, monkeypatch):
    isolate(monkeypatch)
    return p2_repo


@pytest.mark.parametrize("enabled", [False, True])
def test_actual_http_alias_header_combinations_resume_only_after_same_row(
    http_repo, enabled
):
    repo, run = http_repo, seeded(http_repo)
    RunEventReader(repo, "alice", run["id"]).ensure_terminal()
    app = create_app(service(repo), event_hints=enabled)
    with local_app(app) as origin, httpx.Client(timeout=3, trust_env=False) as client:
        endpoint = origin + f"/api/runs/{run['id']}/events"
        combinations = [
            ({}, {"after": "1"}),
            ({}, {"after_seq": "1"}),
            ({"Last-Event-ID": "1"}, {}),
            ({"Last-Event-ID": "1"}, {"after": "1", "after_seq": "1"}),
        ]
        for headers, params in combinations:
            response = client.get(
                endpoint, headers=dict(HEADERS, **headers), params=params
            )
            assert response.status_code == 200
            assert [event["data"]["seq"] for event in decoded(response.text)] == [
                2,
                3,
                4,
            ]
        all_rows = client.get(
            endpoint, headers=HEADERS, params={"after": "0", "after_seq": "0"}
        )
        assert [event["data"]["seq"] for event in decoded(all_rows.text)] == [
            1,
            2,
            3,
            4,
        ]
        schemas = client.get(origin + "/openapi.json").json()["paths"][
            "/api/runs/{ident}/events"
        ]["get"]["parameters"]
        assert {field["name"] for field in schemas if field["in"] == "query"} == {
            "after",
            "after_seq",
        }
        if enabled:
            until(
                lambda: app.state.core["event_hints"].statistics()["subscriptions"] == 0
            )


@pytest.mark.parametrize("alias", ["after", "after_seq"])
def test_noncanonical_query_values_are_rejected_before_sse_and_echo_nothing(
    http_repo, alias
):
    repo, run = http_repo, seeded(http_repo)
    app = create_app(service(repo), event_hints=True)
    before = stored(repo, run)
    with local_app(app) as origin, httpx.Client(timeout=3, trust_env=False) as client:
        for value in (
            "",
            "01",
            "00",
            "+1",
            "-1",
            "1.0",
            "1e3",
            " 1",
            "1 ",
            "１２",
            "9223372036854775808",
            "private-cursor-value",
        ):
            response = client.get(
                origin + f"/api/runs/{run['id']}/events",
                headers=HEADERS,
                params={alias: value},
            )
            assert response.status_code == 422 and response.headers[
                "content-type"
            ].startswith("application/json")
            assert response.json()["detail"] == "事件游标无效"
            assert app.state.core["event_hints"].statistics()["subscriptions"] == 0
    assert stored(repo, run) == before


def test_actual_http_duplicates_conflicts_and_noncanonical_headers_are_all_rejected(
    http_repo,
):
    repo, run = http_repo, seeded(http_repo)
    app = create_app(service(repo), event_hints=True)
    before = stored(repo, run)
    with local_app(app) as origin, httpx.Client(timeout=3, trust_env=False) as client:
        endpoint = origin + f"/api/runs/{run['id']}/events"
        invalid = [
            ([("after", "1"), ("after", "1")], HEADERS),
            ([("after_seq", "1"), ("after_seq", "2")], HEADERS),
            ({"after": "1", "after_seq": "0"}, HEADERS),
            ({"after": "0"}, dict(HEADERS, **{"Last-Event-ID": "1"})),
            ({}, [*HEADERS.items(), ("Last-Event-ID", "1"), ("Last-Event-ID", "1")]),
        ]
        for params, headers in invalid:
            response = client.get(endpoint, headers=headers, params=params)
            assert response.status_code == 422
            assert app.state.core["event_hints"].statistics()["subscriptions"] == 0
        for value in ("", "01", "+1", "-1", "1.0", "1e3", "00", "9223372036854775808"):
            response = client.get(
                endpoint, headers=dict(HEADERS, **{"Last-Event-ID": value})
            )
            assert (
                response.status_code == 422
                and response.json()["detail"] == "事件游标无效"
            )
    assert stored(repo, run) == before


def test_actual_http_missing_row_is_not_replaced_by_foreign_max_but_erased_row_is_legal(
    http_repo,
):
    repo, run = http_repo, seeded(http_repo)
    seeded(repo, "bob")
    with repo.transaction("alice") as connection:
        connection.execute(
            sql.SQL("DELETE FROM {} WHERE owner=%s AND run_id=%s AND seq=2").format(
                repo.table("core_run_events")
            ),
            ("alice", run["id"]),
        )
        connection.execute(
            sql.SQL(
                "UPDATE {} SET payload='{{}}' WHERE owner=%s AND run_id=%s AND seq=1"
            ).format(repo.table("core_run_events")),
            ("alice", run["id"]),
        )
    app = create_app(service(repo), event_hints=True)
    with local_app(app) as origin, httpx.Client(timeout=3, trust_env=False) as client:
        endpoint = origin + f"/api/runs/{run['id']}/events"
        missing, unknown = [
            client.get(endpoint, headers=HEADERS, params={"after": str(value)})
            for value in (2, 999)
        ]
        assert (
            missing.status_code == unknown.status_code == 422
            and missing.json() == unknown.json()
        )
        assert app.state.core["event_hints"].statistics()["subscriptions"] == 0
        legal = client.get(endpoint, headers=HEADERS, params={"after": "1"})
        assert legal.status_code == 200 and [
            event["data"]["seq"] for event in decoded(legal.text)
        ] == [3, 4]


def test_actual_withdrawal_keeps_cursor_identity_but_http_never_replays_erased_text(
    http_repo,
):
    repo, run = http_repo, seeded(http_repo, terminal=False)
    repo.invalidate_derived("alice", [], [run["request"]["source_message_id"]])
    assert all(row["payload"] == {} for row in stored(repo, run))
    app = create_app(service(repo), event_hints=True)
    with local_app(app) as origin, httpx.Client(timeout=3, trust_env=False) as client:
        response = client.get(
            origin + f"/api/runs/{run['id']}/events",
            headers=HEADERS,
            params={"after": "1"},
        )
        actual = decoded(response.text)
        assert response.status_code == 200 and len(actual) == 1
        assert (
            actual[0]["data"]["seq"] == 4
            and actual[0]["data"]["code"] == "SOURCE_REVOKED"
        )
        assert (
            "合成精确游标片段" not in response.text
            and "合成第三片段" not in response.text
        )
        until(lambda: app.state.core["event_hints"].statistics()["subscriptions"] == 0)
