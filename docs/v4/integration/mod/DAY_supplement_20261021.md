# 白天追加②：P5b 纯模块接线（2026-10-21）

本交付只新增 `mingjing_core/organize/supplement_v2/`。冻结的 Q5 分类器、参数、词表、语料、评测器和旧 `Proposal` 未修改；未读取盲评 B。所有输入与测试均为本机合成数据，真实数据库、工具、服务器和模型接线未验证。

## 入口与数据

公开入口可统一从 `mingjing_core.organize.supplement_v2` 导入：

| API | 输出及用途 |
| --- | --- |
| `build_review_proposal(snapshot, predictions, scope=..., operation_id=...)` | 包装冻结 Q5 `Prediction`，生成带指纹的 `ReviewProposal` |
| `review_data(proposal, snapshot, scope=...)` | 重验来源后生成七区和独立 `waiting` 审阅视图，样例最多 80 字 |
| `plan_review_labels(snapshot, proposal, scope=..., approval=..., sensitive_grants=...)` | 生成 label-only `SupplementPlan` |
| `plan_topic_archive(snapshot, scope=..., clock=..., operation_id=...)` | 生成 `TopicArchiveProposal`，不改变话题 |
| `plan_archive_review(snapshot, proposal, scope=..., approval=...)` | 将已审阅的归档候选转换为计划 |
| `propose_case_upgrade(snapshot, topic_id, goal_anchor, scope=..., clock=..., operation_id=...)` | 仅输出 `CaseUpgradeIntent(strategy="undecided")` |
| `project_plan(snapshot, plan, scope=..., approval=...)` / `project_undo(snapshot, plan, scope=...)` | 复制快照以预览正、逆操作；不写数据库 |
| `to_legacy_changeset(snapshot, plan, document, scope=..., approval=...)` | 仅完整用户消息可转换为旧 `ChangeSet` |
| `entity_from_fact(fact, memory_snapshot, labels=..., clock=...)` | 先调用 Q2 授权，再生成跨实体标签投影 |

`SupplementSnapshot` 包含 `MemoryScope`、`entities`、`topics`、原始 `MemorySource`、快照 `revision`、`source_epoch` 和纯预览操作账本。`EntityRecord` 支持 `message/fact/note/case/draw/legacy_archive`，保留原文、`said_at`、`SourceAnchor`、实体 revision、来源角色与生命周期标志。助手判断只能以 `note(origin="assistant_claim")` 输入。

`TopicRecord` 由主线提供当前 `last_at`、revision 和用户原话来源锚点。主线必须从当前事务读取完整话题生命周期，不能把旧缓存的 `last_at` 当最新时间。

## 审阅与标签边界

无把握的 Q5 输出留在 `waiting`，不自动写成日常区，也不生成该实体的标签操作。确定预测仍须用户审阅后才有计划。标签白名单只有 `space_id/topic_id/space_secondary/route_source/route_confidence`；跨区时清除已有旧话题引用，防止消息主区与旧话题区不一致。原文、时间、锚点、source revision、塔罗 draw 和命理解释均不改。

`ReviewApproval(scope, fingerprint, decision="approved", actor="user")` 是**可信宿主输入的审阅收据**，并非加密签名，也不自行验证真实用户身份。主线须先校验真实登录身份或一次性 action token，再构造它；不得接受模型或客户端自行声明的 approval。

审阅指纹绑定实体内容/来源/版本、原标签的缺失或 null 状态、完整预测、快照 revision、source epoch 和 operation ID。计划保留原审阅候选，投影和逆投影会按其重新构造合法操作。只重算 plan hash 无法把已审阅的目标区换成另一区。来源角色、范围、活性、撤销、无痕和原话版本在审阅显示、计划及每次预览时重新核验。

同 operation ID 的相同计划可重放；内容变更、撤销后重新应用均拒绝。逆操作保存字段是否存在和原值，恢复缺失与 null 的区别。来源已撤销或版本改变时，逆预览也拒绝，不会复活来源。全局快照发生并发变动时采取保守冲突，主线需重新生成审阅计划。

## 敏感与事实有效性

沿用 Q2 原话授权和敏感分类，实体提示与规则取严格并集。敏感实体除普通审阅外，还需 `SensitiveGrant(scope, entity_id, entity_revision, evidence_fingerprint, categories, decision="granted")`。拒绝、错主体、错 revision、旧来源指纹、缺类别、重复授权均不能通过。秘密来源或模型摘要中的秘密直接以固定原因拒绝，不能进入样例视图；出生资料留给主线专用 profile 确认。

本模块不发问、不保存“问过一次”账本。主线应复用 Q2 的问一次/拒绝策略，不能把普通整理审阅代替敏感类别授权。`entity_from_fact` 有 `valid_to` 或未来 `valid_from` 时必须注入 Clock，否则固定拒绝 `fact_validity_clock_required`；有 Clock 时按 `valid_from <= now < valid_to` 判断，不把尚未到期的事实误判为失效。

## 话题生命周期与事项

仅 `open` 话题在最后活动后满 14×24 小时进入归档候选，精确边界包含到期时刻。新消息导致 last_at/revision 变化后旧候选失效；归档只修改 status，保留标题、摘要、原话及来源，可逆预览。已有 `case` 不由此模块自动关闭，已有 `archived` 不重复归档。

自动筛选不要求新增用户交互。本包的 `plan_archive_review` / `project_plan` 是受审阅批次的离线模拟入口；主线自动归档消费者应接可信策略及同样的当前来源/版本检查，不能伪造actor=user的收据来冒充用户点击。实际worker尚未接入。

升级事项必须有来自当前用户的明确目标原话。否定、条件、假设、示例目标拒绝；英文守卫为保守规则，并非完整自然语言理解。返回意图仍要求审阅，不创建 case、不把 topic 强行改成 case，也不决定 P5b B3 的迁移二选一。主线须在实际执行前再次核对目标、来源与话题版本。

## 主线接线工作

1. 从同一事务投影 authenticated owner/subject、实体、当前原话来源、修订、无痕/撤销状态和当前话题，调用冻结 Q5 分类器后交入 `Prediction`；不得把测试标签当预测输入。
2. 将 `waiting` 和敏感待确认项交审阅界面；校验登录/CSRF 或 action token、expected revision、真实审阅收据，并接 Q2 敏感授权。
3. 为事实、笔记、case、draw、旧档案分别增加**仅标签**的事务适配器；本交付不新增迁移、列、API、`topic_route` 或 ContextEngine 注册。
4. 旧 bridge 只支持完整用户消息：消息 ID/源 ID、全文、时间、角色、修订和原标签必须一致。其他实体固定报 `mainline_entity_adapter_required`，不能借旧 messages store 写入。
5. 持久化操作和审阅账本、原标签逆操作及来源依赖；实际提交和撤销前重新读取授权状态与版本。把话题/归区变动接入主线的摘要失效和分区上下文计划。

## 本地证据与限制

- 自有目标测试及主线独立测试合计 509 通过（本交付时）；含 300 组缺失/null 标签属性、来源失效、敏感授权、14 天边界、否定/条件目标和重新 seal 篡改反例。
- 性能脚本：`tools/mod_week/benchmark_supplement_v2.py`；报告：`docs/v4/evidence/MOD_2026-10-21/DAY_supplement_performance.json`。使用真实纯模块调用链、一次预热、五次 wall-time 观测及单独 tracemalloc，并检查测量前后源码 hash 未变化。
- 北京时间 `2026-10-21T01:47:27.655111+08:00`：100 个完整标签链中位 0.143 秒、Python 峰值 198086 字节；1000 话题归档完整链中位 7.150 秒、峰值 4883771 字节。包含合成快照构造和正确性断言，10 份产品/脚本 hash 前后一致；不是独占 CPU 或真实数据库吞吐量。
- 尚未验证真实 PG 事务、接口授权、真实用户点击或生产规模性能。纯复制和内存测试不能证明这些接线已完成。
