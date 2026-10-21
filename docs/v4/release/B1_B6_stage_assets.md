# B1 B6：独立合成 Web 库、权限、服务与隔离验证资产

2026-10-21 08:44，北京时间 UTC+08。**仅交可审文本与静态证据；30 号结论仍 No-Go，以下服务器命令全部未执行。** 不能因为本文件存在就去掉 B1 执行单的 No-Go 或五个阻塞门。真实 Linux、systemd/eBPF、PG 权限和浏览器验收仍待实测。B3 restore-proof 不在本片。

## 1. 固定目标与三库分工

| 用途 | 数据库 | 独立数据库角色 | 本片范围 |
|---|---|---|---|
| 固定 b9 的测试 DDL | `core_test_b1` | `core_test_b1_owner` / `core_test_b1_writer` | B5 另管，不借给 Web |
| 合成 Web | `zhiming_core_b1_web` | `zhiming_core_b1_web_owner` / `zhiming_core_b1_web_writer` | 本片新建/初始化/授权 |
| stage dump 恢复副本 | `zhiming_core_b1_restore` | `zhiming_core_b1_restore_owner` / `zhiming_core_b1_restore_writer` | B7 另管，不启动 Web |

历史 `zhiming_core_stage`、live、Hermes 和已有 unit/env/media 不由本片修改。发布目录固定 `/root/zhiming-core-releases/b9a89b6f84f7bebb640de080548010859aae630c`，schema1–7，manifest SHA256 仍为 `49038f8c0dc6bb293ba688af91018cbe6339b319c388d290fd000a256e36b33c`。部署配置/包装文本来自控制分支，分别记录原始 SHA256，不改 b9 包；0008 不在此库。

新对象必须全不存在才开始；发现同名库/角色/目录/unit/8788 监听或未知 drop-in 就停止，不能覆盖、接管或删除。未来授权 B 生效后仍逐步执行；任一异常停止，保留现状交大脑，不自动修复重试。估时：准备/角色 10–15 分，初始化/权限 5–15 分，隔离对照/启动/HTTP 10–20 分；不是实测耗时。

## 2. 文件落点与提取

操作根目录 `B6_ROOT=/root/zhiming-core-b1-stage`；`assets/`、`secrets/`、`media/`、`evidence/` 皆0700，文件0600。以下带 `b6-file` 标记的完整代码块是需审阅/哈希的资产。不得 source env，不读取 live 配置；新 token/数据库口令只生成到 secrets，不回显，不入 Git。运行前核 PG15 的 `psql` / Unix socket、`runuser` / `systemctl` / `ip` 绝对路径与权限，变量必须来自 B0，不能临时依赖 PATH 猜版本。

未来 Go 后，在已核 root 会话内创建全新目录；这里只表示步骤，不是当前许可：

```bash
set -euo pipefail
umask 077
B6_ROOT=/root/zhiming-core-b1-stage
test ! -e "$B6_ROOT"
mkdir -m 0700 "$B6_ROOT"
mkdir -m 0700 "$B6_ROOT/assets" "$B6_ROOT/secrets" "$B6_ROOT/media" "$B6_ROOT/evidence"
test -n "${PG15_PSQL:?B0 must pin psql absolute path}"
test -n "${PG15_SOCKET:?B0 must pin the 5432 Unix socket directory}"
test -n "${RUNUSER:?B0 must pin runuser absolute path}"
test -n "${SYSTEMCTL:?B0 must pin systemctl absolute path}"
test -n "${IP_BIN:?B0 must pin ip absolute path}"
```

由已审文档逐个复制下述有标记文件至 `assets/`，以不覆盖方式创建并 chmod0600；记录 `sha256sum assets/*`，不得把 secrets 加到该命令。不得生成/打印手填通过的 proof。`stage-b1-runtime.env` 后续由 systemd 读取，不能 source 到管理员 shell。

## 3. 新 Web 库 / 角色 SQL

管理员必须是 B0 已核的本机 PG15/5432 postgres，采用 Unix peer 管理入口；不从 live env 借口令。不存在获准管理入口时停止等待，不新增 pg_hba 或改全局认证。下面文件整体用于新对象；首次失败后不能整段重试。

<!-- b6-file: 01-create.sql -->
```sql
\set ON_ERROR_STOP on
DO $$ BEGIN
  IF current_database() <> 'postgres' OR current_user <> 'postgres'
     OR current_setting('port')::int <> 5432
     OR current_setting('server_version_num')::int NOT BETWEEN 150000 AND 159999
  THEN RAISE EXCEPTION 'B6 administrator identity mismatch'; END IF;
  IF EXISTS (SELECT 1 FROM pg_database WHERE datname='zhiming_core_b1_web')
     OR EXISTS (SELECT 1 FROM pg_roles WHERE rolname IN
       ('zhiming_core_b1_web_owner','zhiming_core_b1_web_writer'))
  THEN RAISE EXCEPTION 'B6 target already exists; do not overwrite'; END IF;
END $$;
CREATE ROLE zhiming_core_b1_web_owner LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
CREATE ROLE zhiming_core_b1_web_writer LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
CREATE DATABASE zhiming_core_b1_web OWNER zhiming_core_b1_web_owner TEMPLATE template0 ENCODING 'UTF8';
REVOKE ALL ON DATABASE zhiming_core_b1_web FROM PUBLIC;
GRANT CONNECT ON DATABASE zhiming_core_b1_web TO zhiming_core_b1_web_owner,zhiming_core_b1_web_writer;
REVOKE CREATE,TEMPORARY ON DATABASE zhiming_core_b1_web FROM zhiming_core_b1_web_writer;
ALTER ROLE zhiming_core_b1_web_writer IN DATABASE zhiming_core_b1_web SET search_path=public,mingjing_core;
\connect zhiming_core_b1_web
DO $$ BEGIN
  IF current_database()<>'zhiming_core_b1_web' OR current_user<>'postgres'
     OR current_setting('port')::int<>5432
  THEN RAISE EXCEPTION 'B6 new database identity mismatch'; END IF;
END $$;
ALTER SCHEMA public OWNER TO zhiming_core_b1_web_owner;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
```

postgres 用户不能遍历 root0700目录，故由 root 打开 stdin 后交给 runuser，**不用放宽 /root 权限，也不把私有文件复制到公共目录**：

```bash
"$RUNUSER" -u postgres -- "$PG15_PSQL" -X --no-password --host="$PG15_SOCKET" --port=5432 --dbname=postgres < "$B6_ROOT/assets/01-create.sql"
```

每次 SQL 必须 ON_ERROR_STOP。角色口令由以下生成器创建，只针对刚才新建的两个角色；SQL 与 pgpass 只存本机0600。B0 若发现 SQL/audit 日志会记录口令语句，先阻塞交大脑，不擅改日志配置，也不输出语句。

<!-- b6-file: 02-private-secrets.py -->
```python
import os
import secrets
from pathlib import Path

root = Path('/root/zhiming-core-b1-stage/secrets')
if root.is_symlink() or root.stat().st_uid != 0 or root.stat().st_mode & 0o777 != 0o700:
    raise SystemExit('B6 private directory rejected')

def write_new(name, value):
    fd = os.open(root / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as stream:
        stream.write(value)

statements = ['\\set ON_ERROR_STOP on']
for suffix in ('owner', 'writer'):
    role = 'zhiming_core_b1_web_' + suffix
    password = secrets.token_hex(48)
    statements.append(f"ALTER ROLE {role} PASSWORD '{password}';")
    write_new(suffix + '.pgpass', f'127.0.0.1:5432:zhiming_core_b1_web:{role}:{password}\n')
write_new('role-passwords.sql', '\n'.join(statements) + '\n')
write_new('web-token', secrets.token_hex(32) + '\n')
print('B6_PRIVATE_FILES_CREATED; values withheld')
```

```bash
"$RELEASE_DIR/venv/core/bin/python" "$B6_ROOT/assets/02-private-secrets.py"
"$RUNUSER" -u postgres -- "$PG15_PSQL" -X --no-password --host="$PG15_SOCKET" --port=5432 --dbname=postgres < "$B6_ROOT/secrets/role-passwords.sql"
```

## 4. owner 初始化与 checkpoint 授权

固定 b9 initialize 创建 1–7，不能用主树 P3/P1b 的 repository。新 Web 库的 public schema 已显式转给其独立 owner，不依赖 NOINHERIT 角色对模板 pg_database_owner 的隐含权限；不改变其他库的 public。owner 才能 setup checkpoint；writer 启动始终 initialize=False。锁定 `langgraph-checkpoint-postgres==3.1.2`，不手写一套猜测的 checkpoint 表 DDL。

<!-- b6-file: 03-initialize.py -->
```python
import os
import sys
from pathlib import Path
import psycopg
from psycopg.rows import dict_row

release = Path('/root/zhiming-core-releases/b9a89b6f84f7bebb640de080548010859aae630c')
sys.path.insert(0, str(release))
from mingjing_core.repositories.foundation import migration_manifest
from mingjing_core.repositories.postgres import PostgresRepository
from langgraph.checkpoint.postgres import PostgresSaver

dsn = 'host=127.0.0.1 port=5432 dbname=zhiming_core_b1_web user=zhiming_core_b1_web_owner connect_timeout=5'
if os.environ.get('PGPASSFILE') != '/root/zhiming-core-b1-stage/secrets/owner.pgpass':
    raise SystemExit('B6 owner passfile mismatch')
if sorted(migration_manifest()) != list(range(1, 8)):
    raise SystemExit('B6 candidate migrations mismatch')
with psycopg.connect(dsn, autocommit=True, row_factory=dict_row) as connection:
    row = connection.execute('SELECT current_database() AS db,current_user AS role,inet_server_addr()::text AS ip,inet_server_port() AS port').fetchone()
    if (row['db'], row['role'], row['ip'], row['port']) != ('zhiming_core_b1_web','zhiming_core_b1_web_owner','127.0.0.1',5432):
        raise SystemExit('B6 owner identity mismatch')
    if not 150000 <= int(connection.execute('SHOW server_version_num').fetchone()['server_version_num']) < 160000:
        raise SystemExit('B6 PG15 required')
repo = PostgresRepository(dsn, max_size=1)
try:
    repo.verify_schema()
    repo.ensure_owner('b1-synthetic', settings={'timezone':'Asia/Shanghai','auto_save_low_sensitivity':False})
finally:
    repo.close()
with psycopg.connect(dsn, autocommit=True, prepare_threshold=0, row_factory=dict_row) as connection:
    connection.execute('SET search_path TO public')
    PostgresSaver(connection).setup()
print('B6_SCHEMA7_AND_CHECKPOINT_CREATED; synthetic only')
```

```bash
cd "$RELEASE_DIR"
env -i PATH=/usr/bin:/bin LANG=C.UTF-8 TZ=Asia/Shanghai PYTHONDONTWRITEBYTECODE=1 PGPASSFILE="$B6_ROOT/secrets/owner.pgpass" "$RELEASE_DIR/venv/core/bin/python" "$B6_ROOT/assets/03-initialize.py"
```

授权 SQL 只在新 Web 库，以独立 owner 执行。新库的 PUBLIC 权限撤销不影响其他库；不授 writer owner 成员身份或 CREATE/TEMP。三个 checkpoint 表 CRUD；两本迁移账本 SELECT-only。完整权限语义以 [PostgreSQL15 GRANT](https://www.postgresql.org/docs/15/sql-grant.html) 为准，PUBLIC/成员继承同样影响有效权限，必须核实而非只看 GRANT 成功。

<!-- b6-file: 04-grants.sql -->
```sql
\set ON_ERROR_STOP on
BEGIN;
DO $$ BEGIN
  IF current_database()<>'zhiming_core_b1_web' OR current_user<>'zhiming_core_b1_web_owner'
     OR inet_server_addr()<>inet '127.0.0.1' OR inet_server_port()<>5432
  THEN RAISE EXCEPTION 'B6 owner grant identity mismatch'; END IF;
  IF (SELECT max(version) FROM mingjing_core.schema_migrations)<>7
     OR (SELECT count(*) FROM mingjing_core.schema_migrations)<>7
  THEN RAISE EXCEPTION 'B6 schema7 missing'; END IF;
END $$;
REVOKE ALL ON SCHEMA public,mingjing_core FROM PUBLIC;
GRANT USAGE ON SCHEMA public,mingjing_core TO zhiming_core_b1_web_writer;
REVOKE CREATE ON SCHEMA public,mingjing_core FROM zhiming_core_b1_web_writer;
GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA mingjing_core TO zhiming_core_b1_web_writer;
GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA mingjing_core TO zhiming_core_b1_web_writer;
REVOKE ALL ON mingjing_core.schema_migrations FROM zhiming_core_b1_web_writer;
GRANT SELECT ON mingjing_core.schema_migrations TO zhiming_core_b1_web_writer;
GRANT SELECT,INSERT,UPDATE,DELETE ON public.checkpoints,public.checkpoint_blobs,public.checkpoint_writes TO zhiming_core_b1_web_writer;
REVOKE ALL ON public.checkpoint_migrations FROM zhiming_core_b1_web_writer;
GRANT SELECT ON public.checkpoint_migrations TO zhiming_core_b1_web_writer;
COMMIT;
```

```bash
PGPASSFILE="$B6_ROOT/secrets/owner.pgpass" "$PG15_PSQL" -X --no-password --host=127.0.0.1 --port=5432 --username=zhiming_core_b1_web_owner --dbname=zhiming_core_b1_web < "$B6_ROOT/assets/04-grants.sql"
```

## 5. 无密钥 env 与精确启动包装

env 没有口令或 token 正文；KIMI_MODEL 是非密钥标签，API key 全不配置。真实 b9 的 ConfiguredModel 构造不发请求，generate 在无 key 时先失败，因此 health/state/history 可在无模型下启动；不能把这叫真实回答验收。`MODELS_CONFIG`/新 ModelPort 不启用。

<!-- b6-file: stage-b1-runtime.env -->
```ini
PATH=/usr/bin:/bin
LANG=C.UTF-8
TZ=Asia/Shanghai
PYTHONDONTWRITEBYTECODE=1
PYTHONUNBUFFERED=1
ZHIMING_DATABASE_URL="host=127.0.0.1 port=5432 dbname=zhiming_core_b1_web user=zhiming_core_b1_web_writer connect_timeout=5 application_name=b1-stage-web"
PGPASSFILE=/root/zhiming-core-b1-stage/secrets/writer.pgpass
MINGJING_TOKEN_FILE=/root/zhiming-core-b1-stage/secrets/web-token
MINGJING_OWNER_ID=b1-synthetic
ZHIMING_MEDIA_PATH=/root/zhiming-core-b1-stage/media
CHART_PYTHON=/root/zhiming-core-releases/b9a89b6f84f7bebb640de080548010859aae630c/venv/charts/bin/python
CORE_DB_POOL_SIZE=4
CORE_RUN_CONCURRENCY=1
CORE_FEISHU_ENABLED=false
LANGSMITH_TRACING=false
LANGCHAIN_TRACING_V2=false
KIMI_MODEL=k3
```

包装器拒绝真实 token/供应商凭据等继承项，并用明确 allowlist 构建 exec 环境。只读取刚生成的合成 token；不读 live env、Hermes 或管理员进程环境中的业务配置。检查/启动日志仅返回固定状态，不能回显环境或异常参数。

<!-- b6-file: 05-launch.py -->
```python
import os
import re
import stat
import sys
from pathlib import Path
from psycopg.conninfo import conninfo_to_dict

ROOT = Path('/root/zhiming-core-b1-stage')
RELEASE = Path('/root/zhiming-core-releases/b9a89b6f84f7bebb640de080548010859aae630c')
ALLOWED = {'PATH','LANG','TZ','PYTHONDONTWRITEBYTECODE','PYTHONUNBUFFERED','ZHIMING_DATABASE_URL',
           'PGPASSFILE','MINGJING_TOKEN_FILE','MINGJING_OWNER_ID','ZHIMING_MEDIA_PATH','CHART_PYTHON',
           'CORE_DB_POOL_SIZE','CORE_RUN_CONCURRENCY','CORE_FEISHU_ENABLED','LANGSMITH_TRACING',
           'LANGCHAIN_TRACING_V2','KIMI_MODEL'}

def private(path):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or stat.S_IMODE(info.st_mode) != 0o600:
        raise ValueError('private file')
    return path.read_text(encoding='utf-8').strip()

def environment():
    for key, value in os.environ.items():
        if value and key not in ALLOWED and (re.search(r'KEY|TOKEN|SECRET|PASSWORD|DSN|PROXY', key) or key in {'MODELS_CONFIG','MINGJING_MODEL_PORT'}):
            raise ValueError('inherited credential/config')
    env = {key:os.environ[key] for key in ALLOWED if key in os.environ}
    fields = conninfo_to_dict(env['ZHIMING_DATABASE_URL'])
    expected = {'host':'127.0.0.1','port':'5432','dbname':'zhiming_core_b1_web','user':'zhiming_core_b1_web_writer',
                'connect_timeout':'5','application_name':'b1-stage-web'}
    if fields != expected or env['PGPASSFILE'] != str(ROOT/'secrets/writer.pgpass'):
        raise ValueError('database identity')
    if env['CORE_FEISHU_ENABLED'] != 'false' or env['MINGJING_OWNER_ID'] != 'b1-synthetic':
        raise ValueError('channel/owner identity')
    if env['CHART_PYTHON'] != str(RELEASE/'venv/charts/bin/python') or env['ZHIMING_MEDIA_PATH'] != str(ROOT/'media'):
        raise ValueError('independent paths')
    passfile = private(ROOT/'secrets/writer.pgpass')
    if not re.fullmatch(r'127\.0\.0\.1:5432:zhiming_core_b1_web:zhiming_core_b1_web_writer:[0-9a-f]{96}', passfile):
        raise ValueError('passfile content')
    if env['MINGJING_TOKEN_FILE'] != str(ROOT/'secrets/web-token'):
        raise ValueError('token location')
    token = private(ROOT/'secrets/web-token')
    if re.fullmatch(r'[0-9a-f]{64}', token) is None:
        raise ValueError('synthetic token')
    env.pop('MINGJING_TOKEN_FILE')
    return dict(env, MINGJING_TOKEN=token)

try:
    env = environment()
    if sys.argv[1:] == ['--check']:
        print('B6_ENVIRONMENT_OK; values withheld')
    elif sys.argv[1:]:
        raise ValueError('arguments')
    else:
        os.chdir(RELEASE)
        python = str(RELEASE/'venv/core/bin/python')
        os.execve(python, [python,'-m','uvicorn','main:app','--host','127.0.0.1','--port','8788','--workers','1','--timeout-keep-alive','30','--no-access-log'], env)
except Exception:
    raise SystemExit('B6_LAUNCH_REJECTED; no credentials printed') from None
```

## 6. writer 实际只读预检

以下预检只连接新 Web 库，只读验证 schema/checkpoint/角色、所有 DML、账本只读、空队列/无渠道；不依靠 writer 自己执行 DDL 来“试错”。若需真实 DDL 拒绝演练，在本机新库单独事务测试，不对 stage 反复试写。

<!-- b6-file: 06-preflight.py -->
```python
import os
import sys
import psycopg
from psycopg.rows import dict_row

sys.path.insert(0, '/root/zhiming-core-releases/b9a89b6f84f7bebb640de080548010859aae630c')
from mingjing_core.repositories.postgres import PostgresRepository
from langgraph.checkpoint.postgres import PostgresSaver

def require(value):
    if not value:
        raise ValueError('B6 preflight invariant')

def verify(connection):
    row = connection.execute('SELECT current_database() AS db,current_user AS role,inet_server_addr()::text AS ip,inet_server_port() AS port').fetchone()
    require((row['db'],row['role'],row['ip'],row['port']) == ('zhiming_core_b1_web','zhiming_core_b1_web_writer','127.0.0.1',5432))
    require(150000 <= int(connection.execute('SHOW server_version_num').fetchone()['server_version_num']) < 160000)
    role = connection.execute('SELECT rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls,rolinherit FROM pg_roles WHERE rolname=current_user').fetchone()
    require(not any(role.values()))
    require(connection.execute('SELECT count(*) AS n FROM pg_auth_members WHERE member=(SELECT oid FROM pg_roles WHERE rolname=current_user)').fetchone()['n'] == 0)
    require(not connection.execute("SELECT has_database_privilege(current_user,current_database(),'CREATE') OR has_database_privilege(current_user,current_database(),'TEMP') AS elevated").fetchone()['elevated'])
    for schema in ('public','mingjing_core'):
        require(not connection.execute('SELECT has_schema_privilege(current_user,%s,\'CREATE\') AS elevated',(schema,)).fetchone()['elevated'])
    require(connection.execute("SELECT count(*) AS n FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname IN ('public','mingjing_core') AND c.relowner=(SELECT oid FROM pg_roles WHERE rolname=current_user)").fetchone()['n'] == 0)
    tables = connection.execute("SELECT schemaname,tablename FROM pg_tables WHERE schemaname IN ('public','mingjing_core')").fetchall()
    for row in tables:
        name = row['schemaname'] + '.' + row['tablename']
        ledger = row['tablename'] in {'schema_migrations','checkpoint_migrations'}
        for privilege in ('SELECT','INSERT','UPDATE','DELETE'):
            allowed = connection.execute('SELECT has_table_privilege(current_user,%s,%s) AS allowed',(name,privilege)).fetchone()['allowed']
            require(allowed == (privilege == 'SELECT' or not ledger))
    require(connection.execute('SELECT max(v) AS v FROM public.checkpoint_migrations').fetchone()['v'] == len(PostgresSaver.MIGRATIONS)-1)
    require(connection.execute("SELECT count(*) AS n FROM mingjing_core.core_runs WHERE status IN ('queued','running') OR lease_until>now()").fetchone()['n'] == 0)
    require(connection.execute('SELECT count(*) AS n FROM mingjing_core.core_channels').fetchone()['n'] == 0)
    require(connection.execute('SELECT count(*) AS n FROM mingjing_core.delivery_outbox').fetchone()['n'] == 0)

try:
    repo = PostgresRepository(os.environ['ZHIMING_DATABASE_URL'], initialize=False, max_size=1)
    try:
        repo.verify_schema()
    finally:
        repo.close()
    with psycopg.connect(os.environ['ZHIMING_DATABASE_URL'], row_factory=dict_row) as connection:
        connection.execute('SET TRANSACTION READ ONLY')
        verify(connection)
    print('B6_WRITER_PG15_SCHEMA7_CHECKPOINT_EMPTY_QUEUE_OK')
except Exception:
    raise SystemExit('B6_PREFLIGHT_REJECTED; no connection values printed') from None
```

## 7. 同机出站隔离对照

只选择 B0 当前接口上的一个 RFC1918 私有 IPv4（10/8、172.16/12、192.168/16）；不得用公网/NAT公网、0.0.0.0、网关或任意外部地址。用已核 `ip -j -4 address show up` 的本机地址列表与操作者选值交叉核对；没有可用地址就明确阻塞，不改网卡、防火墙、路由或其他 unit。

<!-- b6-file: 07-network-fixture.py -->
```python
import ipaddress
import json
import os
import secrets
import socket
import sys
import time
from pathlib import Path

root = Path('/root/zhiming-core-b1-stage/evidence')
address = ipaddress.IPv4Address(sys.argv[1])
if not any(address in ipaddress.IPv4Network(net) for net in ('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16')):
    raise SystemExit('B6 private IPv4 required')
listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
listener.bind((str(address), 0))
listener.listen(2)
listener.settimeout(1)
port = listener.getsockname()[1]
if not 32768 <= port <= 65535:
    raise SystemExit('B6 random high port required')
config = {'ip':str(address),'port':port,'nonce':secrets.token_hex(16),'pid':os.getpid()}
fd = os.open(root/'network-control.json', os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW, 0o600)
with os.fdopen(fd, 'w', encoding='utf-8') as stream:
    json.dump(config, stream)
end = time.monotonic() + 180
with listener:
    while time.monotonic() < end:
        try:
            peer, source = listener.accept()
        except TimeoutError:
            continue
        with peer:
            peer.settimeout(1)
            if source[0] == str(address) and peer.recv(128) == config['nonce'].encode():
                peer.sendall(b'b6-ack')
```

<!-- b6-file: 08-network-check.py -->
```python
import errno
import ipaddress
import json
import socket
import sys
from pathlib import Path

config = json.loads(Path('/root/zhiming-core-b1-stage/evidence/network-control.json').read_text())
address = ipaddress.IPv4Address(config['ip'])
if not any(address in ipaddress.IPv4Network(net) for net in ('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16')):
    raise SystemExit('B6_CONTROL_TARGET_REJECTED')
if sys.argv[1:] not in (['positive'], ['deny']):
    raise SystemExit('B6_CONTROL_MODE_REJECTED')
positive = sys.argv[1] == 'positive'
connected = False
established = False
try:
    with socket.create_connection((config['ip'], config['port']), timeout=2) as channel:
        established = True
        channel.sendall(config['nonce'].encode())
        connected = channel.recv(16) == b'b6-ack'
except OSError:
    pass
if positive and not connected or not positive and established:
    raise SystemExit('B6_NETWORK_EXPECTATION_FAILED')
if not positive:
    try:
        channel = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    except OSError as error:
        if error.errno not in {errno.EAFNOSUPPORT, errno.EPERM, errno.EACCES}:
            raise SystemExit('B6_IPV6_RESTRICTION_UNPROVEN') from None
    else:
        channel.close()
        raise SystemExit('B6_IPV6_NOT_RESTRICTED')
print('B6_CONTROL_POSITIVE' if positive else 'B6_SAME_CGROUP_DENY_AND_IPV6_RESTRICTION')
```

阳性控制在新 unit 外，只连接同机私有 listener；阴性控制是新 unit 的 ExecStartPre，必在相同 cgroup；其后 writer 预检证明 loopback5432 仍可用。禁止把 `curl` 供应商/公网地址超时当证据。[systemd 官方说明](https://www.freedesktop.org/software/systemd/man/latest/systemd.resource-control.html#IPAddressAllow=ADDRESS/PREFIXLENGTH%E2%80%A6)指出过滤覆盖该 unit 的 ingress/egress，但内核不支持时可能无效，所以必须实测对照；不能仅看到配置就通过。

## 8. 完整独立 unit

<!-- b6-file: zhiming-core-b1-stage.service -->
```ini
[Unit]
Description=B1 isolated synthetic Web, fixed b9, no provider credentials
After=network.target
ConditionPathExists=/root/zhiming-core-b1-stage/evidence/network-control.json

[Service]
Type=simple
User=root
UMask=0077
WorkingDirectory=/root/zhiming-core-releases/b9a89b6f84f7bebb640de080548010859aae630c
EnvironmentFile=/root/zhiming-core-b1-stage/assets/stage-b1-runtime.env
UnsetEnvironment=KIMI_API_KEY MOONSHOT_API_KEY OPENAI_API_KEY ANTHROPIC_API_KEY AZURE_OPENAI_API_KEY MODELS_CONFIG MINGJING_MODEL_PORT MINGJING_TOKEN ZHIMING_TOKEN_OWNERS FEISHU_APP_ID FEISHU_APP_SECRET FEISHU_VERIFICATION_TOKEN FEISHU_ENCRYPT_KEY LANGSMITH_API_KEY LANGCHAIN_API_KEY HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy PYTHONPATH PYTHONHOME PGSERVICE PGSERVICEFILE PGPASSWORD
ExecStartPre=/root/zhiming-core-releases/b9a89b6f84f7bebb640de080548010859aae630c/venv/core/bin/python /root/zhiming-core-b1-stage/assets/05-launch.py --check
ExecStartPre=/root/zhiming-core-releases/b9a89b6f84f7bebb640de080548010859aae630c/venv/core/bin/python /root/zhiming-core-b1-stage/assets/08-network-check.py deny
ExecStartPre=/root/zhiming-core-releases/b9a89b6f84f7bebb640de080548010859aae630c/venv/core/bin/python /root/zhiming-core-b1-stage/assets/06-preflight.py
ExecStart=/root/zhiming-core-releases/b9a89b6f84f7bebb640de080548010859aae630c/venv/core/bin/python /root/zhiming-core-b1-stage/assets/05-launch.py
Restart=no
TimeoutStartSec=20
TimeoutStopSec=15
KillMode=control-group
IPAddressDeny=any
IPAddressAllow=localhost
IPAccounting=yes
RestrictAddressFamilies=AF_UNIX AF_INET
NoNewPrivileges=yes
CapabilityBoundingSet=
AmbientCapabilities=
ProtectSystem=strict
ProtectHome=read-only
ProtectControlGroups=yes
PrivateTmp=yes
ReadWritePaths=/root/zhiming-core-b1-stage
InaccessiblePaths=-/root/.hermes -/root/zhiming-core-secrets -/root/zhiming-core-media -/root/zhiming-core-backups
StandardOutput=journal
StandardError=journal
```

不写 Install/WantedBy，不 enable；不创建 socket unit，也不 restart/daemon-reload 其他业务 unit。新 unit 的 daemon-reload 只加载新配置，实际必须核其他 unit 的状态/hash 无变化。未知 drop-in、忽略 directive、BPF 警告、前置失败都停止；不得删安全选项来“启动成功”。

## 9. 未来 Go 后的逐步验证命令

先在本机 Linux PG15 完整演练上述资产。主机实际验证须新的30 Go与B0–B5均通过；当前不能运行这些命令。B0应以安全白名单输出核本机私有IPv4，不导出整个环境。`B6_PRIVATE_IPV4` 必须来自已核接口，示例命令不预填服务器地址。

```bash
test -n "${B6_PRIVATE_IPV4:?select a reviewed local RFC1918 interface address}"
test -n "${NOHUP:?B0 must pin nohup absolute path}"
export B6_ROOT B6_PRIVATE_IPV4
"$IP_BIN" -j -4 address show up > "$B6_ROOT/evidence/interfaces.json"
"$RELEASE_DIR/venv/core/bin/python" -c 'import json,os; rows=json.load(open(os.environ["B6_ROOT"]+"/evidence/interfaces.json")); ip=os.environ["B6_PRIVATE_IPV4"]; import sys; sys.exit(0 if any(a.get("local")==ip for r in rows for a in r.get("addr_info",[])) else 1)'
"$NOHUP" env -i PATH=/usr/bin:/bin PYTHONDONTWRITEBYTECODE=1 "$RELEASE_DIR/venv/core/bin/python" "$B6_ROOT/assets/07-network-fixture.py" "$B6_PRIVATE_IPV4" < /dev/null > "$B6_ROOT/evidence/network-listener.log" 2>&1 &
```

固定 listener 自行180秒退出；用新 evidence 目录重复一轮，不能覆盖旧 network-control.json。观察控制文件就绪后，分步运行，任一步非0即停；不自动循环重试：

```bash
test -s "$B6_ROOT/evidence/network-control.json"
"$RELEASE_DIR/venv/core/bin/python" "$B6_ROOT/assets/08-network-check.py" positive
test ! -e /etc/systemd/system/zhiming-core-b1-stage.service
install -m 0600 "$B6_ROOT/assets/zhiming-core-b1-stage.service" /etc/systemd/system/zhiming-core-b1-stage.service
systemd-analyze verify /etc/systemd/system/zhiming-core-b1-stage.service
"$SYSTEMCTL" daemon-reload
"$SYSTEMCTL" show zhiming-core-b1-stage.service --property=FragmentPath,DropInPaths,IPAddressAllow,IPAddressDeny,RestrictAddressFamilies,Restart
"$SYSTEMCTL" start zhiming-core-b1-stage.service
"$RELEASE_DIR/venv/core/bin/python" "$B6_ROOT/assets/08-network-check.py" positive
"$SYSTEMCTL" show zhiming-core-b1-stage.service --property=ActiveState,SubState,MainPID,ControlGroup,IPIngressBytes,IPEgressBytes
```

必须同时有：unit外阳性→同cgroup阴性/IPv6拒绝→同cgroup PG loopback阳性→unit启动→unit外仍阳性。两次阳性之间 listener 必须是同pid/同ip/同port/同nonce；超出180秒、listener退出、配置hash变化或任一对照缺失均不算网络通过。PG/HTTP是同机连接，不是模型/飞书探针。`ss -lntp` 仅筛8788，须只有127.0.0.1，不能0.0.0.0、::或公网；同端口出现未知PID立即停审。

通过只读 HTTP GET 核登录和页面，token从新文件读取，不放argv，不打印正文：

<!-- b6-file: 09-http-readonly.py -->
```python
import json
from pathlib import Path
from urllib.request import Request, build_opener, ProxyHandler
from urllib.error import HTTPError

token = Path('/root/zhiming-core-b1-stage/secrets/web-token').read_text().strip()
opener = build_opener(ProxyHandler({}))
base = 'http://127.0.0.1:8788'
try:
    opener.open(Request(base+'/api/state'), timeout=5)
except HTTPError as error:
    if error.code != 401:
        raise SystemExit('B6 unauthenticated status mismatch') from None
else:
    raise SystemExit('B6 authentication missing')
for path in ('/api/health','/api/state','/api/history','/api/tarot/deck','/api/tarot/draws'):
    with opener.open(Request(base+path,headers={'X-Token':token}),timeout=5) as response:
        if response.status != 200:
            raise SystemExit('B6 authenticated GET failed')
        value = json.load(response)
        if path in ('/api/history','/api/tarot/draws') and value != []:
            raise SystemExit('B6 synthetic empty projection requires review')
print('B6_AUTHENTICATED_READONLY_GETS_OK; values withheld')
```

运行该片段只用 GET，先证明空库与登录；b9 的 history_window 明确返回 list，保持精确空列表断言，不兼容猜测出来的结构。

```bash
"$RELEASE_DIR/venv/core/bin/python" "$B6_ROOT/assets/09-http-readonly.py"
```

随后直接在独立 Web 库通过 b9 原业务服务生成一套纯合成固定牌，不经 chat/reading、无模型、无 sender，不复制 B5 测试库资料。第一次抽牌是真随机，重放必须固定原牌，不能手工伪造 deck 或篡改数据库。

<!-- b6-file: 10-fixed-draw.py -->
```python
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, '/root/zhiming-core-releases/b9a89b6f84f7bebb640de080548010859aae630c')
from mingjing_core.repositories.postgres import PostgresRepository, fingerprint
from mingjing_core.application.memory import MemoryService
from mingjing_core.adapters.tarot import TarotService

dsn = 'host=127.0.0.1 port=5432 dbname=zhiming_core_b1_web user=zhiming_core_b1_web_writer connect_timeout=5'
if os.environ.get('PGPASSFILE') != '/root/zhiming-core-b1-stage/secrets/writer.pgpass':
    raise SystemExit('B6 fixed draw identity mismatch')
repo = PostgresRepository(dsn, initialize=False, max_size=1)
try:
    repo.verify_schema()
    case = MemoryService(repo).create_case('b1-synthetic','self','B1合成固定牌',operation_id='b6-synthetic-case')
    tarot = TarotService(repo)
    arguments = dict(subject_id='self',case_id=case['id'],question='合成演练：整理明天的书桌',
                     spread_id='reflect3',draw_source='auto',reversals=True,idempotency_key='b6-synthetic-draw')
    draw = tarot.create_draw('b1-synthetic', **arguments)['draw']
    fixed = tarot.reveal('b1-synthetic', draw['id'])
    replay = tarot.create_draw('b1-synthetic', **arguments)['draw']
    if fingerprint(fixed['cards']) != fingerprint(replay['cards']) or fixed['id'] != replay['id']:
        raise ValueError('B6 fixed draw changed')
    evidence = {'id':fixed['id'],'case_id':case['id'],'cards_sha256':fingerprint(fixed['cards'])}
    path = Path('/root/zhiming-core-b1-stage/evidence/fixed-draw.json')
    fd = os.open(path, os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd,'w',encoding='utf-8') as stream:
        json.dump(evidence,stream)
finally:
    repo.close()
print('B6_REAL_SYNTHETIC_DRAW_AND_REPLAY_FIXED; no model')
```

```bash
env -i PATH=/usr/bin:/bin LANG=C.UTF-8 TZ=Asia/Shanghai PYTHONDONTWRITEBYTECODE=1 PGPASSFILE="$B6_ROOT/secrets/writer.pgpass" "$RELEASE_DIR/venv/core/bin/python" "$B6_ROOT/assets/10-fixed-draw.py"
```

固定牌公开 GET 再读取两次并只输出 hash 校验状态。令牌仍不放 argv/stdout；不输出牌面、背景或原始正文。

<!-- b6-file: 11-fixed-draw-http.py -->
```python
import hashlib
import json
from pathlib import Path
from urllib.request import Request, build_opener, ProxyHandler

root = Path('/root/zhiming-core-b1-stage')
proof = json.loads((root/'evidence/fixed-draw.json').read_text())
token = (root/'secrets/web-token').read_text().strip()
client = build_opener(ProxyHandler({}))
request = Request('http://127.0.0.1:8788/api/tarot/draws/'+proof['id'],headers={'X-Token':token})
for _ in range(2):
    with client.open(request,timeout=5) as response:
        draw = json.load(response)
    encoded = json.dumps(draw['cards'],ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
    if draw['id'] != proof['id'] or hashlib.sha256(encoded).hexdigest() != proof['cards_sha256']:
        raise SystemExit('B6_FIXED_DRAW_HTTP_CHANGED')
print('B6_FIXED_DRAW_HTTP_TWICE_OK; values withheld')
```

```bash
"$RELEASE_DIR/venv/core/bin/python" "$B6_ROOT/assets/11-fixed-draw-http.py"
```

以上不是 DOM/截图验收。B5 先跑真实业务/ScriptedPort 的撤销与脚本测试；B6 浏览器仅在新合成owner下用新口令查看旧原生静态页和此固定牌，不触发 chat/readings/retry/resume 生成端点，不打开生产域名或公网资源。DOM/截图仍单列证据，不能把这几个 GET 或固定牌服务证明写成已完成浏览器验收。

任何隔离/权限/健康失败时，仅止损停止本次新 unit，保留目录/库/回执，不删除或修复重试；不碰其他服务：

```bash
"$SYSTEMCTL" stop zhiming-core-b1-stage.service
"$SYSTEMCTL" is-active zhiming-core-b1-stage.service
```

记录每一步实际UTC+08时间、退出码、安全计数、工具/配置SHA、同cgroup及阳性对照证据。只看unit配置、Bash/AST通过或HTTP 200都不能填 isolation_passed/Linux_passed=true。

## 10. 本次验证状态与资产 hash

2026-10-21 08:42 北京时间，在主线 HEAD `c7d760addc63ea9c8a12d15d08123b32f6e17238` 的未提交文档片上进行纯内存提取：13个完整资产，其中9段Python全部 AST 与 Ruff E9/F 检查通过，最大函数24行；11段Bash全部由现存Git Bash `--noprofile --norc -n`解析通过。初次检查发现一项未使用import，已删除；Windows默认编码导致中文脚本送入Ruff时解码失败，改用原始UTF8字节复核后9/9通过，不改脚本语义或绕过规则。

env/unit/SQL的结构核对通过：env无API key/token/口令正文；unit固定b9、回环8788、deny any/allow localhost、仅AF_UNIX/AF_INET、Restart=no、无Install；创建SQL只有2个新Web角色与1个Web库、无DROP/TRUNCATE/ALTER SYSTEM、无历史stage/live目标；checkpoint三表CRUD与迁移账本只读均有明确SQL。INI检查使用Python标准库读取，不冒称systemd原生验证；SQL仅静态结构核对，没有PG解析或执行。

`git diff --check`通过；另外以原文B6起止为边界比较，runbook的B6之外内容保持不变。没有运行任何内嵌脚本、SQL、systemd、网络listener/探针、HTTP或pytest，没有生成口令/token；服务器/模型/飞书请求0。真实Linux/PG权限/同cgroup网络/DOM仍未验证，30号No-Go未改变，B1不放行。

08:44补明确新Web库public schema的独立owner，避免依赖NOINHERIT下模板隐含权限；随后重新核13项hash、9段AST/Ruff E9/F、11段Bash -n与SQL/env/unit结构，全部通过。这里只修改新库模板，未执行任何SQL。

下列hash按代码块正文UTF8、LF换行且结尾一个LF计算；未来提取文件必须逐个一致。新生成secrets不在索引中，也不能向公共日志打印其内容或SQL。

| 资产 | 字节 | SHA256 |
|---|---:|---|
| `01-create.sql` | 1608 | `7a5038c7319face846f52d4295e5aeeb182a144397b84131fb24ea7394435fb5` |
| `02-private-secrets.py` | 946 | `881bcabe3e8d7b8cc0041115e6bf40498471a7eda8fbb64f5f6a836fa95a8b22` |
| `03-initialize.py` | 1805 | `d8e346d15ab120cee4e786aed981553d60badb322d2be422af2d69fe7c5d8f9f` |
| `04-grants.sql` | 1322 | `6c79df2d83200983bab18b5d5634a0740b6f217a355e5a5695edd106506daf50` |
| `stage-b1-runtime.env` | 699 | `e4e1ad6f29b934ab1fa583e2169c6ce75d14937dc5985de18c5f4099ccb93620` |
| `05-launch.py` | 2937 | `2b4834d4ac6906d4cf7ae795e72f807238682c68fd22ac6e230f54f9283196f9` |
| `06-preflight.py` | 3444 | `27f7a1aa362a140c66e4ff76f5e597abe5bfbc8fad59959b5d3e46377e000b06` |
| `07-network-fixture.py` | 1260 | `c0b4560e7426237284b72723a751b1f1cdb936ae0cbe17e2f31fd42753550b97` |
| `08-network-check.py` | 1383 | `3526d681c1c9ae12e932fc617b769571ef893859e8a6b560fadad1369d75afe0` |
| `zhiming-core-b1-stage.service` | 1933 | `0a1384418e6c1cb44d33431db200f5469713a92a2cb9ea407821dda61f43cde3` |
| `09-http-readonly.py` | 1056 | `2a46099d2a8bf334b2ae832547ecdf9c37d97ea7cb8e94e9a2b870e4460c5525` |
| `10-fixed-draw.py` | 1818 | `9e02959fad8adc7b6257a979dfee2717661b44ca9f77aedb715ef3de3069d0fc` |
| `11-fixed-draw-http.py` | 836 | `3f4c1f3fc5a29b3e0d8775f684a2601ed9ed9bc23cb2b150d3f07adaab29fc80` |
