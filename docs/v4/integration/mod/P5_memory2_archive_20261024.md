# 到期记忆归档与撤销：主线接线说明

2026-10-24 00:07 +08:00。应用服务与隔离 PG 检查已实现；后台触发、认证按钮和全场景验收尚未接通，不代表记忆2.0就绪。

入口为 `MemoryArchiveService(memory, clock=...).archive(owner, subject, fact_id, expected_revision=..., operation_id=...)`。传入实际认证 owner 和待处理事实修订，在 owner 事务中检查人物、原话修订/区间、无痕、来源角色与授权、撤销账本及 P5 确认凭据。返回只有状态、fact_id、revision 和变更 IDs 的持久回执。本服务的 archived 是应用状态，不能直接当作当前 P3 memory_receipt 事件状态。

绝对日期边界在 `memory2/expiration.py`，没有再解释相对日期。日期事件保留到 owner_timezone 当地日期结束；时刻事件以明确时刻/结束时刻为边界；显式 valid_to 采用结束边界。缺日期、无时区的时刻、错误时区、反向区间或未知结束字段均拒绝猜测。非事件目标不会仅因存在 event_at 而自动到期。single 槽中带 superseded_by 的旧值不归档，保持补充设计要求的 active 历史。

归档将事实改为 archived，保留原话和来源，升修订并写同类 proposal 的前态。原话/事实被忘记时，既有隐私级联会清除该前态。到期本身不调用隐私清除：历史回答、用户编辑和派生记录仍保留；当前事实列表排除 archived，带其 fact_ids 的派生检索同时被现有投影过滤，旧上下文依赖因事实修订变化而失效。不能用删除历史回答来模拟到期。

撤销入口为 `MemoryArchiveUndoService(memory).undo(owner, subject, change_id, expected_revision=..., message_id=..., operation_id=...)`。认证入口须保存当前用户明确操作“撤销这次记忆归档”的 user/web-action 来源，并绑定所选变更。撤销检查变更和目标修订，逐字段恢复业务前态，修订/更新时间保持递增；来源、区间或凭据已撤销就拒绝复活。新的归档需要新的操作 ID；旧归档回执不能在撤销后重放。撤销恢复归档前状态，并不永久豁免后续到期整理。

需要主线配合：在既有 background/reflection 运行内选取候选，显式注入 Clock，调用归档服务；不要在只读 memory_search 中偷偷写库。按既有运行权限/租约/提交机制承接调用，本线未修改调度器、Agent 循环、提交门或渠道。过期历史事件的定向历史检索与前端归档列表还需后续接线，当前普通 memory_search 只返回有效事实。

无需结构迁移；使用现有 fact JSON、proposal 与 mutation_request。代码回滚用普通反向提交；业务撤销用上述服务，禁止从未验证快照批量恢复。证据见 `docs/v4/evidence/P5/20261024_archive_slice.md`。
