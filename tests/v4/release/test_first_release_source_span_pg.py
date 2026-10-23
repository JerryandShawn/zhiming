"""A native correction ledger independently erases one span while retaining the original."""

from __future__ import annotations

import json
import os
import subprocess
import uuid

import pytest
from first_release_support import ROOT, write_json
from test_first_release_candidate_replay_pg import observe, pinned
from test_first_release_legacy_tombstone_pg import FIXED
from test_first_release_legacy_tombstone_pg import candidate_fixture as candidate_fixture
from test_first_release_legacy_tombstone_pg import sample_fixture as sample_fixture
from test_first_release_legacy_tombstone_pg import source_fixture as source_fixture

from tools import first_release_candidate_process as process
from tools import first_release_local_restore as restore
from tools.first_release_contracts import RestoreRejected
from tools.first_release_replay_effects import snapshot
from mingjing_core.repositories.postgres import PostgresRepository

NATIVE = """import hashlib,importlib,json,os,pathlib,runpy,sys
value=json.load(sys.stdin)
path=pathlib.Path(value['worker'])
assert hashlib.sha256(path.read_bytes()).hexdigest()==value['pin']['worker_sha256']
worker=runpy.run_path(str(path),run_name='candidate_span_test_support')
root=pathlib.Path(value['root'])
raw=(root/'__release_manifest__.json').read_bytes()
assert hashlib.sha256(raw).hexdigest()==value['pin']['manifest_sha256']
manifest=json.loads(raw)
assert manifest['commit']==value['pin']['candidate']
sys.meta_path.insert(0,worker['CandidateFinder'](root,manifest['files']))
sys.path.insert(0,str(root))
sites,_=worker['runtime'](value,root)
repository=importlib.import_module('mingjing_core.repositories.postgres')
deployment=importlib.import_module('tools.deploy_core')
memory=importlib.import_module('mingjing_core.application.memory')
runtime=importlib.import_module('mingjing_core.runtime')
from psycopg.types.json import Jsonb
NIGHT='我不能上夜班'
WALK='我喜欢周末徒步'
TEXT=NIGHT+'。'+WALK+'。'

def fact_hash(repo,ident):
    with repo.transaction('alice') as connection:
        return connection.execute(
            "SELECT encode(sha256(convert_to(to_jsonb(e)::text,'UTF8')),'hex') AS value "
            "FROM mingjing_core.core_entities e WHERE owner='alice' AND kind='fact' AND id=%s",
            (ident,)).fetchone()['value']

def checkpoints(repo,run):
    saver=runtime.LangGraphRuntime(repo).checkpointer
    config={'configurable':{'thread_id':run['id']+':e0','checkpoint_ns':''}}
    checkpoint={'v':1,'id':'synthetic-span-checkpoint','ts':'2026-10-17T00:00:00+00:00',
                'channel_values':{'private':'SYNTHETIC_CHECKPOINT_BODY'},
                'channel_versions':{'private':'1'},'versions_seen':{}}
    saved=saver.put(config,checkpoint,{}, {'private':'1'})
    saver.put_writes(saved,[('synthetic-span-write','SYNTHETIC_CHECKPOINT_BODY')],'synthetic-span-task')

def seed(repo):
    for owner in ('alice','bob'):repo.ensure_owner(owner)
    service=memory.MemoryService(repo)
    original=service.receive('alice',content=TEXT,channel='synthetic',source_id='span-original',
                             at='2026-10-17T00:00:00+00:00')
    night=service.save_fact('alice','self',original['id'],NIGHT,'constraint')
    walk=service.save_fact('alice','self',original['id'],WALK,'preference')
    service.receive('bob',content='SYNTHETIC_OTHER_OWNER_BODY',channel='synthetic',source_id='other-owner')
    bob=repo.begin_run('bob','synthetic-bob-run',{'synthetic':'other-owner'},depth='fast')
    repo.fail_run('bob',bob['id'],'SYNTHETIC_FAILED',bob['lease_token'])
    note=repo.put('alice','note','synthetic-span-note',{'content':'SYNTHETIC_NOTE_BODY','fact_ids':[night['id']]})
    run=repo.begin_run('alice','synthetic-span-run',{'source_message_id':original['id'],'message':TEXT},depth='fast')
    repo.set_run_dependencies('alice',run['id'],{'message:'+original['id']:original['revision'],
                              'fact:'+night['id']:night['revision']},run['lease_token'])
    private=repo.put('alice','runtime_step','synthetic-span-private',
                     {'run_id':run['id'],'stage':'synthetic_fixture','output':{'text':'SYNTHETIC_STEP_BODY'}})
    repo.fail_run('alice',run['id'],'SYNTHETIC_FAILED',run['lease_token'])
    with repo.transaction('alice') as connection:
        connection.execute(
            "INSERT INTO mingjing_core.delivery_outbox(id,owner,subject,business_id,channel,target,run_id,"
            "payload,dependencies,status,attempts,due) VALUES('synthetic-span-pending','alice','self',"
            "'synthetic-span-pending','feishu','ou_synthetic',%s,%s,'{}','pending',0,now())",
            (run['id'],Jsonb({'text':'SYNTHETIC_UNSENT_BODY'})))
        for kind,ident in [('message',original['id']),('fact',night['id']),('fact',walk['id'])]:
            connection.execute(
                "INSERT INTO mingjing_core.core_embeddings(owner,kind,entity_id,chunk,model,vec,content_fp) "
                "VALUES('alice',%s,%s,0,'synthetic-local',ARRAY[0.1,0.2]::real[],%s)",(kind,ident,'a'*64))
    checkpoints(repo,run)
    return {'source':original['id'],'night':night['id'],'walk':walk['id'],'run':run['id'],'bob_run':bob['id'],
            'note':note['id'],'private':private['id'],'raw_sha256':hashlib.sha256(TEXT.encode()).hexdigest(),
            'walk_sha256':fact_hash(repo,walk['id'])}

def correct(repo,state):
    service=memory.MemoryService(repo)
    old=repo.get('alice','fact',state['night'])
    current=service.receive('alice',content='更正：我现在可以上白班',channel='synthetic',source_id='span-correction',
                            at='2026-10-18T00:00:00+00:00')
    new=service.correct_fact('alice',old['id'],current['id'],current['content'],expected_revision=old['revision'])
    return dict(state,corrected=new['id'],old_status=repo.get('alice','fact',old['id'])['status'])

def combine(repo,state):
    walk=repo.get('alice','fact',state['walk'])
    repo.delete('alice','fact',walk['id'],expected_revision=walk['revision'])
    return dict(state,combined=True)

def observation(repo,state):
    service=memory.MemoryService(repo)
    raw=service.get_source('alice',state['source'])
    projected=service.get_source('alice',state['source'],for_context=True)
    night=repo.get('alice','fact',state['night'],include_deleted=True)
    note=repo.get('alice','note',state['note'],include_deleted=True)
    private=repo.get('alice','runtime_step',state['private'],include_deleted=True)
    run=repo.fetch_run('alice',state['run'])
    with repo.transaction('alice') as connection:
        fts=connection.execute(
            "SELECT search @@ plainto_tsquery('simple','夜班') AS night,"
            "search @@ plainto_tsquery('simple','徒步') AS walk FROM mingjing_core.core_entities "
            "WHERE owner='alice' AND kind='message' AND id=%s",(state['source'],)).fetchone()
        outbox=connection.execute("SELECT status,payload,claim_token,lease_until FROM mingjing_core.delivery_outbox "
                                  "WHERE owner='alice' AND id='synthetic-span-pending'").fetchone()
        corrected=connection.execute("SELECT 1 FROM mingjing_core.core_entities WHERE owner='alice' "
                                     "AND kind='fact' AND id=%s",(state['corrected'],)).fetchone()
        embeddings=connection.execute("SELECT kind,entity_id FROM mingjing_core.core_embeddings "
                                       "WHERE owner='alice' ORDER BY kind,entity_id").fetchall()
    result={'raw_unchanged':hashlib.sha256(raw['content'].encode()).hexdigest()==state['raw_sha256'],
            'raw_status':raw['status'],'projected_correct':projected['content']=='[该资料已撤销]。'+WALK+'。',
            'night_absent_context':NIGHT not in projected['content'],'walk_present_context':WALK in projected['content'],
            'fts_night':fts['night'],'fts_walk':fts['walk'],'night_deleted':night['status']=='deleted' and 'content' not in night,
            'walk_unchanged':fact_hash(repo,state['walk'])==state['walk_sha256'],
            'note_deleted':note['status']=='deleted' and 'content' not in note,
            'private_deleted':private['status']=='deleted' and 'output' not in private,
            'run_revoked':run['status']=='revoked' and run['request']==run['checkpoint']=={} and run['result'] is None
                           and run['lease_token'] is run['lease_until'] is None,
            'outbox_cancelled':outbox=={'status':'cancelled','payload':{},'claim_token':None,'lease_until':None},
            'corrected_present':corrected is not None,'preserved_embedding_only':embeddings==[{'kind':'fact','entity_id':state['walk']}]}
    if state.get('combined'):
        walk=repo.get('alice','fact',state['walk'],include_deleted=True)
        result['walk_deleted']=walk['status']=='deleted' and 'content' not in walk
        result['all_embeddings_deleted']=embeddings==[]
        del result['walk_unchanged'],result['preserved_embedding_only']
    return result

def missing_observation(repo,state):
    with repo.transaction('alice') as connection:
        entities=connection.execute("SELECT count(*) AS n FROM mingjing_core.core_entities WHERE owner='alice' "
                                     "AND id=ANY(%s)",([state[name] for name in ('source','night','walk','corrected','note','private')],)).fetchone()['n']
        counts={table:connection.execute('SELECT count(*) AS n FROM mingjing_core.'+table+" WHERE owner='alice'")
                .fetchone()['n'] for table in ('core_runs','delivery_outbox','core_embeddings')}
        orphan=connection.execute("SELECT 1 FROM mingjing_core.core_entities WHERE owner='alice' "
                                  "AND kind='note' AND id='synthetic-span-orphan'").fetchone()
    return {'original_entities_absent':entities==0,'runtime_scopes_empty':all(n==0 for n in counts.values()),
            'orphan_present':orphan is not None}

repo=repository.PostgresRepository(os.environ['NATIVE_LOCAL_DSN'],initialize=False,max_size=1)
try:
    state=seed(repo) if value['action']=='seed' else value['state']
    if value['action']=='owners':
        for owner in ('alice','bob'):repo.ensure_owner(owner)
        state={}
    if value['action']=='correct':state=correct(repo,state)
    if value['action']=='combine':state=combine(repo,state)
    if value['action'] in ('orphan','malformed'):
        links=({'field_source_refs':{'field':state['source']}} if value['action']=='malformed'
               else {'source_ids':[state['source']]})
        repo.put('alice','note','synthetic-span-orphan',dict(content='SYNTHETIC_ORPHAN_BODY',**links))
    result={'state':state,'document':deployment.export_withdrawals(repo),'candidate':manifest['commit']}
    if value['action']=='observe':result['observed']=observation(repo,state)
    if value['action']=='missing_observe':result['observed']=missing_observation(repo,state)
    worker['third_party_origins'](sites)
    result['candidate_modules_checked']=worker['business_origins'](root,manifest['files'])
finally:repo.close()
print(json.dumps(result,sort_keys=True))
"""


def native(candidate, dsn, action, state=None):
    sample, request = candidate
    document = json.loads(request.ledger.read_text(encoding="utf-8"))
    payload = process._payload(request, sample.inputs, document)
    payload.update(action=action, state=state)
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
    assert result.returncode == 0, "NATIVE_SOURCE_SPAN_STEP_FAILED_PRIVATE_DETAILS_WITHHELD"
    value = json.loads(result.stdout)
    assert value["candidate"] == FIXED and value["candidate_modules_checked"] > 0
    return value


def save_evidence(folder, *, state, observed=None, proof=None, failure=None, other_owner_unchanged=None):
    write_json(
        folder / "metadata.json",
        dict(
            candidate=FIXED,
            state=state,
            observed=observed,
            proof=proof,
            failure=failure,
            other_owner_unchanged=other_owner_unchanged,
            real_models=0,
            external_sends=0,
            servers=0,
        ),
    )


def orphan_before_replay(candidate, state, monkeypatch, snapshots, *, malformed=False):
    original = process.candidate_replay

    def injected(request, inputs, dsns, creator):
        native(candidate, dsns["owner"], "malformed" if malformed else "orphan", state)
        repo = PostgresRepository(dsns["owner"], initialize=False, max_size=1)
        try:
            snapshots.append(snapshot(repo))
            try:
                return original(request, inputs, dsns, creator)
            finally:
                snapshots.append(snapshot(repo))
        finally:
            repo.close()

    monkeypatch.setattr(process, "candidate_replay", injected)


@pytest.mark.parametrize("sample", [7], indirect=True)
@pytest.mark.parametrize("canonical_source", [FIXED], indirect=True)
def test_native_correction_span_preserves_raw_and_independent_fact_through_real_restore(candidate, monkeypatch):
    sample, _ = candidate
    initial = native(candidate, sample.source, "seed")
    sample.dump()
    latest = native(candidate, sample.source, "correct", initial["state"])
    state = latest["state"]
    assert state["old_status"] == "superseded"
    revocations = next(row["revocations"] for row in latest["document"]["owners"] if row["owner_user_id"] == "alice")
    assert {row["kind"] for row in revocations} == {"source_span", "note"}
    assert [row["operation"] for row in revocations if row["kind"] == "source_span"] == ["superseded"]
    assert latest["document"]["delivery_receipts"] == []
    request = pinned(candidate, latest["document"])
    snapshots = []
    observe(monkeypatch, snapshots, {"id": state["bob_run"]})
    evidence = ROOT / "private" / ("source-span-native-" + uuid.uuid4().hex)
    evidence.mkdir(parents=True)
    save_evidence(evidence, state=state)
    try:
        result = restore.execute(
            sample.inputs,
            apply_local=True,
            upgrade_local=True,
            withdrawals_replay=request,
            environment=sample.environment,
        )
    except Exception as error:
        save_evidence(evidence, state=state, failure=type(error).__name__)
        raise
    observed = native(candidate, sample.environment["FIRST_RELEASE_OWNER_DSN"], "observe", state)["observed"]
    proof = result["withdrawals_replay"]
    save_evidence(
        evidence, state=state, observed=observed, proof=proof, other_owner_unchanged=snapshots[0] == snapshots[1]
    )
    assert snapshots[0] == snapshots[1]
    assert proof["state_first_sha256"] == proof["state_second_sha256"]
    checks = proof["checks"]
    assert checks["span_sources_checked"] == checks["span_facts_checked"] == checks["span_preserved_facts_checked"] == 1
    assert checks["span_runs_checked"] == checks["span_outbox_checked"] == 1
    assert checks["span_private_scopes_checked"] == 2 and checks["checkpoint_ranges_checked"] >= 3
    assert observed["raw_status"] == "active"
    assert observed["fts_night"] is observed["corrected_present"] is False
    assert all(
        value is True
        for name, value in observed.items()
        if name not in {"raw_status", "fts_night", "corrected_present"}
    )


@pytest.mark.parametrize("sample", [7], indirect=True)
@pytest.mark.parametrize("canonical_source", [FIXED], indirect=True)
def test_native_whole_fact_and_source_span_combination_keeps_original_projection_contract(candidate, monkeypatch):
    sample, _ = candidate
    initial = native(candidate, sample.source, "seed")
    sample.dump()
    corrected = native(candidate, sample.source, "correct", initial["state"])
    latest = native(candidate, sample.source, "combine", corrected["state"])
    state = latest["state"]
    revocations = next(row["revocations"] for row in latest["document"]["owners"] if row["owner_user_id"] == "alice")
    assert {row["kind"] for row in revocations} == {"source_span", "fact", "note"}
    assert [row["entity_id"] for row in revocations if row["kind"] == "fact"] == [state["walk"]]
    assert [row["operation"] for row in revocations if row["kind"] == "source_span"] == ["superseded"]
    request = pinned(candidate, latest["document"])
    snapshots = []
    observe(monkeypatch, snapshots, {"id": state["bob_run"]})
    evidence = ROOT / "private" / ("source-span-combined-" + uuid.uuid4().hex)
    evidence.mkdir(parents=True)
    save_evidence(evidence, state=state)
    try:
        result = restore.execute(
            sample.inputs,
            apply_local=True,
            upgrade_local=True,
            withdrawals_replay=request,
            environment=sample.environment,
        )
    except Exception as error:
        save_evidence(evidence, state=state, failure=type(error).__name__)
        raise
    observed = native(candidate, sample.environment["FIRST_RELEASE_OWNER_DSN"], "observe", state)["observed"]
    proof = result["withdrawals_replay"]
    save_evidence(
        evidence, state=state, observed=observed, proof=proof, other_owner_unchanged=snapshots[0] == snapshots[1]
    )
    assert snapshots[0] == snapshots[1] and proof["state_first_sha256"] == proof["state_second_sha256"]
    checks = proof["checks"]
    assert checks["span_sources_checked"] == checks["span_facts_checked"] == 1
    assert checks["span_preserved_facts_checked"] == 0 and checks["whole_revocations_checked"] == 2
    assert checks["span_runs_checked"] == checks["span_outbox_checked"] == 1
    assert checks["checkpoint_ranges_checked"] >= 3
    assert observed["raw_status"] == "active" and observed["fts_night"] is observed["corrected_present"] is False
    assert all(
        value is True
        for name, value in observed.items()
        if name not in {"raw_status", "fts_night", "corrected_present"}
    )


@pytest.mark.parametrize("sample", [7], indirect=True)
@pytest.mark.parametrize("canonical_source", [FIXED], indirect=True)
@pytest.mark.parametrize(
    "residual",
    [False, True, "bad-field-source-refs"],
    ids=["marker-only", "actual-orphan-note", "bad-field-source-refs"],
)
def test_missing_original_after_backup_requires_marker_only_zero_residual(candidate, monkeypatch, residual):
    sample, _ = candidate
    native(candidate, sample.source, "owners")
    sample.dump()
    initial = native(candidate, sample.source, "seed")
    latest = native(candidate, sample.source, "correct", initial["state"])
    state = latest["state"]
    assert state["old_status"] == "superseded"
    markers = next(row["revocations"] for row in latest["document"]["owners"] if row["owner_user_id"] == "alice")
    assert {row["kind"] for row in markers} == {"source_span", "note"}
    request = pinned(candidate, latest["document"])
    snapshots = []
    if residual:
        orphan_before_replay(candidate, state, monkeypatch, snapshots, malformed=residual == "bad-field-source-refs")
    else:
        observe(monkeypatch, snapshots, {"id": state["bob_run"]})
    evidence = ROOT / "private" / ("source-span-missing-" + uuid.uuid4().hex)
    evidence.mkdir(parents=True)
    proof = None
    if residual:
        with pytest.raises(RestoreRejected, match="^REPLAY_ERASURE_FAILED$"):
            restore.execute(
                sample.inputs,
                apply_local=True,
                upgrade_local=True,
                withdrawals_replay=request,
                environment=sample.environment,
            )
        assert snapshots[0] == snapshots[1]
    else:
        result = restore.execute(
            sample.inputs,
            apply_local=True,
            upgrade_local=True,
            withdrawals_replay=request,
            environment=sample.environment,
        )
        proof = result["withdrawals_replay"]
        assert snapshots[0] == snapshots[1] and proof["state_first_sha256"] == proof["state_second_sha256"]
        assert proof["export_first_sha256"] == proof["export_second_sha256"]
        checks = proof["checks"]
        assert checks["span_marker_only_checked"] == 1
        assert checks["span_sources_checked"] == checks["span_facts_checked"] == checks["span_runs_checked"] == 0
    current = native(candidate, sample.environment["FIRST_RELEASE_OWNER_DSN"], "missing_observe", state)
    actual = next(row["revocations"] for row in current["document"]["owners"] if row["owner_user_id"] == "alice")
    if not residual:
        assert actual == markers
    assert current["observed"] == {
        "original_entities_absent": True,
        "runtime_scopes_empty": True,
        "orphan_present": bool(residual),
    }
    save_evidence(
        evidence,
        state=state,
        observed=current["observed"],
        proof=proof,
        failure="REPLAY_ERASURE_FAILED" if residual else None,
        other_owner_unchanged=snapshots[0] == snapshots[1],
    )
