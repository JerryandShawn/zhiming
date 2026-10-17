# P0 本机隔离环境

2026-10-17（UTC+08:00）建立。仅合成数据；没有访问 stage、生产或旧数据库，没有读取真实密钥。

| 项目 | 本次环境 |
| --- | --- |
| Core | `.venv-core/Scripts/python.exe`，CPython 3.11.16 |
| Core 依赖 | `requirements-core.lock` 与 `requirements-test.lock` 原样安装；依赖一致性通过 |
| Charts | `.venv-charts/Scripts/python.exe`，CPython 3.11.16 |
| Charts 依赖 | `requirements-charts.lock` 原样安装；依赖一致性通过 |
| Charts 导入 | `lunar_python`、`swisseph`、`pythonmonkey`、`py_iztro` 均成功 |
| Node | 22.23.3；官方 Windows x64 ZIP，SHA256 与官方清单一致 |
| 前端依赖 | `npm ci` 成功，115 个依赖包；锁文件未改 |
| PostgreSQL | 15.19；新 cluster 位于忽略的 `private/pg-p0/` |
| 连接 | `postgresql://core_test@127.0.0.1:55480/core_test` |

该 DSN 没有密码，只对本次新建 cluster 的回环连接使用 trust。服务只监听 `127.0.0.1`；数据库可丢弃，不存放私人资料。旧工作区仅用于读取 PG 二进制，未使用旧 `pg-data`。

在项目根目录的 PowerShell 设置当前进程环境：

```powershell
$env:CORE_TEST_DSN = 'postgresql://core_test@127.0.0.1:55480/core_test'
$env:ZHIMING_TEST_DSN = $env:CORE_TEST_DSN
$env:ZHIMING_DATABASE_URL = $env:CORE_TEST_DSN
$env:CHART_PYTHON = "$PWD\.venv-charts\Scripts\python.exe"
$env:MINGJING_TOKEN = 'p0-local-synthetic-only'
$env:LANGSMITH_TRACING = 'false'
$env:KIMI_API_KEY = ''
$env:MOONSHOT_API_KEY = ''
$env:FEISHU_APP_ID = ''
$env:FEISHU_APP_SECRET = ''
$env:CORE_FEISHU_ENABLED = 'false'
$env:PYTHONUTF8 = '1'
$nodeDir = (Get-Content -LiteralPath private\runtime\node22-path.txt -Raw).Trim()
$pgBin = 'C:\Users\Administrator\Documents\Codex\2026-10-11\p-jerrymeng-asia-1-14-59\work\postgres\pgsql\bin'
$env:PATH = "$nodeDir;$pgBin;$env:PATH"
```

Node 可执行文件位于 `private/runtime/node-v22.23.3-win-x64/`，不依赖系统当前的 Node 24。默认系统 Python 为 3.14，因此运行检查时必须显式使用 `.venv-core/Scripts/python.exe`。Charts 在 Windows 原生运行，无需 WSL 或 Docker。

`pg_dump` 和 `pg_restore` 必须通过上述 PG bin 路径可见；旧恢复验收会真实创建及恢复合成备份，不能用替身代替。

重启已经初始化的本次 PG cluster：

```powershell
$pgBin = 'C:\Users\Administrator\Documents\Codex\2026-10-11\p-jerrymeng-asia-1-14-59\work\postgres\pgsql\bin'
& "$pgBin\pg_ctl.exe" -D "$PWD\private\pg-p0" -l "$PWD\private\p0-logs\pg-server.log" -o '-h 127.0.0.1 -p 55480' -w start
```

停止本次 PG 时使用同一二进制和 `-D "$PWD\private\pg-p0" -m fast -w stop`，不要操作旧 cluster 或机器上其他服务。原始日志均位于忽略的 `private/p0-logs/`；可提交证据仅保留命令、计数及脱敏摘要。

已观察到的依赖基线风险：`npm ci` 的审计摘要为 8 项漏洞（2 moderate、6 high）；P0 未自动升级依赖，也未运行会修改锁文件的修复命令。具体修复留作独立范围评估。
