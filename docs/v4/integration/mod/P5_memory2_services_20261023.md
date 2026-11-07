# P5 新核心记忆接线（尚未阶段验收）

工作分支 `v4/p5-memory2`，草稿 PR #17，目标 `v4/first-release-integration-20261023`。真实模型请求 0；本说明不表示按钮/渠道/全部 scripted 场景已通过。

## 已接入的路径

`application/agent_tools_memory.save_memory` 在 P3 身份、原话、敏感和日期检查后执行保守去重；`agent_tools_reads.memory_search` 和上下文 `context_time_retrieval` 使用重要度及 180 天衰减，约束/目标不衰减。没有下载或启用向量模型，工具明确返回 vector_available=false。来源修订/撤销/人物/事项检查始终先于排序。

## 主线认证入口需要调用的服务

当前 `adapters/web.py` 有记忆查看/编辑/删除和画像确认，未发现通用敏感 proposal 消费入口。本线未修改这个渠道文件。入口必须从认证上下文取得 owner，校验用户选中的 proposal/change ID、期望修订和稳定 request ID，然后通过既有 `MemoryService.receive(..., channel="web-action", role="user")` 保存真实点击对应的确认消息，再调用：

| 操作 | 应用服务 | 确认消息正文 |
| --- | --- | --- |
| 仅保存一次 | `MemoryProposalService(memory).accept(..., remember_category=False)` | 请保存这条记忆 |
| 保存并授权同类 | 同上，`remember_category=True` | 请保存这条记忆，以后这类都记 |
| 拒绝 | `MemoryProposalService(memory).reject(...)` | 不要保存这条记忆 |
| 撤销确认 | `MemoryProposalUndoService(memory).undo(...)` | 撤销这次记忆确认 |
| 撤销等价合并 | `MemoryMergeUndoService(memory).undo(...)` | 撤销这次记忆合并 |

共同参数是认证 `owner`、`subject`、所选实体 ID、`expected_revision`、上述原始消息的 `message_id` 与稳定 `operation_id`；accept 另有 remember_category。动作正文是程序保存的真实用户动作记录，不是模型提供的授权旗标；不要把内部 ID 或流程说明展示给最终用户。

服务拒绝跨 owner/人物、非用户或无痕动作、失效提案、陈旧/撤销来源和复用同一确认消息授权其它提案。第三人健康需要两类权限。类别授权附证据，其后自动保存也带授权引用；撤销会恢复原提案/记忆设置，停止依赖该授权的事实，并使派生引用失效。若记忆授权设置或目标事实再次修改，则拒绝覆盖。原始消息被忘记后，不得借撤销恢复内容。

## 返回与后续工作

回执沿用 ID/状态白名单，不含私人正文。合并回执 `ids[0]` 是撤销变更 ID；敏感确认回执 `ids[0]` 是原 proposal ID。没有扩展提交门白名单。审计修订保持递增，“逐字段还原”指业务字段而非倒退 revision/时间戳。

仍待本线完成：单值槽更新与矛盾提案、事件过期归档、八节画像反思。单值槽须按 P5 增补增加 memory_write 可选 slot 并校验槽位表，不能用临时出差覆盖长期居住地；updated 回执若需提交门支持，留主线修改。反思调度触发归主线，服务由本线提供。最后使用 `--target v4` 和 scripted 模型验收规定场景，不使用 fake target 或手填回执替代。
