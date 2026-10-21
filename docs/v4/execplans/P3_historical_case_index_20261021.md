# P3：让已证实的历史事项索引可被只读引用

本ExecPlan遵循`.agent/PLANS.md`。所有时间为北京时间；本机时区可能是东京。此片仅修本机候选，不访问服务器、不发真实模型或飞书、不合并；root统一提交推送。

## Purpose / Big Picture

用户问过去那件事时，case_list已经会返回未删除的历史事项标题和状态，但最终提交却把done/archived统一当作无效引用拒绝。此片让真实本轮case_list证明中的历史索引可以被回答引用。只允许已披露的标题/状态索引，不开放未选择事项的目标、原话、事件或修改权限；冻结core4和事件Schema不变。

## Context and Orientation

28号主线储备c写的是“case_list缺口”，Z3规定该工具在事项上下文或用户提及事项进展时出现；33号一§1要求P3收尾。两文件没有逐字规定done/archived状态，因此本片依据是已实现历史索引与最终提交门不一致，不能将推论伪称大脑的字面裁定。root于2026-10-21 07:38确认仅对真实completed索引中的done/archived做最小修复。

复用`application/agent_tools_cases.py:execute_case`只读索引、`application/agent_case_index_lineage.py:case_index_lineage`的当前owner/subject/epoch/完整投影证明、`agent/loop_codec.py:verified_versions`的引用登记、`application/agent_finalization.py:AgentFinalizer._aliases`的提交门。原case_list返回title/status/revision，不返回goal/source正文；原selected_case写权继续要求request.case_ids。其他实体状态门、当前source核验、租约/取消/撤销与精确修订依赖不得改变。

## Progress

- [x] (2026-10-21 07:38 +08:00) 完整核对28、33及原P3/蓝图；静态定位查询/登记接受历史行而Finalizer统一只收active/open/pending。
- [x] (2026-10-21 07:39 +08:00) 本机隔离PG原实现复现2fail/1pass、2.74秒；done/archived均在Finalizer被ScopeError拒绝，open对照通过。
- [x] (2026-10-21 07:40 +08:00) 新增独立helper，Finalizer仅1个import与状态门4行变动；修后原3目标全部通过2.58秒。
- [x] (2026-10-21 07:42 +08:00) 新正反例及原索引/Finalizer组合60项通过21.35秒，0skip/0warning；Ruff E,F,I,B,UP,SIM、120格式及尺寸绿。冻结6文件交root。
- [ ] root统一提交推送；固定tree全量留08:00窗口，不把本机窄组合冒充整库或部署验收。

## Plan of Work

先新增真实PG测试，使用ScriptedPort触发真实case_list→Journal完成→已核血缘别名→Finalizer，历史状态的预期成功在修前应失败，open对照应成功。工具消息必须只有真实标题/状态索引，不能出现未选择的goal或来源正文。

随后新增`application/agent_case_index_citations.py`，从alias中的步骤序号回查同run/epoch的completed case_list实际输出，复用case_index_lineage重新核当前完整索引与只读证明，再逐字段核alias证明与实际行的身份/版本。Finalizer只在case且done/archived时委托；其他状态与实体继续原规则。不得单凭alias自报basis或一条无关写入回执放行。

## Validation and Acceptance

本片补充07号R08事项进展回顾的历史索引边界，不改原R08或冻结评测场景与分数。可观察行为：done/archived查询成功且回答保留已核e#；目标/原话仍未披露、request.case_ids仍空；同样查询不会授予case_update权。缺步骤、错误run/epoch/seq、投影/alias篡改、修订变化、删除/撤销、跨owner/subject和私密条件都应拒绝且不留下assistant/final。其他实体done/archived仍拒绝。

    python -m pytest tests/v4/agent/test_historical_case_index_pg.py \
      tests/v4/agent/test_case_index_lineage_pg.py tests/v4/agent/test_agent_finalization_pg.py -q --tb=short

测试只使用显式回环隔离PG、冻结时钟、替身模型，并清凭据/关追踪；最多1个pytest进程。不在08:00以前开全库回归。

## Surprises & Discoveries

L3稳定上下文只包含进行中事项，这是现有设计，不需要为历史索引把所有已归档正文加入上下文。done/archived不是现有case_update工具的状态枚举（open/paused/closed），此片也不扩工具参数或变更旧实体状态。

case_index_lineage原本会为相同工具输出选择最新匹配步骤；若同轮重复查询，稳定e#仍绑定最初已完成步骤。新helper先精确核alias指向的实际completed行，再复用完整索引校验，并以实际读取的该行seq比较证明；两条重复读取真实Runtime用例保护此边界，不凭空改写来源。

新负例首轮4处准备错误分别是违反真实FK的外owner/人物安排和SQL.format未转义JSON花括号；仅修新测试安排为有效外owner run/已创建人物及字面转义，原产品反例断言保留。修后先58绿，再补重复读取正例后60绿；历史失败不改写成一直绿。

## Decision Log

2026-10-21 07:38，root确认最小范围：仅当前epoch真实completed case_list精确索引的done/archived允许只读标题/状态引用；不改冻结信封、披露闭包和selected_case写权。closed/paused等其他状态保持原行为，后续若需扩展另有明确审查。

## Idempotence and Recovery

无迁移、回填、外部副作用；证明查询只读且在原Finalizer事务内完成。已有run重放仍复用原Journal与别名，不能为缺失证明补造工具步骤。移除helper委托即可回退，历史数据与状态不变。

## Outcomes & Retrospective

真实PG已复现并修复done/archived索引引用不一致，保留旧状态/其他实体/写权限与披露门。60项窄组合与静态门通过，证据见`docs/v4/evidence/P3/2026-10-21-historical-case-index.md`。未执行真实模型、服务器或全量，尚待root提交发布与固定tree回归。

## 修订记录

2026-10-21 07:38：创建；记录文档原文、已获确认的最小边界与先复现后修复步骤。

2026-10-21 07:42：记录原实现精确红例、最小修复、重复查询稳定证明与60项回归，冻结交root。
