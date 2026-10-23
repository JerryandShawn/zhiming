"""A real candidate migration and restore must not revive a withdrawn legacy body."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import uuid
from pathlib import Path

import pytest
from first_release_support import ROOT, write_json
from test_first_release_candidate_preflight_pg import candidate as shared_candidate
from test_first_release_candidate_replay_pg import pinned
from test_first_release_local_restore_pg import sample as shared_sample

from tools import first_release_candidate_process as process
from tools import first_release_local_restore as restore
from tools.first_release_contracts import RestoreRejected

OWNER = "synthetic-legacy-replay"
LEGACY_ID = "synthetic-withdrawn-memory"
BODY = "SYNTHETIC_LEGACY_REPLAY_PRIVATE_BODY"
FIXED = "93886bbbadc5048e8269c0537e278dc0c12886e9"
OLD = "144b81eeed3e792221393673bd611637fbaae01f"
NATIVE = """import hashlib,importlib,json,os,pathlib,runpy,sys
value=json.load(sys.stdin)
path=pathlib.Path(value['worker'])
assert hashlib.sha256(path.read_bytes()).hexdigest()==value['pin']['worker_sha256']
worker=runpy.run_path(str(path),run_name='candidate_test_support')
root=pathlib.Path(value['root'])
raw=(root/'__release_manifest__.json').read_bytes()
assert hashlib.sha256(raw).hexdigest()==value['pin']['manifest_sha256']
manifest=json.loads(raw)
assert manifest['commit']==value['pin']['candidate']
files=manifest['files']
worker['verified'](root/'migration_core.py',root,files)
sys.meta_path.insert(0,worker['CandidateFinder'](root,files))
sys.path.insert(0,str(root))
sites,_=worker['runtime'](value,root)
migration=importlib.import_module('migration_core')
worker['verified'](migration.__file__,root,files)
for name in ('migrate','_migrate','plan','source_manifest'):
    worker['verified'](getattr(migration,name).__code__.co_filename,root,files)
repository=importlib.import_module('mingjing_core.repositories.postgres')
deployment=importlib.import_module('tools.deploy_core')
repo=repository.PostgresRepository(os.environ['NATIVE_LOCAL_DSN'],initialize=False,max_size=1)
try:
    if value['action']=='migrate':
        report=migration.migrate(pathlib.Path(value['legacy_source']),value['owner'],repository=repo,apply=True)
        assert report['errors']==[] and report['source_unchanged'] is True
    mapping=repo.legacy_mapping(value['owner'],'memories',value['legacy_id'],'fact')
    assert mapping and mapping['result_id']
    with repo.transaction(value['owner']) as connection:
        rows=connection.execute(
            'SELECT kind,status,data FROM mingjing_core.core_entities WHERE owner=%s AND id=%s',
            (value['owner'],mapping['result_id']),
        ).fetchall()
    assert len(rows)==1
    entity=rows[0]
    if value['seed']:
        repo.put(value['owner'],'note','synthetic-native-derived-note',
                 {'content':'SYNTHETIC_DERIVED_BODY','source_ids':[mapping['result_id']]},expected_revision=0)
        with repo.transaction(value['owner']) as connection:
            connection.execute(
                "INSERT INTO mingjing_core.core_embeddings(owner,kind,entity_id,chunk,model,vec,content_fp) "
                "VALUES(%s,%s,%s,0,'synthetic-local',ARRAY[0.1,0.2]::real[],%s)",
                (value['owner'],entity['kind'],mapping['result_id'],'a'*64))
    note=repo.get(value['owner'],'note','synthetic-native-derived-note',include_deleted=True)
    with repo.transaction(value['owner']) as connection:
        embeddings=connection.execute(
            'SELECT count(*) AS n FROM mingjing_core.core_embeddings WHERE owner=%s AND entity_id=%s',
            (value['owner'],mapping['result_id'])).fetchone()['n']
    result={'candidate':manifest['commit'],'mapping_kind':mapping['kind'],
            'mapping_status':mapping['status'],'entity_kind':entity['kind'],
            'entity_status':entity['status'],'body_present':bool(entity['data'].get('content')),
            'data_empty':entity['data']=={},'document':deployment.export_withdrawals(repo),
            'derived_status':note['status'],'derived_body_present':bool(note.get('content')),
            'embedding_count':embeddings}
    worker['third_party_origins'](sites)
    result['candidate_modules_checked']=worker['business_origins'](root,files)
finally:
    repo.close()
print(json.dumps(result,sort_keys=True))
"""


@pytest.fixture(scope="module", name="canonical_source")
def source_fixture(request):
    ref = getattr(request, "param", FIXED)
    assert ref in {FIXED, OLD}
    environment = {key: os.environ[key] for key in ("PATH", "SystemRoot", "WINDIR", "TEMP", "TMP") if key in os.environ}
    head = (
        subprocess.run(["git", "rev-parse", ref], cwd=ROOT, env=environment, capture_output=True, check=True)
        .stdout.decode()
        .strip()
    )
    assert head == ref
    archive = subprocess.run(
        ["git", "archive", "--format=tar", head], cwd=ROOT, env=environment, capture_output=True, check=True
    ).stdout
    return head, archive


@pytest.fixture(name="sample")
def sample_fixture(request, tmp_path_factory):
    yield from shared_sample.__wrapped__(request, tmp_path_factory)


@pytest.fixture(name="candidate")
def candidate_fixture(sample, canonical_source):
    yield from shared_candidate.__wrapped__(sample, canonical_source)


def native(candidate, legacy_source: Path, dsn: str, action: str, *, seed: bool = False) -> dict:
    sample, request = candidate
    document = json.loads(request.ledger.read_text(encoding="utf-8"))
    payload = process._payload(request, sample.inputs, document)
    payload.update(action=action, seed=seed, legacy_source=str(legacy_source), owner=OWNER, legacy_id=LEGACY_ID)
    environment = process._environment(dsn)
    environment["NATIVE_LOCAL_DSN"] = dsn
    result = subprocess.run(
        [str(request.python), "-I", "-B", "-X", "pycache_prefix=" + os.path.abspath(os.devnull), "-c", NATIVE],
        input=json.dumps(payload),
        env=environment,
        capture_output=True,
        encoding="utf-8",
        timeout=120,
        shell=False,
    )
    assert result.returncode == 0, "NATIVE_CANDIDATE_MIGRATION_OR_OBSERVATION_FAILED_PRIVATE_DETAILS_WITHHELD"
    observed = json.loads(result.stdout)
    assert observed["candidate"] == sample.inputs.release.candidate
    assert observed["candidate_modules_checked"] > 0
    return observed


def sqlite_memory(directory: Path, *, inactive: bool = False) -> None:
    directory.mkdir(exist_ok=True)
    with sqlite3.connect(directory / "web.db") as connection:
        if inactive:
            connection.execute("UPDATE memories SET status='deleted' WHERE id=?", (LEGACY_ID,))
        else:
            connection.execute(
                "CREATE TABLE memories(id TEXT,text TEXT,quote TEXT,category TEXT,source_turn TEXT,status TEXT)"
            )
            connection.execute(
                "INSERT INTO memories VALUES(?,?,?,?,?,?)", (LEGACY_ID, BODY, BODY, "背景", "missing", "active")
            )


def summary(result: dict) -> dict:
    return {name: value for name, value in result.items() if name != "document"}


def prepare(candidate, tmp_path):
    sample, _ = candidate
    legacy = tmp_path / "native-legacy-source"
    sqlite_memory(legacy)
    original = native(candidate, legacy, sample.source, "migrate", seed=True)
    assert (original["mapping_kind"], original["mapping_status"], original["entity_kind"]) == (
        "fact",
        "legacy_unverified",
        "legacy",
    )
    assert original["entity_status"] == "pending" and original["body_present"] is True
    sample.dump()
    sqlite_memory(legacy, inactive=True)
    latest = native(candidate, legacy, sample.source, "migrate")
    revocations = next(row["revocations"] for row in latest["document"]["owners"] if row["owner_user_id"] == OWNER)
    assert [(row["kind"], row["entity_id"], row["operation"]) for row in revocations] == [
        ("legacy_memory", LEGACY_ID, "deleted")
    ]
    return legacy, original, latest, pinned(candidate, latest["document"])


def save_evidence(candidate, original, latest, restored, *, proof=None, rejected=None):
    sample, _ = candidate
    evidence = ROOT / "private" / ("legacy-native-replay-" + uuid.uuid4().hex)
    evidence.mkdir(parents=True)
    write_json(
        evidence / "metadata.json",
        {
            "candidate": sample.inputs.release.candidate,
            "original": summary(original),
            "latest": summary(latest),
            "restored": summary(restored),
            "rejected": rejected,
            "proof": proof,
            "real_models": 0,
            "external_sends": 0,
            "servers": 0,
        },
    )
    return evidence


@pytest.mark.parametrize("sample", [7], indirect=True)
@pytest.mark.parametrize("canonical_source", [FIXED], indirect=True)
def test_native_legacy_tombstone_erases_mapped_body_after_candidate_replay(candidate, tmp_path):
    sample, _ = candidate
    legacy, original, latest, request = prepare(candidate, tmp_path)
    result = restore.execute(
        sample.inputs, apply_local=True, upgrade_local=True, withdrawals_replay=request, environment=sample.environment
    )
    proof = result["withdrawals_replay"]
    restored = native(candidate, legacy, sample.environment["FIRST_RELEASE_OWNER_DSN"], "observe")
    save_evidence(candidate, original, latest, restored, proof=proof)
    assert proof["second_apply_unchanged"] is True
    assert proof["state_first_sha256"] == proof["state_second_sha256"]
    assert proof["checks"]["legacy_markers_checked"] == proof["checks"]["legacy_targets_checked"] == 1
    assert proof["checks"]["legacy_derivatives_checked"] == 1
    assert proof["checks"]["legacy_embedding_scopes_checked"] == 2
    assert restored["entity_status"] == "deleted" and restored["data_empty"] and not restored["body_present"], (
        "WITHDRAWN_NATIVE_LEGACY_BODY_SURVIVED:" + json.dumps(summary(restored), sort_keys=True)
    )
    assert restored["derived_status"] == "deleted" and not restored["derived_body_present"]
    assert restored["embedding_count"] == 0


@pytest.mark.parametrize("sample", [7], indirect=True)
@pytest.mark.parametrize("canonical_source", [OLD], indirect=True)
def test_old_native_candidate_is_rejected_for_surviving_legacy_body(candidate, tmp_path):
    sample, _ = candidate
    legacy, original, latest, request = prepare(candidate, tmp_path)
    with pytest.raises(RestoreRejected, match="^REPLAY_ERASURE_FAILED$"):
        restore.execute(
            sample.inputs,
            apply_local=True,
            upgrade_local=True,
            withdrawals_replay=request,
            environment=sample.environment,
        )
    restored = native(candidate, legacy, sample.environment["FIRST_RELEASE_OWNER_DSN"], "observe")
    save_evidence(candidate, original, latest, restored, rejected="REPLAY_ERASURE_FAILED")
    assert restored["entity_status"] == "pending" and restored["body_present"] and not restored["data_empty"]
    assert restored["derived_status"] == "active" and restored["derived_body_present"]
    assert restored["embedding_count"] == 1
