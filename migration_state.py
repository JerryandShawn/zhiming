"""Repeatable, read-only-source migration to the authoritative state database.

Default is dry-run. Identity must be supplied explicitly; no name matching.
Rollback switches the caller back to old reads; this script never edits legacy
databases, archive files, Hermes home, or old index contents.
"""
import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'hermes'))
from state_store import StateStore, EvidenceError, ScopeError, digest


def read_json(path,default):
    if not path.exists(): return default
    return json.loads(path.read_text(encoding='utf-8'))


def inventory(base):
    base=Path(base);messages=[];memories=[]
    db=base/'web.db'
    if db.exists():
        c=sqlite3.connect(db.resolve().as_uri()+'?mode=ro',uri=True)
        c.row_factory=sqlite3.Row
        try:
            tables={r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if 'turns' in tables:
                for r in c.execute('SELECT * FROM turns ORDER BY created_at,id'):
                    row=dict(r)
                    if row.get('message'):
                        messages.append({'source':'web','id':row['id']+':user','role':'user','content':row['message'],'at':row.get('created_at'),'conversation_id':row.get('session_id','shared')})
                    if row.get('answer'):
                        messages.append({'source':'web','id':row['id']+':assistant','role':'assistant','content':row['answer'],'at':row.get('updated_at') or row.get('created_at'),'conversation_id':row.get('session_id','shared')})
            if 'memories' in tables: memories=[dict(r) for r in c.execute('SELECT * FROM memories ORDER BY created_at,id')]
        finally: c.close()
    else:
        for n,row in enumerate(read_json(base/'webchat.json',[])):
            if row.get('role') in ('user','assistant') and row.get('content'):
                messages.append({'source':'legacy-web','id':str(row.get('turn_id',row.get('id','entry-'+str(n))))+':'+row['role'],
                                 'role':row['role'],'content':str(row['content']),'at':row.get('at'),'conversation_id':row.get('session_id','shared')})
    archive=read_json(base/'archive.json',{})
    known={str(m['id']) for m in memories}
    for row in archive.get('conversation_state',{}).get('user_facts',[]):
        if isinstance(row,dict) and str(row.get('id')) not in known:
            memories.append(dict(row,id=str(row.get('id') or digest(row)[:24]),status=row.get('status','active')))
    # These are retained as provenance-labelled legacy evidence, never promoted
    # from old summaries/predictions into verified personal facts.
    legacy=[]
    for key in ('user','calibration'):
        if archive.get(key): legacy.append((key,archive[key]))
    continuity={k:v for k,v in archive.get('conversation_state',{}).items() if k!='user_facts'}
    if continuity: legacy.append(('conversation_state',continuity))
    return messages,memories,legacy


def migrate(source_base,destination,owner,subject='self',dry_run=True,bindings=None):
    if not owner or not subject: raise ValueError('迁移必须指定归属用户和人物')
    source_base=Path(source_base)
    messages,memories,legacy=inventory(source_base)
    inactive=[m for m in memories if m.get('status','active')!='active']
    report={'dry_run':dry_run,'owner_user_id':owner,'subject_id':subject,
            'source_messages':len(messages),'source_memories':len(memories),'inactive_first':len(inactive),
            'legacy_sections':len(legacy),'imported_messages':0,'verified_user_quotes':0,
            'legacy_unverified':0,'suppressed':0,'already_mapped':0,'errors':[]}
    # Dry-run deliberately never creates a destination directory/database.
    if dry_run:
        users={m['id']:m for m in messages if m['source']=='web' and m['role']=='user'}
        for mem in memories:
            if mem in inactive: continue
            turn=str(mem.get('source_turn',''));source=users.get(turn if turn.endswith(':user') else turn+':user')
            quote=str(mem.get('quote') or mem.get('text') or '')
            if source and quote and quote in source['content'] and str(mem.get('text') or quote)==quote:
                report['verified_user_quotes']+=1
            else: report['legacy_unverified']+=1
        report['legacy_unverified']+=len(legacy)
        return report
    store=StateStore(destination);store.ensure_owner(owner,subject=subject)
    for binding in bindings or []:
        store.bind_channel(owner,binding['channel'],binding['external_id'],subject)
    # Replay privacy decisions BEFORE any content import, including reinstated
    # backups. Old records cannot reappear just because the new DB is rebuilt.
    for mem in inactive:
        mid=str(mem['id']);status=mem.get('status','hidden')
        store.suppress_source(owner,'legacy-memory',mid,'legacy_'+status,purge_message=status=='deleted')
        turn=str(mem.get('source_turn') or '')
        if turn:
            store.suppress_source(owner,'web',turn,'legacy_'+status,purge_message=status=='deleted')
            if not turn.endswith(':user'):store.suppress_source(owner,'web',turn+':user','legacy_'+status,purge_message=status=='deleted')
        store.map_legacy(owner,'web.memories',mid,'fact',status='suppressed_'+status)
        report['suppressed']+=1
    registered={}
    for message in messages:
        try:
            item=store.import_message(owner,subject=subject,**message)
            registered[(message['source'],message['id'])]=item
            store.map_legacy(owner,message['source'],message['id'],'message',item['id'])
            report['imported_messages']+=1
        except (ValueError,ScopeError) as exc:
            report['errors'].append({'kind':'message','id':message['id'],'error':type(exc).__name__})
    kinds={'偏好':'preference','背景':'background','目标':'goal','事件':'event','更正':'correction'}
    for mem in memories:
        if mem in inactive: continue
        mid=str(mem['id'])
        if store.legacy_mapping(owner,'web.memories',mid,'fact'):
            report['already_mapped']+=1;continue
        quote=str(mem.get('quote') or mem.get('text') or '')
        text=str(mem.get('text') or quote)
        if not text: continue
        turn=str(mem.get('source_turn') or '')
        source=registered.get(('web',turn if turn.endswith(':user') else turn+':user'))
        try:
            if source and quote in source['content'] and text==quote:
                # Author and exact quote are rechecked by StateStore. Explicit
                # means preserving an existing user-created saved-memory action,
                # not interpreting old assistant summaries as authorization.
                fact=store.put_fact(owner,subject,quote,[{'message_id':source['id'],'quote':quote}],
                                    kind=kinds.get(mem.get('category'),'background'),assertion_status='user_asserted',
                                    valid_from=source['at'],idempotency_key='migration-memory-'+mid,explicit=True)
                report['verified_user_quotes']+=1
            else:
                raw=store.import_message(owner,'legacy-memory',mid,'legacy',text,at=mem.get('created_at'),subject=subject)
                fact=store.put_fact(owner,subject,text,[{'message_id':raw['id'],'quote':text}],kind='background',
                                    assertion_status='legacy_unverified',idempotency_key='migration-memory-'+mid,explicit=True)
                report['legacy_unverified']+=1
            store.map_legacy(owner,'web.memories',mid,'fact',fact['id'])
        except (EvidenceError,ValueError,ScopeError) as exc:
            # Invalid historical assertions remain available in unchanged raw
            # history. Never bypass validation just to increase import counts.
            store.map_legacy(owner,'web.memories',mid,'fact',status='quarantined')
            report['errors'].append({'kind':'memory','id':mid,'error':type(exc).__name__})
    for key,value in legacy:
        if store.legacy_mapping(owner,'archive',key,'fact'):
            report['already_mapped']+=1;continue
        content=json.dumps(value,ensure_ascii=False,sort_keys=True)
        # Large legacy sections stay source evidence only, avoiding silent
        # truncation into a misleading fact with missing negative conditions.
        raw=store.import_message(owner,'legacy-archive',key,'legacy',content,subject=subject)
        if len(content)<=3000:
            try:
                fact=store.put_fact(owner,subject,content,[{'message_id':raw['id'],'quote':content}],kind='background',
                                    assertion_status='legacy_unverified',idempotency_key='migration-archive-'+key,explicit=True)
                store.map_legacy(owner,'archive',key,'fact',fact['id']);report['legacy_unverified']+=1
            except EvidenceError:
                store.map_legacy(owner,'archive',key,'fact',status='suppressed')
        else:
            store.map_legacy(owner,'archive',key,'fact',status='source_only')
    report['revision']=store.revision(owner)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description='共享状态迁移；默认只读演练，不修改旧数据')
    parser.add_argument('--source',required=True)
    parser.add_argument('--destination',required=True)
    parser.add_argument('--owner',required=True)
    parser.add_argument('--subject',default='self')
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--bindings',help='显式渠道绑定 JSON 文件（channel/external_id 数组）')
    args=parser.parse_args()
    print(json.dumps(migrate(args.source,args.destination,args.owner,args.subject,not args.apply,
                             read_json(Path(args.bindings),[]) if args.bindings else None),ensure_ascii=False,indent=2))
