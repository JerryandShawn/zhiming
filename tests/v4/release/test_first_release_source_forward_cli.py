"""Actual local SourceForward CLI validation and one nonempty prefix7 native chain."""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import asdict
from pathlib import Path

import psycopg
import pytest
from first_release_support import contract_document, pin_document, write_json
from test_first_release_capture_replay_chain_pg import fact_state
from test_first_release_incremental_backup_pg import archive as shared_archive
from test_first_release_incremental_backup_pg import state
from test_first_release_incremental_forward_pg import materials
from test_first_release_source_backfill_chain_pg import (
    assert_history,
    assert_privacy_and_closed,
    backfill_pin,
    candidate_paths,
    owner_rows,
    reviewed_pin,
)
from test_first_release_source_backfill_chain_pg import proposal_fixture as shared_proposal
from test_first_release_source_backfill_chain_pg import source_fixture as shared_existing

from tools import first_release_source_forward as cli

FLAGS = (
    "pin",
    "contract",
    "dump-pin",
    "dump",
    "pg-restore",
    "capture-inputs",
    "capture-pin",
    "candidate-python",
    "replay-ledger",
    "replay-pin",
    "target-proof-pin",
    "controller-runtime-pin",
    "forward-pin",
    "source-replay-pin",
    "source-backfill-pin",
)


@pytest.fixture(scope="module", name="archive")
def archive_fixture():
    return shared_archive.__wrapped__()


@pytest.fixture(name="existing")
def source_fixture(request, archive):
    yield from shared_existing.__wrapped__(request, archive)


@pytest.fixture(name="proposal")
def proposal_fixture(existing):
    yield from shared_proposal.__wrapped__(existing)


def pin_json(pin, schema):
    value = asdict(pin)
    for name in ("controls", "locks", "source_migrations"):
        if name in value:
            value[name] = dict(value[name])
    return dict(value, schema=schema)


def arguments(proposal, folder):
    request = proposal.request
    replay = reviewed_pin(request)
    backfill = backfill_pin(request, replay)
    candidate_paths(request, backfill)
    target = request.target
    documents = {
        "pin": pin_document(target.release),
        "contract": contract_document(target.contract),
        "dump-pin": pin_json(target.dump_pin, "first-release-local-dump-pin-v1"),
        "capture-pin": pin_json(request.capture.pin, "first-release-local-capture-binding-pin-v1"),
        "replay-pin": dict(
            request.replay.preflight.pin,
            schema="first-release-local-replay-pin-v1",
            effects_sha256=request.replay.effects_sha256,
        ),
        "target-proof-pin": pin_json(request.target_pin, "first-release-local-target-proof-pin-v1"),
        "controller-runtime-pin": pin_json(request.runtime_pin, "first-release-controller-runtime-pin-v1"),
        "forward-pin": pin_json(request.pin, "first-release-local-source-forward-pin-v1"),
        "source-replay-pin": pin_json(replay, "first-release-local-source-replay-pin-v1"),
        "source-backfill-pin": pin_json(backfill, "first-release-local-source-backfill-pin-v1"),
    }
    paths = {
        "dump": target.dump,
        "pg-restore": target.pg_restore,
        "capture-inputs": request.capture.capture_inputs,
        "candidate-python": request.replay.preflight.python,
        "replay-ledger": request.replay.preflight.ledger,
    }
    for name, value in documents.items():
        paths[name] = folder / (name + ".json")
        write_json(paths[name], value)
    return [part for name in FLAGS for part in ("--" + name, str(paths[name]))]


def no_effects(patch):
    def forbidden(*args, **kwargs):
        pytest.fail("CLI_DEFAULT_OR_INVALID_INPUT_MUST_NOT_CONNECT_SPAWN_OR_WRITE")

    original = Path.open

    def read_only(path, mode="r", *args, **kwargs):
        if any(flag in mode for flag in "wax+"):
            forbidden()
        return original(path, mode, *args, **kwargs)

    for obj, name in (
        (psycopg, "connect"),
        (subprocess, "run"),
        (subprocess, "Popen"),
        (os, "open"),
        (Path, "mkdir"),
        (Path, "write_text"),
        (Path, "write_bytes"),
    ):
        patch.setattr(obj, name, forbidden)
    patch.setattr(Path, "open", read_only)


def output(capsys):
    captured = capsys.readouterr()
    assert not captured.err
    return json.loads(captured.out)


def test_default_and_bad_or_missing_pin_inputs_stop_before_effects(tmp_path, monkeypatch, capsys):
    malformed = tmp_path / "malformed.json"
    write_json(malformed, {"schema": "not-a-release-pin", "dsn": "SYNTHETIC_PRIVATE_SENTINEL"})
    all_arguments = [part for name in FLAGS for part in ("--" + name, str(malformed))]
    with monkeypatch.context() as patch:
        no_effects(patch)
        for argv in (
            [],
            ["--apply-source-local"],
            all_arguments[:-2],
            all_arguments,
            all_arguments + ["--apply-source-local"],
        ):
            assert cli.main(argv) == 2
            public = output(capsys)
            assert public["status"] == "blocked" and public["automatic_cleanup"] is False
            assert set(public) <= {"status", "code", "phase", "session_restored", "automatic_cleanup"}
            assert re.fullmatch(r"[A-Z][A-Z0-9_]{0,119}", public["code"])
            assert "SYNTHETIC_PRIVATE_SENTINEL" not in json.dumps(public)


@pytest.mark.parametrize("existing", [7], indirect=True)
def test_main_validates_then_applies_one_real_nonempty_source_chain(
    proposal, tmp_path, monkeypatch, capsys, record_property
):
    source = proposal.case.source
    before = fact_state(source.environment["FIRST_INCREMENTAL_OWNER_DSN"], source.native_state)
    assert before["prefix"] == 7 and before["run_status"] == "stale" and before["checkpoint_counts"] == [1, 1, 1]
    bob = owner_rows(source.environment["FIRST_INCREMENTAL_OWNER_DSN"], "bob")
    prior, material = state(source), materials(proposal.case)
    argv = arguments(proposal, tmp_path)
    monkeypatch.chdir(proposal.request.source.workspace)
    for name, value in proposal.request.environment.items():
        monkeypatch.setenv(name, value)
    with monkeypatch.context() as patch:
        no_effects(patch)
        assert cli.main(argv) == 0
        validated = output(capsys)
    assert validated["database_connections"] == validated["processes"] == validated["file_writes"] == 0
    assert validated["source_forward_completed"] is False and validated["backfill_pending"] is True
    assert state(source) == prior and materials(proposal.case) == material
    assert cli.main(argv + ["--apply-source-local"]) == 0
    result = output(capsys)
    assert result["phase"] == "source_backfill_completed" and result["source_forward_completed"] is True
    assert result["privacy_replay_pending"] is result["backfill_pending"] is False
    assert result["target_proof"]["target_proof_consumed"] is True
    assert result["controller_runtime"]["controller_runtime_verified"] is True
    assert result["owner_postcheck"]["original_fields_verified"] is True
    assert result["writer_postcheck"]["quota_tables_checked"] == 4
    replay, backfill = result["source_replay"], result["source_backfill"]
    assert replay["source_replay_completed"] is replay["parent_final_state_verified"] is True
    assert backfill["source_backfill_completed"] is backfill["parent_final_state_verified"] is True
    assert backfill["all_owners_verified"] is backfill["central_unchanged"] is True
    assert backfill["physical_connections"] == 1
    assert backfill["candidate"] == source.inputs.release.candidate
    assert backfill["preview"]["assistant_created"] == backfill["first"]["assistant_created"] == 2
    assert backfill["first"]["message_metadata"] >= 2 and backfill["first"]["search_tokens"] >= 2
    assert all(backfill["second"][key] == 0 for key in ("message_metadata", "search_tokens", "assistant_created"))
    assert backfill["state_before_sha256"] != backfill["state_after_sha256"]
    assert_history(source)
    assert_privacy_and_closed(source, before, bob, result)
    assert materials(proposal.case) == material and source.inputs.maintenance.is_file()
    record_property("actual_candidate", source.inputs.release.candidate)
    record_property("actual_entry", "first_release_source_forward.main")
    record_property("native_history_backfilled", 2)
    record_property("backfill_second_write_counts", "0/0/0")
    record_property("native_checkpoint_counts", "1/1/1->0/0/0")
