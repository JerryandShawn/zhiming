# P3：已提交工具副作用的同 epoch 恢复矩阵

本 ExecPlan 遵循 `.agent/PLANS.md`，时间为北京时间 UTC+08。

## Purpose / Big Picture

证明实际 AgentRuntime 调用可写工具后，在业务事务已经提交、Journal.complete 尚未确认的窗口崩溃，可保留领域快照的写入在旧租约到期后能在同 epoch 使用同一 operation_id 恢复。真实 memory_update 更正沿用既有 stale/旧lease拒绝契约，单列证明一次更正/收据保留、旧epoch零新模型与零重复效果，不能为全绿放宽 superseded/撤销检查。业务结果、原收据、版本和来源必须不变；本片只新增测试与证据。

## Context and Orientation

复用 `tests/v4/agent/test_agent_runtime_pg.py:invoke/queued`、`test_loop_cycle_support.py:ScriptedPort/SyntheticMeter/cycle_repo` 与既有 Loop/Journal 恢复测试。模型使用明确离线替身，PostgreSQL、AgentRuntime、ToolRegistry、应用工具与 mutation_request 都是真实实现。只在 Journal.complete 针对目标工具恰好一次抛 SystemExit，不伪造工具输出或数据库效果。

## Progress

- [x] (2026-10-21 01:59) 完整读取 Runtime/Loop/Journal 已有恢复测试及实际写入服务，划定崩溃点与同 epoch 不变量。
- [x] (2026-10-21 02:04) 第一片严格矩阵已落盘；8 个非 case_update 分支真实 PG 通过（7.37 秒），其中真实 memory_update 更正保留 stale 安全契约，敏感更正 proposal 另验同 epoch 恢复。
- [x] (2026-10-21 02:01) 先跑 case_update 高风险单例，实际失败已交主代理；原严格断言保留，未 xfail、改 epoch 或改业务源码。
- [x] (2026-10-21 07:33) case_update 最小证明修复与完整窄组通过：41 passed / 20.32 秒，包括新矩阵 9 项、新证明 25 项及原 own_revisions 7 项；旧 completed_step 反例保留。
- [ ] 第二片：待塔罗业务文件冻结后追加 tarot_start；未验不宣称通过。
- [x] (2026-10-21 07:34) Snapshot/Runtime/Journal/case_versions 四文件窄回归 47 passed / 17.16 秒；Ruff/format、尺寸与 diff 检查通过，冻结本片 8 文件交主代理提交。

## Surprises & Discoveries

静态发现：`persisted_receipts` 当前只读 completed 的工具步骤；本矩阵的步骤是 started，但实际 mutation 收据已提交。02:01 真PG单例已证 case_update 的已提交空步骤恢复失败：新lease同epoch取得后在 AgentSnapshotStore._load→reconcile_versions:64 抛 RevisionConflict，尚未请求末模型。原case、mutation收据和core_operations都真实存在。该缺陷已交主代理，未改业务或旧断言。

memory_update 的真实更正与 case_update 不同：既有 test_self_adopted_old_fact_uses_existing_stale_contract 要求旧run stale。主代理02:01裁定保留该安全语义，另验敏感更正proposal可同epoch，不用proposal替代真实更正。

07:28 续作保留原失败记录，没有把额度空档当作工作进度。并行 ToolBatch.accept 新增确认事务后，原夹具“当前连接为空”是假设过细；改为独立 pool 连接、不取 owner advisory lock，非锁 SELECT 已可见的实际 mutation、实体和 operation，证明业务效果确已提交。新 accept 在 Journal.complete 前的全依赖 poll 也使正常自写与真实更正回归，由该片代理移除；原 Journal.complete/_register 事务身份与撤销闸门仍保留。本片既不伪造模型账本，也不放宽缺账本的待确认效果证明。

## Decision Log

2026-10-21 01:59：主代理确认02:00全量来自固定 git archive，不会收集本片在途文件；本片仍等 M8 测试结束释放窄位。若发现缺陷，只认可同 run/epoch/seq、同工具输入的真实持久 mutation 收据；不能遍扫 owner 变化当成自写。这是后续修复约束，本片不实施源码修复。

2026-10-21 02:01：主代理纠正本片内部统一同epoch目标，真实更正保 stale；原 completed_step 篡改反例必须保留。真实待确认窗口应具备 started/空output/空finished_at，与将已完成步骤改回started但仍保留output的篡改状态区别处理。case_update失败保持严格断言，先验证其它工具。

2026-10-21 07:28：主代理批准只为 case_update 加早期自写证明。只接收本 epoch 尾部 started、空 output/finished_at/usage/error 的真实步骤；由已完成 primary model 的原 tool_calls 连续序号、私有 RequestLedger 原请求与来源版本、正规化 args 的 tool input_fp 与 mutation fingerprint 交叉验证。saved 收据必须绑定已选择 case、当前 revision=expected+1、实际字段与逐字来源 ref；精确 core_operation 身份、种类、结果 ID、事务时间与当前 revision 构成因果链。旧 core_operation digest 覆盖不可逆推出的旧完整 payload，仅核形状，不能宣称重算内容等价。

2026-10-21 07:33：Snapshot 只在原身份、依赖、来源、撤销和私密指纹验证全部通过后，在原事务采纳准确新 revision 到 run dependencies；原冻结快照字节与 Journal.started 不变，由原 Registry 重放实际 mutation 收据后正常确认。取消、旧 epoch、外部二次修订、缺模型/账本、read-only 借收据和伪造字段/refs/subject 全拒。真实 memory_update 不进入该特例。

## Outcomes & Retrospective

02:04 第一片 8 passed、1 deselected / 7.37 秒与 case_update 独立 1 failed / 1.68 秒仍保留。07:33 修复后组合为 41 passed / 20.32 秒；其中原矩阵 9 项全部通过，真实更正 stale 与敏感提议分开，新增 25 项证明检查包含 24 项拒绝反例和 1 项“只采纳依赖、不伪造确认”正例。原 own_revisions 7 项全部通过，旧 completed_step/operation/mutation_receipt 拒绝断言未改。首次组合的范围外 subject 夹具先被 PG 外键拒绝，补建真实范围外 subject 后仍由原 Snapshot 范围校验拒绝；没有将夹具错误计作安全通过。

没有宽回归、真实请求、部署或他线源码修改。本矩阵不能替代来源撤销后的清洁 epoch 设计，测试的是相同仍有效来源下本工具的已发生副作用；tarot_start 尚未补入，不能宣称全部可写工具覆盖完成。

07:34 对最小接点另做 Snapshot、Runtime recovery、Journal recovery 和 case versions 四文件回归，47 passed / 17.16 秒。新增 helper 269 行、最长函数 40 行；新增测试及支持各不超过 219 行、最长函数 52 行，单行不超过 120。它们与 41 项组合是两个分别运行的窄测试集，不冒称固定提交全量。

## Plan of Work

用真实 MemoryService 准备合成原话、已有 fact/case；实际 Runtime 模型请求提出工具意图。目标 complete 的 output 来自实际工具，崩溃前后独立读取 mutation receipt、实体版本/内容、source refs 与 core_operations。通过直接使旧 lease 到期并 claim 新 lease 恢复，既有首模型步骤必须重放，只产生最后一条新的脚本模型响应。

## Concrete Steps

在隔离 CORE_TEST_DSN、清凭据/禁追踪、主代理分配一个测试位后：

    python -m pytest tests/v4/agent/test_tool_effect_recovery_matrix_pg.py -q

先以 case_update 或 memory_update 的单个参数实例运行。失败保留精确断言/栈，其他工具继续独立验证；绝不把失败标记 xfail 或在夹具中篡改 journal/state_version。

## Validation and Acceptance

补强 P3 的 X03 幂等崩溃窗口与 M/R 类真实工具效果，不修改原脚本断言。目标实体及所有相关业务实体在崩溃后到恢复后逐字段一致；原 mutation 的 stable request_key、receipt 和 operation 集合不变；工具步骤仍是同 epoch/seq/input_fp，完成后输出等于崩溃点的真实 output。原 source 完整且一个 assistant final；没有重复工具物理副作用。

## Idempotence and Recovery

测试只生成独立 fixture schema，最后由现有夹具清理。注入只触发一次 SystemExit，未确认步骤保持 started。只更新租约到期，不清 step/snapshot/receipt、不改 retry_epoch、不删除/伪造实际业务结果。执行失败整体保留证据并交主代理处理。

## Artifacts and Notes

预定证据：`docs/v4/evidence/P3/2026-10-21-tool-effect-recovery.md`。已知业务源码由其他代理持续修改，本片不覆盖它们。

## Interfaces and Dependencies

新增 `application/agent_pending_effects.py:pending_case_receipts(repo, run)`，仅返回经本轮真实证据证明的当前 case 收据，不写 Journal。`agent_commit_versions.py` 将此证明纳入原自写检查；`agent_snapshots.py` 在完整验证通过后原子保存已采纳依赖。新增测试与支持复用已有 fixture 和离线 Port；不新增外部依赖、迁移或运行配置。

## 修订记录

- 2026-10-21 01:59 建立实际副作用窗口和待验证边界，尚未执行测试。
- 2026-10-21 02:01 记录case_update真实失败；按既有领域契约单列memory_update stale安全分支和proposal恢复分支。
- 2026-10-21 02:04 记录 8 分支真实 PG 通过及 case_update 独立失败，先冻结有明确边界的小片，等待业务修复再完整复验。
- 2026-10-21 07:33 按主代理批准实现最小 case_update 待确认效果证明；记录夹具独立连接改进、并行片交叉回归与 41 项窄组通过，保留原失败和未覆盖塔罗。
- 2026-10-21 07:34 记录 47 项相关窄回归通过，冻结 8 文件；没有扩展真实模型、服务器或发布权限。
