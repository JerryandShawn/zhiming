"""Lease-free, read-only attestation of completed model dependencies; no execution permit."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from psycopg import sql

from mingjing_core.agent.journal import Journal, input_fingerprint
from mingjing_core.agent.loop_codec import assistant_from, assistant_output
from mingjing_core.application.agent_case_completed import CaseEffectIntent, _check_intent, _step_state
from mingjing_core.application.agent_case_effect_attestation import verify_effect
from mingjing_core.application.agent_case_effect_chain import _complete_steps
from mingjing_core.application.agent_case_effect_marker import marker_cases
from mingjing_core.application.agent_case_effect_records import effect_id
from mingjing_core.application.agent_model_calls import RequestLedger
from mingjing_core.application.agent_pending_effects import _initial, _original_call, _saved
from mingjing_core.application.agent_regeneration import AgentRegenerator
from mingjing_core.application.agent_snapshots import AgentSnapshotStore
from mingjing_core.application.agent_tools_contracts import ToolResult
from mingjing_core.application.agent_tools_policy import source_policy, source_span
from mingjing_core.application.thread_sources import ingress_sources, source_segments
from mingjing_core.domain.contracts import EvidenceError
from mingjing_core.repositories.dependencies import entity_dependency, lineage_key
from mingjing_core.repositories.postgres import PostgresRepository, fingerprint
from mingjing_core.timekit.clock import get_clock


def _require(value: Any) -> None:
    if not value:
        raise EvidenceError("历史模型依赖缺少当前完整原生证明")


@dataclass(frozen=True)
class ModelHistoryEvidence:
    owner: str
    run_id: str
    subject: str
    epoch: int
    seq: int
    request_sha256: str
    evidence_sha256: str

    @property
    def execution_authority(self) -> bool:
        return False


def completed_model_history(
    ledger: RequestLedger, owner: str, run_id: str, epoch: int, seq: int
) -> ModelHistoryEvidence:
    """Read twice under an owner lock; neither claim a lease nor reconcile stored versions."""
    _require(type(ledger) is RequestLedger and ledger.offline is False)
    _require(type(ledger.repo) is PostgresRepository)
    _require(all(type(value) is str and value.strip() for value in (owner, run_id)))
    _require(type(epoch) is int and epoch >= 0 and type(seq) is int and seq >= 1)
    repo = ledger.repo
    _require(getattr(repo._local, "connection", None) is None)
    try:
        with repo.transaction() as connection:
            connection.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED, READ ONLY")
            first = _read(ledger, connection, owner, run_id, epoch, seq)
            second = _read(ledger, connection, owner, run_id, epoch, seq)
            _require(first == second)
    except (KeyError, TypeError, ValueError, AttributeError):
        raise EvidenceError("历史模型持久证明结构无效") from None
    subject, request_hash, digest = first
    return ModelHistoryEvidence(owner, run_id, subject, epoch, seq, request_hash, digest)


def _steps(repo: PostgresRepository, connection: Any, run: dict) -> list[dict]:
    rows = connection.execute(
        sql.SQL("SELECT * FROM {} WHERE owner=%s AND run_id=%s AND epoch=%s ORDER BY seq LIMIT 257").format(
            repo.table("core_run_steps")
        ),
        (run["owner"], run["id"], run["retry_epoch"]),
    ).fetchall()
    _require(rows and len(rows) <= 256 and [row["seq"] for row in rows] == list(range(1, len(rows) + 1)))
    for row in rows:
        Journal._validate_identity(row["kind"], row["name"], row["input_fp"])
        Journal._check(row, row["kind"], row["name"], row["input_fp"])
        _require(isinstance(row["started_at"], datetime) and row["started_at"].utcoffset() is not None)
        if row["status"] == "completed":
            _require(row["finished_at"].utcoffset() is not None and row["finished_at"] >= row["started_at"])
            if row["kind"] == "model":
                response = assistant_from(row["output"])
                _require(fingerprint(assistant_output(response)) == fingerprint(row["output"]))
                _require(fingerprint(response.usage) == fingerprint(row["usage"]))
            else:
                ToolResult.model_validate(row["output"])
        else:
            _require(row is rows[-1] and row["output"] is None and row["finished_at"] is None and row["usage"] == {})
    return rows


def _ingress(repo: PostgresRepository, connection: Any, run: dict) -> list[dict]:
    request, owner, subject = run["request"], run["owner"], run["subject"]
    _require(run["thread_id"] == "life:" + subject and request.get("incognito") is False)
    AgentRegenerator(repo)._proven_request(connection, run, run)
    identifiers = request.get("source_message_ids")
    rows = ingress_sources(repo, owner, subject, run["thread_id"], identifiers)
    _require([row["id"] for row in rows] == identifiers and rows[-1]["id"] == request["source_message_id"])
    _require(source_segments(rows) == request.get("source_segments") and rows[-1]["content"] == request["message"])
    adopted = connection.execute(
        sql.SQL(
            "SELECT 1 FROM {} WHERE owner=%s AND kind='request' AND status='active' "
            "AND data->>'ingress'='thread_inbox' AND data->>'parent_run_id'=%s "
            "AND data->>'inbox_state'='adopted' AND data->>'claim_epoch'=%s LIMIT 1"
        ).format(repo.table("core_entities")),
        (owner, run["id"], str(run["retry_epoch"])),
    ).fetchone()
    _require(adopted is None)  # Adopted inbox authority currently has a lease-bearing native API.
    return rows


def _source(run: dict, args: dict, versions: dict, originals: list[dict], revocations: list[dict]):
    source = next((row for row in originals if row["id"] == args["message_id"]), None)
    _require(source is not None)
    source_policy(source, run["subject"], run["thread_id"])
    _require(versions.get("message:" + source["id"]) == source["revision"] and args["id"] in source["case_ids"])
    start, end = source_span(source, args["quote"], None, None)
    for row in revocations:
        span = row["metadata"]
        _require(
            not (
                row["kind"] == "message"
                and row["entity_id"] == source["id"]
                or row["kind"] == "source_span"
                and span.get("message_id") == source["id"]
                and max(start, span["start"]) < min(end, span["end"])
            )
        )
    return source, start, end


def _request(ledger: RequestLedger, run: dict, step: dict) -> tuple[Any, dict]:
    repo = ledger.repo
    saved = _saved(repo, run, ledger._id(run["id"], run["retry_epoch"], step["seq"]), "agent-model-request-v1")
    call = ledger._load(run["owner"], run["id"], run["retry_epoch"], step["seq"])
    _require(call is not None and set(saved["output"]) == {"budget", "choice", "versions", "plan", "role", "name"})
    _require(
        saved.get("stage") == "agent_model_request"
        and saved.get("seq") == step["seq"]
        and saved.get("input_fp") == step["input_fp"]
        and step["name"] in {"", "revision", "critic"}
        and call.name == step["name"]
        and call.role == ("critic" if step["name"] == "critic" else "primary")
        and call.choice in {"auto", "required"}
        and call.plan.source_versions == call.versions
    )
    identity = dict(
        messages=[asdict(message) for message in call.budget.messages],
        tools=[asdict(tool) for tool in call.budget.tools],
        tool_choice=call.choice,
        source_versions=call.versions,
    )
    _require(input_fingerprint("model", call.name, identity) == step["input_fp"])
    return call, saved


def _intent(repo, connection, run, rows, base, sequence, originals, revocations) -> CaseEffectIntent:
    prefix = [row for row in rows if row["seq"] <= sequence]
    _require(prefix and prefix[-1]["seq"] == sequence)
    step = prefix[-1]
    _step_state(step, sequence, False)
    operation = f"run:{run['id']}:e{run['retry_epoch']}:s{sequence}"
    mutation = connection.execute(
        sql.SQL("SELECT * FROM {} WHERE owner=%s AND operation='agent_case_update' AND request_key=%s").format(
            repo.table("core_mutation_requests")
        ),
        (run["owner"], operation),
    ).fetchone()
    _require(mutation is not None)
    args, versions = _original_call(repo, run, prefix, base)
    result = ToolResult.model_validate(step["output"])
    _require(result.ok and not result.ends_turn)
    _check_intent(run, base, args, versions, result.receipt, mutation)
    source, start, end = _source(run, args, versions, originals, revocations)
    return CaseEffectIntent(run, base, args, versions, prefix, mutation, operation, source, start, end)


def _chains(repo, connection, run, rows, base, cases, originals, revocations) -> list[Any]:
    evidence = []
    for ident, sequences in cases.items():
        current = repo.get(run["owner"], "case", ident, include_deleted=True)
        alias = next(
            (value for value in base.alias_map.values() if value["kind"] == "case" and value["id"] == ident), None
        )
        _require(alias is not None and len(sequences) == current["revision"] - alias["revision"])
        _require(
            current["subject_id"] == run["subject"] and current["status"] not in {"deleted", "stopped", "superseded"}
        )
        _require(not repo.is_revoked(run["owner"], "case", ident))
        _require(base.injected_versions.get(entity_dependency("case", ident)) == alias["revision"])
        previous = None
        for offset, sequence in enumerate(sequences):
            proof = _intent(repo, connection, run, rows, base, sequence, originals, revocations)
            before, after = verify_effect(repo, proof, sequence)
            _require(proof.args["id"] == ident and before["revision"] == alias["revision"] + offset)
            _require(previous is None or fingerprint(previous) == fingerprint(before))
            previous = after
            effect = repo.get(run["owner"], "runtime_step", effect_id(run["id"], run["retry_epoch"], sequence))
            operation = connection.execute(
                sql.SQL("SELECT * FROM {} WHERE owner=%s AND operation_id=%s").format(repo.table("core_operations")),
                (run["owner"], proof.operation + ":case"),
            ).fetchone()
            evidence.append([asdict(proof), effect, operation])
        _require(run["state_version"].get(entity_dependency("case", ident)) == current["revision"])
        _require(fingerprint(previous) == fingerprint(current))
        _complete_steps(repo, run, current, sequences)
        evidence.append(current)
    return evidence


def _versions(repo, run, base, versions, model_seq, cases) -> list[dict]:
    _require(type(versions) is dict and versions and "message:" + run["request"]["source_message_id"] in versions)
    entities = []
    for key, revision in versions.items():
        _require(type(key) is str and type(revision) is int and revision >= 1)
        kind, separator, ident = lineage_key(key).partition(":")
        _require(separator and ident and kind not in {"owner", "global", "subject"})
        _require(key == entity_dependency(kind, ident))
        row = repo.get(run["owner"], kind, ident, include_deleted=True)
        _require(row["subject_id"] == run["subject"] and row["status"] not in {"deleted", "stopped", "superseded"})
        _require(row["case_id"] is None or row["case_id"] in run["request"].get("case_ids", []))
        _require(not repo.is_revoked(run["owner"], kind, ident))
        if kind == "case" and ident in cases:
            initial = base.injected_versions.get(key)
            _require(type(initial) is int and initial >= 1)
            _require(revision == initial + sum(sequence < model_seq for sequence in cases[ident]))
            _require(row["revision"] == initial + len(cases[ident]))
        else:
            _require(row["revision"] == revision)
        entities.append(row)
    return entities


def _read(ledger, connection, owner, run_id, epoch, seq) -> tuple[str, str, str]:
    repo = ledger.repo
    run = repo.fetch_run(owner, run_id)
    _require(
        run["id"] == run_id
        and run["owner"] == run["owner_user_id"] == owner
        and run["subject"] == run["subject_id"]
        and run["status"] == "running"
        and run["runtime"] == "v4"
        and type(run["retry_epoch"]) is int
        and run["retry_epoch"] == epoch
        and run["cancel_requested_at"] is None
        and (run["deadline_at"] is None or run["deadline_at"] > get_clock().now())
    )
    scope = repo.assert_scope(owner, run["subject"])
    rows = _steps(repo, connection, run)
    selected = next((row for row in rows if row["seq"] == seq), None)
    _require(selected is not None and selected["kind"] == "model" and selected["status"] == "completed")
    originals, revocations = _ingress(repo, connection, run), repo.revocations(owner)
    base = _initial(repo, run)
    frozen = _saved(repo, run, f"{run_id}:e{epoch}:agent_initial_context", "agent-initial-context-v1")
    _require(frozen.get("privacy_sha256") == AgentSnapshotStore(repo)._privacy(owner, base.injected_versions))
    cases = marker_cases(run) or {}
    effects = _chains(repo, connection, run, rows, base, cases, originals, revocations)
    entities = _versions(repo, run, base, base.injected_versions, 0, cases)
    requests, selected_hash = [], None
    for step in rows:
        if step["kind"] != "model":
            continue
        call, saved = _request(ledger, run, step)
        entities.extend(_versions(repo, run, base, call.versions, step["seq"], cases))
        requests.append(saved)
        if step["seq"] == seq:
            selected_hash = saved["output_sha256"]
    thread = repo.get(owner, "thread", run["thread_id"])
    ingress_operation = connection.execute(
        sql.SQL("SELECT * FROM {} WHERE owner=%s AND operation_id=%s").format(repo.table("core_operations")),
        (owner, "thread-inbox:" + run_id),
    ).fetchone()
    digest = fingerprint(
        [run, scope, thread, ingress_operation, rows, originals, revocations, frozen, requests, effects, entities]
    )
    return run["subject"], selected_hash, digest
