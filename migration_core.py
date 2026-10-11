"""Explicit v5 -> PostgreSQL migration. Source SQLite is always read-only.

Default is a count-only dry run. No service restart, delivery, secret discovery
or production filesystem traversal is performed by this module.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from psycopg import sql
from psycopg.types.json import Jsonb
from mingjing_core.application.memory import CATEGORIES, MemoryService
from mingjing_core.domain.contracts import EvidenceError
from mingjing_core.repositories.postgres import PostgresRepository, fingerprint


def read_json(path,default):
    if not path.is_file():return default
    return json.loads(path.read_text(encoding='utf-8'))


def sqlite_rows(path,table):
    if not path.is_file():return []
    if table not in ('turns','memories','memory_audit','settings','outbox'):raise ValueError('Unsupported legacy table')
    connection=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)
    connection.row_factory=sqlite3.Row
    try:
        connection.execute('PRAGMA query_only=ON')
        if not connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone():return []
        selection='*'
        if table=='outbox':
            # Delivery migration requires identity and receipts, never a saved
            # report body or free-form transport error from the old store.
            columns={row['name'] for row in connection.execute('PRAGMA table_info(outbox)')}
            allowed=('id','kind','date','due','job_id','status','attempts','first_send','next_attempt',
                     'message_id','updated_at','prep_attempts','prep_retry')
            selected=[name for name in allowed if name in columns]
            if 'id' not in selected:raise ValueError('Legacy outbox has no stable identity')
            selection=','.join(selected)
        return [dict(row) for row in connection.execute('SELECT '+selection+' FROM '+table)]
    finally:connection.close()


def plan(source):
    source=Path(source).resolve()
    turns=sqlite_rows(source/'web.db','turns');memories=sqlite_rows(source/'web.db','memories')
    archive=read_json(source/'archive.json',{})
    archive_memories=archive.get('conversation_state',{}).get('user_facts',[])
    # SQLite is the latest authority for memory status; archive cannot reactivate it.
    by_id={str(row.get('id',fingerprint(row))):row for row in archive_memories if isinstance(row,dict)}
    by_id.update({str(row['id']):row for row in memories})
    by_source={};pending=None
    for index,row in enumerate(read_json(source/'webchat.json',[])):
        if not isinstance(row,dict) or row.get('role') not in ('user','assistant') or not isinstance(row.get('content'),str):continue
        ident=row.get('turn_id') or row.get('id')
        if not ident:ident=pending if row['role']=='assistant' and pending else 'legacy-'+str(index)
        if row['role']=='user':pending=str(ident)
        elif row['role']=='assistant':pending=None
        by_source[(str(ident),row['role'])]=dict(row,id=str(ident),conversation_id=row.get('session_id','shared'))
    json_sources=set(by_source);conflicts=0
    for turn in turns:
        for role,field in (('user','message'),('assistant','answer')):
            if not turn.get(field):continue
            key=(str(turn['id']),role)
            if key in by_source and by_source[key]['content']!=str(turn[field]):conflicts+=1
            by_source[key]={'id':str(turn['id']),'role':role,'content':str(turn[field]),'at':turn.get('created_at'),'conversation_id':turn.get('session_id','shared'),'status':turn.get('status','complete'),'images':json.loads(turn.get('images') or '[]') if role=='user' else []}
    sqlite_sources={(str(turn['id']),role) for turn in turns for role,field in (('user','message'),('assistant','answer')) if turn.get(field)}
    history=list(by_source.values())
    inactive=[row for row in by_id.values() if row.get('status','active')!='active']
    active=[row for row in by_id.values() if row.get('status','active')=='active']
    return {'history':history,'turns':turns,'settings':sqlite_rows(source/'web.db','settings'),'legacy_outbox':sqlite_rows(source/'reports.db','outbox'),
            'json_only_messages':len(json_sources-sqlite_sources),'json_sqlite_conflicts':conflicts,
            'inactive':inactive,'active':active,'archive':archive,'pipeline':read_json(source/'report-pipeline.json',{}),'source':str(source)}


def source_manifest(source):
    root=Path(source).resolve()
    paths=[root/name for name in ('web.db','web.db-wal','reports.db','reports.db-wal','archive.json','webchat.json','report-pipeline.json')]
    images=root/'images'
    if images.is_dir():paths.extend(path for path in images.glob('*.jpg') if re.fullmatch(r'[a-f0-9]{64}\.jpg',path.name))
    result={}
    for path in paths:
        if path.is_file():
            if not path.resolve().is_relative_to(root):raise EvidenceError('Migration source path escapes selected root')
            result[str(path.relative_to(root)).replace('\\','/')]=hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def migrate(source,owner,*,repository=None,apply=False,bindings=None):
    before=source_manifest(source)
    if apply:
        if repository is None:raise ValueError('PostgreSQL repository required for --apply')
        with repository.transaction(owner):
            result=_migrate(source,owner,repository=repository,apply=True,bindings=bindings)
            if source_manifest(source)!=before:raise EvidenceError('Migration source changed during read-only import; target transaction rolled back')
    else:
        result=_migrate(source,owner,repository=repository,apply=False,bindings=bindings)
        if source_manifest(source)!=before:raise EvidenceError('Migration source changed during read-only shadow inspection')
    return dict(result,source_sha256=before,source_unchanged=True)


def _migrate(source,owner,*,repository=None,apply=False,bindings=None):
    data=plan(source)
    counters={'dry_run':not apply,'source_messages':len(data['history']),'source_memories':len(data['active'])+len(data['inactive']),
              'inactive_first':len(data['inactive']),'imported_messages':0,'imported_uploads':0,'verified_facts':0,'legacy_unverified':0,'already_mapped':0,'revoked_ranges':0,'errors':[]}
    counters.update(json_only_messages=data['json_only_messages'],json_sqlite_conflicts=data['json_sqlite_conflicts'],queued_legacy_runs=0,legacy_pending_requests=0,legacy_delivery_rows=0,source_delivery_rows=len(data['legacy_outbox']))
    if not apply:return counters
    if repository is None:raise ValueError('PostgreSQL repository required for --apply')
    repo=repository;memory=MemoryService(repo);repo.ensure_owner(owner)
    settings_key=repo.legacy_mapping(owner,'web.db','memory-settings','settings')
    if not settings_key:
        values=[]
        for setting in data['settings']:
            if setting.get('key') in ('auto_save_low_sensitivity','auto_save_memory','auto_save','autosave'):
                raw=str(setting.get('value','')).strip().lower()
                if raw in ('false','0','no','off'):values.append(False)
                elif raw in ('true','1','yes','on'):values.append(True)
        if values:
            with repo.transaction(owner) as c:
                settings=repo.assert_scope(owner)['settings']
                settings['auto_save_low_sensitivity']=settings.get('auto_save_low_sensitivity',True) and all(values)
                c.execute(sql.SQL('UPDATE {} SET settings=%s WHERE id=%s').format(repo.table('core_owners')),(Jsonb(settings),owner))
                repo.bump_revision(c,owner,owner_scope=True)
            repo.map_legacy(owner,'web.db','memory-settings','settings',owner)
    if bindings:
        for binding in bindings:
            if binding.get('owner',owner)!=owner:raise ValueError('Binding owner mismatch')
            subject=binding.get('subject','self')
            if subject!='self':repo.create_subject(owner,subject,binding.get('label',subject))
            repo.bind_channel(owner,binding['channel'],str(binding['external_id']),subject,binding_kind=binding.get('binding_kind','user'))
    original={}
    # Raw originals are registered before span revocations; no candidate is promoted yet.
    for row in data['history']:
        key=row['id']+':'+row['role']
        if row['role']=='assistant':
            parent_id='msg_'+fingerprint([owner,'web',row['id']+':user','user'])[:32]
            if repo.is_revoked(owner,'message',parent_id):
                reply_id='msg_'+fingerprint([owner,'web',key,'assistant'])[:32]
                with repo.transaction(owner) as connection:
                    try:
                        reply=repo.get(owner,'message',reply_id,include_deleted=True)
                        if reply['status']!='deleted':repo.delete(owner,'message',reply_id,expected_revision=reply['revision'])
                    except ScopeError:pass
                    repo.revoke(connection,owner,'message',reply_id,'deleted',{'source_ids':[parent_id]})
                    repo.map_legacy(owner,'web.db',key,'message',reply_id,'withdrawn')
                counters['already_mapped']+=1
                continue
        prior=repo.legacy_mapping(owner,'web.db',key,'message')
        if prior:
            counters['already_mapped']+=1
            try:
                original[key]=memory.get_source(owner,prior['result_id'])
                if original[key]['status']!='deleted' and original[key].get('content')!=row['content']:counters['errors'].append({'entity':'message','id':key,'code':'SOURCE_IDENTITY_CONFLICT'})
            except ValueError:pass
            continue
        try:
            result=memory.receive(owner,'self',row['content'],channel='web',source_id=key,role=row['role'],conversation_id=row['conversation_id'],at=row.get('at'))
            original[key]=result;repo.map_legacy(owner,'web.db',key,'message',result['id']);counters['imported_messages']+=1
        except ValueError as exc:
            counters['errors'].append({'entity':'message','id':key,'code':getattr(exc,'code','INVALID_SOURCE')})
    # Old assistant replies can repeat the user's private text. Preserve their
    # turn lineage so withdrawing the original also removes these derivatives.
    for row in data['history']:
        if row['role']!='assistant':continue
        reply=original.get(row['id']+':assistant');parent=original.get(row['id']+':user')
        if not reply or reply['status']=='deleted':continue
        source_ids=[parent['id']] if parent and parent['status']!='deleted' else []
        if reply.get('source_ids')!=source_ids or not reply.get('legacy_derived'):
            reply=repo.update(owner,'message',reply['id'],{'source_ids':source_ids,'legacy_derived':True},
                              expected_revision=reply['revision'],operation_id='migration:lineage:'+reply['id']+':'+fingerprint(source_ids)[:12])
            original[row['id']+':assistant']=reply
    for row in data['history']:
        if row['role']!='user' or not row.get('images'):continue
        source_row=original.get(row['id']+':user')
        if not source_row or source_row['status']=='deleted':continue
        image_root=(Path(data['source'])/'images').resolve();image_ids=[]
        for image in row['images']:
            if not isinstance(image,str) or not re.fullmatch(r'[a-f0-9]{64}',image):
                counters['errors'].append({'entity':'upload','id':row['id'],'code':'INVALID_UPLOAD_ID'});continue
            path=(image_root/(image+'.jpg')).resolve()
            if path.parent!=image_root or not path.is_file():
                counters['errors'].append({'entity':'upload','id':image,'code':'MISSING_UPLOAD'});continue
            ident='upload:legacy-'+fingerprint([owner,source_row['id'],image])[:32]
            if repo.is_revoked(owner,'upload',ident):continue
            mapped=repo.legacy_mapping(owner,'images',ident,'upload')
            if not mapped:
                repo.put(owner,'upload',ident,{'path':str(path),'mime':'image/jpeg','content_hash':image,'message_id':source_row['id'],'legacy':True},expected_revision=0,operation_id='migration:upload:'+ident)
                repo.map_legacy(owner,'images',ident,'upload',ident);counters['imported_uploads']+=1
            else:counters['already_mapped']+=1
            image_ids.append(ident)
        latest=memory.get_source(owner,source_row['id'])
        if image_ids and latest.get('image_ids')!=image_ids:
            latest=repo.update(owner,'message',latest['id'],{'image_ids':image_ids},expected_revision=latest['revision'],operation_id='migration:images:'+latest['id'])
            original[row['id']+':user']=latest
    def find_source(row):
        quote=str(row.get('quote') or row.get('text') or row.get('content') or '')
        if row.get('text') and row.get('quote') and row['text']!=row['quote']:
            return str(row['text']),None  # Old UI edit lacks a new authenticated original quote.
        source_turn=str(row.get('source_turn') or '')
        candidate=original.get(source_turn+':user')
        matches=[candidate] if candidate and quote in candidate.get('content','') else [m for key,m in original.items() if key.endswith(':user') and quote and quote in m.get('content','')]
        return quote,matches[0] if len(matches)==1 else None
    # Withdrawals win, including inactive SQLite entries duplicated as active archive facts.
    for row in data['inactive']:
        legacy_id=str(row.get('id',fingerprint(row)))
        if repo.legacy_mapping(owner,'memories',legacy_id,'revocation'):
            counters['already_mapped']+=1;continue
        quote,source_row=find_source(row)
        with repo.transaction(owner) as c:
            repo.revoke(c,owner,'legacy_memory',legacy_id,'deleted' if row.get('status')=='deleted' else 'stopped',{'source':'memories','legacy_id':legacy_id})
            if source_row and quote:
                start=source_row['content'].find(quote);end=start+len(quote)
                repo.revoke(c,owner,'source_span',fingerprint([source_row['id'],start,end]),'stopped',{'message_id':source_row['id'],'start':start,'end':end})
                counters['revoked_ranges']+=1
                # A fact from an earlier partial apply is retired before any reimport.
                for fact in memory.facts(owner,include_inactive=True):
                    if any(r.get('message_id')==source_row['id'] and max(start,r.get('start',0))<min(end,r.get('end',0)) for r in fact.get('source_refs',[])) and fact['status'] not in ('deleted','stopped'):
                        memory.retire_fact(owner,fact['id'],expected_revision=fact['revision'],operation='delete' if row.get('status')=='deleted' else 'stop')
            repo.map_legacy(owner,'memories',legacy_id,'revocation',None,'withdrawn')
    for row in data['active']:
        legacy_id=str(row.get('id',fingerprint(row)))
        if repo.legacy_mapping(owner,'memories',legacy_id,'fact') or repo.is_revoked(owner,'legacy_memory',legacy_id):counters['already_mapped']+=1;continue
        quote,source_row=find_source(row);kind=CATEGORIES.get(row.get('category'),'background')
        try:
            if source_row and quote:
                # Original save is a user-facing historic action; preserve verified quote without interpreting a new consent.
                result=memory.save_fact(owner,'self',source_row['id'],quote,kind,operation_id='migration:fact:'+legacy_id,
                                        assertion_status='user_asserted')
                if result.get('write_status')=='pending_confirmation' and not result.get('fact_id'):
                    result=memory.save_fact(owner,'self',source_row['id'],quote,kind,operation_id='migration:pending:'+legacy_id,assertion_status='legacy_unverified')
                if result.get('fact_id'):
                    repo.map_legacy(owner,'memories',legacy_id,'fact',result['fact_id'],'verified' if result['write_status']=='saved' else 'legacy_unverified')
                    counters['verified_facts' if result['write_status']=='saved' else 'legacy_unverified']+=1
                    continue
                if result.get('write_status')=='rejected':
                    repo.map_legacy(owner,'memories',legacy_id,'fact',None,'excluded');continue
            # No exact authoritative user source: retain as visibly unverified legacy, never context evidence.
            legacy='legacy_'+fingerprint([owner,'memories',legacy_id])[:32]
            repo.put(owner,'legacy',legacy,{'assertion_status':'legacy_unverified','legacy_id':legacy_id,'source':'memories','content':quote,'status':'pending'},subject='self',expected_revision=0,operation_id='migration:legacy:'+legacy_id)
            repo.map_legacy(owner,'memories',legacy_id,'fact',legacy,'legacy_unverified');counters['legacy_unverified']+=1
        except EvidenceError:
            repo.map_legacy(owner,'memories',legacy_id,'fact',None,'revoked');counters['already_mapped']+=1
        except ValueError as exc:counters['errors'].append({'entity':'fact','id':legacy_id,'code':getattr(exc,'code','INVALID_FACT')})
    user=data['archive'].get('user',{})
    if user and not repo.legacy_mapping(owner,'archive.json','user','legacy'):
        legacy='legacy_'+fingerprint([owner,'archive:user'])[:32]
        repo.put(owner,'legacy',legacy,{'source':'archive:user','section':'user','payload':user,'assertion_status':'legacy_unverified','profile':user,'status':'pending'},expected_revision=0,operation_id='migration:archive:user')
        repo.map_legacy(owner,'archive.json','user','legacy',legacy,'legacy_unverified');counters['legacy_unverified']+=1
    for section,payload in data['archive'].items():
        if section=='user' or repo.legacy_mapping(owner,'archive.json',section,'legacy'):continue
        legacy='legacy_'+fingerprint([owner,'archive:'+section])[:32]
        repo.put(owner,'legacy',legacy,{'source':'archive:'+section,'section':section,'payload':payload,'assertion_status':'legacy_unverified','status':'pending'},expected_revision=0,operation_id='migration:archive:'+section)
        repo.map_legacy(owner,'archive.json',section,'legacy',legacy,'legacy_unverified');counters['legacy_unverified']+=1
    pipeline=data['pipeline']
    if pipeline:
        jobs=pipeline.get('jobs',[])
        if not isinstance(jobs,list) or any(not isinstance(job,dict) or not job.get('id') or job.get('kind') not in ('daily','weekly','monthly','quarterly') or not isinstance(job.get('target'),str) or not re.fullmatch(r'(ou|oc)_[A-Za-z0-9]+',job['target']) for job in jobs):
            counters['errors'].append({'entity':'report_pipeline','code':'INVALID_TRUSTED_PIPELINE'})
            return counters
        # Trusted existing schedule configuration is preserved. Delivery adapters still require independently explicit bindings.
        with repo.transaction(owner) as c:
            settings=repo.assert_scope(owner)['settings'];old=settings.get('report_pipeline')
            if old is None:
                settings['report_pipeline']=pipeline
                c.execute(sql.SQL('UPDATE {} SET settings=%s WHERE id=%s').format(repo.table('core_owners')),(Jsonb(settings),owner))
                repo.bump_revision(c,owner,owner_scope=True)
        for job in jobs:
            subject=job.get('subject','self');repo.assert_scope(owner,subject)
            repo.bind_channel(owner,'report',str(job.get('external_id') or job['id']),subject,binding_kind='task')
        # targets may be configured in old jobs; exact targets are taken only from this local trusted file.
        for job in jobs:
            target=job['target']
            repo.bind_channel(owner,'feishu',target,job.get('subject','self'),binding_kind='chat' if target.startswith('oc_') else 'user')
    # Pending Web requests are preserved under stable Core operations. Failed
    # or interrupted requests remain visible review items, never invented replies.
    for turn in data['turns']:
        state=turn.get('status','complete');legacy_id=str(turn['id'])
        if state not in ('running','pending','queued','processing','failed','interrupted','error'):continue
        source_row=original.get(legacy_id+':user')
        if not source_row or source_row['status']=='deleted' or not source_row.get('content'):continue
        if repo.legacy_mapping(owner,'web.db',legacy_id,'pending_request'):
            counters['already_mapped']+=1;continue
        current=memory.get_source(owner,source_row['id'],for_context=True)
        active=state in ('running','pending','queued','processing') and current.get('content')==source_row['content']
        if active:
            request={'message':source_row['content'],'conversation_id':source_row.get('conversation_id','shared'),
                     'case_ids':[],'mode':'chat','depth':'standard','selection':{},'draw_id':None,
                     'images':source_row.get('image_ids',[]),'parent_run':None,'source_message_id':source_row['id'],'reading_id':None}
            run=repo.queue_run(owner,'legacy-web:'+legacy_id,request)
            result_id=run['id'];counters['queued_legacy_runs']+=1
        else:
            result_id='legacy-pending:'+fingerprint([owner,legacy_id])[:32]
            repo.put(owner,'request',result_id,{'gateway':'legacy-web','message_id':source_row['id'],
                     'legacy_id':legacy_id,'legacy_status':state,'requires_review':True},operation_id='migration:pending:'+legacy_id)
            counters['legacy_pending_requests']+=1
        repo.map_legacy(owner,'web.db',legacy_id,'pending_request',result_id)
    jobs_by_id={str(job['id']):job for job in pipeline.get('jobs',[])} if pipeline else {}
    for row in data['legacy_outbox']:
        legacy_id=str(row.get('id',''));job=jobs_by_id.get(str(row.get('job_id','')))
        if not job or row.get('kind') not in ('daily','weekly','monthly','quarterly'):
            counters['errors'].append({'entity':'legacy_delivery','id':legacy_id,'code':'UNKNOWN_TRUSTED_JOB'});continue
        try:
            day=datetime.fromisoformat(str(row['date'])).date().isoformat()
            due=datetime.fromisoformat(str(row['due']))
            if due.tzinfo is None:raise ValueError('Timezone required')
            attempts=max(0,int(row.get('attempts') or 0));first_send=float(row.get('first_send') or 0)
        except (KeyError,TypeError,ValueError):
            counters['errors'].append({'entity':'legacy_delivery','id':legacy_id,'code':'INVALID_LEGACY_TIME_OR_ATTEMPTS'});continue
        prior=repo.legacy_mapping(owner,'reports.db',legacy_id,'delivery')
        if prior:
            counters['already_mapped']+=1;continue
        raw_status=str(row.get('status','waiting'));receipt=str(row.get('message_id') or '')
        confirmed=raw_status=='sent' and bool(re.fullmatch(r'om_[A-Za-z0-9]+',receipt))
        ambiguous=raw_status in ('sending','retrying','uncertain','sent') or first_send>0 or attempts>0
        status='sent' if confirmed else 'uncertain' if ambiguous else 'expired' if raw_status=='expired' else 'stale'
        business='report:'+str(job.get('external_id') or job['id'])+':'+row['kind']+':'+day
        ident='legacy-outbox:'+fingerprint([owner,legacy_id])[:32]
        reconciliation={'source':'reports.db','legacy_id':legacy_id,'legacy_status':raw_status,
                        'verification':'legacy_sent' if confirmed else 'unverified',
                        'needs_core_generation':status=='stale','original_due':due.isoformat()}
        with repo.transaction(owner) as c:
            existing=c.execute(sql.SQL('SELECT id FROM {} WHERE owner=%s AND business_id=%s AND channel=%s AND target=%s').format(repo.table('delivery_outbox')),(owner,business,'feishu',job['target'])).fetchone()
            if existing:
                counters['errors'].append({'entity':'legacy_delivery','id':legacy_id,'code':'EXISTING_BUSINESS_REQUIRES_RECONCILIATION'});continue
            c.execute(sql.SQL('INSERT INTO {}(id,owner,subject,business_id,channel,target,run_id,payload,dependencies,status,attempts,due,receipt,error,reconciliation) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)').format(repo.table('delivery_outbox')),
                      (ident,owner,job.get('subject','self'),business,'feishu',job['target'],'legacy:'+fingerprint([owner,legacy_id])[:32],Jsonb({}),Jsonb({}),status,attempts if ambiguous else 0,due,receipt if confirmed else '', 'LEGACY_UNVERIFIED' if not confirmed else '',Jsonb(reconciliation)))
            repo.map_legacy(owner,'reports.db',legacy_id,'delivery',ident)
            counters['legacy_delivery_rows']+=1
    return counters


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',required=True);parser.add_argument('--owner',required=True)
    parser.add_argument('--apply',action='store_true');parser.add_argument('--dsn-env',default='CORE_DATABASE_URL')
    parser.add_argument('--schema',default='mingjing_core');parser.add_argument('--bindings')
    args=parser.parse_args(argv)
    bindings=read_json(Path(args.bindings),[]) if args.bindings else None
    if not args.apply:result=migrate(args.source,args.owner,bindings=bindings)
    else:
        repo=PostgresRepository(os.environ.get(args.dsn_env,''),schema=args.schema)
        try:result=migrate(args.source,args.owner,repository=repo,apply=True,bindings=bindings)
        finally:repo.close()
    print(json.dumps(result,ensure_ascii=False))
    return 1 if result['errors'] else 0


if __name__=='__main__':raise SystemExit(main())
