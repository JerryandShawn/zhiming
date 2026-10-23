# B1：把临时表权限纳入增量工具的运行角色检查

本 ExecPlan 遵循 `.agent/PLANS.md`，2026-10-21 09:33 +08:00 创建。复用 `tools/core_incremental_pg.py::PostgresPort._runtime_safe`、`snapshot` 调用链和既有 B3 随机库夹具；不修改固定 b9、路由/角色 allowlist、迁移、真实服务或其他代理文件。

## Purpose / Big Picture

PostgreSQL TEMP 允许创建临时表，也属于 writer 禁止的 DDL。B3 恢复库验证已经检查它，但增量控制器的只读 runtime_safe 聚合 SQL 只查 CREATE。必须让运行角色即使其它表和账本授权正确、仅有 TEMP 时也被拒绝。检查不主动撤权限；未来 stage 如确有此权限，操作应停止交审。

## Progress

- [x] (2026-10-21 09:33 +08:00) 完整读权限方法和 snapshot、B3 真实 PG 权限测试及初始化/备份夹具，确认 TEMP 漏检。
- [x] (2026-10-21 09:35 +08:00) 原SQL真实PG反例2failed/24.23秒，增加TEMP后组合73passed+4subtests/21.22秒；原失败保留，旧断言不改。
- [x] (2026-10-21 09:37 +08:00) 新证据登记原件hash/精确计数/原JUnit+01时区，Ruff/120格式/diff通过。
- [ ] root独立小提交/推送；正式Linux仍阻塞。

## Surprises & Discoveries

已保护 schema CREATE 和账本只读不等于禁止 TEMP，PUBLIC 的默认 TEMP 也会授权给非 owner。B3 自己撤去 PUBLIC/writer 的数据库权限并做真实拒绝探针；该结果只证明恢复副本，不能自动替代历史 stage 的 runtime_safe 检查。

## Decision Log

2026-10-21 09:33 +08:00 / root：只在只读 SQL 聚合增加 has_database_privilege(...,'TEMP')。不自动 REVOKE、不放宽 stage 5432 名称或把本机端口接入 NativePort。专用真实 PG 测试直调用权限方法，所有实际连接来自已核的 loopback55480 随机库夹具；未调用控制器 connector/snapshot/Native。保留全部旧断言。07 R02/F01 基础授权/恢复不变量不变，无模型评分变化。

## Context and Orientation / Plan of Work

工作树 `C:/Users/Administrator/Documents/Codex/zhiming-v4`，分支 v4/p3-agent-runtime。初始本机 d480ed2ac2adb660373355934933f946876d4050。先使用现有 B3 prepare/generate 生成真实本机恢复库，核已迁7且 writer 安全；只给该随机 writer 或 PUBLIC 增加 TEMP，再调用真实权限 SQL，必须 false；撤回此次新增授权后必须 true。测试只清理自身随机库/角色。

## Concrete Steps / Validation and Acceptance

在清密钥/隐式PG环境、关追踪的 Core3.11 下，一个窄进程，显式 B1_PROOF_TEST_ADMIN_DSN/BIN/CANDIDATE。运行新两个实际 PG 反例，再跑旧5项 PG port 与62项路由契约；不启动宽回归，不访问服务器。

旧实现对 TEMP 错误返回 true 的真实红结果和新 false/撤回 true 结果独立留证。Windows 权限查询来自真实 PG15，但不证明 Linux/fcntl/systemd 或正式 stage 放行。

## Idempotence and Recovery / Interfaces and Dependencies

仅只读生产检查增强，无新依赖、迁移、API 或自动修复。测试故障保留原失败日志；精确自身资源由既有夹具清理，任何外部库均不可操作。B1 五门、30 No-Go、固定 b9 和两次环境尝试上限不变。

## Artifacts and Notes

私有 JUnit/输出放 `private/b1-restore-proof-20261021/`，公开摘要另写 `docs/v4/evidence/B1/2026-10-21-runtime-temp.md`。不输出 DSN/正文/密码。

## Outcomes & Retrospective

实现与先红后绿窄验完成。只加只读TEMP判定，实际PG两个反例覆盖writer直接授权及PUBLIC默认继承，撤回测试新增权限后恢复安全；组合73主用例+4子断言通过。生产不自动修权限，正式Linux/Native/fcntl/systemd未执行，五门和No-Go不解除。服务器、真实模型、飞书0。

## 修订记录

- 2026-10-21 09:33 +08:00 创建，区分恢复库的权限证明与 stage 控制器实际检查，保留失败即停。

- 2026-10-21 09:37 +08:00 记录真实PG先红后绿、73+4组合和SQL单行改动；原JUnit时区原样保留，不借本机结果放行stage。
