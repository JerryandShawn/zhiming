# P3 无痕存储与Z4确认服务切片

本活计划遵守AGENTS/.agent/PLANS，依据28 Z4及P3 M5。全部时刻为北京时间。它是完整线程/运行时之前的存储和应用服务，不把未接线工具/API称为已交付功能。

## Progress

- [x] ThreadService提供owner/subject绑定的人生与无痕线程、稳定消息身份、原话不可覆盖、24小时活动期限与独立历史。
- [x] 无痕消息不生成FTS tokens、不进入长期来源/快照、普通网页history与飞书history；即使原话说“请保存”，也不能授权事实/资料/事项。
- [x] 到期清空本线程原话/助手、run request/result/checkpoint、step输出、event payload、派生缓存；撤销租约，重复清理无变化，保留其他线程/owner。
- [x] IncognitoReminderService给一次固定确认卡；用户新的原话明确同意后只存已批准提醒文字/时间及必要业务元数据，不关联无痕thread/source/run；拒绝或含混不保存。
- [x] 只在实际Outbox sent+receipt匹配业务ID后启动7天期限；清理提醒内容及Outbox payload，保留sent收据防重发。
- [ ] RuntimePort无痕上下文、最终提交与Loop线程ID接线；set_reminder→真实ask_user步骤的程序桥接、确认API和送达hook；退出/到期调度与inbox。上述尚未接入，不能勾完整M5或Z4。

## Surprises & Discoveries

仅过滤MemoryService.sources不足：旧history_window还会从core_runs补出回答，另有/api/feishu_history直接读message。两条旁路均已补私密过滤，渠道历史还沿用原话撤销遮盖。私密FTS清空必须放在searchable_data公共入口，避免后来索引刷新恢复token。

实例化模型、网关或sender不属于本片测试。旧渠道HTTP测试第一次用了不存在的斜线地址而404，改为源码已有/api/feishu_history，保留普通消息可见/私密消息不可见的原断言。

## Decision Log

2026-10-20 / 存储策略：复用现有thread/message实体，无新迁移，不抢0008/0009。写私密原话时在同事务内标incognito/线程与persist_allowed=false；来源ID包含线程，防同外部ID将旧人生原话移进私密线程。敏感正文只在暂存线程/run内，24小时到期逐层清空。

2026-10-20 / Z4：确认只接受当前租约/epoch/最新有效用户原话，不能拿模型布尔值或旧消息充当“同意”。固定确认问题不重复询问；提醒真正入库后不带私密来源链接，私密线程到期不能连带删已授权提醒。首次支持绝对日期/时刻；U4未接前拒绝猜测相对时间。

2026-10-20 / 送达与保留：用户说同意不代表送达，7天期限必须有真实业务Outbox sent收据；不以模板布尔值或替身sender启动。实际发送尚未接线，本片仅合成已发送行测试。到期清理保留收据/状态，不能使消息重新claim。

## Outcomes & Retrospective

39项隐私/线程/确认及P2兼容目标通过（17.95s，一项锁内Starlette弃用告警）；补普通history旁路后私密线程4项重新通过（1.47s）；渠道读取端真实ASGI+PG 1项通过（1.02s）。这些计数重叠，不相加当全阶段成绩。Ruff、格式与新增文件400/函数60/行120检查通过；旧MemoryService只加局部来源限制，未整体重排。

真实服务器/模型/飞书发送均0。尚未连接对外v4默认路由，不改变B1固定包，不宣称完整无痕对话、取消或SSE已验收。

## 下一步与接口

Root完成Runtime life闭环后，将私密ContextBuild限制为本线程消息与明确允许的只读资料，禁止主线程读取它；AgentSnapshotStore/Finalizer应核活跃thread/租约并复用ThreadService.record_private_reply。Loop的thread_id不能硬编码life。set_reminder先保存私密临时确认请求，再由程序产生一次真实ask_user Journal步骤，最终asked必须仍绑定真实步骤。

用户新回答作为新run，IncognitoReminderService.confirm校验原请求没撤销且本轮用户明确同意。后续P7只能使用reminder业务ID与已批准text/due，不携带private source_refs；实际sent后调用delivered，定时调用cleanup_delivered。ThreadService.touch只由受信活动入口触发，不让后台轮询永久续期。前端线与模块线保持只读契约边界。
