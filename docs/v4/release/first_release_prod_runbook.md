main67/R49警告裁定：必须先verify exit0，再逐行精确核对输出。只豁免既有 `/etc/systemd/system/tat_agent.service` 的旧 `/var/run` PIDFile，以及 `/usr/lib/systemd/system/iptables.service`、`ip6tables.service` 的过时syslog输出警告；原始豁免行写回执。其他任何输出/警告，尤其zhiming unit、drop-in或runtime相关，均停止；不改、重载或停用这三个既有unit。下面捕获与严格过滤代码只落实此名单，其他执行步骤不变。

# 首发生产执行单：e578e2d5d83dcf3b63c74af6e1b9f1a4c86453bd

main64/R45认证参数：本机发起的每次SSH/SCP必须显式使用 `-i C:/Users/Administrator/.ssh/gto_deploy_key`；若使用DEPLOY_KEY_FILE，固定为该路径。只供SSH工具按路径使用，不读取/复制/输出钥匙内容，不改服务器认证或网络。Windows向远端bash发送已审脚本时，须以UTF-8且LF原始字节写stdin，禁止text=True等文本管道转成CRLF；失败后仍按本单停止，不现场修补重试。

执行人：**主线**。授权依据为main v17/v34/v37/v41/v49/v50的D-首发，以及同候选、在有效窗口内的31号 `结论：Go`。先有同候选stage成功回执，再进入生产。37/31号实际放行前仅本机准备；现场执行逐步记回执，不以文档就绪代替验收。

质量依据：38号第九节/main v41，安全5/5、其他23/24；TA01仍失败，首发后排查。原机器分数不改。R11和包见stage单；PR24同SHA CI run 40217280728 已实际success（attempt1，最后实际job完成2026-10-25T18:50:07Z），Go必须引用该同SHA成功CI。

本文使用 PostgreSQL 15 原生命令及候选已有Python API，不存在 `first_release_prod --apply` 命令。不得把 `first_release_native_exchange` 的fr_stage guard改成live，也不传 `--local-drill` 冒充生产路径。下面原生SQL/备份/文件切换步骤是本次待审生产操作的明确实现，不依赖尚未开发的CLI。所有代码块先审后执行；任何非0立即停，维护门保留，不覆盖失败产物、不自动重试。

## D0：放行、固定路径、容量与运行时

31号必须明确：首行Go；完整候选SHA；北京时间开始/结束窗口；接受开门前回滚、开门后一次网页冒烟；stage回执成功的operation与路径。缺项、歧义或窗口未到均停止。37号不能代替31号。新operation固定 `1a131275da9dc8d6`，与stage的 `4e680f175ea28cc8` 区分，不复用旧目录。

本机读取31号，核文字与窗口后再进入服务器；不得以文件mtime作为窗口。远端第一次短连仅只读核以下路径/容量/目标，不根据历史状态直接停服务：

```bash
set -euo pipefail
set -C
umask 077
FR_SHA=e578e2d5d83dcf3b63c74af6e1b9f1a4c86453bd
FR_OLD=7dbc951eaffebd3d812169865eaefcde16a00ed9
FR_ID=1a131275da9dc8d6
FR_RELEASE=/root/zhiming-core-releases/$FR_SHA
FR_OLD_RELEASE=/root/zhiming-core-releases/$FR_OLD
FR_STAGE=/root/zhiming-core-fr-stage/releases/$FR_SHA
FR_OP=/root/zhiming-core-backups/first-release-$FR_ID
FR_ADMIN=/root/zhiming-core-secrets/fr-prod-admin.env
test "$(id -u)" = 0
test -d "$FR_OLD_RELEASE" && test -d "$FR_STAGE"
awk 'NR==2 {exit !($4>=8388608)}' < <(df -Pk /)
# v49: use programs beside the actual 5432 postmaster, never a distribution-specific path.
mapfile -t FR_PG_PIDS < <(ss -H -ltnp 'sport = :5432' | grep -oE 'pid=[0-9]+' | cut -d= -f2 | sort -u)
test "${#FR_PG_PIDS[@]}" = 1
FR_PG_EXE="$(readlink -f "/proc/${FR_PG_PIDS[0]}/exe")"
test "$(basename "$FR_PG_EXE")" = postgres -o "$(basename "$FR_PG_EXE")" = postmaster
FR_PG_BIN="$(dirname "$FR_PG_EXE")"
FR_DUMP="$FR_PG_BIN/pg_dump"
FR_RESTORE="$FR_PG_BIN/pg_restore"
FR_PSQL="$FR_PG_BIN/psql"
for program in "$FR_PG_EXE" "$FR_DUMP" "$FR_RESTORE" "$FR_PSQL"; do
 test -x "$program"
 "$program" --version | grep -Eq '\) 15\.'
done
command -v python3.11 sha256sum runuser
test "$(stat -fc %T /sys/fs/cgroup)" = cgroup2fs
grep -Fq 'if (-f /www/wwwroot/p-acme/core-maintenance.flag)' /www/server/panel/vhost/nginx/p.jerrymeng.asia.conf
for unit in mingjingtai.service zhiming-core-feishu.service zhiming-core-reports.service zhiming-core-reports.timer; do
  systemctl show "$unit" -p FragmentPath -p DropInPaths -p NeedDaemonReload -p ActiveState -p UnitFileState -p MainPID -p KillMode
done
```

继续：PG15、容量≥8GiB、旧7dbc951及0aa433a实际目录保留、stage成功且同SHA、私有管理员文件存在。FR_ADMIN只接受 `FIRST_RELEASE_EXCHANGE_ADMIN_DSN`，127.0.0.1或::1、5432、postgres控制库、实际superuser；后面脚本再次核验。缺文件时仅按下方R28就地准备；认证不允许即停并【提醒用户】，不改pg_hba。上述命令不打印私有内容。8GiB只是最低门，实际dump×3＋双环境＋旧包共存余量不足也停。

### R28：只在服务器就地准备回环管理员（stage / 生产共用）

仅在对应37/31号Go及授权范围内运行。先读权限、已有文件和实际身份；两文件都不存在才经 postgres 系统用户和 `/tmp` socket 创建 `zhiming_fr_admin`。32字节随机口令仅在服务器内存/两个root私有文件中，禁止shell tracing、打印、日志或回传；已有角色但凭据文件都缺失则停，不重置口令。只供127.0.0.1本机管理，不配置远程访问，不修改pg_hba。TCP口令认证不允许时停并【提醒用户】，保留现场、不重试建角色。

```bash
set +x
python3.11 -I - "$FR_PSQL" <<'PY'
import os,pathlib,secrets,shlex,shutil,stat,subprocess,urllib.parse
assert os.geteuid()==0
psql=__import__('sys').argv[1]
parent=pathlib.Path('/root/zhiming-core-secrets')
assert not parent.is_symlink()
if not parent.exists():parent.mkdir(mode=0o700)
assert parent.is_dir() and parent.stat().st_uid==0 and stat.S_IMODE(parent.stat().st_mode)==0o700
paths=[parent/'fr-stage-admin.env',parent/'fr-prod-admin.env']
key='FIRST_RELEASE_EXCHANGE_ADMIN_DSN'
def private(path):
 fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
 with os.fdopen(fd,'rb') as stream:
  s=os.fstat(stream.fileno());assert stat.S_ISREG(s.st_mode) and s.st_uid==0 and stat.S_IMODE(s.st_mode)==0o600
  data=stream.read(8193);assert len(data)<=8192
 return data
existing=[private(p) for p in paths if p.exists() or p.is_symlink()]
base={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','PGCONNECT_TIMEOUT':'5'}
def call(argv,query,env):
 r=subprocess.run(argv,input=query,text=True,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
 assert r.returncode==0,'R28 authentication/SQL refused; stop, do not alter pg_hba; private diagnostics not printed'
 return r.stdout.strip()
runuser=shutil.which('runuser');assert runuser and pathlib.Path(runuser).is_absolute()
socket=[runuser,'-u','postgres','--',psql,'-X','-w','-h','/tmp','-p','5432','-d','postgres','-v','ON_ERROR_STOP=1','-Atq']
if existing:
 assert all(data==existing[0] for data in existing),'R28 files disagree; stop'
 data=existing[0];lines=[x for x in data.decode().splitlines() if x.strip()]
 assert len(lines)==1
 name,sep,value=lines[0].partition('=');assert sep and name==key
 values=shlex.split(value);assert len(values)==1
 dsn=values[0];u=urllib.parse.urlsplit(dsn)
 assert u.scheme in ('postgres','postgresql') and u.hostname=='127.0.0.1' and u.port==5432 and u.path=='/postgres' and not u.query and not u.fragment
 user=urllib.parse.unquote(u.username or '');password=urllib.parse.unquote(u.password or '')
 assert user and password
else:
 assert call(socket,"SELECT count(*) FROM pg_roles WHERE rolname='zhiming_fr_admin';",base)=='0','R28 role exists without files; stop, no password rotation'
 password=secrets.token_hex(32);user='zhiming_fr_admin'
 # psql reads separate stdin commands: disable statement logging before sending the credential statement.
 query="SET log_statement='none';\nSET log_min_duration_statement=-1;\nSET log_min_error_statement='panic';\nSET password_encryption='scram-sha-256';\nCREATE ROLE zhiming_fr_admin SUPERUSER LOGIN PASSWORD '"+password+"';\n"
 call(socket,query,base)
 dsn='postgresql://'+user+':'+password+'@127.0.0.1:5432/postgres'
 data=(key+'='+dsn+'\n').encode()
env={**base,'PGPASSWORD':password}
check=call([psql,'-X','-w','-h','127.0.0.1','-p','5432','-U',user,'-d','postgres','-v','ON_ERROR_STOP=1','-Atq'],"SELECT current_user=session_user AND (SELECT rolsuper FROM pg_roles WHERE rolname=session_user) AND current_database()='postgres' AND inet_server_addr()='127.0.0.1'::inet AND inet_server_port()=5432 AND current_setting('server_version_num')::int BETWEEN 150000 AND 159999;",env)
assert check=='t','R28 actual superuser/loopback/PG15 check failed'
for path in paths:
 if path.exists() or path.is_symlink():assert private(path)==data
 else:
  fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
  with os.fdopen(fd,'wb') as stream:stream.write(data);stream.flush();os.fsync(stream.fileno())
 assert private(path)==data
env.clear();password=dsn=data=None
print('R28: local administrator authenticated; two private files verified; credential output=0')
PY
test -f "$FR_ADMIN" && ! test -L "$FR_ADMIN"
test "$(stat -c '%a %u' "$FR_ADMIN")" = '600 0'
test "$(stat -c '%a %u' "$(dirname "$FR_ADMIN")")" = '700 0'
```

上述文件使用单字段URI DSN；若已有文件不是该受支持格式，停止审查而不覆盖。任意错误输出只记录步骤失败，不复制SQL/口令/原stderr；不现场安装软件或修改认证。

包必须与stage同一公开包，SHA256 `e1c245ebc220c136a1902ad878d7fe42014f99c91a72da87c845dde9b19bc795`；不得复制整个stage/private或把stage运行口令带到生产。已有生产release存在即停，不覆盖。用原始archive逐成员校验、解包到新目录；这里使用不带stage路径限制的通用文件校验函数，不调用限定stage的unpack入口：

```bash
test ! -e "$FR_RELEASE" && test ! -e "$FR_OP"
test ! -e /root/zhiming-core-secrets/first-release-service-config.json
test ! -e /root/zhiming-core-secrets/first-release-common.env
test ! -e /root/.hermes/skills/zhiming/first-release-service-assets-manifest.json
mkdir -m 700 "$FR_OP"
python3.11 -I - "$FR_OP/pg-programs.json" "$FR_PG_EXE" "$FR_DUMP" "$FR_RESTORE" <<'PY'
import hashlib,json,pathlib,sys
p=pathlib.Path(sys.argv[1]);programs={k:{'path':v,'sha256':hashlib.sha256(pathlib.Path(v).read_bytes()).hexdigest()} for k,v in zip(('postmaster','pg_dump','pg_restore'),sys.argv[2:])}
with p.open('x') as stream:json.dump(programs,stream)
p.chmod(0o600)
PY
FR_STAGE_PY=/root/zhiming-core-fr-stage/venvs/$FR_SHA/core/bin/python
"$FR_STAGE_PY" -I - "$FR_STAGE" "$FR_RELEASE" <<'PY'
import hashlib,json,os,pathlib,sys,tarfile
sys.path.insert(0,sys.argv[1])
from tools.first_release_stage_unpack import safe_name,extract_member,MANIFEST
a=pathlib.Path('/root/zhiming-core-fr-stage/uploads/release.tar.gz')
assert hashlib.sha256(a.read_bytes()).hexdigest()=='e1c245ebc220c136a1902ad878d7fe42014f99c91a72da87c845dde9b19bc795'
dest=pathlib.Path(sys.argv[2]);assert not dest.exists()
with tarfile.open(a,'r:gz') as t:
    members=t.getmembers();names=[safe_name(x.name) for x in members]
    m=json.load(t.extractfile(MANIFEST))
    assert m['commit']=='e578e2d5d83dcf3b63c74af6e1b9f1a4c86453bd'
    assert m['schema']=='core3-release-v1' and len(names)==len(set(names))
    assert set(names)=={MANIFEST,*m['files']} and all(x.isfile() for x in members)
    dest.mkdir(mode=0o700)
    for x in members:extract_member(t,x,dest/x.name,m['files'].get(x.name))
print('canonical candidate extracted; private data copied=0')
PY
python3.11 -m venv "$FR_RELEASE/venv/core"
python3.11 -m venv "$FR_RELEASE/venv/charts"
"$FR_RELEASE/venv/core/bin/python" -m pip install --require-hashes -r "$FR_RELEASE/requirements-core.lock"
"$FR_RELEASE/venv/charts/bin/python" -m pip install --require-hashes -r "$FR_RELEASE/requirements-charts.lock"
"$FR_RELEASE/venv/core/bin/python" -m pip check
"$FR_RELEASE/venv/charts/bin/python" -m pip check
FR_PY=$FR_RELEASE/venv/core/bin/python
FR_TOKENIZER=/root/zhiming-core-fr-stage/tokenizer/$FR_SHA
cd "$FR_RELEASE"
"$FR_PY" -m tools.install_k3_tokenizer --destination "$FR_TOKENIZER" --verify-only
```

安装/备份/恢复均按stage单的 `start_step/check_step` 后台单步执行，长命令不占长SSH会话；日志、pid、exit只在FR_OP独占写入，结束码0才继续。此处不要重跑评测、重新接入或发模型探测。

## D1：保存旧文件、维护与全部writer停写

在FR_OP保留三service、report timer、所有实际drop-in、Hermes wrapper及manifest、两个原env的原字节/模式/属主；归档不打印正文。实际drop-in存在且不在下面归档范围时先补入清单、复核，再继续，不能忽略。Hermes配置加载次序保持 `.hermes/.env`→`live-runtime.env`，后者不直接覆盖。

```bash
test -f /root/.hermes/skills/zhiming/core_consultation.py
tar --acls --xattrs --numeric-owner -cpf "$FR_OP/runtime-before.tar" \
 /etc/systemd/system/mingjingtai.service \
 /etc/systemd/system/zhiming-core-feishu.service \
 /etc/systemd/system/zhiming-core-reports.service \
 /etc/systemd/system/zhiming-core-reports.timer \
 /root/.hermes/skills/zhiming \
 /root/.hermes/.env /root/zhiming-core-secrets/live-runtime.env \
 /www/server/panel/vhost/nginx/p.jerrymeng.asia.conf
chmod 600 "$FR_OP/runtime-before.tar"
sha256sum "$FR_OP/runtime-before.tar" > "$FR_OP/runtime-before.sha256"
"$FR_PY" -I - "$FR_OP" "$FR_OLD_RELEASE" <<'PY'
import json,pathlib,subprocess,sys
out=pathlib.Path(sys.argv[1]);old=sys.argv[2];units={}
for name in ('mingjingtai.service','zhiming-core-feishu.service','zhiming-core-reports.service','zhiming-core-reports.timer'):
    text=subprocess.check_output(['systemctl','show',name,'-p','ActiveState','-p','UnitFileState','-p','ExecStart','-p','WorkingDirectory'],text=True)
    values=dict(line.split('=',1) for line in text.splitlines() if '=' in line)
    if not name.endswith('.timer'):assert old in values.get('ExecStart','') and values.get('WorkingDirectory')==old
    units[name]=values
with (out/'units-before.json').open('x') as f:json.dump(units,f)
wrapper=pathlib.Path('/root/.hermes/skills/zhiming/core_consultation.py').read_bytes()
assert b'7dbc951eaffebd3d812169865eaefcde16a00ed9' in wrapper
print('previous fixed entries and timer state verified')
PY
for unit in mingjingtai.service zhiming-core-feishu.service zhiming-core-reports.service zhiming-core-reports.timer; do
 systemctl show "$unit" -p ActiveState -p UnitFileState -p FragmentPath -p DropInPaths >> "$FR_OP/units-before.txt"
done
test -f /www/server/panel/vhost/nginx/p.jerrymeng.asia.conf
grep -Fq 'if (-f /www/wwwroot/p-acme/core-maintenance.flag)' /www/server/panel/vhost/nginx/p.jerrymeng.asia.conf
touch /www/wwwroot/p-acme/core-maintenance.flag
chmod 644 /www/wwwroot/p-acme/core-maintenance.flag
nginx -t
systemctl stop zhiming-core-reports.timer
systemctl stop zhiming-core-feishu.service zhiming-core-reports.service mingjingtai.service
for unit in mingjingtai.service zhiming-core-feishu.service zhiming-core-reports.service zhiming-core-reports.timer; do
 if [[ "$unit" != *.timer ]]; then test "$(systemctl show -p MainPID --value "$unit")" = 0; fi
 test "$(systemctl show -p ActiveState --value "$unit")" = inactive
done
```

继续：公网维护响应503、三service/timer停、没有遗留子进程。Hermes主体不重启，旧Core wrapper必须实际具备“维护门内二次检查＋持共享锁直到exec退出”的已审实现；不匹配就停，不能用新锁推断旧wrapper已经受控。下一步在同一控制进程持 `/root/zhiming-core-secrets/core-skill-writer.lock` 排他锁，关闭live新连接并核0连接；不杀PG会话、不伪造清空队列。core_runs queued/running、有效lease、到期pending/sending outbox或未知客户端非0均停，保留现场。

## D2–D4：原生一致备份、新库验证与迁移回填

在FR_OP创建下列 `context.py`（0600），代码为本执行单的一部分，审核时一起核hash。不是产品代码补丁；不修改候选源码。只允许已有live owner/writer，仅R28允许就地创建回环管理角色，不新建业务owner/writer。原中央若位于即将对调的live库，立即停：先由31号给出保留该中央OID/位置的独立方案，本单不自动搬运/重绑中央。

```bash
cat > "$FR_OP/context.py" <<'PY'
# context.py
import hashlib,json,os,sys
from pathlib import Path
import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict,make_conninfo
from psycopg.rows import dict_row
SHA='e578e2d5d83dcf3b63c74af6e1b9f1a4c86453bd'
ROOT=Path('/root/zhiming-core-releases')/SHA
OP=Path('/root/zhiming-core-backups/first-release-1a131275da9dc8d6')
sys.path.insert(0,str(ROOT))
from tools.first_release_hermes_entry import _private_read,_parse_environment
from tools.first_release_database_metadata import capture,validate,apply_metadata,semantic
from tools.first_release_native_exchange import write_private
from tools.first_release_local_restore import process_environment
ADMIN=_parse_environment(_private_read(Path('/root/zhiming-core-secrets/fr-prod-admin.env')))
assert set(ADMIN)=={'FIRST_RELEASE_EXCHANGE_ADMIN_DSN'}
DSN=ADMIN['FIRST_RELEASE_EXCHANGE_ADMIN_DSN'];F=conninfo_to_dict(DSN)
def private_env(path):return _parse_environment(_private_read(Path(path)))
assert F['host'] in ('127.0.0.1','::1') and F['port']=='5432' and F['dbname']=='postgres'
assert not any(k.startswith('PG') and v for k,v in os.environ.items())
assert not set(F)-{'host','port','dbname','user','password','connect_timeout'}
LIVE='zhiming_core_live';NEW='zhiming_core_first_1a131275da9dc8d6';KEPT='zhiming_core_before_1a131275da9dc8d6'
def admin():
 c=psycopg.connect(DSN,autocommit=True,row_factory=dict_row)
 r=c.execute("SELECT current_user,session_user,current_database(),inet_server_port() AS port,current_setting('server_version_num')::int AS version,(SELECT rolsuper FROM pg_roles WHERE rolname=session_user) AS su").fetchone()
 assert r['current_database']=='postgres' and r['port']==5432 and 150000<=r['version']<160000 and r['su']
 assert r['current_user']==r['session_user']==F['user']
 assert c.execute("SELECT pg_try_advisory_lock(hashtextextended('v41-production-live',0)) AS held").fetchone()['held']
 return c
def read(name):return json.loads((OP/name).read_text())
def save(name,value):write_private(OP/name,value)
def h(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def pg_program(name):
 import re,subprocess
 record=read('pg-programs.json');path=Path(record[name]['path'])
 listeners=subprocess.check_output(['ss','-H','-ltnp','sport = :5432'],text=True)
 pids=set(re.findall(r'pid=(\d+)',listeners));assert len(pids)==1
 actual=Path('/proc')/next(iter(pids))/'exe'
 assert actual.resolve()==Path(record['postmaster']['path'])
 assert h(actual)==record['postmaster']['sha256']
 assert path.parent==actual.resolve().parent and path.name==name and h(path)==record[name]['sha256']
 assert re.search(r'\) 15\.',subprocess.check_output([str(path),'--version'],text=True))
 return str(path)

def zero(c,name):
 r=c.execute('SELECT datallowconn,(SELECT count(*) FROM pg_stat_activity WHERE datid=d.oid) AS n FROM pg_database d WHERE datname=%s',(name,)).fetchone()
 assert r and not r['datallowconn'] and r['n']==0
def allow(c,name,value):c.execute(sql.SQL('ALTER DATABASE {} ALLOW_CONNECTIONS {}').format(sql.Identifier(name),sql.SQL('true' if value else 'false')))
def repo(name,readonly=False):
 from mingjing_core.repositories.postgres import PostgresRepository
 return PostgresRepository(make_conninfo(DSN,dbname=name,options='-c role=zhiming_core_live_owner -c search_path=public,pg_catalog'+(' -c default_transaction_read_only=on' if readonly else '')),initialize=False,max_size=1)
def check_queue(r):
 with r.connection() as c:
  c.execute('SET TRANSACTION READ ONLY')
  assert c.execute("SELECT count(*) AS n FROM mingjing_core.core_runs WHERE status IN ('queued','running') OR lease_until>now()").fetchone()['n']==0
  assert c.execute("SELECT count(*) AS n FROM mingjing_core.delivery_outbox WHERE status='sending' OR lease_until>now() OR (status='pending' AND due<=now())").fetchone()['n']==0
PY
chmod 600 "$FR_OP/context.py"
```

D2在同一进程中排空Hermes、核队列、导出隐私旁账与数据库元数据并完成dump。不能用旧deploy_core的maintenance备份（其 `--no-owner/--no-acl` 不满足本单）。

```bash
"$FR_PY" -I - "$FR_OP" <<'PY'
import sys,subprocess
sys.path.insert(0,sys.argv[1]);from context import *
from tools.deploy_core import skill_writer_lock,export_withdrawals
with skill_writer_lock(exclusive=True),admin() as c:
 assert Path('/www/wwwroot/p-acme/core-maintenance.flag').is_file()
 env={}
 for path in ('/root/.hermes/.env','/root/zhiming-core-secrets/live-runtime.env'):
  env.update(private_env(path))
 central=conninfo_to_dict(env.get('MEMBER_CENTRAL_DSN',''))
 assert central and central['dbname']!=LIVE
 assert all(env.get(k) for k in ('MEMBER_CENTRAL_SCHEMA','MEMBER_ACCOUNT_ID','MEMBER_LEDGER_IDENTITY'))
 save('central-before.json',{'fields':{k:env[k] for k in ('MEMBER_CENTRAL_DSN','MEMBER_CENTRAL_SCHEMA','MEMBER_ACCOUNT_ID','MEMBER_LEDGER_IDENTITY')}})
 with psycopg.connect(make_conninfo(DSN,dbname=LIVE),row_factory=dict_row) as db:
  assert db.execute('SELECT count(*) AS n FROM pg_stat_activity WHERE datid=(SELECT oid FROM pg_database WHERE datname=current_database()) AND pid<>pg_backend_pid()').fetchone()['n']==0
 r=repo(LIVE,True)
 try:
  check_queue(r);privacy=export_withdrawals(r)
  with r.connection() as db:
   history=[dict(x) for x in db.execute('SELECT version,checksum FROM mingjing_core.schema_migrations ORDER BY version')]
 finally:r.close()
 snap=capture(c,LIVE);validate(c,snap)
 assert snap['owner']=='zhiming_core_live_owner'
 save('database-before.json',snap);save('privacy-before.json',privacy);save('schema-before.json',{'rows':history})
 allow(c,LIVE,False);zero(c,LIVE)
 assert not c.execute('SELECT 1 FROM pg_database WHERE datname=ANY(%s)',([NEW,KEPT],)).fetchone()
 allow(c,LIVE,True)
 try:
  with (OP/'live-before.dump').open('xb') as out:
   cmd=[pg_program('pg_dump'),'--host='+F['host'],'--port=5432','--username='+F['user'],'--dbname='+LIVE,'--no-password','--format=custom']
   result=subprocess.run(cmd,env=process_environment(DSN),stdout=out,stderr=subprocess.PIPE)
   assert result.returncode==0,'dump failed; keep private diagnostic'
 finally:allow(c,LIVE,False)
 zero(c,LIVE)
 save('backup-receipt.json',{'sha256':h(OP/'live-before.dump'),'source_oid':snap['oid'],'closed':True,'pg_dump_sha256':h(pg_program('pg_dump')),'pg_restore_sha256':h(pg_program('pg_restore'))})
print('D2: backup and privacy captured; live closed')
PY
```

D2结束继续条件：live仍closed/0连接，dump非空且hash与receipt相符，原主机SID/owner/OID/ACL/库及角色SET已捕获；不得重试覆盖。新增候选恢复库仅此operation使用。D3先恢复原schema，核完整dump、owner、ACL与隐私快照，然后D4只在新库前向迁移，不原地修改原live：

```bash
"$FR_PY" -I - "$FR_OP" <<'PY'
import sys,subprocess
sys.path.insert(0,sys.argv[1]);from context import *
from tools.deploy_core import export_withdrawals
with admin() as c:
 zero(c,LIVE);snap=read('database-before.json');validate(c,snap)
 assert capture(c,LIVE)==snap and h(OP/'live-before.dump')==read('backup-receipt.json')['sha256']
 assert not c.execute('SELECT 1 FROM pg_database WHERE datname=ANY(%s)',([NEW,KEPT],)).fetchone()
 c.execute(sql.SQL('CREATE DATABASE {} OWNER {} TEMPLATE template0 ENCODING {} LC_COLLATE {} LC_CTYPE {}').format(sql.Identifier(NEW),sql.Identifier(snap['owner']),sql.Literal(snap['encoding']),sql.Literal(snap['collate']),sql.Literal(snap['ctype'])))
 result=subprocess.run([pg_program('pg_restore'),'--host='+F['host'],'--port=5432','--username='+F['user'],'--dbname='+NEW,'--no-password','--exit-on-error','--single-transaction',str(OP/'live-before.dump')],env=process_environment(DSN),capture_output=True)
 assert result.returncode==0,'restore failed: preserve new database'
 assert h(pg_program('pg_restore'))==read('backup-receipt.json')['pg_restore_sha256']
 with c.transaction():apply_metadata(c,NEW,snap)
 assert semantic(capture(c,NEW))==semantic(snap)
 r=repo(NEW,True)
 try:
  check_queue(r);assert export_withdrawals(r)==read('privacy-before.json')
  with r.connection() as db:assert [dict(x) for x in db.execute('SELECT version,checksum FROM mingjing_core.schema_migrations ORDER BY version')]==read('schema-before.json')['rows']
 finally:r.close()
 allow(c,NEW,False);zero(c,NEW)
 save('restore-verified.json',{'oid':capture(c,NEW)['oid'],'schema_before_verified':True,'privacy_equal':True})
print('D3: new database restored with owner/ACL, original schema and privacy verified')
PY
```

D4必须核候选恰好1–8迁移。由原owner创建新表，primary回填dry-run→apply→repeat；不手填checksum，不启自动schema升级服务，不给runtime DDL权限。

```bash
"$FR_PY" -I - "$FR_OP" <<'PY'
import sys
sys.path.insert(0,sys.argv[1]);from context import *
from mingjing_core.repositories.foundation import migration_manifest,validate_history
from mingjing_core.application.memory import MemoryService
from mingjing_core.memory.backfill import backfill
from mingjing_core.runtime import LangGraphRuntime
from mingjing_core.repositories.permissions import grant_runtime_tables
from tools.deploy_core import export_withdrawals,apply_withdrawals
with admin() as c:
 zero(c,LIVE);zero(c,NEW);allow(c,NEW,True)
 r=repo(NEW)
 try:
  expected=migration_manifest();assert sorted(expected)==list(range(1,9))
  before={x['version']:x['checksum'] for x in read('schema-before.json')['rows']}
  validate_history(before,expected,complete=False)
  r.initialize();assert r.verify_schema()['version']==8;LangGraphRuntime(r)
  memory=MemoryService(r)
  dry=backfill(memory,'primary',apply=False);first=backfill(memory,'primary',apply=True);second=backfill(memory,'primary',apply=True)
  assert all(second[k]==0 for k in ('message_metadata','search_tokens','assistant_created'))
  apply_withdrawals(r,read('privacy-before.json'))
  privacy=export_withdrawals(r);assert privacy==read('privacy-before.json')
  apply_withdrawals(r,read('privacy-before.json'));assert export_withdrawals(r)==privacy
  with r.connection() as db:
   grant_runtime_tables(db,'zhiming_core_live_writer')
   role=sql.Identifier('zhiming_core_live_writer')
   db.execute(sql.SQL('GRANT USAGE ON SCHEMA public TO {}').format(role))
   for table in ('checkpoints','checkpoint_blobs','checkpoint_writes'):
    db.execute(sql.SQL('GRANT SELECT,INSERT,UPDATE,DELETE ON public.{} TO {}').format(sql.Identifier(table),role))
   db.execute(sql.SQL('GRANT SELECT ON public.checkpoint_migrations TO {}').format(role))
   db.execute(sql.SQL('REVOKE INSERT,UPDATE,DELETE,TRUNCATE,TRIGGER ON public.checkpoint_migrations FROM {}').format(role))
   db.execute(sql.SQL('REVOKE INSERT,UPDATE,DELETE,TRUNCATE,TRIGGER ON mingjing_core.schema_migrations FROM {}').format(role))
  save('migration-receipt.json',{'version':8,'repeat':{k:second[k] for k in ('message_metadata','search_tokens','assistant_created')},'privacy_equal':True,'source_oid':read('database-before.json')['oid'],'target_oid':read('restore-verified.json')['oid']})
 finally:r.close();allow(c,NEW,False)
 zero(c,LIVE);zero(c,NEW)
print('D4: schema8, primary repeat-zero and privacy verified; both databases closed')
PY
```

停止：真实owner/ACL/历史checksum异常、存在未知writer、隐私旁账不等、repeat非0、中央位置不受支持等，均保持维护和两个库，不修改工具guard或PG认证来继续。该路径保留原live基线，缩小原地升级风险；不是把恢复成功直接当作允许开门。

## D5：对调与四入口固定到e578e2d

同一个控制事务内检查原SID、两个OID、原库元数据、0连接及closed，再对调。保留旧live为KEPT，不删除。新live的owner/ACL/库与角色SET从原快照恢复。

```bash
"$FR_PY" -I - "$FR_OP" <<'PY'
import sys
sys.path.insert(0,sys.argv[1]);from context import *
with admin() as c:
 snap=read('database-before.json');zero(c,LIVE);zero(c,NEW)
 assert capture(c,LIVE)==snap and capture(c,NEW)['oid']==read('restore-verified.json')['oid']
 assert read('migration-receipt.json')['privacy_equal']
 with c.transaction():
  c.execute("SET LOCAL lock_timeout='2s'")
  assert not c.execute('SELECT 1 FROM pg_database WHERE datname=%s',(KEPT,)).fetchone()
  c.execute(sql.SQL('ALTER DATABASE {} RENAME TO {}').format(sql.Identifier(LIVE),sql.Identifier(KEPT)))
  c.execute(sql.SQL('ALTER DATABASE {} RENAME TO {}').format(sql.Identifier(NEW),sql.Identifier(LIVE)))
  apply_metadata(c,LIVE,snap)
 zero(c,LIVE);zero(c,KEPT)
 save('exchange-receipt.json',{'old_oid':snap['oid'],'new_oid':capture(c,LIVE)['oid'],'kept_database':KEPT,'admission_opened':False})
print('D5 database exchanged; both versions retained and closed')
PY
```

R71：D5回执写成后、渲染入口之前加固writer。e578e2d的 `checked_writer` 拒绝 rolinherit 和库级TEMP，线上原角色不满足。此时三service已停、维护门在、原库已保存为KEPT；D5之前任何失败，线上角色都没动。

```bash
"$FR_PY" -I - "$FR_OP" <<'PY'
import sys
sys.path.insert(0,sys.argv[1]);from context import *
WRITER='zhiming_core_live_writer'
def state(c):
 role=c.execute('SELECT rolinherit FROM pg_roles WHERE rolname=%s',(WRITER,)).fetchone()
 temp=c.execute("SELECT has_database_privilege(%s,%s,'TEMPORARY') AS temp",(WRITER,LIVE)).fetchone()
 return role['rolinherit'],temp['temp']
assert read('exchange-receipt.json')['admission_opened'] is False
with admin() as c:
 live=capture(c,LIVE)
 assert live['oid']==read('exchange-receipt.json')['new_oid']
 inherit,temp=state(c)
 save('role-before.json',{'writer':WRITER,'rolinherit':inherit,'writer_temp':temp,'database_oid':live['oid'],'acl':live['acl']})
 assert Path('/www/wwwroot/p-acme/core-maintenance.flag').is_file() and not (OP/'opened.json').exists()
 with c.transaction():
  c.execute(sql.SQL('ALTER ROLE {} NOINHERIT').format(sql.Identifier(WRITER)))
  c.execute(sql.SQL('REVOKE TEMPORARY ON DATABASE {} FROM PUBLIC').format(sql.Identifier(LIVE)))
 assert state(c)==(False,False)
 save('writer-hardened.json',{'writer':WRITER,'rolinherit':False,'writer_temp':False,'database_oid':live['oid']})
print('writer hardened: NOINHERIT and no database TEMP; prior state saved')
PY
```

失败即走R1，r02b按 `role-before.json` 恢复。`role-before.json` 已存在时本块拒绝重跑。

用候选实际 `first_release_service_assets` 渲染四入口。SID和新live OID从当前PG采集，writer OID仍用原角色。配置从原两env按原次序加载，新增common.env固定Agent=true、k3.1-pro/high配置、双解释器及公开K3；不更改旧env，以便原样回退。生成后先审核manifest和unit，后安装，manifest最后写。

```bash
"$FR_PY" -I - "$FR_OP" <<'PY'
import sys
sys.path.insert(0,sys.argv[1]);from context import *
from tools.first_release_service_assets import Assets,render
with admin() as c:
 zero(c,LIVE)
 snap=capture(c,LIVE)
 writer=c.execute("SELECT oid FROM pg_roles WHERE rolname='zhiming_core_live_writer'").fetchone()['oid']
a=Assets(SHA,str(OP),snap['system_identifier'],LIVE,snap['oid'],'zhiming_core_live_writer',writer,'primary',('/root/.hermes/.env','/root/zhiming-core-secrets/live-runtime.env'),'/root/zhiming-core-secrets/first-release-service-config.json','/root/zhiming-core-secrets/first-release-common.env',str(Path('/root/zhiming-core-fr-stage/tokenizer')/SHA))
out=OP/'assets';out.mkdir(mode=0o700)
for name,data in render(a).items():
 with (out/name).open('xb') as f:f.write(data)
 (out/name).chmod(0o600)
fences=OP/'private/first-release-writers';fences.mkdir(mode=0o700,parents=True)
lock=fences/(snap['system_identifier']+'-'+str(snap['oid'])+'.lock');lock.touch(exist_ok=False,mode=0o600)
save('service-identity.json',{'sid':snap['system_identifier'],'oid':snap['oid'],'writer_oid':writer,'fence':str(lock),'maintenance':str(lock.with_suffix('.maintenance.json'))})
Path(str(lock.with_suffix('.maintenance.json'))).write_text('{"closed":true}\n');lock.with_suffix('.maintenance.json').chmod(0o600)
print('four-entry assets generated, not started')
PY
systemd-analyze verify "$FR_OP/assets/mingjingtai.service" "$FR_OP/assets/zhiming-core-feishu.service" "$FR_OP/assets/zhiming-core-reports.service" > "$FR_OP/verify-prod.log" 2>&1
# R49: set -e requires verify exit0 before this exact whitelist check.
python3.11 -I - "$FR_OP/verify-prod.log" <<'PY'
import pathlib,re,sys
patterns=(
 r'/etc/systemd/system/tat_agent\.service:[0-9]+: PIDFile= references a path below legacy directory /var/run/, updating /var/run/tat_agent\.pid → /run/tat_agent\.pid; please update the unit file accordingly\.',
 r'/usr/lib/systemd/system/(?:ip6tables|iptables)\.service:[0-9]+: Standard output type syslog is obsolete, automatically updating to journal\. Please update your unit file, and consider removing the setting altogether\.',
)
for line in pathlib.Path(sys.argv[1]).read_text(encoding='utf-8').splitlines():
 if not line.strip():continue
 assert any(re.fullmatch(pattern,line) for pattern in patterns),'R49 non-exempt verify output; stop'
 print(line)
PY
install -m 600 "$FR_OP/assets/service-config.json" /root/zhiming-core-secrets/first-release-service-config.json
install -m 600 "$FR_OP/assets/service-common.env" /root/zhiming-core-secrets/first-release-common.env
install -m 644 "$FR_OP/assets/mingjingtai.service" /etc/systemd/system/mingjingtai.service
install -m 644 "$FR_OP/assets/zhiming-core-feishu.service" /etc/systemd/system/zhiming-core-feishu.service
install -m 644 "$FR_OP/assets/zhiming-core-reports.service" /etc/systemd/system/zhiming-core-reports.service
install -m 600 "$FR_OP/assets/core_consultation.py" /root/.hermes/skills/zhiming/core_consultation.py
install -m 600 "$FR_OP/assets/manifest.json" /root/.hermes/skills/zhiming/first-release-service-assets-manifest.json
systemctl daemon-reload
```

manifest是新增四入口审核manifest，原Core skill manifest/退役stub保留，不能谎称旧deploy verifier支持新manifest。旧Core skill描述、别名或其他入口仍指向旧wrapper时停止；不得整体重启Hermes。各实际drop-in必须与审核清单一致且不能覆盖ExecStart/WorkingDirectory为旧包。配置文件已存在或与保存清单不符时先保存原件再安装，禁止覆盖未知私有文件。

## D6：门内核验（0模型、0投递）

四入口暂不启动。核验有效unit与配置，模型注册表六个角色均只有精确k3.1-pro、effort/reasoning_effort high；provider URL官方coding端点。原四MEMBER字段必须逐字相等；不得把本机评测账本当作生产中央或自动provision。

```bash
for unit in mingjingtai.service zhiming-core-feishu.service zhiming-core-reports.service; do
 systemctl show "$unit" -p FragmentPath -p DropInPaths -p ExecStart -p WorkingDirectory -p NeedDaemonReload
done
"$FR_PY" -I - "$FR_OP" <<'PY'
import sys
sys.path.insert(0,sys.argv[1]);from context import *
from tools.first_release_service_assets import Assets
from tools.first_release_hermes_entry import load_environment
import yaml
a=Assets.parse(json.loads(Path('/root/zhiming-core-secrets/first-release-service-config.json').read_text()))
env=load_environment(a)
assert all(env[k]==v for k,v in read('central-before.json')['fields'].items())
assert env['MINGJING_AGENT_ENABLED']=='true'
model=yaml.safe_load((ROOT/'config/models.first-release.yaml').read_text())
for role in ('primary','critic','evaluation','background','fast','vision'):
 ids=model['roles'][role];assert len(ids)==1
 v=model['models'][ids[0]]
 assert v['model']=='k3.1-pro' and v['settings']['effort']==v['settings']['reasoning_effort']=='high'
 assert model['providers'][v['provider']]['base_url']=='https://api.kimi.com/coding/v1'
assert Path(env['CHART_PYTHON']).is_file()
with admin() as c:
 zero(c,LIVE);allow(c,LIVE,True)
 r=repo(LIVE,True)
 try:check_queue(r);assert r.verify_schema()['version']==8
 finally:r.close();allow(c,LIVE,False)
save('preopen-receipt.json',{'candidate':SHA,'model':'k3.1-pro','effort':'high','queue_empty':True,'schema':8,'opened':False})
print('preopen verified; no model request or delivery')
PY
```

继续核验实际writer身份和维护标记拒绝。以下不调用业务入口，不启动模型/dispatcher。临时连接准入只供这次只读检查，结束即关闭；任一失败保持公共维护门。

```bash
"$FR_PY" -I - "$FR_OP" <<'PY'
import sys
sys.path.insert(0,sys.argv[1]);from context import *
from tools.first_release_service_assets import Assets
from tools.first_release_hermes_entry import load_environment
from tools.first_release_service_binding import ServiceBinding,writer_parameters,checked_writer
from tools.first_release_writer_fence import file_lock,pg_lock
a=Assets.parse(json.loads(Path('/root/zhiming-core-secrets/first-release-service-config.json').read_text()))
b=ServiceBinding('web',ROOT,OP,a.system_identifier,a.database,a.database_oid,a.writer,a.writer_oid)
env=load_environment(a);os.environ.clear();os.environ.update(env)
b.validate([]);params=writer_parameters(b)
with admin() as c:
 zero(c,LIVE);allow(c,LIVE,True)
 try:
  with psycopg.connect(**params,autocommit=True,row_factory=dict_row) as writer:
   checked_writer(writer,b,params)
   with file_lock(b.fence_path,exclusive=True,existing_only=True),pg_lock(writer,b.fence_key,exclusive=True):
    assert b.maintenance.is_file()
    assert writer.execute("SELECT NOT has_table_privilege(current_user,'mingjing_core.core_model_usage','DELETE') AS safe").fetchone()['safe']
    save('writer-preopen.json',{'identity_verified':True,'maintenance_rejects_admission':b.maintenance.is_file(),'model_requests':0})
 finally:allow(c,LIVE,False)
 zero(c,LIVE)
print('writer identity and closed maintenance checked; no business/model entry invoked')
PY
```

实际四入口都由同一已核service入口在锁内再次检查maintenance；这里不把“标记存在”说成已经运行四次真实业务。任一入口配置没有走该service就停止，不能开门。

## D7：开门点和恢复服务

继续条件：31号仍在窗口、stage回执成功、D2–D6所有receipt与hash一致、原文件备份可读、当前无未知连接/任务、门内writer身份及维护拒绝验证通过。主线现场逐项核准，再执行以下块。首次移除任一writer维护限制即为开门点，先独占落盘opened记录，之后禁止旧备份回滚。

```bash
"$FR_PY" -I - "$FR_OP" <<'PY'
import sys
from datetime import datetime,timezone
sys.path.insert(0,sys.argv[1]);from context import *
assert read('preopen-receipt.json')['candidate']==SHA
assert read('writer-preopen.json')['identity_verified'] and read('writer-preopen.json')['maintenance_rejects_admission']
assert not (OP/'opened.json').exists()
with admin() as c:
 zero(c,LIVE);zero(c,KEPT)
 save('opened.json',{'candidate':SHA,'at':datetime.now(timezone.utc).isoformat(),'rollback_after_this_point':False})
 allow(c,LIVE,True)
 Path(read('service-identity.json')['maintenance']).unlink()
Path('/www/wwwroot/p-acme/core-maintenance.flag').unlink()
print('opened boundary recorded')
PY
systemctl start mingjingtai.service
systemctl is-active --quiet mingjingtai.service
systemctl start zhiming-core-feishu.service
systemctl is-active --quiet zhiming-core-feishu.service
```

报告timer只按D1保存的原active/enabled状态恢复，31号必须明确接受恢复已到期报告的正常投递。原状态的机器读取命令：

```bash
"$FR_PY" -I - "$FR_OP/units-before.json" <<'PY'
import json,sys
v=json.load(open(sys.argv[1]))['zhiming-core-reports.timer']
print('prior report timer:',v['ActiveState'],v['UnitFileState'])
PY
```

若原timer active且31号允许正常报告恢复，执行 `systemctl start zhiming-core-reports.timer`；原inactive不启动，不手动执行report service补发。未得到该项许可则保持停，并如实记录报告入口未恢复，不能宣布全入口上线完成。Hermes无需重启，下一次Core调用应走新固定wrapper；不主动发测试飞书。

任何开门后异常：重建公共维护门，停三service及timer；保存最新数据/隐私/收据与日志，发【提醒用户】；不换回旧包、不restore旧dump。开门前已接受的非原子服务启动顺序不能变成“部分成功仍放行”的理由。

## D8：一次网页冒烟和回执

主线只用网页做一次真实对话：核返回完整、实际model为k3.1-pro/high、同owner历史可读；不发飞书、不触发报告、不重试凑绿。token只由受保护页面会话读取，不放argv/日志。记录一次对话实际物理请求数（含内评）、实际model核验及安全结果，不输出用户正文/思考。失败按开门后止损处理，不再补一次。

最终核三个入口PID有效ExecStart/WorkingDirectory/新SHA、Hermes固定wrapper hash、报告timer与维护前状态；保留7dbc951、0aa433a、全部旧库及备份≥14天，不自动清理。回执≤1页：SHA/operation、31号窗口、stage来源、每步exit/hash/实际用时、四入口状态、开门时刻、网页冒烟实际物理数和结果、异常与未验证项。文档语法检查不是Linux演练或生产验收。

## R1：开门前回滚＝恢复到另一个新库＋改名对调＋全部入口回7dbc951

触发：D3–D6失败或窗口不足，且FR_OP/opened.json不存在。公共维护门保持，三service/timer停，Hermes仍被门与旧writer锁挡住。原live未对调时不需要回退原库，保留失败新库；已对调则执行下面恢复，禁止在新live上 `--clean` 或删除表。

先在候选新live只读导出当前privacy，与D2精确相等才可使用D2 dump；本路径开门前没有正常writer，新隐私差异意味着前提不成立，停止并保留现场，不丢弃最新撤销/送达收据。恢复到第三个全新库 `zhiming_core_rb_1a131275da9dc8d6`，对调失败新live保存为 `zhiming_core_failed_1a131275da9dc8d6`。恢复保owner/ACL/库与角色SET，旧包schema与D2原前缀一致。

```bash
systemctl stop zhiming-core-reports.timer zhiming-core-feishu.service zhiming-core-reports.service mingjingtai.service
"$FR_PY" -I - "$FR_OP" <<'PY'
import sys,subprocess
sys.path.insert(0,sys.argv[1]);from context import *
from tools.deploy_core import skill_writer_lock,export_withdrawals
assert not (OP/'opened.json').exists() and (OP/'exchange-receipt.json').is_file()
RB='zhiming_core_rb_1a131275da9dc8d6';FAILED='zhiming_core_failed_1a131275da9dc8d6'
with skill_writer_lock(exclusive=True),admin() as c:
 snap=read('database-before.json');allow(c,LIVE,False);zero(c,LIVE)
 allow(c,LIVE,True);r=repo(LIVE,True)
 try:assert export_withdrawals(r)==read('privacy-before.json')
 finally:r.close();allow(c,LIVE,False)
 assert not c.execute('SELECT 1 FROM pg_database WHERE datname=ANY(%s)',([RB,FAILED],)).fetchone()
 assert h(OP/'live-before.dump')==read('backup-receipt.json')['sha256']
 c.execute(sql.SQL('CREATE DATABASE {} OWNER {} TEMPLATE template0 ENCODING {} LC_COLLATE {} LC_CTYPE {}').format(sql.Identifier(RB),sql.Identifier(snap['owner']),sql.Literal(snap['encoding']),sql.Literal(snap['collate']),sql.Literal(snap['ctype'])))
 result=subprocess.run([pg_program('pg_restore'),'--host='+F['host'],'--port=5432','--username='+F['user'],'--dbname='+RB,'--no-password','--exit-on-error','--single-transaction',str(OP/'live-before.dump')],env=process_environment(DSN),capture_output=True)
 assert result.returncode==0
 with c.transaction():apply_metadata(c,RB,snap)
 r=repo(RB,True)
 try:
  assert export_withdrawals(r)==read('privacy-before.json')
  with r.connection() as db:assert [dict(x) for x in db.execute('SELECT version,checksum FROM mingjing_core.schema_migrations ORDER BY version')]==read('schema-before.json')['rows']
 finally:r.close();allow(c,RB,False)
 zero(c,LIVE);zero(c,RB)
 with c.transaction():
  c.execute("SET LOCAL lock_timeout='2s'")
  c.execute(sql.SQL('ALTER DATABASE {} RENAME TO {}').format(sql.Identifier(LIVE),sql.Identifier(FAILED)))
  c.execute(sql.SQL('ALTER DATABASE {} RENAME TO {}').format(sql.Identifier(RB),sql.Identifier(LIVE)))
  apply_metadata(c,LIVE,snap)
 save('rollback-database.json',{'restored_old_schema':True,'failed_database':FAILED,'new_live_oid':capture(c,LIVE)['oid'],'closed':True})
print('old schema restored to a new database and exchanged; failed database retained')
PY
```

之后从D1归档恢复所有旧unit/drop-in/两env/Hermes完整目录（包含原manifest和wrapper），逐项hash核对，所有四入口必须明确回到 `7dbc951eaffebd3d812169865eaefcde16a00ed9`，不能只切Web：

```bash
sha256sum -c "$FR_OP/runtime-before.sha256"
tar --acls --xattrs --numeric-owner -xpf "$FR_OP/runtime-before.tar" -C /
systemctl daemon-reload
for unit in mingjingtai.service zhiming-core-feishu.service zhiming-core-reports.service; do
 systemctl show "$unit" -p ExecStart -p WorkingDirectory -p DropInPaths -p NeedDaemonReload
done
test -d /root/zhiming-core-releases/7dbc951eaffebd3d812169865eaefcde16a00ed9
```

R71：恢复writer。在恢复归档之后、旧包校验之前执行。角色是集群级属性，不随库回退；库ACL由R1的 `apply_metadata` 恢复，这里只核对。

```bash
"$FR_PY" -I - "$FR_OP" <<'PY'
import sys
sys.path.insert(0,sys.argv[1]);from context import *
WRITER='zhiming_core_live_writer'
assert not (OP/'opened.json').exists() and Path('/www/wwwroot/p-acme/core-maintenance.flag').is_file()
hardened=(OP/'role-before.json').is_file()
assert not hardened or (OP/'rollback-database.json').is_file()
snap=read('database-before.json')
with admin() as c:
 zero(c,LIVE)
 if hardened:
  before=read('role-before.json');assert before['writer']==WRITER
  c.execute(sql.SQL('ALTER ROLE {} {}').format(sql.Identifier(WRITER),sql.SQL('INHERIT' if before['rolinherit'] else 'NOINHERIT')))
  assert c.execute('SELECT rolinherit FROM pg_roles WHERE rolname=%s',(WRITER,)).fetchone()['rolinherit'] is before['rolinherit']
  temp=c.execute("SELECT has_database_privilege(%s,%s,'TEMPORARY') AS temp",(WRITER,LIVE)).fetchone()['temp']
  assert temp is before['writer_temp']
 assert semantic(capture(c,LIVE))==semantic(snap)
 save('role-restored.json',{'writer':WRITER,'hardened':hardened,'verified':True})
print('writer state matches the state before hardening; database ACL matches the original snapshot')
PY
```

回退完成后仍保持公共维护、恢复库closed、三service/timer停。用原归档核四入口文件，再用旧7dbc解释器做只读schema兼容检查；不启动旧服务：

```bash
tar --acls --xattrs --numeric-owner -dpf "$FR_OP/runtime-before.tar" -C /
"$FR_PY" -I - "$FR_OP" "$FR_OLD_RELEASE" <<'PY'
import sys,subprocess
sys.path.insert(0,sys.argv[1]);from context import *
old=Path(sys.argv[2]);assert old.name=='7dbc951eaffebd3d812169865eaefcde16a00ed9'
code="import os,sys;sys.path.insert(0,sys.argv[1]);from mingjing_core.repositories.postgres import PostgresRepository;r=PostgresRepository(os.environ['ZHIMING_DATABASE_URL'],initialize=False);r.verify_schema();r.close()"
with admin() as c:
 zero(c,LIVE);allow(c,LIVE,True)
 try:
  env={'PATH':'/usr/bin:/bin','ZHIMING_DATABASE_URL':make_conninfo(DSN,dbname=LIVE,options='-c default_transaction_read_only=on -c role=zhiming_core_live_owner')}
  result=subprocess.run([str(old/'venv/core/bin/python'),'-I','-c',code,str(old)],env=env,capture_output=True)
  assert result.returncode==0,'old package read-only schema check failed; keep closed'
 finally:allow(c,LIVE,False)
 zero(c,LIVE)
 save('rollback-old-runtime.json',{'old_sha':old.name,'schema_readonly_verified':True,'closed':True})
print('old runtime verified read-only; public and database admission remain closed')
PY
```

媒体路径、撤销与送达收据不恢复旧文件副本来覆盖新数据；其相等性由前述privacy校验保护。完成后向审核人报告。未经门内旧包兼容验证不重开门。本单不删除新manifest、候选、旧包、KEPT/FAILED库或备份。任何对调中间错误不自行逆向rename重试，不强制断连、不改PG认证。


## 首发后待办

TA01第2轮未调用tarot_read，保留失败原件后查；followup_due规整为过去时间时应退回模型原未来时间，另加定向脚本。两项不在本次冻结e578e2d上改，不再发评测请求。
