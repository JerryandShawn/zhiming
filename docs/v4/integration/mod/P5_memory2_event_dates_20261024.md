# P5 C2：旧事件日期与知识缺口接线

本片是受测的内部应用服务，未接后台调度/认证渠道，尚未记忆2.0就绪。时间均为 Asia/Shanghai +08:00。

`MemoryEventTimeRepairService(memory, clock=...).repair(owner, subject, fact_id, expected_revision=..., operation_id=...)` 接收认证人物和旧事件的准确版本，只处理明确 `kind=event` 或 `requested_kind=event`、缺少 `event_at` 的当前授权事实。原话、敏感授权、人物/事项、撤销账本和原 `said_at` 都需有效；缺人物时区或未来原话拒绝。复用真正共享日期解析器，以原说话时刻解释日期，不以整理任务运行日解释。

唯一高置信度单点才补绝对日期、原日期表达和说话时刻，其他业务字段保持。范围、模糊或无日期生成 `knowledge_gap(kind=memory_time_confirmation, status=open)`；原事实不变，同事实同版本跨任务去重，被撤销的缺口不重建。有效缺口可进入原生 L3，目标事实版本/来源/授权变化或日期已补全则排除，最终提交仍使用既有上下文版本闭包。

回执 `updated` 仅是内部应用结果，不是已开放的模型工具更新证明。`ids[0]` 为日期变更 proposal；待确认回执 `id` 为 knowledge_gap；`context_revision` 是对应内部记录修订，不能充当 Agent generation。事务日志不存原话或快照正文；撤销快照沿用原生 proposal 来源/事实依赖级联。

`MemoryEventTimeUndoService(memory, clock=...).undo(owner, subject, record_id, record_kind="proposal"|"knowledge_gap", expected_revision=..., message_id=..., operation_id=...)` 要求真实当前用户在同一长期线程明确说“撤销这次事件日期整理”。动作须晚于变更、不在未来，每条动作绑定一个操作。日期撤销逐字段恢复前态，审计修订递增，清除引用派生；缺口撤销只清缺口。来源撤销、事实归档或后续修改均拒绝覆盖，缓存回执同样复核。撤销/级联失败整个事务回滚。

本机隔离 PG：相关47项通过；新增真实 L3 与既有上下文12项通过；新增级联失败回滚、动作单用及受影响撤销9项通过，范围重叠不相加。补显式接收/检索冻结时钟后，新文件29项全部通过（12.21秒），与前述分组重叠；Ruff/格式/大小检查通过。首轮新测试辅助函数错误及修复如实见聚合证据 `docs/v4/evidence/P5/20261024_memory_event_dates.json`，未改旧断言。真实请求0，无下载/服务器/飞书操作；未重跑全仓或37题。

需要主线配合：后台何时选择旧事件、认证渠道如何选择指定变更/知识缺口、用户回答消费接线仍待完成。M08 的“这周”仍需要确认具体日期，不能填周一或把事件改成 background；原37题完整证据34/37保持。无迁移或正式编号；回滚用普通反向提交，不复活被撤销来源。
