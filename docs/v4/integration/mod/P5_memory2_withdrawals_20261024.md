# P5 所选记忆/来源撤销接线

MemoryWithdrawalService(memory) 入口：withdraw_fact(owner, subject, fact_id, expected_revision, message_id, operation_id) 与 delete_source(owner, subject, source_id, expected_revision, message_id, operation_id)，后四项为关键字参数。调用方必须是认证用户选中项的路由；选中 ID 不能由模型自授信。

路由需先用当前线程保存真实 web-action 原文。来源按钮原文为“删除这条来源消息”；事实撤销原文为“撤销这条记忆”或其中带具体对象、以“记忆”结尾的同类明确命令。服务不把泛泛讨论删除、助手话语或无痕资料当成授权。相同原话与操作 ID 只能绑定一个目标；动作与目标不能是同一原话。跨 owner/人物/事项、旧版本、早于来源或晚于当前时钟的命令均拒绝。

事实撤销复用 retire_fact 的既有删除/更新链修复。来源删除先撤销所有依赖事实，再删除来源并 invalidate_derived；沿用 on_revoke 清理现有下游，失败回滚。当前 native 状态为 deleted，空审计 tombstone 留存；不是 retired/cancelled 的状态别名。撤销删除不提供复活已忘记正文的入口。

评测接线：MemoryPrivacySeeder 建声明的 native 初始派生层；profile_item 明确映射 profile_doc，embedding 为真实 PG 合成索引，run_event/run_step 来自真实脚本 Runtime 运行。FTS 查询词在删除前冻结，删除后继续查同一组词；不把被删来源解析成空查询。MemoryWithdrawDriver 调实际应用服务，source.deleted/derived.invalidated 只是有真实存储证据的 evaluator-only 观察名。

F01/F03 仍失败：旧验收要求 retired/cancelled 或逻辑实体列表清空；native 存储采用 deleted + 空 tombstone。需要主线/大脑确认统一的展示/验收视图和 fixture id 映射，本线不改评分或伪装状态。F04 已通过真实冻结上下文→并发撤销→一次原生重生成；仅在离线测试模型替身中注入撤销，不改运行循环、提交门、渠道、调度器或真实模型层。
