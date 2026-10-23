# P3：固定塔罗效果已提交、确认前退出的恢复

本 ExecPlan 遵循 `.agent/PLANS.md`，记录均为北京时间 UTC+08。

## Purpose / Big Picture

证明真正的 AgentRuntime 请求 tarot_start，固定唯一牌堆及应用 mutation 收据已提交，但 Journal 确认前退出后，旧租约到期可在同 epoch 恢复原牌堆，不再洗牌、抽牌或生成第二个事项。取消运行、取消牌阵、原话及来源区间撤销后，旧运行不能复活该结果。只增加新的测试与证据，发现业务缺口先交主代理审最小修复方案。

## Context and Orientation

复用 `tests/v4/agent/test_agent_runtime_pg.py:invoke`、`test_loop_cycle_support.py:cycle_repo/ScriptedPort`、`tool_effect_recovery_support.py:queued/step_row`。真实业务是 `application/agent_tools_tarot.py:execute_tarot/start_effect`、`agent_tarot_lineage.py:save_tarot_snapshot`、`adapters/tarot.py:TarotService.create_draw`。模型仅为离线脚本替身；PG、应用工具、牌堆与 Journal 都是真实实现。不改已冻结的通用副作用矩阵及旧测试，不改变固定牌、U7 防反复、租约、撤销或秘密牌堆不向模型披露的契约。

## Progress

- [x] (2026-10-21 07:38) 读取塔罗工具、固定牌服务、快照/血缘和已有真实 PG 测试，确定只在完整业务事务可由另一连接看见后注入退出。
- [x] (2026-10-21 07:39) auto/pick 两种真实洗牌模式通过：同 epoch 新租约恢复，固定牌堆、native 请求、原 mutation/operation、事项和来源均不变。
- [x] (2026-10-21 07:39) 运行取消、牌阵取消、来源消息/区间撤销四反例全部通过，零新模型、零额外洗牌或 draw。
- [x] (2026-10-21 07:39) 新测试完整 6 passed / 3.58 秒；Ruff/format/尺寸通过，未发现需要改业务源码的缺口，冻结 3 文件交主代理提交。

## Surprises & Discoveries

tarot_start 的 durable 收据使用 `draw_id`，没有通用实体的 id/revision；固定牌堆存于专用 tarot_draws，不在 core_entities。不能套用通用事实夹具伪造实体回执。本片使用独立真实连接读原 mutation、原 native draw 与 create 请求后再抛 SystemExit。

实际已存在的应用幂等机制足以恢复这两个未揭牌窗口：原 mutation 返回同 draw，原 native create request 与 private_deck 保持不变。没有借新 epoch 绕过原快照或 U7，也没有为测试更换业务实现。

## Decision Log

2026-10-21 07:38：只包裹真实 TarotService._shuffle 计数并调用原实现，不固定假牌或替换洗牌结果。原完整 private_deck 只在隔离测试进程内比较，不写证据或日志；证据仅记录同一性、牌数与唯一性。

## Outcomes & Retrospective

最小 auto 单例先通过 1 项 / 1.57 秒；初次完整 6 项 / 3.63 秒通过，补原 mutation/operation 和完整事项不变断言后，最终 6 项 / 3.58 秒通过。真实洗牌调用每次只一次，真实 PG 私有完整 78 张唯一牌堆在重领前后逐字段一致；原 Journal 输出最终等于崩溃前真实 ToolResult。四个安全操作分支均在请求新模型前拒绝，原牌堆没有被重建。

未改变业务源码，未发真实模型、飞书或服务器请求。覆盖未揭牌 auto/pick 的 tarot_start；不覆盖选牌或揭牌另一个并发窗口、真实供应商、正式 stage 或整库回归。原通用矩阵 8 文件未修改。

## Plan of Work

通过真实 queued 用户原话与运行调用 tarot_start；在 Journal.complete 的目标工具分支第一次执行前，从另一 PG 连接核业务效果与原 mutation 收据均已可见，记录真实 ToolResult 然后退出。只让旧租约到期并同 epoch 重领；恢复首模型步骤后，原 Registry 再执行同工具意图，必须复用原 mutation/native 请求和固定牌堆。对取消与来源撤销分别使用真实应用入口或撤销账本，不能仅标记假结果。

## Concrete Steps

在本机隔离 PG、清空凭据、关闭追踪后，使用一个窄测试进程：

    python -m pytest tests/v4/agent/test_tarot_effect_recovery_pg.py -q --tb=short

运行真实外部请求数必须为 0。若正例失败，保留原断言与栈，不跳过、xfail 或换 epoch。业务修复必须先提交最小设计供主代理决定。

## Validation and Acceptance

对照 P3 的 T 类固定牌、X03 幂等与撤销不复活要求：auto/pick 真实洗牌各发生一次；同一 78 张唯一牌堆、牌背、方向、已选状态和原 draw ID 保持逐字段相同，首业务收据及稳定 operation_id 不变。恢复只产生最后一条脚本模型回应。取消或撤销后不发新模型、不新增 draw/create request、不改回待确认步骤为已完成。

## Idempotence and Recovery

每项使用独立 fixture schema，已存在夹具负责结束时清理；测试只过期 lease，不清快照或日志、不改 retry_epoch。运行/牌阵取消及来源撤销是隔离合成数据的真实安全操作，拒绝后的牌堆状态与其安全操作完成时相同。

## Artifacts and Notes

测试位于 `tests/v4/agent/test_tarot_effect_recovery_pg.py`；证据预定 `docs/v4/evidence/P3/2026-10-21-tarot-effect-recovery.md`。本片不修改原通用矩阵、塔罗业务文件或其他线独占目录。

## Interfaces and Dependencies

只新增测试和本 ExecPlan；复用既有 ScriptedPort、真实 PG 与运行接口，不新增依赖、迁移、公开契约或发布权限。

## 修订记录

- 2026-10-21 07:38 创建独立崩溃窗口计划，尚未执行测试。
- 2026-10-21 07:39 记录两种真实模式与四类安全拒绝 6 项通过，补稳定原收据、operation 和事项不变断言后复验通过，冻结交主代理。
