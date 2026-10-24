# P5 敏感确认与单值槽组合撤销

2026-10-24T03:29:36.231765+08:00

入口是 `MemoryConfirmedSlotService(memory).accept(owner, subject, proposal_id, old_id, slot=..., expected_proposal_revision=..., expected_old_revision=..., message_id=..., remember_category=..., operation_id=...)`。这是内部应用入口，复用真实 `MemoryProposalService.accept` 和 `MemorySlotUpdateService.update`；一次事务内保存已确认新事实并关闭旧值。旧值须在新类别授权产生之前就有合法来源，不能用新授权洗白旧敏感记录。更新失败会同时回滚提案、事实、凭据、设置、操作记录及 owner 修订。

返回 body-free receipt：`fact_id`/`revision` 指新事实，`ids[0]` 是槽变更、`ids[1]` 是原 P3 提案，`context_revision` 在此内部入口中仅指槽变更修订，不能冒充 Agent 上下文 generation 或运行提交证明。仓储 mutation receipt 白名单未放宽。

组合撤销入口为 `MemoryConfirmedSlotUndoService(memory).undo(owner, subject, change_id, expected_revision=receipt.context_revision, message_id=..., operation_id=...)`。认证用户需要明确说“撤销这次记忆更新和确认”；单说撤销更新不能自动撤销敏感授权。原话必须属于长期记忆线程、晚于该次实际变更且不在未来；同一动作只绑定同一变更/操作。

撤销先验证当前 old/new 修订、双向更新链、提案、敏感确认及原始范围；恢复原 pending 的来源结构后，复用槽撤销来逐字段还原旧值，退役新值，撤销该次类别授权，退役后来依赖此授权的事实并使派生内容失效。仅还原两个记忆设置键，不覆盖其他设置。审计版本继续递增。新的重放守卫只有 ID/修订，来源或事实再失效会清除此守卫；不额外复制敏感快照。撤销结果 `ids` 依次为退役新事实、恢复的 P3 提案、撤销的 consent、内部结果守卫；不应在用户卡片展示此数组。

需要主线配合：认证确认/撤销路由接入这两个入口；真实工具/提交门若支持 updated，应单独提供严格证明映射。本片不改这些跨所有权路径，也未让 KU01/KU02 通过。已有先分两次调用普通 accept/update 的变更不自动提升为“组合”授权；组合服务只消费自己创建并绑定的变更。

验证：相关 54 passed；补守卫后新文件 22 passed；新增未来确认及正向受影响分支 3 passed，范围重叠。首次新实现违反仓储回执白名单、测试错 API/覆盖参数的失败已如实修复，没有改旧仓储/隐私/提交规则。此前指定记忆场景为 34/37，本片未重复该套或全仓测试，仍未就绪。
