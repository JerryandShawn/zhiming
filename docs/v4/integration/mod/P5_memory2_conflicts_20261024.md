# 冲突待确认提案的接线边界（WIP）

2026-10-24 00:40 +08:00。真实 memory_write 已在存事实前调用 `create_conflict_proposal`，不需要新增工具或改 Agent 循环。其返回仍为既有 `pending_confirmation` + proposal ID/版本；即时工具数据新增 possible_conflict，含旧 fact_id、逐字原话构造的提问及本地词法/无向量标记。提问正文不写进持久 mutation receipt 或日志。

提案复用现有 proposal 实体，`proposal_type=memory_conflict`，保留实际请求 kind/sensitivity/fact_metadata，额外绑定 target_fact_id/target_revision。source_refs/source_ids 同时覆盖新旧原话，fact_ids 绑定旧事实；沿用同一隐私级联和现有 Agent 的来源闭包，已在真实 PG 调用未修改的 verified_versions 验证。

`MemoryProposalService.reject(...)` 使用同一认证用户操作“不要保存这条记忆”，可清除待确认提案并保留原事实。不创建第二套授权存储或拒绝流程。`accept(...)` 的“请保存这条记忆”不能决定冲突真值，因此对本 subtype 明确拒绝；不能把它强塞进敏感确认来保存两条相反事实。

后续本线待做：明确选择新/旧说法的 `resolve_conflict` 应用消费及撤销，继续复用原话/提案凭据；敏感选择须同时具有真正保存授权。选择新值若形成 updated 回执，仍需主线严格提交证明及 v1 外部映射，不能自行绕门。认证入口/按钮由主线接线；当前尚未新增消费端，不应显示为“选新值已生效”。

候选识别保守，仅处理明确相反的单一偏好词和完全一致的剩余主题，限定 preference/habit。无向量、无通用语义保证；多个/跨槽冲突与完整消费仍未验收。旧来源比本轮晚、源版本变化、撤销、无痕、不同 owner/人物/事项均不能借候选恢复资料。任何 UI/最终对话质量、M/KU 场景通过仍须单独验证。
