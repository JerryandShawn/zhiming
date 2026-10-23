# B1 增量 PG 首次连接路由边界：独立第二片

记录时间：2026-10-21 09:30（北京时间 UTC+08）。本片在第一 cache 片远端 `31e1133474b81c88ebde84d5122b667d905d3e2e` 后实施，由 root 独立审查提交；未修改固定发布包 b9a89b6。

## 改变与边界

`PostgresPort` 在首次 connector/子进程前拒绝 11 种非空 ambient libpq 配置；显式 DSN 白名单固定 literal loopback、5432、Request 精确库和独立角色、同一 owner/writer hostaddr/port/db、空 options、5 秒连接超时。_connection/environment 执行前再次检查，未使用 raw conninfo 回退。非法解析异常只保留固定错误码。

显式 DSN password 不读取或回显内容，只经原连接和必要 dump 环境传递；缺省 passfile 固定为空设备绝对路径，禁止回落用户 home。显式受审 passfile 先复用 `regular(private=True)` 检查绝对路径、普通文件、无 symlink 与私有模式，执行时重核。pg_dump 明确携带 PGHOSTADDR/PGPASSFILE/PGOPTIONS；候选子环境仍不含供应商 key。

旧 test Factory 从 URI 子串改为 `conninfo_to_dict(dsn)['user'].endswith('_writer')`，这是 root 事先批准的规范化适配。原 SQL、权限、只读事务、业务 hash、固定候选 Python 与不传模型凭据断言均保留。

## 实际验证

在主工作树清供应商/飞书/PG 凭据与追踪后，仅一个窄 pytest 进程：

    ../zhiming-v4-p2/.venv-core/Scripts/python.exe -m pytest tests/v4/release/test_b1_incremental_pg_routing.py tests/test_core_incremental_pg_port.py tests/v4/release/test_b1_existing_candidate_bytecode.py -q --junitxml=private/b1-restore-proof-20261021/incremental-routing-1.xml -o cache_dir=private/b1-restore-proof-20261021/routing-cache

结果：**71 passed、4 subtests passed，0.57s，exit 0**，failure/error/skip 均为0。新路由 62 项、旧 PG port 5 项、既有真实 pyc 合成入口 4 项。JUnit `tests=75` 包括4个子测试，普通 testcase=71；原 timestamp `2026-10-21T10:29:47.564925+09:00` 等于北京时间 09:29:47。

新目标覆盖 11 种 ambient 在构造前拒绝和在构造后 connect/candidate/dump 前拒绝；坏 hostaddr、多 host、service、options、timeout、port、dbname、role、未知字段、相对 passfile、非法 conninfo；不同 IPv4/IPv6 loopback 拒同服务器假设；显式合成 password 保留与默认空 passfile；private 门重复调用与保护变化；非私有文件拒绝且文件内容没有读取；dump/candidate 显式参数与供应商凭据隔离。所有失败反例 connector/runner 均为0调用。

Ruff `E,F,I,B,UP,SIM`、`ruff format --line-length 120`、尺寸检查通过：修改生产文件323行，新测试271行，所有相关函数≤60行。`git diff --check` 由冻结前复核，不涉及其他代理文件。

## 原始产物

| 文件 | bytes | SHA256 |
| --- | ---: | --- |
| tools/core_incremental_pg.py | 14255 | a0261f91144dab47c753411057f2d0ff0bd05dd26ec7675f8dd839744f329756 |
| tests/test_core_incremental_pg_port.py | 7963 | eed2ee1f68df701e461d733fe7f2393562f4d5c26b050830205bf313bd92ad2e |
| tests/v4/release/test_b1_incremental_pg_routing.py | 10914 | b349a3d69362e0e8ba4d4d7f78afc2bb0283bfe8cd3e88163f6ca86abd8dfdc7 |
| private/b1-restore-proof-20261021/incremental-routing-1.xml | 12266 | 132d000112eda21d1c7b8b0169348c54e255c3a43c59cd2fd1afb51620784c45 |

## 未验证与不变的阻塞

本次没有真实 PG 连接、迁移、备份、服务器/SSH、真实模型或飞书请求。新目标只用 connector/runner 替身验证边界，只有既有 pyc 入口测试实际运行本机 Python 与合成模块。private passfile 正例使用保护函数替身，只证传递/调用顺序，不能作为 Linux0600、root 所有权、真实 passfile 或 libpq 握手证据；反例真实文件的模式拒绝也不等于 Linux 权限验收。没有重探 Docker/WSL/Linux，正式 stage 与 B1 仍 No-Go。固定 b9、五项阻塞门和原审批不放宽；工具摘要变化需要 root 重新审查。B6 13资产缓存前缀由第三片单独处理。
