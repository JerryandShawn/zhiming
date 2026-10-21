# MOD 最终跨模块来源链 ExecPlan

## Purpose / Scope

用全新显式虚构材料独立验收：当前原话→记忆2.0写入/重放→reflection_v3纯计划与八节画像→reports_v2内容，
以及当前来源全文、角色、epoch变化和撤销后的协同失效。只新增测试、fixture和说明，不改任何产品/旧断言。
真实模型、PG、服务、网络、飞书、Git均为0，不读Q5 B或75校准正文。全量只能root启动。

## Progress

- [x] (2026-10-21 08:29 +08) 阅读公开入口与契约，确定使用当前来源快照而不是持久化假回执。
- [x] (2026-10-21 08:30 +08) 先冻结41条全新合成语义矩阵，LF SHA `90074adfba23e5d2ba0d8f049743ecb52bbf9dad4fcd37587a6565d172dfe5f5`。
- [x] (2026-10-21 08:34 +08) 七区、三类报告、六时区独立民用周界/半开期间、同operation重放。
- [x] (2026-10-21 08:34 +08) 来源全文/role/origin/epoch变动、撤源不改epoch、pin/edit不复活和敏感/拒记边界。
- [x] (2026-10-21 08:34 +08) 64目标通过/3.07s，含1000随机完整链再撤源；全部effects0，默认后台许可关闭。
- [x] (2026-10-21 08:36 +08) 120完整链+撤源性能样本，p50约9.60ms/p95约10.81ms、tracemalloc峰值834546字节，源稳定；接线/回执已写。

## Surprises & Discoveries

reports_v2接收可信host的BasisRef/BriefSourceState投影，不自行读MemorySnapshot。
组合测试将保留旧ReportRecord及旧依据，只替换由当前原话/角色/epoch计算的source state；不在helper预过滤所有失败输入。
此边界仅是合成host一致性验证，不能声称已认证PG、登录身份或真实撤销广播。
首轮43通过/1受控拒绝：assistant_claim搭配background不属于合法助手笔记形状，MemoryGuardError正确阻止。
helper改用公开契约支持的note形状继续完整链，原“不得保存成用户事实”真值不变，不修改冻结fixture。
note的拒绝计划也不能再强行apply；helper保留saved=None和初始snapshot，不构造假的MutationOutcome或保存回执。

## Decision Log

先冻结真实语义，再按公开API接线；接口不兼容或产品缺陷只报告root，不反向修改gold。
来源投影hash显式绑定原话全文、角色、origin、owner/subject、revision与source epoch，避免仅凭消息ID授权陈旧内容。
当前回执与operation/revision元数据允许变化，正文/来源语义不得被helper偷偷修正。
所有新fixture从开始使用显式LF；只按root新授权读取git hash-object做过滤核对，原始/过滤Git blob均为754667981bb18b875e25e1774185e59fa035418c。未写Git。

## Outcomes & Retrospective

独立组合目标通过且未改任何产品或旧测试，41条gold未改变。指标仅代表本机纯模块与合成host投影，不代表PG、真实后台调度、发送或上线。
主线仍需在同一授权事务内构造当前来源投影；D4在本链仅证明未创建任何主动发送副作用，真实使用提醒开关不在本纯内容路径。
