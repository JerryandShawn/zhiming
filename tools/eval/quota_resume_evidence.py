"""Read-only pre-clear evidence; neither a lease nor permission to send a request."""

from __future__ import annotations

from mingjing_core.models.quota_r16 import core_token_stage

import re
from dataclasses import asdict, dataclass
from typing import Any

from psycopg import sql

from mingjing_core.agent.journal import Journal
from mingjing_core.agent.loop_codec import assistant_from, assistant_output
from mingjing_core.application.agent_model_attempts import SCHEMA
from mingjing_core.application.agent_model_calls import RequestLedger
from mingjing_core.application.agent_tools_contracts import ToolResult
from mingjing_core.application.runtime_limits import deadline
from mingjing_core.models.quota_delegated import token_parts
from mingjing_core.models.quota_guard import QuotaGuard
from mingjing_core.models.quota_types import instant
from mingjing_core.repositories.postgres import PostgresRepository, fingerprint
from mingjing_core.timekit.clock import get_clock
from tools.eval.lifecycle_control import LifecycleControl
from tools.eval.lifecycle_identity import LifecycleBinding, LifecycleError
from tools.eval.targets.v4_execution_budget_store import BudgetStore
from tools.eval.targets.v4_lifecycle_state import read_private


def require(value: Any) -> None:
    if not value:
        raise LifecycleError("QUOTA_RESUME_EVIDENCE_REJECTED")


@dataclass(frozen=True, repr=False)
class ResumeEvidence:
    sha256: str
    run_id: str
    epoch: int
    turn: int
    seq: int
    reset_at: str
    consumed_ns: int
    has_text: bool
    terminal_id: str
    terminal_sha256: str
    stop_sha256: str
    usage_sha256: str
    batches_sha256: str


def typed(target: Any, control: Any, binding: Any, guard: Any) -> None:
    from tools.eval.targets.v4_durable import DurableCore30Target

    require(
        type(target) is DurableCore30Target
        and type(control) is LifecycleControl
        and type(binding) is LifecycleBinding
        and type(guard) is QuotaGuard
        and type(target.repo) is PostgresRepository
    )


def _private(target: Any, control: Any, binding: Any, guard: Any) -> tuple[dict, dict]:
    typed(target, control, binding, guard)
    require(
        target._attached
        and target.lifecycle_session
        and target._lifecycle_binding == binding
        and target._budget_scope is None
        and not target._budget_unknown
        and not target._budget_legacy
        and control.schema not in {target.schema, guard.store.schema}
    )
    record = control.load(target.lifecycle_session, binding, guard)
    require(record == target._lifecycle_record)
    with target.repo.transaction() as connection:
        require(
            control.location(connection, target.schema) == record["target_location"]
        )
    state = read_private(target.repo, target.owner, record, binding)
    require(
        state["phase"] == "primary_pending"
        and state.get("execution_budget")
        and target.run_ids == state["targets"]["run_ids"]
        and target.seed == state["targets"]["seed"]
        and target.bindings == state["targets"]["bindings"]
        and target.thread["id"] == state["thread_id"]
        and target.model == binding.model
        and type(state["turn"]) is int
        and state["turn"] > 0
        and state["targets"]["bindings"].get(f"turn-{state['turn']}")
        == state["runs"][-1]["sources"][0]["id"]
    )
    return record, state


def _central(guard: Any, run_id: str) -> tuple[dict, list[dict], dict[str, dict]]:
    with guard.store.connect() as connection, connection.transaction():
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        account = guard.store.verify(connection)
        rows = connection.execute(
            sql.SQL(
                "SELECT * FROM {} WHERE account_id=%s AND run_id=%s ORDER BY id"
            ).format(guard.store.table("core_model_usage")),
            (guard.store.account_id, run_id),
        ).fetchall()
        batches = connection.execute(
            sql.SQL(
                "SELECT * FROM {} WHERE account_id=%s AND batch_id=ANY(%s) ORDER BY batch_id"
            ).format(guard.store.table("core_model_batches")),
            (guard.store.account_id, sorted({row["batch_id"] for row in rows})),
        ).fetchall()
    return account, rows, {row["batch_id"]: row for row in batches}


def _budget(target: Any, state: dict, binding: Any, run: dict) -> dict:
    store = BudgetStore(target.repo, target.owner, binding, target.lifecycle_session)
    summary = store.read_closed(run["id"])
    require(summary is not None and summary in state["execution_budget"]["runs"])
    with target.repo.transaction(target.owner):
        row, value = store._record(run)
    require(
        row is not None
        and value is not None
        and summary["consumed_ns"] < value["limit_ns"]
    )
    pin = run["usage"]["agent_runtime"]["limit_epochs"][str(run["retry_epoch"])]
    require(deadline(pin) > get_clock().now() and run["deadline_at"] == deadline(pin))
    return dict(
        summary=summary,
        sha256=row["budget_sha256"],
        has_text=any(s["has_text"] for s in value["segments"]),
    )


def _journal(target: Any, run: dict) -> list[dict]:
    with target.repo.transaction(target.owner) as connection:
        rows = connection.execute(
            sql.SQL(
                "SELECT * FROM {} WHERE owner=%s AND run_id=%s AND epoch=%s ORDER BY seq"
            ).format(target.repo.table("core_run_steps")),
            (target.owner, run["id"], run["retry_epoch"]),
        ).fetchall()
    require(
        0 < len(rows) <= 256
        and [row["seq"] for row in rows] == list(range(1, len(rows) + 1))
    )
    for row in rows:
        Journal._validate_identity(row["kind"], row["name"], row["input_fp"])
        Journal._check(row, row["kind"], row["name"], row["input_fp"])
        require(row["kind"] in {"model", "tool"} and not row["error_code"])
        require(
            type(row["input_fp"]) is str
            and re.fullmatch(r"[0-9a-f]{64}", row["input_fp"])
        )
        require(row["started_at"] is not None)
        if row is rows[-1]:
            require(
                row["kind"] == "model"
                and row["status"] == "started"
                and row["finished_at"] is None
            )
            require(row["output"] is None and row["usage"] == {})
        else:
            require(
                row["status"] == "completed"
                and row["finished_at"] is not None
                and type(row["output"]) is dict
            )
            require(row["finished_at"] >= row["started_at"])
            if row["kind"] == "model":
                response = assistant_from(row["output"])
                require(
                    fingerprint(assistant_output(response))
                    == fingerprint(row["output"])
                    and fingerprint(response.usage) == fingerprint(row["usage"])
                )
            else:
                ToolResult.model_validate(row["output"])
    return rows


def _request(target: Any, run: dict, step: dict) -> tuple[dict, dict]:
    ident = f"{run['id']}:e{run['retry_epoch']}:agent_model_request:{step['seq']}"
    row = target.repo.get(target.owner, "runtime_step", ident, include_deleted=True)
    ledger = RequestLedger(target.repo, target.runtime.meter, offline=False)
    call = ledger._load(target.owner, run["id"], run["retry_epoch"], step["seq"])
    require(call is not None and not target.runtime.offline)
    role = "critic" if step["name"] == "critic" else "primary"
    require(
        row["status"] == "active"
        and row["subject_id"] == run["subject"]
        and row.get("stage") == "agent_model_request"
        and row.get("input_fp") == step["input_fp"]
        and call.role == role
        and call.name == step["name"]
        and step["name"] in {"", "revision", "critic"}
    )
    identity = dict(
        messages=[asdict(message) for message in call.budget.messages],
        tools=[asdict(tool) for tool in call.budget.tools],
        tool_choice=call.choice,
        source_versions=call.versions,
    )
    from mingjing_core.agent.journal import input_fingerprint

    require(input_fingerprint("model", step["name"], identity) == step["input_fp"])
    return row, dict(role=role, name=step["name"], request_sha256=row["output_sha256"])


def _entries(
    target: Any, binding: Any, run: dict, step: dict
) -> tuple[list[dict], str]:
    request, fields = _request(target, run, step)
    anchor = dict(
        binding=asdict(binding),
        owner=target.owner,
        subject=run["subject"],
        run_id=run["id"],
        epoch=run["retry_epoch"],
        seq=step["seq"],
        input_fp=step["input_fp"],
        operation_id=f"run:{run['id']}:e{run['retry_epoch']}:s{step['seq']}",
        **fields,
    )
    ident = f"{run['id']}:e{run['retry_epoch']}:agent_model_attempts:{step['seq']}"
    row = target.repo.get(target.owner, "runtime_step", ident, include_deleted=True)
    value = row.get("value")
    require(
        row["status"] == "active"
        and row["subject_id"] == run["subject"]
        and row.get("schema") == SCHEMA
        and row.get("stage") == "agent_model_attempts"
        and row.get("run_id") == run["id"]
        and row.get("epoch") == run["retry_epoch"]
        and type(value) is dict
        and set(value) == set(anchor) | {"attempts"}
        and all(value[key] == item for key, item in anchor.items())
        and row.get("value_sha256") == fingerprint(value)
        and type(value["attempts"]) is list
        and 0 < len(value["attempts"]) <= 64
    )
    return value["attempts"], fingerprint([request, row])


def _terminal(
    entry: dict, row: dict, batch: dict, binding: Any, run: dict, role: str
) -> None:
    fields = {
        "run_id",
        "lane",
        "scenario_id",
        "batch_id",
        "authorization_sha256",
        "role",
        "provider",
        "model",
    }
    require(
        type(entry) is dict
        and set(entry)
        == fields | {"attempt_id", "state", "terminal_sha256", "result_kind"}
    )
    require(
        type(entry["attempt_id"]) is str
        and re.fullmatch(r"http-[0-9a-f]{32}", entry["attempt_id"])
    )
    require(
        entry["state"] == "finished"
        and row["finished_at"] is not None
        and row["status"] not in {"reserved", "unknown"}
    )
    expected = dict(
        run_id=run["id"],
        lane="eval",
        scenario_id=binding.scenario_id,
        role=role,
        provider="kimi_code",
        model=binding.model,
    )
    require(all(entry[key] == item == row[key] for key, item in expected.items()))
    require(entry["batch_id"] == row["batch_id"] == batch["batch_id"])
    require(
        token_parts(batch["authorization_id"])
        == (binding.candidate_commit, core_token_stage(binding.model))
        and binding.scenario_id in batch["scenario_ids"]
        and fingerprint(batch["authorization_id"]) == entry["authorization_sha256"]
        and entry["result_kind"] == row["status"]
        and entry["terminal_sha256"] == fingerprint(row)
    )


def _attempts(
    target: Any,
    binding: Any,
    run: dict,
    steps: list[dict],
    usage: list[dict],
    batches: dict,
) -> tuple[dict, list[str]]:
    central = {row["attempt_id"]: row for row in usage}
    require(len(central) == len(usage))
    seen, hashes, last = set(), [], None
    for step in steps:
        if step["kind"] != "model":
            continue
        entries, digest = _entries(target, binding, run, step)
        if step is steps[-1]:
            require(all(entry.get("result_kind") == "quota_5h" for entry in entries))
        hashes.append(digest)
        for entry in entries:
            require(
                type(entry) is dict
                and entry.get("attempt_id") in central
                and entry["attempt_id"] not in seen
            )
            row = central[entry["attempt_id"]]
            require(row["batch_id"] in batches)
            _terminal(
                entry,
                row,
                batches[row["batch_id"]],
                binding,
                run,
                "critic" if step["name"] == "critic" else "primary",
            )
            seen.add(entry["attempt_id"])
            last = row
        require(
            entries[-1]["result_kind"] == ("quota_5h" if step is steps[-1] else "ok")
        )
    require(seen == set(central) and last is not None and last["status"] == "quota_5h")
    return last, hashes


def _stop(account: dict, terminal: dict, guard: Any) -> dict:
    now = instant(guard.clock.now())
    require(account["stop_kind"] == "quota_5h" and account["resume_at"] is not None)
    require(
        account["stopped_at"] == terminal["finished_at"]
        and account["resume_at"] > account["stopped_at"]
        and now >= account["resume_at"]
        and (account["last_clock_at"] is None or now >= account["last_clock_at"])
    )
    return {
        key: account[key]
        for key in (
            "stop_kind",
            "stopped_at",
            "resume_at",
            "clear_authorization",
            "ledger_identity",
            "location_id",
        )
    }


def gather(target: Any, control: Any, binding: Any, guard: Any) -> ResumeEvidence:
    record, state = _private(target, control, binding, guard)
    run = target.repo.fetch_run(target.owner, state["runs"][-1]["id"])
    require(
        run["runtime"] == "v4"
        and run["status"] == "running"
        and run["retry_epoch"] == state["runs"][-1]["epoch"]
    )
    account, usage, batches = _central(guard, run["id"])
    steps, budget = _journal(target, run), _budget(target, state, binding, run)
    terminal, hashes = _attempts(target, binding, run, steps, usage, batches)
    stop = _stop(account, terminal, guard)
    end_record, end_state = _private(target, control, binding, guard)
    end_account, end_usage, end_batches = _central(guard, run["id"])
    end_steps = _journal(target, run)
    end_terminal, end_hashes = _attempts(
        target, binding, run, end_steps, end_usage, end_batches
    )
    require(record == end_record and fingerprint(state) == fingerprint(end_state))
    require(
        fingerprint([steps, terminal, hashes])
        == fingerprint([end_steps, end_terminal, end_hashes])
    )
    require(
        fingerprint([stop, usage, batches])
        == fingerprint([_stop(end_account, terminal, guard), end_usage, end_batches])
    )
    value = dict(
        record=record,
        state_sha256=fingerprint(state),
        journal=steps,
        requests=hashes,
        stop=stop,
        usage=usage,
        batches=batches,
        budget=budget,
        policy=asdict(guard.policy),
    )
    return ResumeEvidence(
        fingerprint(value),
        run["id"],
        run["retry_epoch"],
        state["turn"],
        steps[-1]["seq"],
        stop["resume_at"].isoformat(),
        budget["summary"]["consumed_ns"],
        budget["has_text"],
        terminal["attempt_id"],
        fingerprint(terminal),
        fingerprint(stop),
        fingerprint(usage),
        fingerprint(batches),
    )
