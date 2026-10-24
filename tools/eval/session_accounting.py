"""Account actual same-run UUID sets; reports and local port counters are never evidence."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from psycopg import sql

from mingjing_core.models.quota_delegated import token_parts
from mingjing_core.repositories.postgres import fingerprint
from tools.eval.judge_journal import JudgeJournal
from tools.eval.quota_resume_evidence import _central, _entries, _terminal, require


@dataclass(frozen=True, repr=False)
class SessionAccounting:
    rows: dict = field(repr=False)
    target_ids: frozenset[str]
    judge_ids: frozenset[str]


def _judge_ids(target, control, binding, guard, state):
    journal = JudgeJournal(target, control, binding, guard)
    if state["phase"] == "primary_pending":
        from mingjing_core.domain.contracts import ScopeError

        try:
            target.repo.get(target.owner, "runtime_step", journal.ident, include_deleted=True)
        except ScopeError:
            return frozenset()
        require(False)
    expected = journal._expected()
    row = journal._load(expected)
    if row is None:
        return frozenset()
    value = row["value"]
    require(value["attempt_state"] in {"prepared", "completed"})
    identifiers = value["attempt_ids"]
    require(type(identifiers) is list and len(identifiers) == len(set(identifiers)))
    if value["attempt_state"] == "completed":
        require(len(identifiers) == 1)
        journal._completed(row)
    else:
        require(identifiers == [])
    return frozenset(identifiers)


def _target_ids(target, binding, run, central, batches):
    with target.repo.transaction(target.owner) as connection:
        steps = connection.execute(
            sql.SQL(
                "SELECT * FROM {} WHERE owner=%s AND run_id=%s AND epoch=%s AND kind='model' ORDER BY seq LIMIT 257"
            ).format(target.repo.table("core_run_steps")),
            (target.owner, run["id"], run["retry_epoch"]),
        ).fetchall()
    require(len(steps) <= 256)
    found = set()
    for step in steps:
        entries, _ = _entries(target, binding, run, step)
        for entry in entries:
            ident = entry["attempt_id"]
            require(ident not in found and ident in central and central[ident]["batch_id"] in batches)
            _terminal(
                entry,
                central[ident],
                batches[central[ident]["batch_id"]],
                binding,
                run,
                "critic" if step["name"] == "critic" else "primary",
            )
            found.add(ident)
    return frozenset(found)


def snapshot(target, control, binding, guard, state) -> SessionAccounting:
    run = target.repo.fetch_run(target.owner, state["runs"][-1]["id"])
    account, rows, batches = _central(guard, run["id"])
    require(account["location_id"] == binding.central_location and guard.store.identity == binding.central_identity)
    require(guard.store.account_id == binding.central_account and len(rows) <= 1024)
    central = {row["attempt_id"]: row for row in rows}
    require(len(central) == len(rows))
    for row in rows:
        require(type(row["attempt_id"]) is str and re.fullmatch(r"http-[a-f0-9]{32}", row["attempt_id"]))
        require(
            (row["run_id"], row["lane"], row["scenario_id"], row["provider"], row["model"])
            == (run["id"], "eval", binding.scenario_id, "kimi_code", binding.model)
            and row["role"] in {"primary", "critic"}
            and row["finished_at"] is not None
            and row["status"] not in {"reserved", "unknown"}
            and row["finished_at"] >= row["at"]
            and type(row["latency_ms"]) in {int, float}
            and math.isfinite(row["latency_ms"])
            and row["latency_ms"] >= 0
        )
        batch = batches.get(row["batch_id"])
        require(
            batch is not None
            and batch["status"] == "completed"
            and batch["finished_at"] is not None
            and batch["recovery_authorization"] is None
            and row["finished_at"] <= batch["finished_at"]
            and binding.scenario_id in batch["scenario_ids"]
            and token_parts(batch["authorization_id"]) == (binding.candidate_commit, "core-" + binding.model)
        )
    target_ids = _target_ids(target, binding, run, central, batches)
    judge_ids = _judge_ids(target, control, binding, guard, state)
    require(not target_ids & judge_ids and target_ids | judge_ids == set(central))
    require(all(central[ident]["role"] == "critic" and central[ident]["status"] == "ok" for ident in judge_ids))
    _, end_rows, end_batches = _central(guard, run["id"])
    require(fingerprint([rows, batches]) == fingerprint([end_rows, end_batches]))
    return SessionAccounting(central, target_ids, judge_ids)


def _usage(rows, target_ids, judge_ids):
    target_seconds = sum(rows[ident]["latency_ms"] for ident in target_ids) / 1000
    judge_seconds = sum(rows[ident]["latency_ms"] for ident in judge_ids) / 1000
    return dict(
        model_calls=len(target_ids) + len(judge_ids),
        target_model_calls=len(target_ids),
        judge_model_calls=len(judge_ids),
        target_model_elapsed_seconds=target_seconds,
        judge_model_elapsed_seconds=judge_seconds,
        elapsed_seconds=target_seconds + judge_seconds,
    )


def reconcile(before: SessionAccounting, after: SessionAccounting) -> dict:
    require(set(before.rows) <= set(after.rows))
    require(all(fingerprint(row) == fingerprint(after.rows[ident]) for ident, row in before.rows.items()))
    require(before.target_ids <= after.target_ids and before.judge_ids <= after.judge_ids)
    new_ids = set(after.rows) - set(before.rows)
    groups = {
        "new": (after.target_ids & new_ids, after.judge_ids & new_ids),
        "inherited": (before.target_ids, before.judge_ids),
        "historical_actual": (after.target_ids, after.judge_ids),
    }
    result = {"current_observation_only": True, "basis": "actual_same_run_central_UUID_rows_and_JudgeJournal"}
    for name, (target_ids, judge_ids) in groups.items():
        result[name] = dict(target=len(target_ids), judge=len(judge_ids), total=len(target_ids) + len(judge_ids))
        result[name + "_usage"] = _usage(after.rows, target_ids, judge_ids)
    require(result["new"]["total"] + result["inherited"]["total"] == result["historical_actual"]["total"])
    result["before_sha256"] = fingerprint(before.rows)
    result["after_sha256"] = fingerprint(after.rows)
    return result
