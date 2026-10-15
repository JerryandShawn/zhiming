"""Pinned Core v3 release tooling. No SSH and no probe messages.

bundle runs in a clean checkout. prepare/freeze/install/publish/maintenance run
locally on the authorized Linux server. plan only prints non-secret paths.
install keeps the maintenance gate closed; publish requires acceptance evidence.
"""
from __future__ import annotations
import argparse
from contextlib import closing,contextmanager
from datetime import datetime,timezone
import hashlib
import io
import json
import os
from pathlib import Path,PurePosixPath
import re
import shlex
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import time
import urllib.request
import uuid

RELEASE_ROOT='/root/zhiming-core-releases'
BACKUP_ROOT='/root/zhiming-core-backups'
NGINX='/www/server/panel/vhost/nginx/p.jerrymeng.asia.conf'
MAINTENANCE='/www/wwwroot/p-acme/core-maintenance.flag'
MAINTENANCE_HTML='/www/wwwroot/p-acme/core-maintenance.html'
SKILL_WRITER_LOCK='/root/zhiming-core-secrets/core-skill-writer.lock'
SKILL_WRITER_TIMEOUT=900
LEGACY_SOURCE='/root/.hermes/zhiming'
LEGACY_CONFIG='/root/.hermes/config.yaml'
LEGACY_JOBS='/root/.hermes/cron/jobs.json'
LEGACY_HERMES_DB='/root/.hermes/state.db'
HERMES_SKILL='/root/.hermes/skills/zhiming'
SKILL_MANIFEST='__core_skill_manifest__.json'
SKILL_BACKUP_MANIFEST='__hermes_skill_backup__.json'
RETIRED_SKILL_PY=('archive.py','archive_store.py','astro.py','bazi.py','chart_context.py','chat_agent.py',
                  'context_engine.py','context_query.py','conversation_store.py','guidance.py','report_pipeline.py',
                  'report_store.py','semantic_index.py','ziwei.py','v6_agent.py','state_store.py','domain_api.py',
                  'tarot_deck.py','tarot_store.py','tarot_guidance.py')
MANIFEST='__release_manifest__.json'
DBS={'stage':'zhiming_core_stage','live':'zhiming_core_live'}
LEGACY_JOB_COUNT=4
CORE_EXTERNAL_WRITERS=('zhiming-core-reports.timer','zhiming-core-reports.service','zhiming-core-feishu.service')
CORE_WRITERS=(*CORE_EXTERNAL_WRITERS,'mingjingtai.service')
CORE_BOOT_WRITERS=('zhiming-core-reports.timer','zhiming-core-feishu.service','mingjingtai.service')


def sha(data):return hashlib.sha256(data).hexdigest()


def file_sha(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):digest.update(chunk)
    return digest.hexdigest()


def release_path(commit,value):
    if not re.fullmatch(r'[0-9a-f]{40}',commit):raise ValueError('commit must be the exact 40-character reviewed SHA')
    expected=PurePosixPath(RELEASE_ROOT)/commit
    if PurePosixPath(value)!=expected:raise ValueError('release path must be '+str(expected))
    return Path(value)


def safe_member(name):
    path=PurePosixPath(name)
    if not name or not path.parts or path.is_absolute() or '..' in path.parts or '\\' in name:raise ValueError('unsafe artifact member')
    return str(path)


def write_private(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    if path.is_symlink():raise ValueError('refusing symlink destination')
    temporary=path.with_name(path.name+'.tmp')
    descriptor=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    try:
        with os.fdopen(descriptor,'wb') as stream:stream.write(data)
        os.replace(temporary,path);os.chmod(path,0o600)
    finally:
        if temporary.exists():temporary.unlink()


def command(argv,*,cwd=None,env=None,capture=False):
    result=subprocess.run(argv,cwd=cwd,env=env,text=True,capture_output=True,encoding='utf-8')
    if result.returncode:
        diagnostic='captured output withheld'
        if sys.platform=='linux' and os.geteuid()==0:
            path=Path(BACKUP_ROOT)/('command-failure-'+stamp()+'-'+str(os.getpid())+'.log')
            write_private(path,(result.stdout+'\n'+result.stderr).encode())
            diagnostic='protected diagnostic: '+str(path)
        raise RuntimeError('Command failed: '+Path(str(argv[0])).name+' (exit '+str(result.returncode)+'); '+diagnostic)
    return result.stdout.strip() if capture else None


def bundle(args):
    root=Path(args.source).resolve()
    head=command(['git','rev-parse','HEAD'],cwd=root,capture=True)
    if head!=args.commit:raise ValueError('checkout is not the requested commit')
    if command(['git','status','--porcelain','--untracked-files=all'],cwd=root,capture=True):raise ValueError('bundle requires a clean committed checkout')
    tree=subprocess.run(['git','ls-tree','-r','-z','--full-tree',args.commit],cwd=root,capture_output=True)
    if tree.returncode:raise RuntimeError('Could not read fixed Git release tree')
    entries=[]
    for record in filter(None,tree.stdout.split(b'\0')):
        metadata,name=record.split(b'\t',1);mode,kind,blob=metadata.decode().split();name=safe_member(name.decode('utf-8'))
        if kind!='blob' or mode not in ('100644','100755'):raise ValueError('release requires ordinary tracked Git blobs; links and submodules require review')
        entries.append((name,mode,blob))
    canonical=subprocess.run(['git','cat-file','--batch'],cwd=root,input=('\n'.join(blob for _,_,blob in entries)+'\n').encode(),capture_output=True)
    if canonical.returncode:raise RuntimeError('Could not read canonical Git release bytes')
    files={};contents={};position=0
    for name,mode,blob in entries:
        boundary=canonical.stdout.index(b'\n',position);ident,kind,size=canonical.stdout[position:boundary].decode().split();size=int(size)
        data=canonical.stdout[boundary+1:boundary+1+size];position=boundary+size+2
        identity=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
        if ident!=blob or kind!='blob' or len(data)!=size or identity!=blob or name in files:raise ValueError('fixed Git blob identity mismatch')
        contents[name]=data;files[name]={'sha256':sha(data),'git_blob_sha1':blob,'mode':int(mode,8)&0o777}
    manifest={'schema':'core3-release-v1','commit':args.commit,'files':files}
    output=Path(args.artifact).resolve();output.parent.mkdir(parents=True,exist_ok=True)
    with tarfile.open(output,'w:gz') as archive:
        content=json.dumps(manifest,sort_keys=True,ensure_ascii=False).encode();info=tarfile.TarInfo(MANIFEST);info.size=len(content);info.mode=0o600
        archive.addfile(info,io.BytesIO(content))
        for name,row in files.items():
            info=tarfile.TarInfo(name);info.size=len(contents[name]);info.mode=row['mode'];archive.addfile(info,io.BytesIO(contents[name]))
    return {'commit':args.commit,'artifact':str(output),'sha256':file_sha(output),'tracked_files':len(files)}


def verify_artifact(path,expected_sha,commit):
    if not re.fullmatch(r'[0-9a-f]{64}',expected_sha or '') or file_sha(path)!=expected_sha:raise ValueError('artifact digest does not match the reviewed package')
    with tarfile.open(path,'r:gz') as archive:
        members=archive.getmembers();names=[safe_member(m.name) for m in members]
        if len(names)!=len(set(names)) or any(not m.isfile() for m in members):raise ValueError('artifact has duplicate or non-regular entries')
        manifest=json.load(archive.extractfile(MANIFEST))
        if manifest.get('schema')!='core3-release-v1' or manifest.get('commit')!=commit:raise ValueError('artifact commit mismatch')
        if set(names)!={MANIFEST,*manifest['files']}:raise ValueError('artifact manifest/member mismatch')
        for name,row in manifest['files'].items():
            safe_member(name)
            data=archive.extractfile(name).read()
            if sha(data)!=row['sha256']:raise ValueError('artifact member digest mismatch')
            if row.get('git_blob_sha1') and hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()!=row['git_blob_sha1']:raise ValueError('artifact Git blob identity mismatch')
        return manifest


def verify_release(args):
    release=release_path(args.commit,args.release_dir)
    if release.is_symlink():raise ValueError('release directory must not be a symlink')
    manifest=json.loads((release/MANIFEST).read_text(encoding='utf-8'))
    if manifest.get('schema')!='core3-release-v1' or manifest.get('commit')!=args.commit or not isinstance(manifest.get('files'),dict):raise ValueError('installed commit or manifest mismatch')
    for name,row in manifest['files'].items():
        path=release/safe_member(name)
        if path.is_symlink() or not path.is_file() or file_sha(path)!=row['sha256']:raise ValueError('installed release was modified')
    return release


def load_environment(args,database):
    env=dict(os.environ)
    for name in args.env_file:
        path=Path(name)
        if path.is_symlink() or not path.is_file() or path.stat().st_mode&0o077:raise ValueError('environment file must exist and be mode 0600: '+name)
        env.update(parse_environment(path.read_text(encoding='utf-8')))
    dsn=env.get('ZHIMING_DATABASE_URL','')
    if not dsn:raise ValueError('protected environment is missing ZHIMING_DATABASE_URL')
    from urllib.parse import urlparse,unquote
    if dsn.startswith(('postgres://','postgresql://')):dbname=unquote(urlparse(dsn).path.lstrip('/'))
    else:dbname=dict(piece.split('=',1) for piece in shlex.split(dsn) if '=' in piece).get('dbname')
    if dbname!=database:raise ValueError('database must be the dedicated '+database)
    if env.get('CORE_DB_POOL_SIZE','4')!='4':raise ValueError('production pool size must remain 4')
    expected_chart=str(Path(args.release_dir)/'venv/charts/bin/python')
    if env.get('CHART_PYTHON',expected_chart)!=expected_chart:raise ValueError('protected chart interpreter must match the accepted release')
    if env.get('ZHIMING_MEDIA_PATH','/root/zhiming-core-media')!='/root/zhiming-core-media':raise ValueError('protected media path must match the dedicated location')
    if env.get('MINGJING_OWNER_ID','primary')!='primary':raise ValueError('release primary owner differs from the reviewed migration')
    if env.get('CORE_FEISHU_ENABLED','true').lower()!='true':raise ValueError('protected live Core Feishu flag must be true')
    env.update(CORE_DB_POOL_SIZE='4',CHART_PYTHON=str(Path(args.release_dir)/'venv/charts/bin/python'),
               ZHIMING_MEDIA_PATH='/root/zhiming-core-media',TZ='Asia/Shanghai')
    return env


def parse_environment(content):
    result={}
    for line in content.splitlines():
        line=line.strip()
        if not line or line.startswith('#'):continue
        if '=' not in line:raise ValueError('unsupported environment file syntax')
        key,value=line.split('=',1)
        if not re.fullmatch('[A-Za-z_][A-Za-z_0-9]*',key):raise ValueError('unsupported environment variable name')
        value=value.strip()
        if value.startswith(("'",'"')):
            tokens=shlex.split(value,comments=False,posix=True)
            if len(tokens)!=1:raise ValueError('environment value must be one quoted literal')
            result[key]=tokens[0]
        else:
            if any(character.isspace() for character in value) or '\\' in value:raise ValueError('environment values with spaces or escapes must be quoted')
            # Preserve JSON mappings and embedded quotes in literal values,
            # matching the reviewed systemd EnvironmentFile format.
            result[key]=value
    return result


def require_host():
    if sys.platform!='linux' or os.geteuid()!=0:raise ValueError('this action runs locally as root on the reviewed Linux host')


def prepare(args):
    require_host();release=release_path(args.commit,args.release_dir)
    manifest=verify_artifact(args.artifact,args.artifact_sha256,args.commit)
    if release.exists():verify_release(args)
    else:
        release.mkdir(parents=True,mode=0o700)
        with tarfile.open(args.artifact,'r:gz') as archive:
            for member in archive.getmembers():
                target=release/safe_member(member.name);target.parent.mkdir(parents=True,exist_ok=True)
                target.write_bytes(archive.extractfile(member).read());target.chmod(member.mode&0o755)
    for name,lock in [('core','requirements-core.lock'),('charts','requirements-charts.lock')]:
        directory=release/'venv'/name
        if not (directory/'bin/python').exists():command([args.python,'-m','venv',str(directory)])
        command([str(directory/'bin/python'),'-m','pip','install','--disable-pip-version-check','-r',str(release/lock)])
        command([str(directory/'bin/python'),'-m','pip','check'])
    command([str(release/'venv/charts/bin/python'),str(release/'tools/verify_core_calculators.py'),'--output',str(release/'calculator-validation.json')],cwd=release)
    return {'prepared':True,'commit':manifest['commit'],'release':str(release),'production_writers_changed':False}


def render_nginx(content):
    if len(re.findall(r'^\s*server\s*\{',content,re.M))!=2 or '127.0.0.1:8787' not in content:raise ValueError('unexpected nginx target configuration; requires fresh review')
    locations=list(re.finditer(r'(?m)^([ \t]*)location\s+/\s*\{',content))
    candidates=[match for match in locations if re.search(r'proxy_pass\s+http://127\.0\.0\.1:8787\s*;',content[match.end():block_end(content,match.end()-1)])]
    if len(candidates)!=1:raise ValueError('nginx reviewed proxy root location is missing or ambiguous')
    match=candidates[0]
    server=next((server for server in re.finditer(r'(?m)^\s*server\s*\{',content) if server.end()<=match.start()<block_end(content,server.end()-1)),None)
    if not server or not re.search(r'listen\s+(?:\S*:)?443\b',content[server.end():match.start()]):raise ValueError('reviewed proxy must belong to the HTTPS server')
    if '# Core v3 maintenance gate' in content:
        body=content[match.end():block_end(content,match.end()-1)]
        https=content[server.end():block_end(content,server.end()-1)]
        if MAINTENANCE not in body or 'error_page 503 =503 /core-maintenance.html;' not in body or 'location = /core-maintenance.html' not in https:raise ValueError('maintenance marker is outside the reviewed HTTPS proxy')
        return content
    indent=match.group(1)
    prefix=indent+'# Core v3 maintenance gate\n'+indent+'location = /core-maintenance.html { root /www/wwwroot/p-acme; internal; }\n'
    replacement=prefix+match.group(0)+'\n'+indent+'    if (-f '+MAINTENANCE+') { return 503; }\n'+indent+'    error_page 503 =503 /core-maintenance.html;\n'
    if re.search(r'proxy_buffering\s+on\s*;',content):raise ValueError('existing nginx buffering must be reviewed before Core SSE release')
    if 'proxy_buffering' not in content:replacement+=indent+'    proxy_buffering off;\n'
    if 'proxy_read_timeout' not in content:replacement+=indent+'    proxy_read_timeout 180s;\n'
    result=content[:match.start()]+replacement+content[match.end():]
    return result


def block_end(content,start):
    depth=0;quote=None;escaped=False;comment=False
    for index in range(start,len(content)):
        character=content[index]
        if comment:
            if character=='\n':comment=False
            continue
        if escaped:escaped=False;continue
        if character=='\\':escaped=True;continue
        if quote:
            if character==quote:quote=None
            continue
        if character in ('"',"'"):quote=character;continue
        if character=='#':comment=True;continue
        if character=='{':depth+=1
        if character=='}':
            depth-=1
            if depth==0:return index
    raise ValueError('unbalanced nginx configuration')


def maintenance_gate():
    Path(MAINTENANCE).parent.mkdir(parents=True,exist_ok=True)
    Path(MAINTENANCE).touch(mode=0o644,exist_ok=True)
    os.chmod(MAINTENANCE,0o644)
    Path(MAINTENANCE_HTML).write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>明镜台维护中</title><body style="margin:10vh auto;max-width:40em;padding:2em;font:18px/1.8 sans-serif;color:#40583d;background:#f4f1e9"><h1>明镜台正在维护</h1><p>你的历史记录与撤销信息正在保留。维护期间暂停写入和投递，恢复后可继续查看。</p></body></html>',encoding='utf-8')
    os.chmod(MAINTENANCE_HTML,0o644)


@contextmanager
def skill_writer_lock(*,exclusive=False,timeout=SKILL_WRITER_TIMEOUT):
    """Linux advisory fence held through CLI exec or the complete backup.

    New Hermes calls check maintenance inside the shared lock. Setting the
    gate before the exclusive lock therefore drains existing calls and closes
    the check/start race, without stopping unrelated Hermes channels.
    """
    import fcntl
    path=Path(SKILL_WRITER_LOCK)
    path.parent.mkdir(parents=True,mode=0o700,exist_ok=True)
    descriptor=os.open(path,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    try:
        os.fchmod(descriptor,0o600)
        deadline=time.monotonic()+timeout
        operation=fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
        while True:
            try:
                fcntl.flock(descriptor,operation|fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic()>=deadline:raise TimeoutError('Core skill writer fence is busy; maintenance retained')
                time.sleep(0.05)
        yield descriptor
    finally:
        os.close(descriptor)


def execute_hermes_core(args,argv):
    """Only the installed Hermes entrypoint uses this maintenance fence."""
    if Path(MAINTENANCE).exists():raise ValueError('Core skill unavailable during maintenance')
    with skill_writer_lock(timeout=0) as descriptor:
        if Path(MAINTENANCE).exists():raise ValueError('Core skill unavailable during maintenance')
        release=verify_release(args)
        env=load_environment(args,DBS['live'])
        python=str(release/'venv/core/bin/python')
        entry=str(release/'hermes/core_consultation.py')
        os.set_inheritable(descriptor,True)
        os.environ.clear();os.environ.update(env)
        os.execv(python,[python,entry,*argv])


def stamp():return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')


def evidence(args):
    report=json.loads(Path(args.acceptance).read_text(encoding='utf-8'))
    if report.get('schema')=='core3-actual-stage-acceptance-incremental-v2':
        from tools.incremental_acceptance import dependency_loader,validate_acceptance,validate_live_acceptance
        release=release_path(args.commit,args.release_dir)
        read=dependency_loader(release)
        validate_acceptance(report,args.commit,(release/MANIFEST).read_bytes(),read)
        if args.action=='publish':validate_live_acceptance(json.loads(read('delivery-live-http.json')),args.commit)
        return report
    required=('stage_accepted','frontend_passed','migration_replay_passed','live_provider_smoke_passed')
    if report.get('commit')!=args.commit or report.get('database')!=DBS['stage'] or report.get('calculator_skips')!=0 or any(report.get(k) is not True for k in required):raise ValueError('release acceptance does not meet the reviewed commit/database gates')
    return report


def legacy_jobs(path,jobs):
    selected=json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(selected,list) or len(selected)!=LEGACY_JOB_COUNT or any(not isinstance(value,str) for value in selected) or len(set(selected))!=LEGACY_JOB_COUNT:
        raise ValueError('exactly four reviewed legacy zhiming job IDs are required')
    found=[job for job in jobs if str(job.get('id')) in selected]
    if len(found)!=LEGACY_JOB_COUNT or any(not any(marker in json.dumps(job,ensure_ascii=False).lower() for marker in ('zhiming','report_pipeline','知命')) for job in found):raise ValueError('legacy job identity/content drifted')
    return selected,found


def snapshot_hashes(directory):
    rows={}
    for path in sorted(Path(directory).rglob('*')):
        if path.is_symlink():raise ValueError('frozen snapshot must not contain symlinks')
        if path.is_file():rows[path.relative_to(directory).as_posix()]=file_sha(path)
    return rows


def snapshot_sqlite(original,destination):
    original=Path(original);destination=Path(destination)
    if original.is_symlink() or not original.is_file() or destination.is_symlink():raise ValueError('SQLite snapshot requires ordinary protected files')
    with closing(sqlite3.connect(original.resolve().as_uri()+'?mode=ro',uri=True)) as source,closing(sqlite3.connect(destination)) as target:
        source.backup(target)
    os.chmod(destination,0o600)
    for suffix in ('-wal','-shm'):Path(str(destination)+suffix).unlink(missing_ok=True)
    return file_sha(destination)


def sync_frozen_hermes(repo,source,bindings,owner='primary'):
    """Final trusted DM originals only: no extraction, consultation or sends."""
    from types import SimpleNamespace
    from mingjing_core.application.memory import MemoryService
    from mingjing_core.adapters.channels.hermes import HermesChannelAdapter
    source=Path(source);before=file_sha(source)
    authors=[row for row in bindings if row.get('channel')=='feishu' and row.get('binding_kind','user')=='user']
    if not authors:raise ValueError('Final Hermes migration requires trusted DM author bindings')
    adapter=HermesChannelAdapter(source.parent,service=SimpleNamespace(repo=repo,memory=MemoryService(repo)),hermes_db=source)
    with repo.transaction(owner):
        prior=len(repo.list(owner,'message'));facts=len(repo.list(owner,'fact'));matched=0
        for row in authors:
            if row.get('owner',owner)!=owner or row.get('subject','self')!='self':raise ValueError('Final Hermes author binding scope differs from the reviewed owner')
            binding=adapter.identity('feishu',row['external_id'])
            if binding['owner']!=owner or binding['subject']!='self' or binding['binding_kind']!='user':raise ValueError('Final Hermes author binding is not trusted')
            matched+=len(adapter.original_rows('feishu',row['external_id'],binding_kind='user'))
            adapter.sync('feishu',row['external_id'],binding_kind='user')
        after=len(repo.list(owner,'message'))
        for row in authors:adapter.sync('feishu',row['external_id'],binding_kind='user')
        if len(repo.list(owner,'message'))!=after or len(repo.list(owner,'fact'))!=facts:raise ValueError('Hermes replay created originals twice or extracted facts')
        if file_sha(source)!=before:raise ValueError('Frozen Hermes source changed')
    return {'trusted_authors':len(authors),'matched_originals':matched,'added_originals':after-prior,'repeat_added':0,'facts_created':0,'external_sends':0}


def export_withdrawals(repo):
    """Export program-compatible privacy ledgers and identifier-only guards."""
    from psycopg import sql
    with repo.connection() as c:
        c.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
        owners=[row['id'] for row in c.execute(sql.SQL('SELECT id FROM {} ORDER BY id').format(repo.table('core_owners'))).fetchall()]
        ledgers=[repo.export_privacy(owner) for owner in owners]
        tarot=c.execute(sql.SQL('SELECT owner,operation,request_key,fingerprint,result_type FROM {} WHERE deleted=true ORDER BY owner,operation,request_key').format(repo.table('tarot_requests'))).fetchall()
        deleted=[]
        for row in c.execute(sql.SQL("SELECT owner,receipt FROM {} WHERE operation LIKE 'tarot-delete:%%' ORDER BY owner,operation,request_key").format(repo.table('core_mutation_requests'))).fetchall():
            deleted.extend({'owner':row['owner'],'draw_id':ident} for ident in row['receipt'].get('deleted_ids',[]))
        receipts=c.execute(sql.SQL("SELECT id,owner,subject,business_id,channel,target,run_id,status,attempts,due,receipt FROM {} WHERE status IN ('sent','sending','uncertain') ORDER BY owner,business_id,channel,target").format(repo.table('delivery_outbox'))).fetchall()
    return {'schema':'core3-withdrawals-v2','owners':ledgers,'tarot_requests':tarot,'deleted_draws':deleted,
            'delivery_receipts':[dict(row,due=row['due'].isoformat(),status='uncertain' if row['status']=='sending' else row['status']) for row in receipts]}


def apply_withdrawals(repo,document):
    """Replay before reopening an older restored PG; never restore old bodies."""
    from collections import defaultdict
    from psycopg import sql
    from psycopg.types.json import Jsonb
    from mingjing_core.adapters.tarot import TarotService
    from mingjing_core.runtime import LangGraphRuntime
    if not isinstance(document,dict) or document.get('schema')!='core3-withdrawals-v2':raise ValueError('A current complete withdrawal export is required')
    ledgers=document.get('owners');requests=document.get('tarot_requests');draws=document.get('deleted_draws');receipts=document.get('delivery_receipts')
    if any(not isinstance(value,list) for value in (ledgers,requests,draws,receipts)):raise ValueError('Withdrawal export arrays are invalid')
    owners={ledger.get('owner_user_id') for ledger in ledgers}
    if any(not isinstance(owner,str) or not owner for owner in owners) or len(owners)!=len(ledgers):raise ValueError('Withdrawal owners must be explicit and unique')
    grouped_requests=defaultdict(list);grouped_draws=defaultdict(set);grouped_receipts=defaultdict(list)
    for row in requests:
        if set(row)!={'owner','operation','request_key','fingerprint','result_type'} or row['owner'] not in owners or not all(isinstance(row[k],str) and row[k] for k in row):raise ValueError('Tarot withdrawal metadata is invalid')
        if row['result_type'] not in ('draw','reading') or not re.fullmatch('[0-9a-f]{64}',row['fingerprint']):raise ValueError('Tarot withdrawal fingerprint/type is invalid')
        grouped_requests[row['owner']].append(row)
    for row in draws:
        if set(row)!={'owner','draw_id'} or row['owner'] not in owners or not isinstance(row['draw_id'],str) or not row['draw_id']:raise ValueError('Deleted draw identifiers are invalid')
        grouped_draws[row['owner']].add(row['draw_id'])
    for row in receipts:
        fields={'id','owner','subject','business_id','channel','target','run_id','status','attempts','due','receipt'}
        if set(row)!=fields or row['owner'] not in owners or row['status'] not in ('sent','uncertain') or type(row['attempts']) is not int or row['attempts']<0:raise ValueError('Delivery receipt metadata is invalid')
        if not all(isinstance(row[k],str) and row[k] for k in fields-{'attempts','receipt'}) or not isinstance(row['receipt'],str) or row['status']=='sent' and not row['receipt']:raise ValueError('Delivery receipt identifiers are invalid')
        due=datetime.fromisoformat(row['due'])
        if due.tzinfo is None:raise ValueError('Delivery receipt due must include a timezone')
        grouped_receipts[row['owner']].append(row)
    removed=0;replayed=0;protected=0;purge=[]
    # Keep every owner's privacy effects and the independent idempotency guards
    # in one transaction. Any mismatched fingerprint aborts the whole replay.
    with repo.transaction() as c:
        for ledger in ledgers:
            owner=ledger['owner_user_id'];repo.assert_scope(owner)
            with repo.transaction(owner):
                draw_ids=set(grouped_draws[owner]);reading_ids=set()
                for row in grouped_requests[owner]:
                    old=c.execute(sql.SQL('SELECT fingerprint,result_id,result_type FROM {} WHERE owner=%s AND operation=%s AND request_key=%s FOR UPDATE').format(repo.table('tarot_requests')),(owner,row['operation'],row['request_key'])).fetchone()
                    if old and (old['fingerprint']!=row['fingerprint'] or old['result_type']!=row['result_type']):raise ValueError('Restored Tarot request differs from the latest withdrawal')
                    if old and old['result_id']:
                        (reading_ids if row['result_type']=='reading' else draw_ids).add(old['result_id'])
                repo.apply_privacy(owner,ledger)
                revocations=repo.revocations(owner)
                fact_ids=[row['entity_id'] for row in revocations if row['kind']=='fact']
                source_ids=[row['entity_id'] for row in revocations if row['kind']=='message']+[row['metadata']['message_id'] for row in revocations if row['kind']=='source_span' and row['metadata'].get('message_id')]
                TarotService(repo).purge_context(owner,fact_ids,source_ids)
                if draw_ids or reading_ids:
                    runs=c.execute(sql.SQL("SELECT id,retry_epoch FROM {} WHERE owner=%s AND (request->>'draw_id'=ANY(%s) OR request->>'reading_id'=ANY(%s)) FOR UPDATE").format(repo.table('core_runs')),(owner,list(draw_ids),list(reading_ids))).fetchall()
                    ids=[row['id'] for row in runs];purge.extend(runs)
                    if ids:
                        c.execute(sql.SQL("UPDATE {} SET request='{{}}',result=NULL,checkpoint='{{}}',status='revoked',error='SOURCE_REVOKED',lease_token=NULL,lease_until=NULL WHERE owner=%s AND id=ANY(%s)").format(repo.table('core_runs')),(owner,ids))
                        c.execute(sql.SQL("UPDATE {} SET data='{{}}',status='deleted' WHERE owner=%s AND kind IN ('runtime_step','interpretive_claim','artifact','model_call','report') AND data->>'run_id'=ANY(%s)").format(repo.table('core_entities')),(owner,ids))
                        c.execute(sql.SQL("UPDATE {} SET payload='{{}}',status=CASE WHEN status IN ('sending','uncertain') THEN 'uncertain' WHEN status='sent' THEN 'sent' ELSE 'cancelled' END,error='SOURCE_REVOKED' WHERE owner=%s AND run_id=ANY(%s)").format(repo.table('delivery_outbox')),(owner,ids))
                    removed+=c.execute(sql.SQL('DELETE FROM {} WHERE owner=%s AND id=ANY(%s)').format(repo.table('tarot_draws')),(owner,list(draw_ids))).rowcount
                    c.execute(sql.SQL('DELETE FROM {} WHERE owner=%s AND id=ANY(%s)').format(repo.table('tarot_readings')),(owner,list(reading_ids)))
                for row in grouped_requests[owner]:
                    c.execute(sql.SQL("INSERT INTO {}(owner,operation,request_key,fingerprint,result_id,result_type,deleted) VALUES(%s,%s,%s,%s,'',%s,true) ON CONFLICT(owner,operation,request_key) DO UPDATE SET result_id='',deleted=true").format(repo.table('tarot_requests')),(owner,row['operation'],row['request_key'],row['fingerprint'],row['result_type']))
                    replayed+=1
                for row in grouped_receipts[owner]:
                    old=c.execute(sql.SQL('SELECT status,receipt FROM {} WHERE owner=%s AND business_id=%s AND channel=%s AND target=%s FOR UPDATE').format(repo.table('delivery_outbox')),(owner,row['business_id'],row['channel'],row['target'])).fetchone()
                    if old and old['status']=='sent' and row['status']=='sent' and old['receipt']!=row['receipt']:raise ValueError('Restored external receipt conflicts with latest delivery ledger')
                    if old and old['status']=='sent':continue
                    proof={'verification':'latest_withdrawal_export'}
                    c.execute(sql.SQL("INSERT INTO {}(id,owner,subject,business_id,channel,target,run_id,payload,dependencies,status,attempts,due,receipt,reconciliation) VALUES(%s,%s,%s,%s,%s,%s,%s,'{{}}','{{}}',%s,%s,%s,%s,%s) ON CONFLICT(owner,business_id,channel,target) DO UPDATE SET payload='{{}}',dependencies='{{}}',status=EXCLUDED.status,attempts=GREATEST({}.attempts,EXCLUDED.attempts),receipt=EXCLUDED.receipt,reconciliation=EXCLUDED.reconciliation,claim_token=NULL,lease_until=NULL").format(repo.table('delivery_outbox'),sql.Identifier('delivery_outbox')),(row['id'],owner,row['subject'],row['business_id'],row['channel'],row['target'],row['run_id'],row['status'],row['attempts'],datetime.fromisoformat(row['due']),row['receipt'],Jsonb(proof)))
                    protected+=1
    # Latest source revocations may have removed additional runs. Purge all
    # revoked threads, not only the run IDs directly linked to a Tarot request.
    with repo.connection() as c:
        purge=c.execute(sql.SQL("SELECT id,retry_epoch FROM {} WHERE owner=ANY(%s) AND status='revoked'").format(repo.table('core_runs')),(list(owners),)).fetchall()
    if purge:
        runtime=LangGraphRuntime(repo,initialize=False)
        for run in purge:
            for epoch in range(run['retry_epoch']+1):runtime.purge(run['id'],epoch)
    return {'owners':len(owners),'deleted_draws':removed,'tarot_tombstones':replayed,'protected_receipts':protected,'external_sends':0,'model_calls':0}


def freeze(args):
    require_host();release=verify_release(args);evidence(args)
    backup=Path(BACKUP_ROOT)/(stamp()+'-'+args.commit[:12]);backup.mkdir(parents=True,mode=0o700)
    original=Path(NGINX).read_bytes();write_private(backup/'nginx.conf',original)
    maintenance_gate();candidate=render_nginx(original.decode())
    Path(NGINX).write_text(candidate,encoding='utf-8')
    try:command(['nginx','-t']);command(['systemctl','reload','nginx'])
    except Exception:
        Path(NGINX).write_bytes(original)
        raise
    with skill_writer_lock(exclusive=True):
        return _freeze_behind_skill_fence(args,backup)


def _freeze_behind_skill_fence(args,backup):
    command(['systemctl','disable','--now','mingjingtai-reports.timer','mingjingtai-reports.service'])
    import yaml
    config_path=Path(LEGACY_CONFIG);jobs_path=Path(LEGACY_JOBS)
    write_private(backup/'hermes-config.yaml',config_path.read_bytes());write_private(backup/'hermes-jobs.json',jobs_path.read_bytes())
    config=yaml.safe_load(config_path.read_text(encoding='utf-8')) or {};jobs_container=json.loads(jobs_path.read_text(encoding='utf-8'));jobs=jobs_container if isinstance(jobs_container,list) else jobs_container['jobs']
    selected,found=legacy_jobs(args.legacy_job_ids,jobs)
    config.setdefault('platforms',{}).setdefault('feishu',{})['enabled']=False
    for job in found:job['enabled']=False
    write_private(config_path,yaml.safe_dump(config,allow_unicode=True,sort_keys=False).encode())
    write_private(jobs_path,json.dumps(jobs_container,ensure_ascii=False,indent=2).encode())
    kill_mode=command(['systemctl','show','hermes.service','--property=KillMode','--value'],capture=True)
    kill_children=command(['systemctl','show','hermes.service','--property=SendSIGKILL','--value'],capture=True)
    if kill_mode not in ('control-group','mixed') or kill_children!='yes':raise ValueError('Hermes restart must terminate old skill children before snapshot')
    # Retire direct old skill entrypoints before refreshing Hermes. The empty
    # source directory only anchors the protected original skill backup; final
    # legacy data snapshots are made after old in-flight Hermes children stop.
    source=backup/'source';source.mkdir(mode=0o700)
    skill=install_hermes_skill(args,source)
    command(['systemctl','restart','hermes.service']);command(['systemctl','is-active','--quiet','hermes.service'])
    command(['systemctl','stop','mingjingtai.service'])
    shutil.copytree(LEGACY_SOURCE,source,symlinks=True,dirs_exist_ok=True)
    snapshot_hashes(source)
    for original_db in Path(LEGACY_SOURCE).rglob('*.db'):
        snapshot_sqlite(original_db,source/original_db.relative_to(LEGACY_SOURCE))
    hermes=backup/'hermes-state.db';hermes_sha=snapshot_sqlite(LEGACY_HERMES_DB,hermes)
    journal={'commit':args.commit,'backup':str(backup),'source_snapshot':str(source),'source_hashes':snapshot_hashes(source),
             'hermes_snapshot':str(hermes),'hermes_sha256':hermes_sha,
             'old_feishu_disabled':True,'old_reports_disabled':True,'legacy_jobs_disabled':selected,'frozen_at':stamp(),
             'skill_entrypoints_retired_before_snapshot':True,'skill_writers_quiescent':True,'hermes_skill':skill}
    write_private(backup/'freeze.json',json.dumps(journal,ensure_ascii=False,indent=2).encode())
    return journal


def units(args):
    release_path(args.commit,args.release_dir);release=PurePosixPath(args.release_dir)
    for path in args.env_file:
        if not re.fullmatch(r'/[A-Za-z0-9_./-]+',path):raise ValueError('unsupported environment file path')
    environment=''.join('EnvironmentFile='+path+'\n' for path in args.env_file)
    base='[Unit]\nAfter=network-online.target\nWants=network-online.target\n\n[Service]\nUser=root\nUMask=0077\nWorkingDirectory='+str(release)+'\n'+environment+'Environment=TZ=Asia/Shanghai\nEnvironment=CORE_DB_POOL_SIZE=4\nEnvironment=CHART_PYTHON='+str(release/'venv/charts/bin/python')+'\nEnvironment=ZHIMING_MEDIA_PATH=/root/zhiming-core-media\n'
    python=str(release/'venv/core/bin/python')
    web=base+'Type=simple\nExecStart='+python+' -m uvicorn main:app --host 127.0.0.1 --port 8787 --workers 1 --timeout-keep-alive 30\nRestart=on-failure\nRestartSec=5\n\n[Install]\nWantedBy=multi-user.target\n'
    report=base+'Type=oneshot\nExecStart='+python+' -m mingjing_core.adapters.core_report_worker --owner primary\nTimeoutStartSec=900\n'
    gateway=base+'Type=simple\nEnvironment=CORE_FEISHU_ENABLED=true\nExecStart='+python+' -m mingjing_core.adapters.feishu_gateway\nRestart=on-failure\nRestartSec=10\n\n[Install]\nWantedBy=multi-user.target\n'
    timer='[Unit]\nDescription=Check Core PG report outbox each Shanghai minute\n\n[Timer]\nOnCalendar=*-*-* *:*:00 Asia/Shanghai\nAccuracySec=1s\nRandomizedDelaySec=0\nPersistent=true\nUnit=zhiming-core-reports.service\n\n[Install]\nWantedBy=timers.target\n'
    return {'mingjingtai.service':web,'zhiming-core-reports.service':report,'zhiming-core-reports.timer':timer,'zhiming-core-feishu.service':gateway}


def verify_legacy_disabled(args):
    import yaml
    config=yaml.safe_load(Path(LEGACY_CONFIG).read_text(encoding='utf-8'))
    if config.get('platforms',{}).get('feishu',{}).get('enabled') is not False:raise ValueError('old Hermes Feishu adapter is still enabled')
    container=json.loads(Path(LEGACY_JOBS).read_text(encoding='utf-8'));jobs=container if isinstance(container,list) else container['jobs']
    selected,matches=legacy_jobs(args.legacy_job_ids,jobs)
    if any(job.get('enabled') is not False for job in matches):raise ValueError('old zhiming cron jobs are still enabled or changed')
    for name in ('mingjingtai-reports.timer','mingjingtai-reports.service'):
        result=subprocess.run(['systemctl','is-active','--quiet',name])
        if result.returncode==0:raise ValueError('old report writer is active')


def verify_core_external_inactive():
    for name in CORE_EXTERNAL_WRITERS:
        state=command(['systemctl','show',name,'--property=ActiveState','--value'],capture=True)
        if state not in ('inactive','failed'):raise ValueError('Core external writers must be inactive before install or publish')


def stop_core_writers():
    """Best effort every unit, then prove quiescence and persistent boot state."""
    result={'maintenance_gate_reinstated':False,'units':{},'unit_writers_stopped':False,'skill_writers_quiescent':False,'writers_stopped':False,
            'boot_writers_disabled':False,'cleanup_complete':False,'errors':[]}
    def failed(phase,error,name=None):
        row={'phase':phase,'code':'CORE_WRITER_SHUTDOWN_FAILED','type':type(error).__name__}
        if name is not None:row['unit']=name
        result['errors'].append(row)
    try:
        maintenance_gate();result['maintenance_gate_reinstated']=True
    except BaseException as error:failed('maintenance_gate',error)
    for name in CORE_WRITERS:
        row={'disable_ok':None,'stop_ok':False,'inactive':False,'boot_disabled':None};result['units'][name]=row
        if name in CORE_BOOT_WRITERS:
            try:command(['systemctl','disable','--now',name]);row['disable_ok']=True
            except BaseException as error:row['disable_ok']=False;failed('disable_writer',error,name)
        try:command(['systemctl','stop',name]);row['stop_ok']=True
        except BaseException as error:failed('stop_writer',error,name)
    for name,row in result['units'].items():
        try:
            state=command(['systemctl','show',name,'--property=ActiveState','--value'],capture=True)
            row['active_state']=state if state in ('inactive','failed','active','activating','deactivating','reloading') else 'unknown'
            row['inactive']=state in ('inactive','failed')
            if not row['inactive']:raise ValueError('Core writer still active')
        except BaseException as error:failed('verify_writer_stopped',error,name)
        if name in CORE_BOOT_WRITERS:
            try:
                state=command(['systemctl','show',name,'--property=UnitFileState','--value'],capture=True)
                row['unit_file_state']=state if state in ('disabled','masked','masked-runtime','enabled','enabled-runtime','static','indirect') else 'unknown'
                row['boot_disabled']=state in ('disabled','masked')
                if not row['boot_disabled']:raise ValueError('Core writer may restart on boot')
            except BaseException as error:failed('verify_boot_writer_disabled',error,name)
    result['unit_writers_stopped']=all(row['inactive'] is True for row in result['units'].values())
    if result['maintenance_gate_reinstated']:
        try:
            # After the gate is present no new wrapped CLI can begin. This
            # check waits out inherited shared fds; maintenance takes the
            # same exclusive fence again through the actual backup/journal.
            with skill_writer_lock(exclusive=True):result['skill_writers_quiescent']=True
        except BaseException as error:failed('quiesce_skill_writers',error)
    result['writers_stopped']=result['unit_writers_stopped'] and result['skill_writers_quiescent']
    result['boot_writers_disabled']=all(result['units'][name]['boot_disabled'] is True for name in CORE_BOOT_WRITERS)
    result['cleanup_complete']=(result['maintenance_gate_reinstated'] and result['writers_stopped']
                                and result['boot_writers_disabled'] and not result['errors'])
    return result


def record_operation_failure(args,action,error,cleanup):
    """Private operational evidence; recording must not mask the original error."""
    try:
        directory=Path(BACKUP_ROOT)/(stamp()+'-'+action+'-failure-'+args.commit[:12]+'-'+uuid.uuid4().hex[:8])
        directory.mkdir(parents=True,mode=0o700)
        record={'schema':'core3-release-operation-failure-v1','commit':args.commit,'action':action,
                'failure':{'code':'RELEASE_OPERATION_FAILED','type':type(error).__name__},'cleanup':cleanup,
                'rollback_complete':False,'automatic_retry_performed':False,'old_loop_reenabled':False}
        write_private(directory/'failure.json',json.dumps(record,ensure_ascii=False).encode())
    except BaseException:pass


def skill_paths(source=None):
    target=Path(HERMES_SKILL)
    if not target.is_absolute() or target.name!='zhiming' or target.parent.name!='skills' or not target.parent.is_dir():raise ValueError('Hermes skill path must be the explicit existing skills/zhiming directory')
    for path in (target,*target.parents):
        if path.is_symlink():raise ValueError('Hermes skill path must not contain a symlink')
    if target.exists() and not target.is_dir():raise ValueError('Hermes skill target must be a directory')
    if source is None:return target,None
    source=Path(source)
    backup=source.parent/'hermes-skill'
    if source.is_symlink() or not source.is_dir() or not source.resolve().is_relative_to(Path(BACKUP_ROOT).resolve()):raise ValueError('Hermes skill backup requires the explicit frozen source directory')
    for path in (backup,*backup.parents):
        if path.is_symlink():raise ValueError('Hermes skill backup path must not contain a symlink')
    return target,backup


def skill_wrapper(args):
    release_path(args.commit,args.release_dir)
    # No credential values are embedded. Parse the exact service env-file order
    # in the fixed release, then exec without a shell or argv reconstruction.
    config={'commit':args.commit,'release_dir':args.release_dir,'env_file':list(args.env_file)}
    return ('''"""Fixed Core entrypoint; runtime secrets stay in protected env files."""
import json,os,sys
from types import SimpleNamespace
def main():
 try:
  config=json.loads(CONFIG_JSON)
  sys.path.insert(0,config['release_dir'])
  from tools.deploy_core import execute_hermes_core
  args=SimpleNamespace(**config)
  execute_hermes_core(args,sys.argv[1:])
 except Exception:
  sys.stderr.write('CORE_SKILL_CONFIGURATION_ERROR: protected configuration or fixed release failed; no legacy fallback.\\n')
  raise SystemExit(78)
if __name__=='__main__':main()
'''.replace('CONFIG_JSON',repr(json.dumps(config,sort_keys=True)))).encode()


def retired_skill_stub():
    return ("import sys\nsys.stderr.write('LEGACY_SKILL_RETIRED: 旧入口已退役，请使用本目录 core_consultation.py；禁止旧事实写入或第二次解释。\\n')\nraise SystemExit(64)\n").encode()


def expected_skill_files(args,legacy_names):
    release=verify_release(args)
    names=set(RETIRED_SKILL_PY)|set(legacy_names)
    if any(not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*\.py',name) for name in names):raise ValueError('Unexpected Hermes legacy source name')
    names.discard('core_consultation.py')
    files={name:retired_skill_stub() for name in names}
    files['SKILL.md']=(release/'hermes/SKILL.md').read_bytes()
    files['core_consultation.py']=skill_wrapper(args)
    return files


def install_hermes_skill(args,source):
    target,backup=skill_paths(source)
    target.mkdir(mode=0o700,exist_ok=True)
    original_names={path.name for path in target.iterdir() if path.name=='SKILL.md' or path.suffix=='.py' or path.name==SKILL_MANIFEST}
    for name in original_names:
        path=target/name
        if path.is_symlink() or not path.is_file():raise ValueError('Hermes skill source must be an ordinary file')
    if backup.exists():
        if not backup.is_dir():raise ValueError('Hermes skill backup is not a directory')
        journal=json.loads((backup/SKILL_BACKUP_MANIFEST).read_text(encoding='utf-8'))
        if journal.get('schema')!='core3-hermes-skill-backup-v1' or journal.get('commit')!=args.commit or not isinstance(journal.get('files'),dict):raise ValueError('Hermes skill backup belongs to a different freeze')
        for name,row in journal['files'].items():
            if name not in ('SKILL.md',SKILL_MANIFEST) and not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*\.py',name):raise ValueError('Unsafe Hermes skill backup member')
            path=backup/name
            if path.is_symlink() or not path.is_file() or file_sha(path)!=row['sha256']:raise ValueError('Original Hermes skill backup changed; refusing overwrite')
        if {p.name for p in backup.iterdir()}!={SKILL_BACKUP_MANIFEST,*journal['files']}:raise ValueError('Unexpected Hermes skill backup member')
        allowed_python={name for name in journal['files'] if name.endswith('.py')}|set(RETIRED_SKILL_PY)|{'core_consultation.py'}
        if {name for name in original_names if name.endswith('.py')}-allowed_python:raise ValueError('Unknown Hermes Python entrypoint appeared after the frozen inventory')
    else:
        backup.mkdir(mode=0o700)
        journal={'schema':'core3-hermes-skill-backup-v1','commit':args.commit,'files':{}}
        for name in sorted(original_names):
            data=(target/name).read_bytes();write_private(backup/name,data)
            journal['files'][name]={'sha256':sha(data)}
        write_private(backup/SKILL_BACKUP_MANIFEST,json.dumps(journal,sort_keys=True).encode())
    legacy_names={name for name in original_names|set(journal['files']) if name.endswith('.py')}
    files=expected_skill_files(args,legacy_names)
    for name,data in sorted(files.items()):write_private(target/name,data)
    installed={'schema':'core3-hermes-skill-v1','commit':args.commit,'release_dir':args.release_dir,
               'env_files':list(args.env_file),'legacy_names':sorted(set(files)-{'SKILL.md','core_consultation.py'}),
               'original_files':journal['files'],'backup_path':str(backup),
               'backup_manifest_sha256':file_sha(backup/SKILL_BACKUP_MANIFEST),
               'files':{name:{'sha256':sha(data)} for name,data in sorted(files.items())}}
    write_private(target/SKILL_MANIFEST,json.dumps(installed,sort_keys=True).encode())
    verify_hermes_skill(args)
    return {'installed':True,'commit':args.commit,'retired_python_entries':len(installed['legacy_names']),'original_backup_preserved':True,'model_calls':0,'external_sends':0}


def verify_hermes_skill(args):
    target,_=skill_paths()
    path=target/SKILL_MANIFEST
    if path.is_symlink() or not path.is_file():raise ValueError('Fixed Core Hermes skill is not installed')
    installed=json.loads(path.read_text(encoding='utf-8'))
    if installed.get('schema')!='core3-hermes-skill-v1' or installed.get('commit')!=args.commit or installed.get('release_dir')!=args.release_dir or installed.get('env_files')!=list(args.env_file):raise ValueError('Hermes skill version or protected environment order differs')
    legacy=installed.get('legacy_names')
    if not isinstance(legacy,list):raise ValueError('Hermes skill retired-source manifest is missing')
    backup=Path(installed.get('backup_path',''))
    if not backup.is_absolute() or backup.name!='hermes-skill' or not backup.resolve().is_relative_to(Path(BACKUP_ROOT).resolve()) or any(p.is_symlink() for p in (backup,*backup.parents)):raise ValueError('Hermes original backup location differs')
    backup_manifest=backup/SKILL_BACKUP_MANIFEST
    if backup_manifest.is_symlink() or not backup_manifest.is_file() or file_sha(backup_manifest)!=installed.get('backup_manifest_sha256'):raise ValueError('Hermes original backup manifest changed')
    original=json.loads(backup_manifest.read_text(encoding='utf-8'))
    if original.get('schema')!='core3-hermes-skill-backup-v1' or original.get('commit')!=args.commit or original.get('files')!=installed.get('original_files'):raise ValueError('Hermes original source inventory differs')
    original_python={name for name in original['files'] if name.endswith('.py') and name!='core_consultation.py'}
    if set(legacy)!=(original_python|set(RETIRED_SKILL_PY)):raise ValueError('Hermes retired inventory is incomplete')
    for name,row in original['files'].items():
        if name not in ('SKILL.md',SKILL_MANIFEST) and not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*\.py',name):raise ValueError('Unsafe Hermes original backup name')
        path=backup/name
        if path.is_symlink() or not path.is_file() or file_sha(path)!=row['sha256']:raise ValueError('Hermes original source backup changed')
    expected=expected_skill_files(args,legacy)
    if installed.get('files')!={name:{'sha256':sha(data)} for name,data in sorted(expected.items())}:raise ValueError('Hermes skill manifest differs from the fixed release')
    actual={p.name for p in target.iterdir() if p.suffix=='.py'}
    if actual!={name for name in expected if name.endswith('.py')}:raise ValueError('Unknown or missing Hermes Python entrypoint')
    for name,data in expected.items():
        path=target/name
        if path.is_symlink() or not path.is_file() or path.read_bytes()!=data:raise ValueError('Hermes Core wrapper, SKILL or retired entrypoint changed')
    return {'verified':True,'commit':args.commit,'retired_python_entries':len(legacy)}


def install(args):
    require_host();release=verify_release(args);evidence(args);verify_legacy_disabled(args)
    if not Path(MAINTENANCE).exists():raise ValueError('public writes must be frozen before final migration')
    verify_core_external_inactive()
    env=load_environment(args,DBS['live']);source=Path(args.source_snapshot)
    bindings=Path(args.bindings)
    if bindings.is_symlink() or not bindings.is_file() or bindings.stat().st_mode&0o077:raise ValueError('trusted binding file must be protected mode 0600')
    if not source.is_dir() or not source.resolve().is_relative_to(Path(BACKUP_ROOT).resolve()):raise ValueError('final migration requires the protected frozen snapshot')
    frozen=json.loads((source.parent/'freeze.json').read_text(encoding='utf-8'))
    if frozen.get('commit')!=args.commit or frozen.get('source_snapshot')!=str(source) or frozen.get('source_hashes')!=snapshot_hashes(source):raise ValueError('frozen migration source or commit changed')
    hermes=Path(frozen.get('hermes_snapshot',''))
    if hermes!=source.parent/'hermes-state.db' or hermes.is_symlink() or not hermes.is_file() or hermes.stat().st_mode&0o077 or file_sha(hermes)!=frozen.get('hermes_sha256'):raise ValueError('final frozen Hermes source or digest changed')
    migration_args=argparse.Namespace(**vars(args));migration_args.env_file=args.env_file+args.migration_env_file
    migration_env=load_environment(migration_args,DBS['live'])
    python=str(release/'venv/core/bin/python')
    migration_env['CORE_RUNTIME_DSN_CHECK']=env['ZHIMING_DATABASE_URL']
    check='import os,psycopg; from psycopg.conninfo import conninfo_to_dict; m=conninfo_to_dict(os.environ["ZHIMING_DATABASE_URL"]); r=conninfo_to_dict(os.environ["CORE_RUNTIME_DSN_CHECK"]); assert m.get("user") and m.get("user")!=r.get("user") and all(m.get(k)==r.get(k) for k in ("dbname","host","port")); c=psycopg.connect(os.environ["ZHIMING_DATABASE_URL"]); v=c.execute("SHOW server_version_num").fetchone()[0]; assert 150000<=int(v)<160000; role=c.execute("SELECT rolsuper,rolcreatedb,rolcreaterole FROM pg_roles WHERE rolname=%s",(r.get("user"),)).fetchone(); assert role is not None and not any(role); c.close()'
    command([python,'-c',check],env=migration_env)
    command([python,str(release/'migration_core.py'),'--source',str(source),'--owner','primary','--apply','--dsn-env','ZHIMING_DATABASE_URL','--schema','mingjing_core','--bindings',args.bindings],cwd=release,env=migration_env)
    migration_env['CORE_FINAL_HERMES_SNAPSHOT']=str(hermes)
    migration_env['CORE_FINAL_HERMES_SHA256']=frozen['hermes_sha256']
    migration_env['CORE_FINAL_BINDINGS']=str(bindings)
    hermes_sync='''import os,json
from pathlib import Path
from tools.deploy_core import file_sha,sync_frozen_hermes
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.application.report_schedules import ReportScheduleService
source=Path(os.environ['CORE_FINAL_HERMES_SNAPSHOT'])
assert file_sha(source)==os.environ['CORE_FINAL_HERMES_SHA256']
bindings=json.loads(Path(os.environ['CORE_FINAL_BINDINGS']).read_text(encoding='utf-8'))
repo=PostgresRepository(os.environ['ZHIMING_DATABASE_URL'],initialize=False,max_size=2)
try:
 repo.verify_schema()
 result=sync_frozen_hermes(repo,source,bindings)
 result['schedule_defaults']=ReportScheduleService(repo).seed_defaults('primary')
finally:repo.close()
path=source.parent/'final-hermes-migration.json'
descriptor=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
with os.fdopen(descriptor,'w') as stream:json.dump(result,stream)
'''
    command([python,'-c',hermes_sync],env=migration_env,cwd=release)
    checkpoint='''import os,psycopg
from psycopg.rows import dict_row
from langgraph.checkpoint.postgres import PostgresSaver
with psycopg.connect(os.environ['ZHIMING_DATABASE_URL'],autocommit=True,prepare_threshold=0,row_factory=dict_row) as connection:
 connection.execute('SET search_path TO public')
 PostgresSaver(connection).setup()
'''
    command([python,'-c',checkpoint],env=migration_env)
    grants='''import os,psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict
role=sql.Identifier(conninfo_to_dict(os.environ['CORE_RUNTIME_DSN_CHECK'])['user'])
with psycopg.connect(os.environ['ZHIMING_DATABASE_URL']) as c:
 c.execute(sql.SQL('GRANT USAGE ON SCHEMA mingjing_core TO {}').format(role))
 c.execute(sql.SQL('GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA mingjing_core TO {}').format(role))
 c.execute(sql.SQL('GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA mingjing_core TO {}').format(role))
 c.execute(sql.SQL('REVOKE INSERT,UPDATE,DELETE ON mingjing_core.schema_migrations FROM {}').format(role))
 c.execute(sql.SQL('GRANT USAGE ON SCHEMA public TO {}').format(role))
 c.execute('REVOKE CREATE ON SCHEMA public FROM PUBLIC')
 c.execute(sql.SQL('REVOKE CREATE ON SCHEMA public,mingjing_core FROM {}').format(role))
 for table in ('checkpoints','checkpoint_blobs','checkpoint_writes'):
  c.execute(sql.SQL('GRANT SELECT,INSERT,UPDATE,DELETE ON public.{} TO {}').format(sql.Identifier(table),role))
 c.execute(sql.SQL('GRANT SELECT ON public.checkpoint_migrations TO {}').format(role))
'''
    command([python,'-c',grants],env=migration_env)
    runtime_check='''from mingjing_core.application.consultation import ConsultationService
service=ConsultationService.from_base()
try:
 service.repo.assert_scope('primary')
 with service.repo.connection() as c:
  permissions=c.execute("SELECT has_schema_privilege(current_user,'mingjing_core','CREATE') OR has_schema_privilege(current_user,'public','CREATE') AS elevated").fetchone()
  assert permissions['elevated'] is False
finally:service.repo.close()
'''
    command([python,'-c',runtime_check],env=env,cwd=release)
    skill_install=install_hermes_skill(args,source)
    command(['systemctl','restart','hermes.service']);command(['systemctl','is-active','--quiet','hermes.service'])
    verify_legacy_disabled(args)
    unit_directory=Path('/etc/systemd/system');backup=source.parent/'units';backup.mkdir(mode=0o700,exist_ok=True)
    for name,text in units(args).items():
        target=unit_directory/name
        if target.exists() and not (backup/name).exists():write_private(backup/name,target.read_bytes())
        target.write_text(text,encoding='utf-8');target.chmod(0o644)
    command(['systemctl','daemon-reload']);command(['systemctl','enable','--now','mingjingtai.service'])
    return {'installed':True,'commit':args.commit,'maintenance':True,'database':DBS['live'],'effects_started':False,'hermes_skill':skill_install}


def publish(args):
    require_host();release=verify_release(args);evidence(args);verify_legacy_disabled(args)
    verify_hermes_skill(args)
    env=load_environment(args,DBS['live'])
    if not Path(MAINTENANCE).exists():raise ValueError('release must remain behind the maintenance gate until publication')
    if render_nginx(Path(NGINX).read_text(encoding='utf-8'))!=Path(NGINX).read_text(encoding='utf-8'):raise ValueError('reviewed maintenance gate is not installed')
    command(['systemctl','is-active','--quiet','mingjingtai.service'])
    if command(['systemctl','show','mingjingtai.service','--property=WorkingDirectory','--value'],capture=True)!=str(release):raise ValueError('running web service does not point at the accepted release')
    request=urllib.request.Request('http://127.0.0.1:8787/api/health',headers={'X-Token':env.get('MINGJING_TOKEN','')})
    with urllib.request.urlopen(request,timeout=30) as response:health=json.load(response)
    if not health.get('ok') or health.get('context_version')!='core3.0' or health.get('database')!='postgresql' or health.get('runtime')!='langgraph':raise ValueError('new website health did not confirm Core v3')
    try:
        verify_core_external_inactive()
        command(['nginx','-t'])
        command(['systemctl','enable','--now','zhiming-core-feishu.service','zhiming-core-reports.timer'])
        command(['systemctl','is-active','--quiet','zhiming-core-feishu.service','zhiming-core-reports.timer'])
        Path(MAINTENANCE).unlink(missing_ok=True)
    except BaseException as error:
        try:
            cleanup=stop_core_writers()
            cleanup.update(latest_backup_attempted=False,latest_backup_completed=False)
            if cleanup['cleanup_complete']:
                cleanup['latest_backup_attempted']=True
                try:
                    backup=maintenance(args)
                    cleanup['latest_backup_completed']=backup.get('maintenance') is True and backup.get('writers_stopped') is True
                    if not cleanup['latest_backup_completed']:raise ValueError('Latest maintenance backup incomplete')
                except BaseException as backup_error:
                    cleanup['cleanup_complete']=False
                    cleanup['errors'].append({'phase':'latest_pg_and_withdrawal_backup','code':'LATEST_MAINTENANCE_BACKUP_FAILED','type':type(backup_error).__name__})
            record_operation_failure(args,'publish',error,cleanup)
        except BaseException as cleanup_error:
            record_operation_failure(args,'publish',error,{'cleanup_complete':False,'errors':[{'phase':'cleanup_internal','type':type(cleanup_error).__name__}]})
        raise
    return {'published':True,'commit':args.commit,'live_health':True,'probe_messages_sent':0,'model_probe_calls':0}


def maintenance(args):
    require_host();cleanup=stop_core_writers()
    if cleanup['cleanup_complete'] is not True:
        error=ValueError('Core writer shutdown incomplete; maintenance gate retained')
        record_operation_failure(args,'maintenance',error,cleanup)
        raise error
    cleanup['skill_writers_quiescent']=False
    try:
        with skill_writer_lock(exclusive=True):
            cleanup['skill_writers_quiescent']=True
            return _maintenance_backup(args,cleanup)
    except BaseException as error:
        if not cleanup['skill_writers_quiescent']:
            cleanup['writers_stopped']=False;cleanup['cleanup_complete']=False
            cleanup['errors'].append({'phase':'skill_writer_fence','code':'CORE_SKILL_WRITER_FENCE_BUSY','type':type(error).__name__})
            record_operation_failure(args,'maintenance',error,cleanup)
        raise


def _maintenance_backup(args,cleanup):
    Path(NGINX).write_text(render_nginx(Path(NGINX).read_text(encoding='utf-8')),encoding='utf-8')
    command(['nginx','-t']);command(['systemctl','reload','nginx'])
    release=verify_release(args)
    env=load_environment(args,DBS['live']);directory=Path(BACKUP_ROOT)/(stamp()+'-maintenance-'+args.commit[:12]+'-'+uuid.uuid4().hex[:8]);directory.mkdir(parents=True,mode=0o700)
    code='''import os,json,subprocess
from psycopg.conninfo import conninfo_to_dict
from tools.deploy_core import export_withdrawals
from mingjing_core.repositories.postgres import PostgresRepository
repo=PostgresRepository(os.environ['ZHIMING_DATABASE_URL'],initialize=False,max_size=2)
try:ledger=export_withdrawals(repo)
finally:repo.close()
descriptor=os.open(os.environ['CORE_REVOCATION_EXPORT'],os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
with os.fdopen(descriptor,'w') as f:json.dump(ledger,f,ensure_ascii=False,default=str)
fields=conninfo_to_dict(os.environ['ZHIMING_DATABASE_URL']); dump_env=dict(os.environ)
for key,name in [('host','PGHOST'),('port','PGPORT'),('user','PGUSER'),('password','PGPASSWORD'),('dbname','PGDATABASE')]:
 if key in fields:dump_env[name]=fields[key]
descriptor=os.open(os.environ['CORE_DATABASE_EXPORT'],os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
with os.fdopen(descriptor,'wb') as f:subprocess.run(['pg_dump','--format=custom','--no-owner','--no-acl'],env=dump_env,stdout=f,stderr=subprocess.PIPE,check=True)
'''
    env['CORE_REVOCATION_EXPORT']=str(directory/'withdrawals-latest.json')
    env['CORE_DATABASE_EXPORT']=str(directory/'core-live-latest.dump')
    command([str(release/'venv/core/bin/python'),'-c',code],cwd=release,env=env)
    write_private(directory/'maintenance.json',json.dumps({'commit':args.commit,'database':DBS['live'],'withdrawals':'withdrawals-latest.json','withdrawals_sha256':file_sha(directory/'withdrawals-latest.json'),
                  'database_snapshot':'core-live-latest.dump','database_sha256':file_sha(directory/'core-live-latest.dump'),'old_loop_reenabled':False,'at':stamp()}).encode())
    return {'maintenance':True,'writers_stopped':True,'latest_revocations_retained':str(directory),'old_explanation_loop_reenabled':False,'safety_cleanup':cleanup}


def restore_withdrawals(args):
    require_host();release=verify_release(args);verify_legacy_disabled(args)
    if not Path(MAINTENANCE).is_file():raise ValueError('withdrawal restore requires the public maintenance gate')
    for name in ('mingjingtai.service','zhiming-core-feishu.service','zhiming-core-reports.service','zhiming-core-reports.timer'):
        if subprocess.run(['systemctl','is-active','--quiet',name]).returncode==0:raise ValueError('withdrawal restore requires every Core writer stopped')
    with skill_writer_lock(exclusive=True):
        return _restore_withdrawals_behind_skill_fence(args)


def _restore_withdrawals_behind_skill_fence(args):
    release=Path(args.release_dir)
    path=Path(args.withdrawals)
    if path.is_symlink() or not path.is_file() or path.stat().st_mode&0o077 or not path.resolve().is_relative_to(Path(BACKUP_ROOT).resolve()):raise ValueError('latest withdrawals must be a protected backup file')
    journal=json.loads((path.parent/'maintenance.json').read_text(encoding='utf-8'))
    if path.name!=journal.get('withdrawals') or file_sha(path)!=journal.get('withdrawals_sha256') or journal.get('database')!=DBS['live']:raise ValueError('withdrawal backup digest/database mismatch')
    inputs=argparse.Namespace(**vars(args));inputs.env_file=args.env_file+args.migration_env_file
    env=load_environment(inputs,DBS['live']);env['CORE_WITHDRAWAL_RESTORE']=str(path)
    code='''import os,json
from pathlib import Path
from tools.deploy_core import apply_withdrawals
from mingjing_core.repositories.postgres import PostgresRepository
repo=PostgresRepository(os.environ['ZHIMING_DATABASE_URL'],initialize=False,max_size=2)
try:
 repo.verify_schema()
 result=apply_withdrawals(repo,json.loads(Path(os.environ['CORE_WITHDRAWAL_RESTORE']).read_text(encoding='utf-8')))
finally:repo.close()
print(json.dumps(result))
'''
    result=json.loads(command([str(release/'venv/core/bin/python'),'-c',code],cwd=release,env=env,capture=True))
    return dict(result,maintenance=True,withdrawals_replayed=True,old_explanation_loop_reenabled=False)


def parser():
    result=argparse.ArgumentParser(description=__doc__)
    result.add_argument('action',choices=('plan','bundle','prepare','freeze','install','publish','maintenance','restore-withdrawals'))
    result.add_argument('--commit',required=True);result.add_argument('--release-dir',required=True)
    result.add_argument('--source',default='.');result.add_argument('--artifact');result.add_argument('--artifact-sha256')
    result.add_argument('--python',default='/usr/bin/python3.11')
    result.add_argument('--env-file',action='append',default=[])
    result.add_argument('--migration-env-file',action='append',default=[])
    result.add_argument('--acceptance');result.add_argument('--bindings');result.add_argument('--legacy-job-ids');result.add_argument('--source-snapshot')
    result.add_argument('--withdrawals')
    return result


def main(argv=None):
    args=parser().parse_args(argv);release_path(args.commit,args.release_dir)
    if args.action=='plan':
        output={'commit':args.commit,'release':args.release_dir,'databases':DBS,'nginx':NGINX,'maintenance_flag':MAINTENANCE,'sequence':['bundle','prepare','stage acceptance','freeze','install','publish'],'rollback':'maintenance preserves live PG and latest revocation ledger; never restarts old controller','units':list(units(args))}
    else:
        required={'bundle':['artifact'],'prepare':['artifact','artifact_sha256'],'freeze':['acceptance','legacy_job_ids'],'install':['acceptance','legacy_job_ids','bindings','source_snapshot'],'publish':['acceptance','legacy_job_ids'],'maintenance':[],'restore-withdrawals':['withdrawals','legacy_job_ids']}[args.action]
        if any(not getattr(args,name) for name in required):raise ValueError('missing action inputs: '+', '.join(required))
        if args.action in ('install','publish','maintenance','restore-withdrawals') and not args.env_file:raise ValueError('protected original/provider/Core environment files required')
        if args.action in ('install','restore-withdrawals') and not args.migration_env_file:raise ValueError('a separate protected migration-owner environment file is required')
        output=globals()[args.action.replace('-','_')](args)
    print(json.dumps(output,ensure_ascii=False,indent=2));return 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except (ValueError,RuntimeError,OSError,KeyError) as exc:
        print(json.dumps({'ok':False,'error':str(exc)},ensure_ascii=False),file=sys.stderr);raise SystemExit(1)
