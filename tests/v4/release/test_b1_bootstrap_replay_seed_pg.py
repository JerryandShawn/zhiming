from __future__ import annotations

import json

import pytest
from b1_bootstrap_replay_seed_support import seed_db  # noqa: F401

from tools.b1_bootstrap_replay_fixture import PRIVATE_CHECKPOINT, REPLY, SCHEMA4, SOURCE_TEXT, SeedBlocked
from tools.b1_bootstrap_replay_observe import observe
from tools.b1_bootstrap_replay_seed import run_worker


def test_actual_schema4_seed_and_export_but_withdrawal_is_atomic_candidate_blocker(seed_db):  # noqa: F811
    seeded = run_worker(seed_db.request())
    assert seeded["checksums"] == SCHEMA4 and seeded["admissible"] is False
    assert seeded["models"] == seeded["sends"] == 0 and seeded["at"].endswith("+08:00")
    assert seeded["checkpoints"]["checkpoints"] == 1
    assert seeded["checkpoints"]["checkpoint_blobs"] == 1
    assert seeded["details"]["protected_receipts"] == 2
    ids = seeded["ids"]
    with seed_db.connect() as conn:
        assert conn.execute("SELECT result FROM mingjing_core.core_runs WHERE id='synthetic-run'").fetchone()[
            "result"
        ] == {"answer": REPLY}
        assert (
            conn.execute(
                "SELECT data->>'content' AS value FROM mingjing_core.core_entities WHERE id=%s", (ids["source"],)
            ).fetchone()["value"]
            == SOURCE_TEXT
        )
    before = observe(seed_db.request(), checkpoint=True)
    with pytest.raises(SeedBlocked, match="SEED_PINNED_UNDEFINEDTABLE_CORE_EMBEDDINGS"):
        run_worker(seed_db.request("withdraw"), seeded)
    after = observe(seed_db.request(), checkpoint=True)
    assert before == after and after["state_sha256"] == seeded["state_sha256"]
    public = json.dumps(seeded)
    assert SOURCE_TEXT not in public and PRIVATE_CHECKPOINT not in public and REPLY not in public
    with seed_db.connect() as conn:
        rows = conn.execute(
            "SELECT id,status,data FROM mingjing_core.core_entities WHERE id=ANY(%s)", ([ids["source"], ids["fact"]],)
        ).fetchall()
        assert len(rows) == 2 and all(row["status"] == "active" for row in rows)
        assert conn.execute("SELECT count(*) AS n FROM mingjing_core.tarot_draws").fetchone()["n"] == 1
        assert conn.execute("SELECT count(*) AS n FROM mingjing_core.core_model_charges").fetchone()["n"] == 0
        assert {
            row["version"]: row["checksum"]
            for row in conn.execute("SELECT version,checksum FROM mingjing_core.schema_migrations")
        } == {int(key): value for key, value in SCHEMA4.items()}


@pytest.mark.parametrize(
    "query,code",
    [
        (
            "INSERT INTO mingjing_core.core_entities(owner,kind,id,subject,data) "
            "VALUES('primary','message','extra','self','{}')",
            "INITIAL_ENTITIES",
        ),
        ("INSERT INTO mingjing_core.core_owners(id) VALUES('extra')", "OWNER_SET"),
        ("UPDATE mingjing_core.core_runs SET request='{\"extra\":true}'", "INITIAL_RUNS"),
        ("UPDATE mingjing_core.delivery_outbox SET status='pending' WHERE id='synthetic-uncertain'", "RECEIPT_CONTENT"),
    ],
)
def test_uncompiled_source_is_rejected_before_setup_or_write(seed_db, query, code):  # noqa: F811
    with seed_db.connect() as conn:
        conn.execute(query)
    before = observe(seed_db.request(), checkpoint=False)["state_sha256"]
    with pytest.raises(SeedBlocked, match=code):
        run_worker(seed_db.request())
    assert observe(seed_db.request(), checkpoint=False)["state_sha256"] == before


def test_repeated_seed_is_not_silently_overwritten(seed_db):  # noqa: F811
    value = run_worker(seed_db.request())
    before = observe(seed_db.request(), checkpoint=True)["state_sha256"]
    with pytest.raises(SeedBlocked, match="TABLE_SET"):
        run_worker(seed_db.request())
    assert observe(seed_db.request(), checkpoint=True)["state_sha256"] == before == value["state_sha256"]


def test_changed_source_even_rehashed_receipt_is_not_a_synthetic_permission(seed_db):  # noqa: F811
    value = run_worker(seed_db.request())
    with seed_db.connect() as conn:
        conn.execute(
            "UPDATE mingjing_core.core_entities SET data=jsonb_set(data,'{content}','\"other text\"') WHERE id=%s",
            (value["ids"]["source"],),
        )
    changed = observe(seed_db.request(), checkpoint=True)["state_sha256"]
    value["state_sha256"] = changed
    with pytest.raises(SeedBlocked, match="ENTITY_PROVENANCE"):
        run_worker(seed_db.request("withdraw"), value)
    assert observe(seed_db.request(), checkpoint=True)["state_sha256"] == changed


@pytest.mark.parametrize(
    "change,code",
    [
        ({"operation_id": "b1-wrong-operation"}, "RECEIPT_SCOPE"),
        ({"phase": "withdraw"}, "PRIOR_PHASE"),
        ({"checksums": {}}, "RECEIPT_SCHEMA4"),
        ({"admissible": True}, "RECEIPT_SCHEMA4"),
        ({"models": 1}, "RECEIPT_LOCAL_ONLY"),
        ({"unknown": "extra"}, "RECEIPT_FIELDS"),
        ({"state_sha256": "0" * 64}, "PRIOR_STATE_CHANGED"),
    ],
)
def test_foreign_or_mutated_prior_receipt_never_authorizes_withdrawal(seed_db, change, code):  # noqa: F811
    value = run_worker(seed_db.request())
    before = observe(seed_db.request(), checkpoint=True)["state_sha256"]
    with pytest.raises(SeedBlocked, match=code):
        run_worker(seed_db.request("withdraw"), dict(value, **change))
    assert observe(seed_db.request(), checkpoint=True)["state_sha256"] == before


@pytest.mark.parametrize(
    "query,code",
    [
        ("UPDATE mingjing_core.core_operations SET fingerprint=repeat('0',64) WHERE kind='fact'", "OPERATION"),
        ("UPDATE mingjing_core.core_runs SET request='{}' WHERE id<>'synthetic-run'", "RUN_PROVENANCE"),
        (
            "UPDATE mingjing_core.core_entities SET data=jsonb_set(data,'{source_refs}','[]') WHERE kind='fact'",
            "ENTITY_PROVENANCE",
        ),
        ("INSERT INTO mingjing_core.core_versions VALUES('primary','unknown:extra',1)", "SEED_VERSIONS"),
        ("UPDATE mingjing_core.core_versions SET revision=2 WHERE dependency='global:self'", "SEED_VERSIONS"),
    ],
)
def test_seed_lineage_mutations_are_not_authorized_by_rehashing(seed_db, query, code):  # noqa: F811
    value = run_worker(seed_db.request())
    with seed_db.connect() as conn:
        conn.execute(query)
    before = observe(seed_db.request(), checkpoint=True)["state_sha256"]
    value["state_sha256"] = before
    with pytest.raises(SeedBlocked, match=code):
        run_worker(seed_db.request("withdraw"), value)
    assert observe(seed_db.request(), checkpoint=True)["state_sha256"] == before


def test_other_live_connection_is_rejected_without_setup(seed_db):  # noqa: F811
    before = observe(seed_db.request(), checkpoint=False)["state_sha256"]
    with seed_db.connect(), pytest.raises(SeedBlocked, match="OTHER_SESSIONS"):
        run_worker(seed_db.request())
    assert observe(seed_db.request(), checkpoint=False)["state_sha256"] == before
