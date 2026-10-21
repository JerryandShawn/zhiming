# 夜M2第一批七工具：应用与PG子切片回执

分支v4/p3-agent-runtime，Draft PR #8。本切片没有接入完整AgentLoop/API，**U4统一解析未交付，因此完整夜M2仍未完成**。真实模型/服务器/飞书操作均0。

## 完成了什么

- time_context、calendar_lookup、memory_search、memory_write、memory_forget、note_write、profile_get七工具，Pydantic严格参数、扁平schema、固定注册顺序及中文适用/副作用/约束描述。危机只time/search，无痕不暴露长期写入。
- 真实PG lease/epoch/cancel/deadline/subject/thread/持久选中case核验；当前写入来源必须是run.request.source_message_id。模型不能替换来源、owner、事项或operation_id。规范化参数补默认后与来源版本共同生成步骤指纹，首次执行即拒绝换参，不能等缓存回执形成后才防重放。
- v4普通goal/background等默认保存由真实MemoryService授权包装实现，v3原行为不变；原话区间、拒存、假设/他人/密钥规则仍由程序验证。敏感只建真实proposal；出生资料转资料确认请求。note明确inferred并绑血缘；forget走真实撤销闭包。所有副作用带稳定operation，持久回执只含标识/状态。
- 读路径补齐事项投影与source_ids/source_refs校验、失效profile重建、消息字段白名单；不返回原始search_tokens，部分撤销不能借它泄漏。来源跨人物/无痕/未选事项、失效版本或撤销区间时不进入工具结果。
- U4薄适配只调用注入的resolve(text,said_at,timezone)。真实来源said_at/时区、event_at、原说法分开保存；跨日重放不重算，歧义/冲突/显式事件缺parser返回needs_confirmation。没有写第二份日期词表。

## 验证

P2 Core Python3.11，本机隔离PG15；每用例独立p2_test_* schema，清所有provider凭据、tracing=false并禁止HTTP。最终：

```text
pytest tests/v4/agent/test_tool_reads_privacy_pg.py tests/v4/agent/test_toolkit_pg.py tests/v4/agent/test_toolkit_contracts.py tests/v4/agent/test_journal_pg.py tests/v4/test_p2_memory_policy.py tests/v4/test_p2_privacy_closure.py -q --tb=short
136 passed in 17.84s
ruff check --select E,F,I,B,UP,SIM --line-length 120 <本切片Python>
ruff format --check --line-length 120 <本切片Python>
```

136包含首批工具41、新增读取/首次执行参数篡改/默认参数等价等隐私8、相关旧契约87。新源均≤400行、函数≤60行、行≤120。测试替身仅日期解析器与HTTP拒绝器；MemoryService/PG/历法/撤销/mutation_request为真实实现。注入解析器正例仅证明接线，不是日期理解准确率或U4≥20正反例。

## 审查修正与限制

根代理与独立同伴审查在提交前发现并修正：未选case消息/派生检索、失效profile字典、ctx.case_ids扩大持久scope，以及首次执行参数未绑定step.input_fp。旧测试行为断言保留；只将本夜新Harness改为规范化指纹协议以真实检验输入绑定。

U4正反各20、统一parser/date_calc/parse_time_range未完成；普通goal若含未显式声明的相对日期，当前无可靠程序识别，不能当U4完成或启用真实v4。搜索每kind最多100候选后按事件/来源日期过滤，可能漏更旧命中；同文本第二处原话区间保守拒绝。撤销UI/独立undo API、完整Loop、第二批工具与正式v4全脚本尚未交付。发布后CI以精确提交结果单独记录；新增迁移0。

回滚：撤回本切片即可；v3默认路由和线上未切换。后续在现有应用边界接Loop、模块日期解析和第二批工具，不绕开原话/租约/隐私限制。
