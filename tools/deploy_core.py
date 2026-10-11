"""Pinned Core v3 release tooling. No SSH and no probe messages.

bundle runs in a clean checkout. prepare/freeze/install/publish/maintenance run
locally on the authorized Linux server. plan only prints non-secret paths.
install keeps the maintenance gate closed; publish requires acceptance evidence.
"""
from __future__ import annotations
import argparse
from contextlib import closing
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
import urllib.request

RELEASE_ROOT='/root/zhiming-core-releases'
BACKUP_ROOT='/root/zhiming-core-backups'
NGINX='/www/server/panel/vhost/nginx/p.jerrymeng.asia.conf'
MAINTENANCE='/www/wwwroot/p-acme/core-maintenance.flag'
MAINTENANCE_HTML='/www/wwwroot/p-acme/core-maintenance.html'
LEGACY_SOURCE='/root/.hermes/zhiming'
LEGACY_CONFIG='/root/.hermes/config.yaml'
LEGACY_JOBS='/root/.hermes/cron/jobs.json'
MANIFEST='__release_manifest__.json'
DBS={'stage':'zhiming_core_stage','live':'zhiming_core_live'}
LEGACY_JOB_COUNT=4


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


def stamp():return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')


def evidence(args):
    report=json.loads(Path(args.acceptance).read_text(encoding='utf-8'))
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
    command(['systemctl','restart','hermes.service']);command(['systemctl','is-active','--quiet','hermes.service'])
    command(['systemctl','stop','mingjingtai.service'])
    source=backup/'source';shutil.copytree(LEGACY_SOURCE,source,symlinks=True)
    snapshot_hashes(source)
    for original_db in Path(LEGACY_SOURCE).rglob('*.db'):
        destination_path=source/original_db.relative_to(LEGACY_SOURCE)
        with closing(sqlite3.connect(original_db.as_uri()+'?mode=ro',uri=True)) as original_connection,closing(sqlite3.connect(destination_path)) as destination:
            original_connection.backup(destination)
        for suffix in ('-wal','-shm'):
            candidate=Path(str(destination_path)+suffix)
            if candidate.exists():candidate.unlink()
    journal={'commit':args.commit,'backup':str(backup),'source_snapshot':str(source),'source_hashes':snapshot_hashes(source),'old_feishu_disabled':True,'old_reports_disabled':True,'legacy_jobs_disabled':selected,'frozen_at':stamp()}
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


def install(args):
    require_host();release=verify_release(args);evidence(args);verify_legacy_disabled(args)
    if not Path(MAINTENANCE).exists():raise ValueError('public writes must be frozen before final migration')
    env=load_environment(args,DBS['live']);source=Path(args.source_snapshot)
    bindings=Path(args.bindings)
    if bindings.is_symlink() or not bindings.is_file() or bindings.stat().st_mode&0o077:raise ValueError('trusted binding file must be protected mode 0600')
    if not source.is_dir() or not source.resolve().is_relative_to(Path(BACKUP_ROOT).resolve()):raise ValueError('final migration requires the protected frozen snapshot')
    frozen=json.loads((source.parent/'freeze.json').read_text(encoding='utf-8'))
    if frozen.get('commit')!=args.commit or frozen.get('source_snapshot')!=str(source) or frozen.get('source_hashes')!=snapshot_hashes(source):raise ValueError('frozen migration source or commit changed')
    migration_args=argparse.Namespace(**vars(args));migration_args.env_file=args.env_file+args.migration_env_file
    migration_env=load_environment(migration_args,DBS['live'])
    python=str(release/'venv/core/bin/python')
    migration_env['CORE_RUNTIME_DSN_CHECK']=env['ZHIMING_DATABASE_URL']
    check='import os,psycopg; from psycopg.conninfo import conninfo_to_dict; m=conninfo_to_dict(os.environ["ZHIMING_DATABASE_URL"]); r=conninfo_to_dict(os.environ["CORE_RUNTIME_DSN_CHECK"]); assert m.get("user") and m.get("user")!=r.get("user") and all(m.get(k)==r.get(k) for k in ("dbname","host","port")); c=psycopg.connect(os.environ["ZHIMING_DATABASE_URL"]); v=c.execute("SHOW server_version_num").fetchone()[0]; assert 150000<=int(v)<160000; role=c.execute("SELECT rolsuper,rolcreatedb,rolcreaterole FROM pg_roles WHERE rolname=%s",(r.get("user"),)).fetchone(); assert role is not None and not any(role); c.close()'
    command([python,'-c',check],env=migration_env)
    command([python,str(release/'migration_core.py'),'--source',str(source),'--owner','primary','--apply','--dsn-env','ZHIMING_DATABASE_URL','--schema','mingjing_core','--bindings',args.bindings],cwd=release,env=migration_env)
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
    unit_directory=Path('/etc/systemd/system');backup=source.parent/'units';backup.mkdir(mode=0o700,exist_ok=True)
    for name,text in units(args).items():
        target=unit_directory/name
        if target.exists() and not (backup/name).exists():write_private(backup/name,target.read_bytes())
        target.write_text(text,encoding='utf-8');target.chmod(0o644)
    command(['systemctl','daemon-reload']);command(['systemctl','enable','--now','mingjingtai.service'])
    return {'installed':True,'commit':args.commit,'maintenance':True,'database':DBS['live'],'effects_started':False}


def publish(args):
    require_host();release=verify_release(args);evidence(args);verify_legacy_disabled(args)
    env=load_environment(args,DBS['live'])
    if not Path(MAINTENANCE).exists():raise ValueError('release must remain behind the maintenance gate until publication')
    if render_nginx(Path(NGINX).read_text(encoding='utf-8'))!=Path(NGINX).read_text(encoding='utf-8'):raise ValueError('reviewed maintenance gate is not installed')
    command(['systemctl','is-active','--quiet','mingjingtai.service'])
    if command(['systemctl','show','mingjingtai.service','--property=WorkingDirectory','--value'],capture=True)!=str(release):raise ValueError('running web service does not point at the accepted release')
    request=urllib.request.Request('http://127.0.0.1:8787/api/health',headers={'X-Token':env.get('MINGJING_TOKEN','')})
    with urllib.request.urlopen(request,timeout=30) as response:health=json.load(response)
    if not health.get('ok') or health.get('context_version')!='core3.0' or health.get('database')!='postgresql' or health.get('runtime')!='langgraph':raise ValueError('new website health did not confirm Core v3')
    command(['systemctl','enable','--now','zhiming-core-feishu.service','zhiming-core-reports.timer'])
    command(['systemctl','is-active','--quiet','zhiming-core-feishu.service','zhiming-core-reports.timer'])
    command(['nginx','-t']);Path(MAINTENANCE).unlink(missing_ok=True)
    return {'published':True,'commit':args.commit,'live_health':True,'probe_messages_sent':0,'model_probe_calls':0}


def maintenance(args):
    require_host();release=verify_release(args);maintenance_gate()
    for name in ('zhiming-core-reports.timer','zhiming-core-reports.service','zhiming-core-feishu.service','mingjingtai.service'):
        command(['systemctl','stop',name])
    Path(NGINX).write_text(render_nginx(Path(NGINX).read_text(encoding='utf-8')),encoding='utf-8')
    command(['nginx','-t']);command(['systemctl','reload','nginx'])
    env=load_environment(args,DBS['live']);directory=Path(BACKUP_ROOT)/(stamp()+'-maintenance-'+args.commit[:12]);directory.mkdir(parents=True,mode=0o700)
    code='''import os,json,psycopg,subprocess
from psycopg.rows import dict_row
from psycopg.conninfo import conninfo_to_dict
with psycopg.connect(os.environ['ZHIMING_DATABASE_URL'],row_factory=dict_row) as c:
 rows=c.execute('SELECT owner,kind,entity_id,operation,metadata,revision,created_at FROM mingjing_core.core_revocations ORDER BY owner,revision,kind,entity_id').fetchall()
descriptor=os.open(os.environ['CORE_REVOCATION_EXPORT'],os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
with os.fdopen(descriptor,'w') as f:json.dump({'schema':'core3-revocations-v1','rows':rows},f,ensure_ascii=False,default=str)
fields=conninfo_to_dict(os.environ['ZHIMING_DATABASE_URL']); dump_env=dict(os.environ)
for key,name in [('host','PGHOST'),('port','PGPORT'),('user','PGUSER'),('password','PGPASSWORD'),('dbname','PGDATABASE')]:
 if key in fields:dump_env[name]=fields[key]
descriptor=os.open(os.environ['CORE_DATABASE_EXPORT'],os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
with os.fdopen(descriptor,'wb') as f:subprocess.run(['pg_dump','--format=custom','--no-owner','--no-acl'],env=dump_env,stdout=f,stderr=subprocess.PIPE,check=True)
'''
    env['CORE_REVOCATION_EXPORT']=str(directory/'revocations-latest.json')
    env['CORE_DATABASE_EXPORT']=str(directory/'core-live-latest.dump')
    command([str(release/'venv/core/bin/python'),'-c',code],cwd=release,env=env)
    write_private(directory/'maintenance.json',json.dumps({'commit':args.commit,'database':DBS['live'],'revocations':'revocations-latest.json','database_snapshot':'core-live-latest.dump','old_loop_reenabled':False,'at':stamp()}).encode())
    return {'maintenance':True,'writers_stopped':True,'latest_revocations_retained':str(directory),'old_explanation_loop_reenabled':False}


def parser():
    result=argparse.ArgumentParser(description=__doc__)
    result.add_argument('action',choices=('plan','bundle','prepare','freeze','install','publish','maintenance'))
    result.add_argument('--commit',required=True);result.add_argument('--release-dir',required=True)
    result.add_argument('--source',default='.');result.add_argument('--artifact');result.add_argument('--artifact-sha256')
    result.add_argument('--python',default='/usr/bin/python3.11')
    result.add_argument('--env-file',action='append',default=[])
    result.add_argument('--migration-env-file',action='append',default=[])
    result.add_argument('--acceptance');result.add_argument('--bindings');result.add_argument('--legacy-job-ids');result.add_argument('--source-snapshot')
    return result


def main(argv=None):
    args=parser().parse_args(argv);release_path(args.commit,args.release_dir)
    if args.action=='plan':
        output={'commit':args.commit,'release':args.release_dir,'databases':DBS,'nginx':NGINX,'maintenance_flag':MAINTENANCE,'sequence':['bundle','prepare','stage acceptance','freeze','install','publish'],'rollback':'maintenance preserves live PG and latest revocation ledger; never restarts old controller','units':list(units(args))}
    else:
        required={'bundle':['artifact'],'prepare':['artifact','artifact_sha256'],'freeze':['acceptance','legacy_job_ids'],'install':['acceptance','legacy_job_ids','bindings','source_snapshot'],'publish':['acceptance','legacy_job_ids'],'maintenance':[]}[args.action]
        if any(not getattr(args,name) for name in required):raise ValueError('missing action inputs: '+', '.join(required))
        if args.action in ('install','publish','maintenance') and not args.env_file:raise ValueError('protected original/provider/Core environment files required')
        if args.action=='install' and not args.migration_env_file:raise ValueError('a separate protected migration-owner environment file is required')
        output=globals()[args.action](args)
    print(json.dumps(output,ensure_ascii=False,indent=2));return 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except (ValueError,RuntimeError,OSError,KeyError) as exc:
        print(json.dumps({'ok':False,'error':str(exc)},ensure_ascii=False),file=sys.stderr);raise SystemExit(1)
