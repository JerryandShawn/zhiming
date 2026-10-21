# B1：在增量工具首次连接前固定 PG 路由

本 ExecPlan 遵循 `.agent/PLANS.md`。四活节持续更新，全部时间为北京时间（UTC+08）。本片独立于已冻结的候选 Python cache 修复，不修改固定 b9 或 B1 No-Go。

## Purpose / Big Picture

显式 DSN 的 host/port 看似合法时，libpq 仍可能从 PGHOSTADDR、service、options 或默认 pgpass 读取未受审配置。连接之后才核身份无法阻止第一次连接越出回环。本片在任何连接/子进程之前拒绝这些隐式输入，并把 owner/writer 路由规范为精确回环、5432、正确库与独立角色。

## Context and Orientation

主工作树 `C:/Users/Administrator/Documents/Codex/zhiming-v4`，`v4/p3-agent-runtime`。root 授权第二小片修改 `tools/core_incremental_pg.py` 的输入规范化、首次/后续连接与子环境/pg_dump 传递；新增独占 `tests/v4/release/test_b1_incremental_pg_routing.py`、本计划和独立证据。第一 cache 片由 root 提交本机 ca266a6、远端 31e1133 后解冻，才修改同一个 core_incremental_pg.py；本片仍由 root 独立审查提交。

复用现有 Request.database、独立 owner/writer 名、conninfo_to_dict、require/UpgradeRejected、受保护文件 regular(private=True)、CommandRunner 与 connector 注入。`snapshot` 的只读事务、迁移/回填/withdrawals 业务、运行角色与 source/manifest/审批门不变；不改 B3/App/consumer 或其他 portable 支持文件。

## Progress

- [x] (2026-10-21 09:25 +08:00) 已读完整 PostgresPort 与文件保护函数，确认 _connection 直接传 raw DSN，pg_dump 也缺显式 passfile/hostaddr。
- [x] (2026-10-21 09:25 +08:00) root 批准最小旧 Factory 适配：从 URI 子串判 role 改为 conninfo_to_dict(dsn)['user'].endswith('_writer')，旧 SQL/断言全部保留。
- [x] (2026-10-21 09:29 +08:00) cache 片提交后新增受审路由规范化与执行时重核；11 种 ambient、首次/后续连接、显式 DSN 与密码文件反例已实现。
- [x] (2026-10-21 09:30 +08:00) 窄组 71 passed + 4 subtests passed / 0.57s：新路由 62 项、旧 PG port 5 项、实际 pyc 合成入口 4 项；无 failure/error/skip。Ruff、120 字符格式、文件/函数尺寸检查通过。
- [ ] root 复核差分、冻结并独立提交；B6 缓存文本为下一片，本片不修改。

## Surprises & Discoveries

当前构造器只解析 host/port/db/user，_connection 随后把原字符串交给 libpq，PGHOSTADDR 可在第一次连接前覆盖路由。候选子环境已有明确清理，但不覆盖父进程 connector。禁止 ambient 一次也不够，构造后到执行前环境可能变化；须在 _connection/environment 再核。pg_dump 必须携带 canonical PGHOSTADDR/PGPASSFILE/PGOPTIONS，不能因它的环境重建漏掉禁用默认 passfile 的要求。

规范化使 URI 转为 key=value conninfo，因此旧 Factory 按 `_writer@` 子串识别角色失效；经 root 预先批准，改为真正解析 user 后看 `_writer` 后缀。旧角色身份、只读事务、权限、hash、固定解释器与凭据清理断言原样保留。

## Decision Log

2026-10-21 09:25 / Codex、root：拒绝 PGHOST/PGHOSTADDR/PGPORT/PGDATABASE/PGUSER/PGSERVICE/PGSERVICEFILE/PGSYSCONFDIR/PGOPTIONS/PGPASSFILE/PGPASSWORD 的非空 ambient。DSN 字段白名单，明确 hostaddr、port=5432、options 空、connect_timeout=5；owner/writer 的 hostaddr/port/db 必须相同。仍只允许 Request 的 stage/live 精确库与各自 owner/writer，不因为是本机测试开放新端口。

2026-10-21 09:25 / Codex、root：显式 DSN password 原样透传，不读取或显示；没有显式 passfile 时用绝对空设备路径，禁止回落用户 home。显式 passfile 必须绝对路径、无 symlink、通过现有 private 文件保护；不引入新授权文件或私有口令协议。Windows 无法证明 Linux0600，相关替身只证“先调用保护门再透传”的 ABI，不能宣称 Linux 权限通过。

2026-10-21 09:25 / Codex、root：只改旧 test_core_incremental_pg_port.py::Factory 的一行 URI 格式假设及必要 import。规范化成 key=value 是正确行为，保留所有 SQL/owner/readonly/hash/凭据/固定源码安全断言，不改预期来迁就路由错误。

## Outcomes & Retrospective

实现已通过第二片独立窄组：71 passed + 4 subtests passed / 0.57s。Mock connector/runner 只证明物理边界前参数拒绝、显式规范参数和子环境传递；本次只有既有 pyc 合成测试实际执行本机 Python，不连接 PG。Windows 密码文件正例替身只证明 private 保护调用 ABI，不证明 Linux0600。服务器/SSH/真实模型/飞书为0，没有第三次 Linux 环境尝试。固定 b9、B1 No-Go 与五项阻塞不变；cache 第一片历史证据保留。

## Plan of Work

在连接类之前新增短私有 helper：拒 ambient、规范 DSN、验证显式 passfile。构造时先对两角色都规范化再比较同一服务器，不在部分校验完成时启动 pool。_connection 和 environment 再拒 ambient；不输出原始 parse 异常。dump 从 owner canonical conninfo 显式派生 libpq 变量，仍经原 CommandRunner，不引入 shell。

新增反例把 connector/subprocess/runner 设为一旦执行就失败：坏 ambient、hostaddr、service/options、库/role/port、混 owner/writer 主机、非法/非私有 passfile，均在物理边界前停止。正例检查 canonical 参数、显式合成 password 保留、默认 passfile=null、私有 passfile 保护函数调用、构造后环境变化拒绝和 pg_dump 的显式受控环境；不真实连接5432或服务器。

## Concrete Steps

使用已有 Core Python、清供应商/飞书/ambient PG 凭据并禁追踪，单窄进程：

    ../zhiming-v4-p2/.venv-core/Scripts/python.exe -m pytest tests/v4/release/test_b1_incremental_pg_routing.py tests/test_core_incremental_pg_port.py tests/v4/release/test_b1_existing_candidate_bytecode.py -q
    .venv-core/Scripts/python.exe -m ruff check --select E,F,I,B,UP,SIM --line-length 120 tools/core_incremental_pg.py tests/test_core_incremental_pg_port.py tests/v4/release/test_b1_incremental_pg_routing.py

只跑必要窄目标；10:00 前不跑整库。没有依赖安装、PG 写入或环境修复。

## Validation and Acceptance

坏输入零 connector/runner 调用；合法 canonical hostaddr 不受隐式环境干扰（ambient 改变则直接拒绝）；host/port/db/user不放宽；默认 home pgpass 不读取；显式合成 secret 不回显；dump/candidate 不重新引入未受审路由。旧只读快照/角色权限与业务 argv 目标保持通过。07 号 F/X 的撤销/幂等/中断行为不改，本片不改评测分数。

## Idempotence and Recovery

纯参数规范化可重复执行，canonical passfile=null 的输入仍可接受；失败不回退 raw DSN，不重试、不改变环境。原维护门/停止服务/授权上下文由外层负责，本片不放行。没有数据库迁移；controller 摘要随工具改变，旧审批仍需重新审查。

## Artifacts and Notes

证据路径 `docs/v4/evidence/B1/2026-10-21-incremental-pg-routing.md`；私有 JUnit 保存精确时间/数量/摘要。仅合成口令可出现在测试输入源码，任何真实 DSN/env 值/口令不出日志或回执。

本片 JUnit 为 `private/b1-restore-proof-20261021/incremental-routing-1.xml`，12266 bytes，SHA256 `132d000112eda21d1c7b8b0169348c54e255c3a43c59cd2fd1afb51620784c45`。原始 timestamp `2026-10-21T10:29:47.564925+09:00`，对应北京时间 09:29:47；不把主机 Tokyo 时间当作北京时间。JUnit tests=75 包括 4 个 subtest，普通 testcase=71。

## Interfaces and Dependencies

PostgresPort 的公开签名与 CommandRunner/connector 不变；self.dsns 从 raw 字符串变为受控 canonical conninfo，兼容显式密码和私有 passfile。测试旧 Factory 需按实际 conninfo 取 user，不依赖 URI 文本布局。只用现有 psycopg 与标准库，不新增依赖。

## 修订记录

- 2026-10-21 09:25 +08:00：按 root 第二小片授权创建，先列旧测试改动与秘密/权限边界，等待第一片提交后实施。
- 2026-10-21 09:30 +08:00：第一片解冻后实现并记录实际 71+4 窄组结果；保持 Linux/PG/stage 未验证，B6 文本留独立第三片。
