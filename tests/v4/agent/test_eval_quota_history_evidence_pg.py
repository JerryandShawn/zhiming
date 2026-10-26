"""True core/Mock HTTP case effects prove historical requests after the original lease expires."""

from __future__ import annotations

import copy
import json
import re
import time
from contextlib import contextmanager
from dataclasses import asdict
from types import SimpleNamespace

import httpx
import pytest
from models.test_quota_http_pg import rows as quota_rows
from psycopg import sql
from psycopg.types.json import Jsonb

from mingjing_core.agent.journal import input_fingerprint
from mingjing_core.application.agent_case_effect_records import effect_id
from mingjing_core.application.agent_model_calls import RequestLedger
from mingjing_core.application.agent_model_history_evidence import completed_model_history
from mingjing_core.domain.contracts import CoreError
from mingjing_core.models.quota_guard import QuotaGuard
from mingjing_core.repositories.dependencies import entity_dependency
from mingjing_core.repositories.postgres import PostgresRepository, fingerprint
from tools.eval.quota import ProviderStopped

from .model_attempt_support import observed as shared_observed
from .test_eval_v4_live_pg import wire

TEXT = "请把目标改成合成第一计划，然后改成合成最终计划。"


def record_tool_diagnostic(request, target, run, case):
    def code(value):
        return value if type(value) is str and re.fullmatch(r"[A-Za-z0-9_.:-]{1,80}", value) else "absent_or_invalid"

    with target.repo.transaction(target.owner) as connection:
        tools = connection.execute(
            sql.SQL(
                "SELECT seq,output FROM {} WHERE owner=%s AND run_id=%s AND epoch=%s "
                "AND kind='tool' AND name='case_update' ORDER BY seq LIMIT 3"
            ).format(target.repo.table("core_run_steps")),
            (target.owner, run["id"], run["retry_epoch"]),
        ).fetchall()
    observed = []
    for row in tools:
        output = row["output"] if type(row["output"]) is dict else {}
        data = output.get("data") if type(output.get("data")) is dict else {}
        receipt = output.get("receipt") if type(output.get("receipt")) is dict else {}
        observed.append(
            dict(
                seq=row["seq"],
                ok=output.get("ok") is True,
                code=code(data.get("code")),
                write_status=code(receipt.get("write_status")),
            )
        )
    source = target.repo.get(target.owner, "message", run["request"]["source_message_id"])
    actual = target.repo.get(target.owner, "case", case["id"])
    delta = actual["revision"] - case["revision"]
    request.node.user_properties.extend(
        [
            ("history_tool_receipts", json.dumps(observed, sort_keys=True, separators=(",", ":"))),
            ("history_source_case_selected", case["id"] in source.get("case_ids", [])),
            ("history_run_case_selected", case["id"] in run["request"].get("case_ids", [])),
            ("history_case_revision_delta", delta if -256 <= delta <= 256 else "out_of_bounds"),
        ]
    )
    assert len(observed) == 2 and all(row["ok"] and row["write_status"] == "saved" for row in observed)
    assert [row["seq"] for row in tools] == [2, 4]
    assert delta == 2
    for offset, row in enumerate(tools, 1):
        receipt = {"write_status": "saved", "kind": "case", "id": case["id"], "revision": case["revision"] + offset}
        assert row["output"]["receipt"] == receipt
        effect = target.repo.get(
            target.owner, "runtime_step", effect_id(run["id"], run["retry_epoch"], row["seq"]), include_deleted=True
        )
        assert effect["status"] == "active" and effect["subject_id"] == run["subject"]
        assert (effect["run_id"], effect["epoch"], effect["seq"]) == (run["id"], run["retry_epoch"], row["seq"])
        assert effect["target_case_id"] == case["id"] and effect["output"]["receipt"] == receipt


@pytest.fixture
def history(p2_repo, monkeypatch, request):
    with contextmanager(shared_observed.__wrapped__)(p2_repo, monkeypatch, request) as observed:
        target, live = observed.target, observed.live
        target.seeder.seed_case({"id": "history-case", "title": "合成历史事项", "goal": "合成原计划"}, 901)
        case = target.repo.get(target.owner, "case", target.seeder.case_ids[-1])

        def respond(message):
            position = len(live.sent)
            if position <= 2:
                return wire(
                    {
                        "type": "tool_use",
                        "id": f"history-change-{position}",
                        "name": "case_update",
                        "input": {
                            "id": case["id"],
                            "message_id": target.bindings["turn-1"],
                            "quote": TEXT,
                            "expected_revision": case["revision"] + position - 1,
                            "changes": {"goal": "合成第一计划" if position == 1 else "合成最终计划"},
                        },
                    }
                )
            return httpx.Response(
                403,
                headers={"Retry-After": "18000"},
                json={"error": {"type": "permission_error", "message": "5-hour usage limit"}},
            )

        live.primary = respond
        with pytest.raises(ProviderStopped) as stopped:
            target.send({"user": TEXT, "channel": "web", "_index": 1})
        assert stopped.value.reason == "quota_5h"
        run = target.repo.fetch_run(target.owner, target.run_ids[-1])
        assert not target.runtime.offline and target.runtime.meter.live_admissible
        assert len(live.sent) == 3 and [row["status"] for row in quota_rows(live.guard)] == ["ok", "ok", "quota_5h"]
        assert all(row["run_id"] == run["id"] for row in quota_rows(live.guard))
        assert {entry["attempt_id"] for row in observed.links() for entry in row["value"]["attempts"]} == {
            row["attempt_id"] for row in quota_rows(live.guard)
        }
        record_tool_diagnostic(request, target, run, case)
        target.repo.renew_run(target.owner, run["id"], run["lease_token"], lease_seconds=1)
        time.sleep(1.15)
        with target.repo.transaction(target.owner) as connection:
            expired = connection.execute(
                sql.SQL("SELECT lease_until<=now() AS expired FROM {} WHERE owner=%s AND id=%s").format(
                    target.repo.table("core_runs")
                ),
                (target.owner, run["id"]),
            ).fetchone()["expired"]
        assert expired
        yield SimpleNamespace(observed=observed, case=case, run=run)


def arguments(value, *, seq=1):
    target = value.observed.target
    ledger = RequestLedger(target.repo, target.runtime.meter, offline=False)
    return ledger, target.owner, value.run["id"], value.run["retry_epoch"], seq


def state(value):
    target, guard = value.observed.target, value.observed.live.guard
    names = [
        (target.repo, name)
        for name in (
            "core_runs",
            "core_run_steps",
            "core_run_events",
            "core_entities",
            "core_mutation_requests",
            "core_operations",
            "core_versions",
            "core_revocations",
        )
    ] + [
        (guard.store, name)
        for name in ("core_model_accounts", "core_model_usage", "core_model_batches", "core_model_authorizations")
    ]
    digests = []
    for store, name in names:
        with target.repo.transaction() as connection:
            actual = connection.execute(
                sql.SQL('SELECT to_jsonb(t) AS row FROM {} t ORDER BY to_jsonb(t)::text COLLATE "C"').format(
                    store.table(name)
                )
            ).fetchall()
        digests.append(fingerprint(actual))
    return digests, len(value.observed.live.sent)


def forbid_effects(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("HISTORY_EVIDENCE_MUST_NOT_WRITE_CLAIM_CLEAR_OR_SEND")

    for cls, name in (
        (QuotaGuard, "acquire"),
        (QuotaGuard, "clear_stop"),
        (httpx.Client, "send"),
        (PostgresRepository, "claim_run"),
        (PostgresRepository, "_leased"),
        (PostgresRepository, "put"),
        (PostgresRepository, "update"),
        (PostgresRepository, "delete"),
        (PostgresRepository, "set_run_dependencies"),
    ):
        monkeypatch.setattr(cls, name, forbidden)


def test_true_core_case_history_is_readonly_after_real_lease_expiry(history, monkeypatch):
    target = history.observed.target
    actual = target.repo.get(target.owner, "case", history.case["id"])
    assert actual["revision"] == history.case["revision"] + 2
    before = state(history)
    forbid_effects(monkeypatch)
    first = completed_model_history(*arguments(history))
    second = completed_model_history(*arguments(history, seq=3))
    assert (first.run_id, first.epoch, first.seq) == (history.run["id"], history.run["retry_epoch"], 1)
    assert second.seq == 3 and first.request_sha256 != second.request_sha256
    assert len(first.evidence_sha256) == len(second.evidence_sha256) == 64
    assert not first.execution_authority and not second.execution_authority
    assert not any("计划" in str(value) for value in asdict(first).values())
    for override in (("another-owner", history.run["id"], 0, 1), (target.owner, history.run["id"], 0, 5)):
        with pytest.raises(CoreError):
            completed_model_history(arguments(history)[0], *override)
    with target.repo.transaction(), pytest.raises(CoreError):
        completed_model_history(*arguments(history))
    assert state(history) == before


@pytest.mark.parametrize("change", ["external_revision", "revoked"])
def test_external_same_body_revision_or_actual_withdrawal_rejects(history, monkeypatch, change):
    target = history.observed.target
    current = target.repo.get(target.owner, "case", history.case["id"])
    if change == "external_revision":
        changed = target.repo.update(
            target.owner, "case", current["id"], {"title": current["title"]}, expected_revision=current["revision"]
        )
        assert changed["state"] == current["state"] and changed["revision"] == current["revision"] + 1
    else:
        target.repo.delete(target.owner, "case", current["id"], expected_revision=current["revision"])
        assert target.repo.is_revoked(target.owner, "case", current["id"])
    before = state(history)
    forbid_effects(monkeypatch)
    with pytest.raises(CoreError):
        completed_model_history(*arguments(history))
    assert state(history) == before


def historical_request_tamper(value):
    target, run = value.observed.target, value.run
    ident = RequestLedger._id(run["id"], run["retry_epoch"], 3)
    row = target.repo.get(target.owner, "runtime_step", ident)
    output = copy.deepcopy(row["output"])
    key = entity_dependency("case", value.case["id"])
    assert output["versions"][key] == value.case["revision"] + 1
    output["versions"][key] = output["plan"]["source_versions"][key] = value.case["revision"]
    identity = dict(
        messages=output["budget"]["messages"],
        tools=output["budget"]["tools"],
        tool_choice=output["choice"],
        source_versions=output["versions"],
    )
    digest = input_fingerprint("model", "", identity)
    with target.repo.transaction(target.owner) as connection:
        data = connection.execute(
            sql.SQL("SELECT data FROM {} WHERE owner=%s AND kind='runtime_step' AND id=%s").format(
                target.repo.table("core_entities")
            ),
            (target.owner, ident),
        ).fetchone()["data"]
        data.update(output=output, output_sha256=fingerprint(output), input_fp=digest)
        connection.execute(
            sql.SQL("UPDATE {} SET data=%s WHERE owner=%s AND kind='runtime_step' AND id=%s").format(
                target.repo.table("core_entities")
            ),
            (Jsonb(data), target.owner, ident),
        )
        connection.execute(
            sql.SQL("UPDATE {} SET input_fp=%s WHERE owner=%s AND run_id=%s AND epoch=%s AND seq=3").format(
                target.repo.table("core_run_steps")
            ),
            (digest, target.owner, run["id"], run["retry_epoch"]),
        )


@pytest.mark.parametrize("change", ["missing_effect", "historical_revision"])
def test_complete_effect_chain_and_seq_specific_historical_version_are_required(history, monkeypatch, change):
    target, run = history.observed.target, history.run
    if change == "historical_revision":
        historical_request_tamper(history)
    else:
        with target.repo.transaction(target.owner) as connection:
            deleted = connection.execute(
                sql.SQL("DELETE FROM {} WHERE owner=%s AND kind='runtime_step' AND id=%s RETURNING id").format(
                    target.repo.table("core_entities")
                ),
                (target.owner, effect_id(run["id"], run["retry_epoch"], 2)),
            ).fetchall()
            assert len(deleted) == 1 and deleted[0]["id"] == effect_id(run["id"], run["retry_epoch"], 2)
    before = state(history)
    forbid_effects(monkeypatch)
    with pytest.raises(CoreError):
        completed_model_history(*arguments(history, seq=3))
    assert state(history) == before
