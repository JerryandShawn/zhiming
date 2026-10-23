# Q3 主动规则接线说明

适用提交：模块线 Q3 `c7df71f`，回执 `2ea5ecb`。本说明只列主线后续接线位置；本次没有修改现有入口、配置、数据库、调度器或发送器。

## 1. 已有模块与实际入口

| 新增文件 | 公开入口 | 调用方提供 | 返回结果 |
| --- | --- | --- | --- |
| `application/followups_contracts.py` | `FollowupScope`、`FollowupSettings`、`FollowupCandidate`、`ProactiveNotice`、`UserActivity`、`ReceptivityState` | 可信 owner/subject、实体状态、源状态、用户设置与时间 | 不可变投影；不写库 |
| `application/followups_rules.py` | `count_followups_today(notices, *, scope, clock, timezone)` | 已发送、已绑定身份的无正文记录 | 按 owner 当地日期去重后的 followup 数；不含 brief/reminder |
| 同上 | `decide_delivery(candidate, settings, state, *, scope, clock, sent_today)` | 当前权威状态与领取事务中的计数 | `allowed`、`next_due`、受控 `reason`、有效日限、锁屏预览 |
| 同上 | `safe_preview(text, category='', *, proactive=True, sensitive=False)` | 可信敏感标记及规范类别 | 身心/健康/财务/金钱主动消息固定返回“明镜想问问你” |
| `application/followups_adaptation.py` | `classify_response(notice, activities, *, scope, clock, muted_at=None)` | 真实用户活动及明确静音操作时间 | `pending/replied/ignored/muted` |
| 同上 | `apply_response(state, notice, status, *, scope, clock, timezone)` | 上一步状态和当前持久投影 | 新接收度状态；不延长既有暂停、不提前恢复 |
| 同上 | `brief_prompt_due`、`mark_brief_prompted` | 下一次真实用户对话、当前状态、scope、Clock | 是否询问晨报偏好；一次提问后的新状态 |
| `application/divination_rules.py` | `repetition_decision(current, history, *, clock)` | 同一人生线程的有效用户原话/规则或模型主题标签 | 24 小时计数、L3 提示、旧引用、是否允许新结论/暴露 tarot_start |
| `application/decision_autonomy_rules.py` | `detect_delegation`、`autonomy_decision`、`autonomy_warnings` | 本轮用户文本、已授权偏好及有效别名 | present_options/单问要求、J4 辅助告警 |
| 同上 | `dependency_copy_warnings` | 候选晨报、跟进、回答文案 | 诱导依赖词的受控告警 |
| `application/usage_guard_rules.py` | `usage_decision(events, state, *, clock, timezone, policy, crisis, confirming_data)` | 交互活动元数据、owner 设置、危机/资料确认状态 | 是否提醒、时长、受控原因和后续状态 |

以上路径均相对 `mingjing_core/`。函数只计算结果，不创建后台任务、不调用模型、不投递消息。

## 2. 主线需要改哪些现有位置

| 现有位置 | 后续接线内容 |
| --- | --- |
| `adapters/delivery.py::OutboxService.claim_delivery` | 在原有领取事务内重读源撤销、实体 active、scope、目标 binding、设置、接收度和日计数，再运行 `decide_delivery`；顺延时更新原 Outbox 的 due，不新建业务编号 |
| `adapters/delivery.py::_fresh` | 为跟进新增经过评审的依赖策略：用户新聊天不应使有效跟进自动失效；仍必须验证来源授权、撤销、人物和事项有效性。不能简单删除现有版本检查 |
| `adapters/channels/delivery.py::CoreDeliveryWorker.deliver` | 使用 claim 中固定的最终正文和预览；保持不二次生成、明确失败有界重试、送达不明不重发 |
| `adapters/feishu_gateway.py::FeishuGateway.accept` | 只从 sender=user、p2p、绑定正确的已提交入站事件投影 `UserActivity`；卡片选项应沿主线正常入站路径计入真实回复 |
| `application/report_schedules.py::ReportScheduleService`、`domain/report_schedules.py` | 复用原报告时区、准备窗口、期间和受保护投递规则；晨报时刻冲突确认后再接 brief 的免打扰策略 |
| `application/consultation.py` 的现有阶段及后续 v4 finalize/ContextEngine | 接入重复占卜、委托决定、使用时长信号；本分支没有 `agent/`，不宣称已有 v4 ContextEngine 接线 |
| `application/consultation_context.py` 及后续 P3 L1/L3 装配 | 使用同一运行程序时钟；将受控提示写入上下文，别名由当前授权映射发放；不得直接拼入不可信主题标签作为指令 |
| 主线 P5/P7 状态仓储与设置入口 | 持久化接收度观察、暂停、晨报单问冷却、用户明确提醒授权及使用提醒设置；迁移编号由主线统一分配 |

本模块没有新增 SQL，也没有改变现有 v3 的运行行为。主线接线须保持 v3/v4 路由边界。

## 3. 领取事务与时间口径

1. 从认证上下文取得 owner/subject；从 PG 权威状态读取 candidate 和设置。`scope` 同时核对 candidate 与接收度状态，不能从请求正文猜人物。
2. 锁定原 Outbox/业务记录，按 owner 当地日期读取主动投递计数与在途占位。`count_followups_today` 只数已发 followup；在途及送达不明占位要在主线事务中另行计入，并避免与已发记录重复计数。
3. 先检查来源撤销和 active，再检查具体类别静音、全局开关、接收度、到期、免打扰和日限；`decide_delivery` 返回 allowed 后，在同一事务内原子占用当日额度并领取租约。
4. 事务外发送；回执使用原 claim/operation。发送未知必须保留占位并走现有对账，不能把 due 改到另一日、换 business_id 或目标获取新额度。
5. 所有时间由注入的 `Clock` 取得。消息、期限和冷却在边界规范化为 UTC；当地日、22:00–08:00 和次日 08:30 使用 owner 的 `ZoneInfo`。不能用 UTC 加 24 小时模拟“次日”。

默认主动日限 2，不含晨报；明确 set_reminder 不占日限。全局“先别主动找我”保留已明确提醒，但新近的“别再提醒这类”属于具体撤销，优先于旧提醒授权。

明确提醒也受免打扰；只有可核验的用户明确指定夜间时刻才能设置 `explicit_quiet_time=True`。`explicit_requested`、`essential`、`source_active`、`source_revoked`、`category`、`sensitive` 均由服务端权威投影产生，不能采用模型任意自报值。

`next_due` 是下一次允许重查的建议，不是已经获得发送授权。到点仍须重新执行整个领取检查。

## 4. 接收度与一次提问

- 用户在发送之后、发送后 24 小时以内的任何消息都算 replied，右端点计入；同一瞬间及未来事件不算。正文无需传入，短回复不会提高日限。
- 连续两条非提醒主动消息 ignored 后，日限降到最多 1，并暂停 7 天非必要 followup。明确提醒不受该暂停；必要 followup 仍受日限和其他检查。
- 后续聊天不提前清除暂停；暂停期间更多 ignored 不逐日延长期限。期限届满恢复原上限；之后两条新 ignored 才产生新暂停。
- 晨报按 owner 日历日计算连续五天 ignored，在下一次用户对话询问一次。选项为“保持 / 换个时间 / 先停一周”，提问冷却 30 天；不由后台主动再发一条询问。
- `apply_response` 仅做投影。调用方须保存稳定 notice 标识、发送时间、状态及观察历史，或从 PG 权威账本重建；不能丢掉 observations 后只保留计数。写入仍需 operation_id/expected_revision 与适当锁。
- 晨报偏好问题必须与当轮其他 ask_user 竞争同一个“一轮一次”额度。主线在提问实际入队/记录成功后，才原子保存 `mark_brief_prompted` 的状态；不可先标记、后因工具拒绝而丢失问题。

## 5. 主题、来源与别名

`DivinationScope` 包含 owner、subject、thread。24 小时窗口只聚合同线程、有效且未撤销的命运类原话；参与计数的相同来源标识冲突投影会拒绝。主题标签只帮助归并人物或事件，不会把模型推断升级为事实。

第 2 次返回 repeat：复用已有档案/draw，不给新结论。第 3 次及以后返回 reframe：最多一个问题、1–2 个可控行动，且不再暴露 tarot_start。主线必须让该决定影响实际工具列表，不能只把提醒写在提示词里。

`reference_alias` 和已有偏好别名的语法通过不等于授权通过。调用方必须重新检查当前 alias 映射、对应来源区间、修订、人物/事项和撤销；没有有效旧引用时不得发明档案或 draw。P6 的未知别名检查仍需运行。

`autonomy_decision` 只返回需要 present_options、是否应问偏好及禁止唯一指令的信号。真实工具、提示词与结构检查由主线接上；`autonomy_warnings` 的 J4 辅助证据不能绕过 P6 校准门槛强行触发修订。

## 6. D4 与待决问题

`UsagePolicy.enabled=False` 是当前默认，依据 18 号索引 §4a D4，优先于 P7 增补中旧的“默认开”。设置里可以保留开关；本次没有开使用提醒，也没有登记紧急联系人。

启用后，代码按当地同日、相邻消息间隔严格小于 10 分钟的连续活动计算，严格超过 120 分钟才提醒；两小时内不重复，危机不提醒，资料确认时只顺延当前连续段。程序只传“应提醒”事实，文案由后续主线按版本化提示词生成。

待决问题统一列入夜间汇总，本夜不等待回答：

1. 旧晨报默认 07:00 与 22:00–08:00 免打扰冲突。当前纯规则对 brief 采用保守的 08:30 顺延；没有修改旧报告计划。需用户/大脑明确晨报是否单独豁免后再由主线接线。
2. 夜间精确提醒授权需由主线保留哪种原话/来源/版本证据，才能设置 quiet 例外。当前不将“允许主动联系”推断为任意夜间发送许可。
3. 本夜对服务器、真实模型、真实飞书均无操作授权。后续真实 stage 投递需针对那次操作取得接收人和时间窗口授权；代码内的提醒授权标记不能替代该授权。

## 7. 验证与未覆盖

Q3 回执与指标见 `docs/v4/evidence/MOD_2026-10-19/Q3_followups_receipt.md`、`Q3_followups_metrics.json`。固定种子属性测试覆盖投递、发送回复序列、去重账本、多个时区与 DST；这些证据只适用于本地纯规则。

仍未验证或未实现：真实 PG 领取并发、真实后端调度、Outbox 持久化接线、源撤销的端到端级联、P3 工具列表与上下文接线、真实回复语气、真实飞书/CardKit、stage/生产。后续接线不得用这些单元测试声称上述行为已经上线。
