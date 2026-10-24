# 单值槽更新与撤销：应用服务接线说明

2026-10-24 00:22 +08:00。本地服务和相关 PG 检查已实现；memory_write 的可选 slot 参数、冲突提案及 updated 的提交门/外部事件尚未接通，不代表 KU 产品场景通过。

`memory/slots.py` 给出 10 个有限槽位，含 cardinality、识别线索与反例；`normalize_slot(value)` 接受规范名或表内中文名，未知值返回 None。槽必须由模型明确给出，代码不从用户句子偷偷猜槽。临时出差、暂住、代班、试吃、假设/疑问等不能覆盖长期单值槽。该表是保守校验，不是通用语义分类器，也没有向量模型。

服务：

```
MemorySlotUpdateService(memory, clock=...).update(
    owner, subject, old_id, new_id, slot=...,
    expected_old_revision=..., expected_new_revision=..., operation_id=...)

MemorySlotUndoService(memory).undo(
    owner, subject, change_id, expected_revision=...,
    message_id=..., operation_id=...)
```

调用者须在同一个 owner 数据库事务里完成原话校验、敏感提案确认后的新事实准入及更新调用；不要先提交新事实，再在另一个请求中尝试替换。已有 PG 测试证明：临时状态拒绝时，新原话/新事实准入可随外层事务整体回滚。未知 slot 不调用更新服务，多值槽不调用替换；等价内容先走既有去重。旧事实尚未标槽时，不擅自回填后直接覆盖；交后续整理/用户确认。

服务重新核对 owner/subject/事项、原话修订与区间、来源角色、无痕、撤销账本、类别授权和提案凭据。敏感正文不能因 kind 被标成 preference 而绕过授权。时间取实际原始说法，而非批准消息或入库时间；必须旧说法 < 新说法 <= 注入 Clock，且有效期已开始。同槽多个当前候选、临时状态、已有关闭区间/更新链冲突均拒绝自动选择。

成功时旧事实保持 active，但 valid_to 关闭、superseded_by 指新值；新事实的 valid_from 为新原话时刻，supersedes 指旧值。历史保留，当前 `memory.facts()` 只见新值；事实修订变化使旧快照依赖失效。返回内部 updated 回执和变更 IDs，前态保存在带原话/事实依赖的既有 proposal，忘记后级联清正文。**不能直接把此内部回执送给当前 P3 提交门或冻结 v1 事件。** 主线接口协调见 `P5_slot_receipt_coordination_20261023.md`。

撤销入口将实际认证用户操作存成 user/web-action 原话“撤销这次记忆更新”，并绑定所选变更。旧值逐字段恢复业务前态，新值 retired，依赖新值的派生内容按既有失效路径处理；前一更新链保留。修订与更新时间保持递增，缓存回执重放也重新检查来源和结果；后续手改/忘记/失效不允许复活。

剩余接线与限制：memory_write 参数与 pending conflict 的统一提案消费、更新后的遗忘链两端修复、历史定向检索、认证入口与 updated 回执证明仍待完成。组合操作（例如敏感确认→更新→撤销更新→再撤销类别授权）的跨变更撤销也尚未验收；既有派生级联可能清除更早的 proposal 快照，不能宣称所有组合已可撤销。没有改 Agent 循环、提交门、渠道或调度器；无需结构迁移。


## 01:13 更新：遗忘链两端已装入

`MemoryService.retire_fact` 已在同一隐私事务、清理快照前调用 `detach_withdrawn_chain`；现有 memory_forget 不需额外接线。删除新值可恢复有当前合法依据的旧值；删旧值清前驱，删中间值连接存活端，source 批量删除不互相复活。来源/授权无效、快照修订失配或用户后来修改时不恢复历史有效期。旧更新撤销快照仍按隐私级联清除。

中间链的存活端恢复依据沿用 proposal（kind=memory2_chain_repair, status=applied），只绑定存活 fact_ids 和来源；不是待确认提案，不展示为新的用户操作。整体 updated 工具/提交证明和组合授权撤销仍未验收。证据：`docs/v4/evidence/P5/20261024_forget_chain_slice.md`。
