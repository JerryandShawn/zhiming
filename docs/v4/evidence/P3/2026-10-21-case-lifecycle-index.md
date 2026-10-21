# P3 合法事项生命周期索引：分离目标回执

2026-10-21 07:48，北京时间。root统一提交；无服务器、真实模型、飞书、迁移或合并。

## 完成范围

Case domain契约（domain/contracts.py:Case）定义open/paused/closed/deleted，Agent的CaseChanges也合法接受open/paused/closed。paused/closed是真正事项状态，与run/Agent运行态无关。

此前只读case_list会返回未删除的这些行，而Finalizer只读索引例外只允许额外历史done/archived。此次生产**仅1行**把允许集合扩为paused/closed/done/archived；同owner、run、当前epoch、实际completed case_list、精确步骤seq、当前完整PG投影、alias元数据/版本hash核对全部保持。不扩非case实体状态、L3内容、未选事项正文或case_update写权，不改core4/事件Schema。

## 先发现的独立完整双轮缺口

最初使用两个完整真实Runtime：第一轮已选case通过真实case_update产生paused/closed，saved且rev+1并完成；第二轮未选case查询case_list。两条测试均在第二轮快照构造抛`context_l5_append_only_violation`，尚未到索引提交：**2 failed / 2.53秒**。

精确复现文件`tests/v4/agent/test_case_lifecycle_index_pg.py`，node `test_legally_updated_case_is_citable_by_a_later_read_only_index[paused|closed]`。根因线索为第一轮case绑定原话进入L5，第二轮case_ids=[]按既有授权范围过滤它，同life缓存epoch却未随scope变化新开。原断言与完整路径保留交root修Context；**没有删除反例、清缓存、加入xfail或宣称双轮闭环**。该文件不属于本片4件冻结或下方65项已绿命令，root另管后续修复/纳入。

## 真实组件分离目标

经root确认，独立文件使用真正ToolRegistry→case_update→Journal，原CaseChanges合法参数、当前原话、选中case与版本，实际保存状态且验证saved receipt和rev+1。随后明确cancel组件run，注明“未发布对话或冻结L5”；再新Runtime查询只读case_list并最终引用e#。这隔离了索引状态门，但不是完整两轮产品验收。

修前分离组**2 failed / 3 passed，3.02秒**；paused/closed均精确在Finalizer helper状态门失败，其他实体paused/closed及未知case状态负例通过。生产仅扩两种合法常量后，运行：

    python -m pytest tests/v4/agent/test_case_lifecycle_index_component_pg.py \
      tests/v4/agent/test_historical_case_index_pg.py \
      tests/v4/agent/test_historical_case_index_guards_pg.py \
      tests/v4/agent/test_case_index_lineage_pg.py \
      tests/v4/agent/test_agent_finalization_pg.py -q --tb=short

**65 passed / 17.35秒，0skip、0warning。** 包含本片5例与前片60例，不相加历史不同轮。其他实体paused/closed、未知case状态、新修订/删除/撤销、stopped/superseded、陈旧投影/伪造步骤与未选写权负例保持。旧closed/paused负例是改变真实行却不重新查询索引，仍拒绝陈旧证明，而不是要求合法当前索引永远不可引用。

仅本机回环PG `127.0.0.1:55480/core_test_main`，每例独立schema，TZ=Asia/Tokyo与显式冻结业务时钟；清凭据/禁追踪，脚本模型、HTTP/子进程拒绝夹具，一次1个pytest进程。未执行全库。

Ruff E,F,I,B,UP,SIM、120格式及尺寸检查通过。生产helper58行/最长函数41行，新增组件测试113行/最长函数33行；无新依赖或参数。LF SHA256：

- `application/agent_case_index_citations.py`：b13f0ea7c8b6882b30ae652c7fdda6f8e56600d17902f06b9495839062a629aa。
- `tests/v4/agent/test_case_lifecycle_index_component_pg.py`：e015ea38a5c2ec36093b9eee5e39ac907600fb40d5cd20da2eea06a8888720ce。

## 未完成

完整双轮Runtime的L5 scope切换缺口由root独立处理，另有本轮选中case_update关闭/暂停后引用原e#的独立授权路径待复现审查；本片不借case_list证明解决后者。未跑全库、Linux、真实供应商、网页/渠道或部署验收。回退本片1行状态集合即可，数据不迁移不回填。
