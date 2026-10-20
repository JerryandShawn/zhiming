# P3：组件测试按真实同线程串行契约收尾

本 ExecPlan 遵循.agent/PLANS.md。复用真实PostgresRepository.fail_run/claim_run、Journal、MemoryService撤销/重导保护；不得修改生产claim、容量或串行规则。只改tests/v4/agent/中明确归属的组件fixture/调用方及证据，root统一提交。

## Purpose / Big Picture

M7已规定同owner/thread运行串行，旧组件测试在同一个schema中连续setup却保留旧run running，导致01:00固定76c62b8快照42fail里的串行失败。测试应在完成当前组件所保护的行为后显式结束该run，再开始下一轮；需要真正并行的Journal用合法不同人物线程。不得扫描或自动终止其他测试run来掩盖错误。

## Progress

- [x] (2026-10-21 01:09 +08:00) 对照固定v4.log完整42fail清单，完整读6个直接文件和必要调用方，向root报范围并获确认。
- [x] (2026-10-21 01:19 +08:00) Toolkit/ContextUsage/Feedback顺序组件显式结束各自run，Journal真实不同线程；保留Journal重放在运行态。
- [x] (2026-10-21 01:19 +08:00) U7第二run同线程拒claim且保持queued，首轮结束后复查同deck不洗牌；其余顺序调用显式finish。
- [x] (2026-10-21 01:19 +08:00) 12文件完整组件目标138 passed/40.24s、0skip/warning；原42fail中41个nodeid覆盖通过，M04归root另测；静态/证据后冻结。

## Surprises & Discoveries

Toolkit.setup是多个工具测试共享函数，不能在setup里宽扫running或自动结束上个run；需要显式Harness.finish和每个调用点。ContextUsage.record与Journal重放需要仍有效lease，不能在completed helper提前结束。反馈helper循环用真实工具完成但未走最终Runtime，收尾是cancelled组件运行，不是伪造成功core4对话。

## Decision Log

Harness.finish只对self.run和其原lease调用真实fail_run(status=cancelled)，assert真实terminal/result为空；不造final，不全局扫。需要多轮的测试在上轮组件断言后明确调用。旧note撤销负例不能仅因旧lease已取消而变绿，因此另加MemoryService对同撤销原话重导必须真实拒绝，保留撤销而非只有租约保护。

原并发塔罗测试允许两个同life线程run同时running，已与M7合同冲突；改为第二run真实queued、claim抛LeaseConflict且不产生牌，再首run执行/结束、第二run取得lease并命中原deck，仍只一副牌。保持24h、明确强制重抽、取消不绕过、固定牌面/身份/撤销所有既有断言。Journal独立run序号测试使用同owner两个真实授权subject的life线程，仍同时running并可重放各自日志，不在terminal重放旧工具。

## Outcomes & Retrospective

完整目标138 passed/40.24s，10个测试文件改动，未修改生产claim或容量/串行逻辑。原42fail清单中的41个case在本12目标文件中通过；其中chart计算相关通过依赖root已修真实生产事务问题，不能冒认本片修生产。v3 M04不在本片目标，由root单独修复验证。没有真实外部调用/部署/合并。

## Context and Orientation

独占test_toolkit_pg、test_context_usage_pg、test_journal_pg、test_loop_cycle_case_versions_pg、test_tool_tarot_pg，以及必要调用方test_tool_case_privacy_pg、test_tool_interactions_pg、test_tool_tarot_bounds_pg、test_tool_visibility_pg、test_computation_wiring_pg。test_loop_cycle_own_revisions_pg与test_tool_self_revision_pg的fixture复用反馈helper，预期无需改断言。固定原log在任务目录private/regression-20261021-0100-76c62b8/v4.log，只读，不改历史结果。

## Plan of Work

先按测试持有的真实run提供显式收尾，再逐个顺序调用点接线。真正并行序号场景区分真实thread，真正同线程争用场景保留拒绝和后续执行。最后跑归属测试目标并对原42fail中相关case ID逐个核对，记录root另外两类而不冒认已修。

## Concrete Steps

    python -m pytest -q tests/v4/agent/test_toolkit_pg.py tests/v4/agent/test_context_usage_pg.py tests/v4/agent/test_journal_pg.py tests/v4/agent/test_loop_cycle_case_versions_pg.py tests/v4/agent/test_loop_cycle_own_revisions_pg.py tests/v4/agent/test_tool_tarot_pg.py

仅本机隔离PG15独立schema、真实业务/替身外部I/O；单个测试进程并清凭据/关追踪。完成上述第一片后补所有必要调用方目标。

## Validation and Acceptance

原串行错误消失，同线程两个有效lease依旧不可得；第二queued不丢、不先抽牌，前run结束后二次同题不洗牌。Journal重放、计量连续3次提醒/幂等、工具原话/撤销/固定牌面与各scope断言全保留；note撤销leaf重导负例不靠terminal lease产生假绿。

## Idempotence and Recovery

测试schema可丢弃但生产串行不动；明确收尾只作用指定run。没有迁移/依赖或服务器操作，root自行决定下一次固定头整库回归并按整点00–15启动。

## Artifacts and Notes

证据docs/v4/evidence/P3/2026-10-21-serial-test-harness.md，含原42个nodeid逐项映射。10改动测试文件均小于400行、函数≤60；Ruff E/F/I/B/UP/SIM 120列绿，9文件format120列绿。test_tool_visibility_pg原为88列布局，保留原格式只改.finish一行，format88列绿，避免无意义整体重排。

## Interfaces and Dependencies

Harness.finish()->真实terminal，setup(...,claim=False)只在测试中保留真实queued run，任何tool执行仍需后续repo.claim_run提供有效lease。无生产接口变化。

## 修订记录

- 2026-10-21 01:09 +08:00 创建，记录42fail分类、测试行为保护与root确认范围。
- 2026-10-21 01:19 +08:00 138目标通过并映射原41失败；冻结10测试文件和2文档，生产代码未动。
