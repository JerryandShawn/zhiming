# P3 合并原话撤销后干净epoch：组件证据

2026-10-21 01:05 +08:00（Asia/Shanghai），工作树C:/Users/Administrator/Documents/Codex/zhiming-v4，分支v4/p3-agent-runtime。本片只改application/agent_regeneration.py、新test_merged_regeneration_pg.py及本证据/ExecPlan；未改Loop、Context、Finalizer、Runtime或撤销清理代码。没有服务器/真实模型/飞书发送/合并/自主提交。

## 实现边界

真实撤销清空PG run.request和私密快照后，不能信caller旧request即恢复。restart先在owner事务锁实际run，核原队列fingerprint绑定的base request，再核core_operations中thread-inbox创建操作的精确初始source IDs/区间元数据指纹；即使对应实体已经删除，fingerprint不会包含或恢复原话正文。实际正文始终从当前有效PG message重读。

最多64条初始合并原话中，只有账本确证撤销的辅助可剔除；有效来源仍须人物、线程、角色/current_user、run_context、版本、完整区间和顺序完全匹配。primary整条/局部撤销均终止，不拿更晚补充偷换问题；非撤销修改不泛清版本。原epoch一次/租约hash/截止/cancel闸门全部保留，旧源/草稿/别名/旧adoption不带入新epoch。

旧epoch已采用的Inbox不搬进initial source列表。被撤销的补充不会恢复；仍有效补充不再被旧adoption授权，在parent新epoch提交后恢复fallback下一轮queued。私密和其他复杂输入仍保守拒绝自动重生成，此处不是完整复杂输入支持。

局部撤销的message仍可在新Context中以既有分段撤销投影作为历史（source ID可相同），但不能带撤销正文/旧fact alias，亦不再属于本轮可写initial sources。整条撤销则该message、旧fact均无新alias。没有修改Context的既有历史投影契约。

## 已运行目标

隔离PG15：127.0.0.1:55480/core_test_main，独立schema。已锁定Core测试环境、UTC冻结Clock，测试进程清供应商/追踪凭据且关LangSmith追踪；仅ScriptedPort外部替身，业务/事务/Journal/RequestLedger/撤销与Finalizer真实。

    python -m pytest -q tests/v4/agent/test_merged_regeneration_pg.py tests/v4/agent/test_agent_runtime_recovery_pg.py tests/v4/agent/test_thread_inbox_runtime_pg.py

最终结果（2026-10-21 01:09 +08:00）：**20 passed / 9.17s，0skip、0warning**。11个新增真实PG场景、旧恢复7项、既有Inbox Runtime2项。

新增覆盖：辅助整条/片段撤销→两次物理脚本模型请求、一清洁epoch、精确保留有效source/segment、无旧稿/撤销正文；primary整条/片段撤销无新epoch/无final；取消并撤销辅助仍不能重生；PG已清请求时caller篡改源列表拒绝；非撤销版本变化不能靠重绑掩盖；已真实adopted补充撤销/仍有效两种情况→三次脚本请求，新epoch不复用旧adoption，仍有效补充fallback排队。

首轮扩展18 passed/11.02s后，另增source_range/primary_text指纹反例；root临时借用slot定位宽回归时没有启动新测试，释放后已复验上述最终20项。Ruff/format和AST函数≤60检查通过；没有新依赖、表或迁移。修复时保留合法旧v4行thread_id=NULL的life兼容，不把空值当私密字符串调用。

## 已知边界

没有真实供应商/CI/全量回归证据，不代表完整P3验收。私密复杂输入仍拒绝自动恢复；不能重建>64条初始合并源，不盲迁移时间更晚的旧Inbox采用。目标仅恢复当前PG仍有效、最初入队已被真实指纹绑定的原话，不从被清理的模型快照复原正文。
