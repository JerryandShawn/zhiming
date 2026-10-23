# P3 case_list 索引引用证明

2026-10-21 01:30 +08:00（Asia/Shanghai），工作树C:/Users/Administrator/Documents/Codex/zhiming-v4，分支v4/p3-agent-runtime。只改Loop codec、新case index证明helper/测试及ExecPlan；不改Runtime/Finalizer/Context、P8/charts/skills/knowledge。没有真实外部请求、服务器、飞书、部署或合并。

## 已实现

case_list成功结果必须精确匹配当前run/epoch已完成工具步骤，并重查同owner/subject的PG index(title/status/revision/最多100)。证明仅附真实kind=case和真实ID/revision，basis=case_index/index_only是元数据，不是新实体kind。Loop登记exact entity:case版本和e别名，工具消息只投影受证别名，清掉工具data自报别名字段。

未选case仅索引可读；不顺着_source_links扩其目标或用户原话，不能把已读ID变成case_update/case_add_event权限。真实Runtime三次脚本模型调用：case_list→尝试修改未选case→引用e1发布；第二工具AUTH_SCOPE_ERROR，case PG revision不变，used_fact_ids/used_claim_ids均空、run.case_ids仍空。索引被引用不等于用户事实或专业象征声明。

重复同结果工具步骤可真实存在，按当前epoch最新匹配步骤复核，不重复分配e别名/不新建case。跨owner、旧epoch、篡改title/revision/id/专业persisted字段、自报别名、case已删/版本改变都拒。private Registry先拒tool_unavailable且无alias；绕过Registry的真实应用只读结果也不能通过private proof注册。真实MemoryService撤销来源会清事项目标/source_refs并提升revision、保留case ID；旧index必须失效重查，不改隐私清理行为。

## 验证

隔离PG15 127.0.0.1:55480/core_test_main、独立schema，已锁定Core环境，测试进程清模型/追踪凭据并关闭LangSmith。业务、事务、Journal、撤销和Finalizer真实，只有模型使用ScriptedPort。

    python -m pytest -q tests/v4/agent/test_case_index_lineage_pg.py tests/v4/agent/test_computation_wiring_pg.py tests/v4/agent/test_loop_cycle_case_versions_pg.py

**26 passed/8.00s，0skip、0warning**（新增14、旧Chart wiring10/selected-case2）。其中专业c/r原防伪完整保留，case不能借此放宽Chart证明。源/测试Ruff E/F/I/B/UP/SIM与format120列、AST≤60函数、diffcheck均绿。

冻结文件：mingjing_core/agent/loop_codec.py（260行）、mingjing_core/application/agent_case_index_lineage.py（67）、tests/v4/agent/test_case_index_lineage_pg.py（193）、docs/v4/execplans/P3_case_index_lineage.md、本证据；由root统一提交推送。

## 未完成边界

Tarot native draw/reading全血缘转下一片，尚未实现；closed/done/archived事项引用尚未覆盖，Finalizer当前只支持active/open/pending，本片不改。没有全量回归/CI或真实模型证据，不能据此宣称全部P3完成。
