# P3：事项索引引用不扩权

本ExecPlan遵循.agent/PLANS.md。复用真实case_list服务、Journal completed步骤、repo.get/list/versions与Finalizer现有case实体引用；只改agent/loop_codec.py、新application/agent_case_index_lineage.py及测试/文档。case_index是proof标记，实体kind仍case/真实PG ID；不得新造未注册entity kind或放宽事项写授权。

## Purpose / Big Picture

case_list返回索引目前没有被Loop收集为依赖/别名。用户可引用已查的事项标题/状态，但未选事项的正文/目标不能借索引展开，工具可见/已读更不能扩权case_update或case_add_event。先独立完成此小片，再接native tarot全血缘，避免借case或draw放宽c/r专业产物证明。

## Progress

- [x] (2026-10-21 01:20 +08:00) 读完整Loop codec/Chart证明/Case服务/Finalizer结构引用，root确认先case独立片、真实kind=case。
- [x] (2026-10-21 01:30 +08:00) 仅当前run/epoch/lease已完成case_list+PG精确索引才能注册e别名/版本；未选事项不展开source_links。
- [x] (2026-10-21 01:30 +08:00) 新14+旧chart wiring10/selected-case2联合26 passed/8.00s，Ruff/format/AST绿，证据后冻结交root。

## Surprises & Discoveries

case读取与修改共用kind=case，旧_verified_row一律要求selected，因此不能简单往candidates追加ID。新证明只为case_list真实索引旁路这项读取限制，所有case写仍由selected_case和原run.case_ids拒绝；不触Runtime/Finalizer。重复相同read工具可有多个真实completed步骤，证明采用当前epoch最新匹配步骤而不是假定输出唯一。

初轮22/24失败均为新测试契约解释：未选case真实拒绝码AUTH_SCOPE_ERROR而非REFERENCE_ERROR；private Registry已先拒tool_unavailable，故失败工具不再抛lineage异常。改为先证Registry拒绝/无别名，再通过真实application只读返回作防御层证明private仍拒注册。新增真实来源撤销正例时发现既有privacy_cases会保留事项ID并清goal/source_refs、提升revision，测试按此真实契约证明旧index失效，不改隐私代码。

## Decision Log

索引只输出title/status/revision，无目标/原话；未选case不走_source_links，防止把未选事项正文送模型。别名kind=case、附basis=case_index/index_only，现Finalizer/结构引用能按真实实体核版本，不增加事实或命理声明。c/r保持原Chart全证明，case数据不能借附加persisted字段伪造专业别名。

tool_message先移除result.data自行带的registered_aliases/alias_registration，再只投影已受证registry；避免工具文本自报别名伪装已登记。没有修改Chart产物/解释的严格计算证明。closed/done/archived状态的引用尚未验证，现Finalizer只支持active/open/pending；已向root记录该读取契约边界，本片不改Finalizer。

## Outcomes & Retrospective

真实PG目标26 passed/8.00s（新增14+旧chart wiring10+selected-case2），0skip/warning；Runtime索引引用可发布、随后的未选事项修改被AUTH_SCOPE_ERROR拒且PG revision不变。Tarot native draw/reading不在本case小片，尚未完成全血缘，不冒报。

## Context and Orientation

复用agent/loop_codec.py:verified_versions/_verified_row/_source_links/extend_aliases/tool_message；application/agent_tools_cases.py:execute_case/selected_case；application/agent_finalization.py:_aliases；repositories/dependencies.py:entity_dependency。不得改Runtime/Finalizer/Context、P8/charts/skills/knowledge。

## Plan of Work

新helper在同owner事务核当前lease/epoch、拒private、取真实completed case_list精确输出，然后重查PG同subject索引投影。Loop只对这些case ID允许读取索引，版本+e别名随模型工具消息传递；未selected case不扩原话闭包，写权限原样。

## Concrete Steps

    python -m pytest -q tests/v4/agent/test_case_index_lineage_pg.py tests/v4/agent/test_computation_wiring_pg.py tests/v4/agent/test_loop_cycle_case_versions_pg.py

单个测试进程，本机隔离PG15/独立schema，清供应商凭据并关追踪，仅替身外部模型。

## Validation and Acceptance

真实Runtime case_list→e1可引用，随后试写未选case仍拒且PG revision不变；used_fact_ids/used_claim_ids均无该索引。篡改ID/标题/版本/professional字段、跨owner、旧epoch、已撤销或PG版本变化全部拒；重复工具不重分配别名；private拒注册长期事项索引。

## Idempotence and Recovery

只读证明无新实体/表/迁移/依赖；重复取PG最新匹配completed步骤、精确版本不变。root统一提交推送，不部署或合并。

## Artifacts and Notes

证据docs/v4/evidence/P3/2026-10-21-case-index-lineage.md；Loop codec260行、新helper67、新测试193，AST无函数>60，Ruff E/F/I/B/UP/SIM 120列与format/diffcheck绿。

## Interfaces and Dependencies

case_index_lineage(service,run,result)->真实case proof records；kind保持case，basis/index_only仅内部元数据。tool_message只投影已经注册的case_index e别名及原有c/r，不信工具data中的别名声明。

## 修订记录

- 2026-10-21 01:20 +08:00 建独立小片计划，先case再tarot。
- 2026-10-21 01:30 +08:00 26目标通过、真实闭包/权限/私密/撤销证据冻结；Tarot转下一片。
