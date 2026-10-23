# P5 单值槽的回执接线边界（待主线配合）

P5 时间与冲突增补要求 memory_write 新增可选 slot（未知值视为未填），并在同一 single 槽的新说法较晚时，关闭旧值的有效区间、建立 supersedes 链，返回 write_status=updated 和撤销凭据。临时出差不能覆盖居住城市；历史查询与当前值必须区分。

本线可修改 MemoryWrite 参数、槽位校验/服务、memory_* 工具及对应测试。尚未修改这些参数或实现槽更新；当前回执仍是实际受检的 saved。下一步应先完成槽位表和独立服务，不绕过 P3 的回执验证。

主线需要处理的现存边界：

- `agent/loop_codec.py` 的工具实体修订验证目前只针对 saved。
- `application/agent_commit_versions.py` 的保存回执门目前只接受 saved。
- `agent/options.py` 的决策卡记忆保存声明也要求 saved。
- `agent/event_contracts.py` 的 MemoryReceipt 线上状态枚举是 saved/pending_confirm/undone/rejected，已有事件契约 v1 不应由模块线擅改。

建议由主线定义内部 updated 的严格写入证明，并在外部 v1 事件继续映射到 saved、用摘要表达“已更新”；如果要求外部状态也改为 updated，须先协调契约版本与前端。无论选择哪种，不能只把所有 saved 条件扩大成 updated；必须核对当前人物/事项、实际 fact ID 与修订、同槽更新链及撤销变更记录，保持失效回执拒绝、原话/撤销/epoch 守卫。

本说明是接线待办，不是已实现或已获批准的协议变更。不阻塞独立记忆服务、归档与反思模块的开发；产品级 KU/Q06 通过前仍不标记记忆2.0就绪。
