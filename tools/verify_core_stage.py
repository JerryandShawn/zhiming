"""Stage-only migration, runtime privileges and privacy restore acceptance.

DSNs are supplied through named environment variables. This program never
reads an environment/secret file, calls a model, starts a receiver, or sends.
The selected source must be a frozen copy; the live Hermes paths are refused.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import sys
from types import SimpleNamespace
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import psycopg
from psycopg.rows import dict_row
from psycopg import sql
from psycopg.types.json import Jsonb
from migration_core import migrate,plan,read_json,source_manifest
from mingjing_core.application.memory import MemoryService
from mingjing_core.adapters.delivery import OutboxService
from mingjing_core.adapters.channels.hermes import HermesChannelAdapter
from mingjing_core.domain.contracts import EvidenceError,LeaseConflict,ScopeError
from mingjing_core.repositories.postgres import PostgresRepository,fingerprint
from mingjing_core.runtime import LangGraphRuntime

EXPECTED_DATABASE='zhiming_core_stage'
HERMES_BACKUPS=Path('/root/zhiming-core-backups')


class StageFailure(RuntimeError):
    def __init__(self,code):self.code=code;super().__init__(code)


def require(condition,code):
    if not condition:raise StageFailure(code)


def env_dsn(name):
    require(bool(re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',name)),'INVALID_ENV_NAME')
    value=os.environ.get(name)
    require(bool(value),'MISSING_DATABASE_ENV')
    return value


def frozen_source(value):
    path=Path(value)
    require(path.is_dir() and not path.is_symlink(),'FROZEN_SOURCE_REQUIRED')
    path=path.resolve()
    require(not path.is_relative_to(Path('/root/.hermes')) and not path.is_relative_to(Path('/root/mingjingtai')),'LIVE_LEGACY_SOURCE_REFUSED')
    require(bool(source_manifest(path)),'EMPTY_FROZEN_SOURCE')
    return path


def checked_bindings(value,owner):
    path=Path(value)
    require(path.is_file() and not path.is_symlink(),'TRUSTED_BINDINGS_REQUIRED')
    if sys.platform=='linux':require(path.stat().st_mode&0o077==0,'BINDINGS_MUST_BE_PRIVATE')
    rows=read_json(path,[])
    require(isinstance(rows,list),'INVALID_BINDINGS')
    seen={}
    for row in rows:
        require(isinstance(row,dict) and row.get('owner',owner)==owner,'BINDING_OWNER_MISMATCH')
        require(row.get('subject','self')=='self','STAGE_BINDING_SUBJECT_REQUIRES_REVIEW')
        channel=row.get('channel');kind=row.get('binding_kind','user');external=row.get('external_id')
        require(channel in ('feishu','report') and isinstance(external,str),'INVALID_TRUSTED_BINDING')
        require((channel=='report' and kind=='task' and 0<len(external)<=200) or
                (channel=='feishu' and kind=='user' and re.fullmatch(r'ou_[A-Za-z0-9]+',external)) or
                (channel=='feishu' and kind=='chat' and re.fullmatch(r'oc_[A-Za-z0-9]+',external)),
                'BINDING_TYPE_OR_IDENTIFIER_MISMATCH')
        key=(channel,external)
        require(key not in seen or seen[key]==kind,'CONFLICTING_TRUSTED_BINDING')
        seen[key]=kind
    return rows


def database_identity(dsn,expected_database=EXPECTED_DATABASE):
    with psycopg.connect(dsn,autocommit=True,row_factory=dict_row) as connection:
        with connection.transaction():
            connection.execute('SET TRANSACTION READ ONLY')
            row=connection.execute('SELECT current_database() AS database,current_user AS role,inet_server_addr()::text AS address,inet_server_port() AS port,rolsuper,rolcreatedb,rolcreaterole FROM pg_roles WHERE rolname=current_user').fetchone()
    require(row['database']==expected_database,'DEDICATED_STAGE_DATABASE_REQUIRED')
    require(not any(row[key] for key in ('rolsuper','rolcreatedb','rolcreaterole')),'PRIVILEGED_APPLICATION_ROLE_REFUSED')
    return row


def runtime_readonly(repo,migration_role):
    with repo.connection() as connection:
        connection.execute('SET TRANSACTION READ ONLY')
        version=repo.verify_schema()['version']
        LangGraphRuntime(repo,initialize=False)
        privilege=connection.execute('SELECT has_database_privilege(current_user,current_database(),\'CREATE\') AS database_create,has_schema_privilege(current_user,%s,\'CREATE\') AS core_create,has_schema_privilege(current_user,\'public\',\'CREATE\') AS public_create,pg_has_role(current_user,%s,\'MEMBER\') AS migration_member', (repo.schema,migration_role)).fetchone()
        require(not any(privilege.values()),'RUNTIME_DDL_AUTHORITY_REFUSED')
        owned=connection.execute('SELECT count(*) AS count FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname IN (%s,\'public\') AND c.relkind IN (\'r\',\'p\') AND pg_has_role(current_user,c.relowner,\'USAGE\')',(repo.schema,)).fetchone()['count']
        require(owned==0,'RUNTIME_TABLE_OWNERSHIP_REFUSED')
        for table in (repo.schema+'.schema_migrations','public.checkpoint_migrations'):
            rights=connection.execute("SELECT has_table_privilege(current_user,%s,'INSERT,UPDATE,DELETE,TRUNCATE,TRIGGER') AS writes",(table,)).fetchone()['writes']
            require(not rights,'RUNTIME_MIGRATION_LEDGER_WRITES_REFUSED')
    return {'read_only_startup':True,'schema_version':version,'ddl_authority':False,'separate_migration_role':True}


def pg_counts(repo,owner):
    with repo.connection() as connection:
        entities=connection.execute(sql.SQL('SELECT kind,status,count(*) AS count FROM {} WHERE owner=%s GROUP BY kind,status').format(repo.table('core_entities')),(owner,)).fetchall()
        ledger=connection.execute(sql.SQL('SELECT kind,count(*) AS count FROM {} WHERE owner=%s GROUP BY kind').format(repo.table('core_revocations')),(owner,)).fetchall()
        mapped=connection.execute(sql.SQL('SELECT count(*) AS count FROM {} WHERE owner=%s').format(repo.table('core_legacy_map')),(owner,)).fetchone()['count']
    return {'entities':{row['kind']+':'+row['status']:row['count'] for row in entities},'revocations':{row['kind']:row['count'] for row in ledger},'legacy_mappings':mapped}


def verify_import(repo,source,owner,bindings):
    before=source_manifest(source);data=plan(source)
    dry=migrate(source,owner,bindings=bindings)
    require(not dry['errors'],'MIGRATION_DRY_ERRORS')
    first=migrate(source,owner,repository=repo,bindings=bindings,apply=True)
    repeat=migrate(source,owner,repository=repo,bindings=bindings,apply=True)
    require(not first['errors'] and not repeat['errors'],'MIGRATION_APPLY_ERRORS')
    new_fields=('imported_messages','imported_uploads','verified_facts','legacy_unverified','queued_legacy_runs','legacy_pending_requests','legacy_delivery_rows','revoked_ranges')
    require(all(repeat[key]==0 for key in new_fields),'MIGRATION_REPEAT_CREATED_EFFECT')
    sqlite_count=sum(bool(turn.get(field)) for turn in data['turns'] for field in ('message','answer'))
    require(dry['source_messages']==sqlite_count+dry['json_only_messages'],'HISTORY_UNION_COUNT_MISMATCH')
    ids=[]
    for original in data['history']:
        key=original['id']+':'+original['role'];mapping=repo.legacy_mapping(owner,'web.db',key,'message')
        require(mapping and mapping['result_id'],'MISSING_ORIGINAL_MAPPING')
        ident=mapping['result_id'];ids.append(fingerprint(ident))
        try:row=repo.get(owner,'message',ident,include_deleted=True)
        except ScopeError:
            require(repo.is_revoked(owner,'message',ident),'MISSING_ORIGINAL_OR_TOMBSTONE');continue
        if row['status']!='deleted':require(row.get('content')==original['content'],'IMMUTABLE_ORIGINAL_MISMATCH')
    if data['archive'].get('user'):
        mapping=repo.legacy_mapping(owner,'archive.json','user','legacy')
        require(bool(mapping),'MISSING_LEGACY_PROFILE')
        legacy=repo.get(owner,'legacy',mapping['result_id'],include_deleted=True)
        require(legacy['status']=='deleted' or legacy.get('assertion_status')=='legacy_unverified','LEGACY_PROFILE_AUTO_AUTHORIZED')
        require(not any(fact.get('source')=='archive:user' for fact in MemoryService(repo).facts(owner)),'ARCHIVE_PROFILE_BECAME_FACT')
    outbox=OutboxService(repo);protected=0;statuses=Counter()
    for old in data['legacy_outbox']:
        mapping=repo.legacy_mapping(owner,'reports.db',str(old['id']),'delivery')
        require(bool(mapping),'MISSING_LEGACY_DELIVERY')
        with repo.connection() as connection:
            row=connection.execute(sql.SQL('SELECT id,status,attempts,payload,receipt FROM {} WHERE owner=%s AND id=%s').format(repo.table('delivery_outbox')),(owner,mapping['result_id'])).fetchone()
        require(row and row['payload']=={},'LEGACY_DELIVERY_CONTAINS_UNVERIFIED_BODY')
        statuses[row['status']]+=1
        confirmed=str(old.get('status'))=='sent' and bool(re.fullmatch(r'om_[A-Za-z0-9]+',str(old.get('message_id') or '')))
        if confirmed:require(row['status']=='sent' and row['receipt']==old['message_id'],'LEGACY_SENT_RECEIPT_LOST')
        if row['status'] in ('sent','uncertain'):
            try:outbox.claim_delivery(owner=owner,outbox_id=row['id'])
            except LeaseConflict:protected+=1
            else:raise StageFailure('LEGACY_DELIVERY_RECLAIMED')
            with repo.connection() as connection:
                current=connection.execute(sql.SQL('SELECT status,attempts FROM {} WHERE id=%s').format(repo.table('delivery_outbox')),(row['id'],)).fetchone()
            require(current=={'status':row['status'],'attempts':row['attempts']},'LEGACY_CLAIM_CHANGED_LEDGER')
    require(source_manifest(source)==before,'FROZEN_SOURCE_CHANGED')
    return {'dry_run':dry,'apply':first,'repeat':repeat,'history_ids_sha256':fingerprint(sorted(ids)),
            'legacy_profile_unverified':True,'legacy_delivery_statuses':dict(statuses),'protected_delivery_rows':protected,'postgres':pg_counts(repo,owner)}


def verify_privacy_restore(dsn):
    schema='verify_core_'+uuid.uuid4().hex[:24]
    repo=PostgresRepository(dsn,schema=schema,max_size=2)
    try:
        owner='synthetic-stage-verification';repo.ensure_owner(owner);memory=MemoryService(repo)
        marker='SYNTHETIC_STAGE_PRIVACY_291'
        source=memory.receive(owner,'self','我喜欢'+marker,source_id='synthetic-restore')
        fact=memory.save_fact(owner,'self',source['id'],source['content'])
        with repo.connection() as connection:
            backup=connection.execute(sql.SQL('SELECT kind,id,data,status,revision FROM {} WHERE owner=%s').format(repo.table('core_entities')),(owner,)).fetchall()
        memory.retire_fact(owner,fact['id'],expected_revision=fact['revision'],scope='source')
        latest=repo.export_privacy(owner)
        require(marker not in json.dumps(latest,ensure_ascii=False),'PRIVACY_LEDGER_CONTAINS_BODY')
        with repo.transaction(owner) as connection:
            # Restore only synthetic entities in this disposable schema, then
            # replay the separately preserved, newer body-free withdrawal log.
            for row in backup:
                connection.execute(sql.SQL('UPDATE {} SET data=%s,status=%s,revision=%s WHERE owner=%s AND kind=%s AND id=%s').format(repo.table('core_entities')),(Jsonb(row['data']),row['status'],row['revision'],owner,row['kind'],row['id']))
            connection.execute(sql.SQL('DELETE FROM {} WHERE owner=%s').format(repo.table('core_revocations')),(owner,))
        repo.apply_privacy(owner,latest)
        require(marker not in json.dumps(memory.snapshot(owner),ensure_ascii=False),'RESTORED_PRIVATE_BODY_REAPPEARED')
        try:memory.receive(owner,'self','我喜欢'+marker,source_id='synthetic-restore')
        except EvidenceError:pass
        else:raise StageFailure('WITHDRAWN_ORIGINAL_REIMPORTED')
        return {'disposable_schema':True,'latest_withdrawal_replayed':True,'body_free_ledger':True,'reimport_blocked':True}
    finally:
        with repo.connection() as connection:connection.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
        repo.close()


def verify_hermes(repo,path,expected_sha,owner,bindings):
    path=Path(path)
    require(path.is_file() and not path.is_symlink(),'HERMES_BACKUP_REQUIRED')
    require(path.resolve().is_relative_to(HERMES_BACKUPS.resolve()),'PROTECTED_HERMES_BACKUP_PATH_REQUIRED')
    if sys.platform=='linux':require(path.stat().st_mode&0o077==0,'HERMES_BACKUP_MUST_BE_PRIVATE')
    require(bool(re.fullmatch(r'[a-f0-9]{64}',expected_sha or '')),'HERMES_SNAPSHOT_SHA_REQUIRED')
    require(not Path(str(path)+'-wal').exists(),'HERMES_BACKUP_MUST_BE_CONSISTENT_SQLITE_COPY')
    require(hashlib.sha256(path.read_bytes()).hexdigest()==expected_sha,'HERMES_SNAPSHOT_SHA_MISMATCH')
    service=SimpleNamespace(repo=repo,memory=MemoryService(repo));adapter=HermesChannelAdapter(ROOT,service=service,hermes_db=path)
    authors=list({row['external_id']:row for row in bindings if row['channel']=='feishu' and row.get('binding_kind','user')=='user'}.values())
    require(bool(authors),'HERMES_DM_AUTHOR_BINDING_REQUIRED')
    imported=skipped=matched=0
    with repo.transaction(owner):
        before=len(repo.list(owner,'message'))
        facts_before=len(repo.list(owner,'fact'))
        for binding in authors:
            external=binding['external_id'];actual=adapter.identity('feishu',external)
            require(actual['owner']==owner and actual['subject']=='self' and actual['binding_kind']=='user','HERMES_BINDING_SCOPE_MISMATCH')
            rows=adapter.original_rows('feishu',external,binding_kind='user');matched+=len(rows)
            result=adapter.sync('feishu',external,binding_kind='user');imported+=result['imported'];skipped+=result['skipped']
        after=len(repo.list(owner,'message'))
        require(len(repo.list(owner,'fact'))==facts_before,'HERMES_SYNC_EXTRACTED_FACTS')
        repeat=[adapter.sync('feishu',row['external_id'],binding_kind='user') for row in authors]
        require(len(repo.list(owner,'message'))==after,'HERMES_REPEAT_CREATED_ORIGINAL')
        require(len(repo.list(owner,'fact'))==facts_before,'HERMES_SYNC_EXTRACTED_FACTS')
        require(hashlib.sha256(path.read_bytes()).hexdigest()==expected_sha,'HERMES_SNAPSHOT_CHANGED')
    return {'trusted_dm_authors':len(authors),'matched_active_originals':matched,'imported':imported,'skipped':skipped,
            'actual_postgres_added':after-before,'repeat_postgres_added':0,'repeat_skipped':sum(row['skipped'] for row in repeat),'source_unchanged':True}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',required=True);parser.add_argument('--owner',required=True)
    parser.add_argument('--bindings',required=True);parser.add_argument('--schema',default='mingjing_core')
    parser.add_argument('--migration-dsn-env',default='CORE_MIGRATION_DATABASE_URL')
    parser.add_argument('--runtime-dsn-env',default='ZHIMING_DATABASE_URL')
    parser.add_argument('--hermes-snapshot');parser.add_argument('--hermes-sha256')
    args=parser.parse_args(argv)
    logging.getLogger('psycopg.pool').disabled=True
    migration_repo=runtime_repo=None
    try:
        source=frozen_source(args.source);bindings=checked_bindings(args.bindings,args.owner)
        migration_dsn=env_dsn(args.migration_dsn_env);runtime_dsn=env_dsn(args.runtime_dsn_env)
        migrator=database_identity(migration_dsn);runtime=database_identity(runtime_dsn)
        require(migrator['role']!=runtime['role'] and (migrator['database'],migrator['address'],migrator['port'])==(runtime['database'],runtime['address'],runtime['port']),'SEPARATE_ROLES_SAME_STAGE_REQUIRED')
        require(args.schema=='mingjing_core','REVIEWED_CORE_SCHEMA_REQUIRED')
        migration_repo=PostgresRepository(migration_dsn,schema=args.schema,max_size=2)
        imported=verify_import(migration_repo,source,args.owner,bindings)
        runtime_repo=PostgresRepository(runtime_dsn,schema=args.schema,initialize=False,max_size=2,max_running=1)
        startup=runtime_readonly(runtime_repo,migrator['role'])
        privacy=verify_privacy_restore(migration_dsn)
        hermes=verify_hermes(migration_repo,args.hermes_snapshot,args.hermes_sha256,args.owner,bindings) if args.hermes_snapshot else {'enabled':False}
        require(not args.hermes_sha256 or args.hermes_snapshot,'HERMES_SNAPSHOT_REQUIRED_FOR_SHA')
        print(json.dumps({'ok':True,'database':EXPECTED_DATABASE,'owner_sha256':fingerprint(args.owner),'runtime':startup,
                          'migration':imported,'privacy_restore':privacy,'hermes':hermes,'model_calls':0,'external_sends':0},ensure_ascii=False))
        return 0
    except Exception as exc:
        code=getattr(exc,'code',None)
        print(json.dumps({'ok':False,'error_code':code if isinstance(code,str) and re.fullmatch(r'[A-Z_]+',code) else type(exc).__name__,'model_calls':0,'external_sends':0}))
        return 1
    finally:
        if runtime_repo:runtime_repo.close()
        if migration_repo:migration_repo.close()


if __name__=='__main__':raise SystemExit(main())
