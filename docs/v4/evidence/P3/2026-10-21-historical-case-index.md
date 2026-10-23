# P3 历史事项索引：只读引用修复回执

2026-10-21 07:42，北京时间。本机候选，root统一提交。没有服务器、真实模型、飞书、迁移或分支合并；冻结core4/SSE Schema未改。

## 问题与设计来源

case_list实际查询包括未删除的done/archived历史事项，返回标题/状态/修订；真实completed步骤与当前PG投影已由case_index_lineage证明并注册e#。Finalizer却对所有实体统一只接受active/open/pending，因此历史索引在最终提交失败。

28号主线储备c仅写“case_list缺口”、Z3约束暴露；33号一§1要求P3收尾。两文没有done/archived字面裁定，本修复依据是既有只读索引与最终提交门不一致。主线root明确确认只修这两种历史状态的精确索引引用，不扩公开信封、正文披露或事项写权。原07号R08仍保持原场景和评分，本片是其历史回顾边界的附加PG用例。

## 完成的行为

新增`application/agent_case_index_citations.py`。只有同owner、当前run/epoch、实际completed且无error、有finished_at的case_list指定步骤，才会复用原case_index_lineage再次核完整当前标题/状态投影，并精确匹配alias的来源元数据、实体身份、修订和投影hash。`index_only=1`不能冒充布尔True；普通字典自报basis、错误步骤或无关saved回执不构成授权。

Finalizer只增加helper导入与4行状态门变动。原owner/subject、依赖、当前原话、修订、撤销、租约和取消门均保持；其他实体及closed/paused/stopped/superseded状态仍按旧规则拒绝。done/archived只允许已核索引标题/状态引用，未选事项的goal、来源原话、事件不进模型，request.case_ids也不扩展；case_update仍拒绝未选事项。

相同索引重复读取时沿用最早已核e#。helper查询alias对应的真实步骤seq，而不是用最新相同输出的seq覆盖旧来源；重新核当前完整投影不等于重写历史证明。

## 真实本机验证

回环PG `127.0.0.1:55480/core_test_main`，每测试独立schema，TZ=Asia/Tokyo且业务时钟显式冻结。执行前清供应商密钥、禁LangSmith/LangChain/OTel追踪，使用ScriptedPort，HTTP/子进程拒绝夹具保留；单个pytest进程，未跑整库。

修前首先运行3条真实Runtime路径：**2 failed / 1 passed，2.74秒**。open对照成功，done/archived均精确在AgentFinalizer._aliases抛ScopeError，查询、Journal完成和登记先已发生。修后同3条原断言**3 passed / 2.58秒**。

新安全负例首轮4处夹具失败分别为无合法FK的外owner/人物安排及SQL.format花括号；只修新测试准备，没有放宽产品或反例断言。随后原索引/Finalizer组合**58 passed / 20.23秒**；再补两条重复历史读取的完整Runtime正例，最终：

    python -m pytest tests/v4/agent/test_historical_case_index_pg.py \
      tests/v4/agent/test_historical_case_index_guards_pg.py \
      tests/v4/agent/test_case_index_lineage_pg.py \
      tests/v4/agent/test_agent_finalization_pg.py -q --tb=short

**60 passed / 21.35秒，0skip、0warning。** 60包含34个本片新例及原26例；不同轮结果不相加。

新例包含真实case_list→Journal→alias→Runtime/Finalizer的open/done/archived引用、未选历史case写拒绝、重复查询稳定alias；以及basis/index_only/run/epoch/seq/hash/revision篡改、缺失/started/error/错工具/旧epoch/外owner步骤、损坏输出或投影、行修订/删除/撤销/跨人物、其他case状态与非case实体拒绝。所有拒绝不留assistant或result。原私密、撤销来源、跨owner、索引伪造等26例继续绿。

Ruff E,F,I,B,UP,SIM与120格式通过；最大文件195行、函数54行、单行120字符。没有新增依赖、工具参数、迁移或冻结评测文件修改。

## 文件身份

以下SHA256以规范LF计；最终提交号由root发布。

| 文件 | 行数 | LF SHA256 |
| --- | ---: | --- |
| application/agent_case_index_citations.py | 58 | 3a7d166f200e851b279052df03dd436326627a24e11a44c547a8e8d7daec0c33 |
| application/agent_finalization.py | 195 | f382f1f37acafef371cf15355425234ebcea7a4f14879166a0c6c1885714e99f |
| tests/v4/agent/test_historical_case_index_pg.py | 129 | 40ce3bf11c2f74187d6e0e0ee6382b6a9deb28f24c3df57673ab32f61d8dda8a |
| tests/v4/agent/test_historical_case_index_guards_pg.py | 151 | 9e330b9f74a111b216af603e557ef010fa25dd6536e0ce7eb54bf362996954c4 |

## 未验证与回退

这不是全库、Linux、真实模型质量、网页/飞书或生产验收。closed/paused等其他状态没有被扩展；若需要另立明确状态与披露策略。精确投影在提交前改变则继续拒绝，不能引用旧索引。移除Finalizer委托即可回退，历史行状态、正文及数据库结构不变。待root提交后在合法窗口固定tree回归。
