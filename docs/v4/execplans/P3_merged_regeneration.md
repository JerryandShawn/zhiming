# P3：合并原话撤销后只生成一次干净批次

本 ExecPlan 遵循 .agent/PLANS.md。复用 application/agent_regeneration.py 的一次epoch/受信executor租约校验、MemoryService.get_source/retire_fact、thread_sources.ingress_sources/source_segments、repo.prepare_retry/claim_run与core_operations仅指纹凭据；不得改变Loop、Context、Finalizer、撤销清正文或已取消不可恢复的契约。工作树C:/Users/Administrator/Documents/Codex/zhiming-v4，分支v4/p3-agent-runtime；本片只改regenerator与新测试/证据。

## Purpose / Big Picture

飞书合并与Inbox接入后，普通请求带source_message_ids/source_segments；原Regenerator不接受这些键，导致辅助原话撤销后无法按P3 M6重生成一次。干净epoch表示重新从有效原话/资料建Context与别名，不能复用撤销正文、旧模型稿或旧Inbox采用授权。primary（主问题，即有序合并列表最后一条）整条或局部撤销必须终止，不能拿另一条偷换问题。

## Progress

- [x] (2026-10-21 01:00 +08:00) 读完整Regenerator/Runtime/ThreadSources/Inbox及真实撤销清理调用方，确认PG请求与快照会被清空，不能直接信caller旧request。
- [x] (2026-10-21 01:05 +08:00) PG持久指纹核对原请求和初始合并源元数据；只剔除有真实撤销账本的辅助源，有效源版本不泛重置。
- [x] (2026-10-21 01:05 +08:00) 真实Runtime辅助/已adopted补充撤销、primary/取消/篡改/非撤销版本变化及旧恢复/Inbox目标18 passed/11.02s。
- [x] (2026-10-21 01:09 +08:00) root释放slot后含区间/主问题正文指纹反例最终20 passed/9.17s，证据冻结交root统一提交。

## Surprises & Discoveries

真实撤销会清core_runs.request={}、runtime快照和命中的request实体；保留的core_operations只有指纹和实体ID。原队列digest绑定base request，thread-inbox创建操作的指纹绑定初始source IDs/精确区间，能证明候选原元数据而无需恢复已删正文；有效正文仍重新读PG。

首14目标12通过/2失败：局部撤销保留当前投影历史的message alias，不能把它当作整条删除；另一测试将用于撤销的背景源放在primary之后，初始边界未采用，_related正确不触发。修正新测试符合现存历史投影/边界契约后14通过，再扩真实旧adoption边界得18通过，没有改Context或放宽Regenerator。

## Decision Log

root裁定先支持最多64条初始合并源重建，保留原primary最后顺序；不把更晚的旧epoch adopted补充直接塞进initial source_message_ids偷换边界。旧Inbox adoption不迁移，仍有效补充按fallback下一轮处理；私密、复杂输入维持保守拒绝。辅助局部撤销也整条退出本轮initial来源，Context历史只可通过既有撤销投影读取未撤销部分。

新正例初稿把任何被局部撤销source ID出现在新alias都当作失败，这比旧 memory/threads.py:project_sources 的分段撤销投影契约更严；改成整条撤销必须完全无该message alias，局部仅允许当前投影历史alias，不得含已撤销正文、旧fact alias或复用旧模型草稿。新epoch仍不把该源纳入可写initial source IDs，不能靠历史alias再获工具写授权。此为更正新测试的契约解释，不删除既有保护。

## Outcomes & Retrospective

最终真实PG目标20 passed/9.17s，包含两次/三次真实ScriptedRuntime模型请求的清洁重生成。新增区间和主问题正文指纹反例已通过；不宣称完整P3/CI或所有复杂私密输入支持。

## Plan of Work

restart先在owner事务锁PG当前run，用原队列fingerprint核base request，再核thread-inbox创建操作的精确元数据fingerprint。primary当前PG原话与ledger有效后，逐项初始源检查scope/区间；仅账本确证撤销的辅助可剔除，其他版本变化失败关闭。写新request后使用原prepare_retry开一次epoch，旧步骤输出照常清空。

## Concrete Steps

    python -m pytest -q tests/v4/agent/test_merged_regeneration_pg.py tests/v4/agent/test_agent_runtime_recovery_pg.py

仅本机隔离PG15、独立schema、UTC冻结Clock与脚本模型，进程清供应商凭据并关追踪；单个窄目标进程。

## Validation and Acceptance

对P3 M6及评测撤销类契约：真实Runtime第一次调用期间撤销非primary原话，随后只第二次模型调用发布新答，request精确保留有效source/segment，无撤销正文或旧别名ID；主问题整条/片段撤销不发布；取消与相关撤销不能借restart逃过。旧caller篡改合并列表、区间、scope或未被撤销的版本变化失败关闭，PG已清请求不能成为跳过原始授权的理由。

## Idempotence and Recovery

一次regen仍要求retry_epoch=0、executor lease hash、无cancel/未过期，使用PG事务原子写request/usage/retry/claim。主源失效、未知键、旧adoption或复杂私密输入不恢复；不新增迁移、依赖、远端操作。root统一提交推送。

## Artifacts and Notes

证据docs/v4/evidence/P3/2026-10-21-merged-regeneration.md。源/测试Ruff/format和函数长度检查通过；未改任何生产并发规则或数据清理代码。

## Interfaces and Dependencies

保留AgentRegenerator.restart(original,frozen)和RuntimePort外部接口。新增内部PG候选请求证明与辅助源筛选，不允许HTTP或模型直接指定新源，也不从撤销的旧body重建正文。

## 修订记录

- 2026-10-21 01:00 +08:00 建独立修复计划，原证明边界与root裁定先记录。
- 2026-10-21 01:05 +08:00 实现并验证18项目标，记录局部撤销历史投影/旧adoption边界；测试slot让给root定位宽回归。
- 2026-10-21 01:09 +08:00 slot释放后最终20通过，冻结4文件交root提交。
