# 冲突待确认提案与明确选择的接线边界

2026-10-24 00:40 +08:00。真实 memory_write 已在存事实前调用 `create_conflict_proposal`，不需要新增工具或改 Agent 循环。其返回仍为既有 `pending_confirmation` + proposal ID/版本；即时工具数据新增 possible_conflict，含旧 fact_id、逐字原话构造的提问及本地词法/无向量标记。提问正文不写进持久 mutation receipt 或日志。

提案复用现有 proposal 实体，`proposal_type=memory_conflict`，保留实际请求 kind/sensitivity/fact_metadata，额外绑定 target_fact_id/target_revision。source_refs/source_ids 同时覆盖新旧原话，fact_ids 绑定旧事实；沿用同一隐私级联和现有 Agent 的来源闭包，已在真实 PG 调用未修改的 verified_versions 验证。

`MemoryProposalService.reject(...)` 使用同一认证用户操作“不要保存这条记忆”，可清除待确认提案并保留原事实。不创建第二套授权存储或拒绝流程。`accept(...)` 的“请保存这条记忆”不能决定冲突真值，因此对本 subtype 明确拒绝；不能把它强塞进敏感确认来保存两条相反事实。

01:03 +08:00 更新：应用消费和撤销已实现，入口为：

```python
MemoryProposalService(memory).resolve_conflict(
    owner, subject, proposal_id, expected_revision=revision,
    message_id=authenticated_action_id, choice="old",  # 或 "new"
    remember_category=False, operation_id=stable_operation_id,
)
MemoryProposalService(memory).undo_conflict(
    owner, subject, proposal_id, expected_revision=resolved_revision,
    message_id=authenticated_action_id, operation_id=stable_operation_id,
)
```

认证入口应把真实点击形成该 owner 的当前 user/web-action 原话：选旧为“以以前的说法为准，这条不保存”；选新为“以这次说法为准并保存”；选新同时授权敏感类别加“，以后这类都记”；撤销为“撤销这次冲突选择”。参数不能作为模型提供的授权旗标。原话、人物/事项、源修订、撤销账本、提案版本、实际操作入库先后均重新验证；一个操作消息只绑定一次选择/撤销操作，不能用于后来提案。普通偏好拒绝额外敏感类别授权。

选旧不写事实或授权，提案进入 resolved_old；选新进入 resolved_new，创建有原话/确认凭据的新事实，旧事实保持 active 历史并关闭有效期，建立 supersedes/superseded_by。说法时间相同则验证实际来源入库顺序，不凭确认时间重写事实发生时间。内部选新回执为 updated，仍需主线严格提交证明及 v1 外部映射，不能自行绕门。认证入口/按钮由主线接线，尚未接入前不应显示“选新值已生效”。

撤销恢复旧业务字段和 pending 提案，审计修订继续递增，target_revision 更新为实际恢复行的版本；停止新值和本次类别凭据下后续自动保存，撤销凭据并清派生引用。仅恢复两个 memory 设置键，保留无关 runtime 设置；后续记忆设置或事实已改动则拒绝覆盖。忘记来源/新旧事实后不能恢复快照。撤销后新确认须新的操作消息，新事实使用新身份，不复活已停止记录。

候选识别保守，仅处理明确相反的单一偏好词和完全一致的剩余主题，限定 preference/habit。无向量、无通用语义保证；多候选选择拒绝自动裁决，跨槽及完整渠道消费仍未验收。旧来源比本轮晚、源版本变化、撤销、无痕、不同 owner/人物/事项均不能借候选恢复资料。任何 UI/最终对话质量、M/KU 场景通过仍须单独验证。
