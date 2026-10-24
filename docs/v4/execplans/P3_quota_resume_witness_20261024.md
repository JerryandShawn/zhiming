# P3：额度恢复前的只读资格核验

本活计划遵循 AGENTS 与 `.agent/PLANS.md`，北京时间，沿用指令板 v8。工作分支 `v4/p3-wire-quota-resume-20261024` 从已推 60eb8e4 继续；只做本机隔离 PG 和 MockTransport，不改暂停线、模块记忆服务或金标，不发真实模型请求、访问服务器或外发。

## Purpose / Big Picture

为明确五小时额度恢复后从原场景继续建立可核验基础。本片仅回答“原物理请求已可信结束为 quota_5h，明确恢复时间已到，原检查点和累计预算仍相同”这一资格问题，不能执行恢复。中央停机仍保留，原 run 不 claim，Durable 的 attached send、普通 StepAttempts.begin 和 CLI 继续关闭。

## Context and Orientation

复用 `LifecycleControl.load`、`v4_lifecycle_state.read_private`、`BudgetStore.read_closed`、原 RequestLedger 与模型私密 attempts，以及中央 `QuotaStore.verify`。后者只读；不能使用会更新 last_clock_at 的 locked。实际每次 usage 只有状态和 finished_at，reset_at 在 account 上，因此只接受中央仍停在同一 quota_5h 的 pre-clear 观察；已经清停不能从历史 usage 猜恢复窗口。

StepAttempts 的 authority 依赖有效 lease；本片不借用它 mint 执行权，也不为了核历史申请新 lease。必须按实际请求/Journal/中央字段只读比较同样锚点，不能把 ProviderStopped 的异常或零计数当未发送证明。

## Progress

- [x] (2026-10-24 08:13 +08:00) 根与两位只读审阅者核实际字段和接缝，记录先做 pre-clear 资格、不打开执行的范围；尚未实现或测试。
- [x] (2026-10-24 08:26 +08:00) 两 helper 318/129行、新PG文件180行，最长函数43行；Ruff/format/AST通过，根已全文及最终差异审阅，两位独立审阅的实质边界均采纳。实际为3组9个不同节点；尚未运行，代码冻结后仅授一个主线测试槽。
- [x] (2026-10-24 08:30 +08:00) 唯一首链9/9、148.38秒、0 skip/错误/失败/警告，08:26:47.673399–08:29:17.065168；根已独立核 metadata/XML/log，槽已释放，三路径继续冻结。不重复已绿目标或做全量；真实模型/服务器/外发0。
- [x] (2026-10-24 08:30 +08:00) 已提交并推 e2af97d 至自己的 v4/p3-wire-quota-resume-20261024。新CI待核；正式integration/feed和原69/81/真实评测门均不前进。此为推后实际状态，随下一实质片保存，不为进度取消刚启动检查。

## Plan of Work

新增 `tools/eval/quota_resume_evidence.py`，只读收集实际检查点、预算、Journal/请求、attempt 及中央停机证据。新增 `tools/eval/quota_resume_witness.py`，以当前受信 core DelegatedSession、原 target/repo/control/guard 对象和证据摘要绑定进程内短期 witness；普通构造、JSON、复制对象或退出后的 witness 不被接受。每次 check 都重读原 PG，不只检查内存 registry。摘要不放正文或凭据，明确 execution_authority=false、central_stop_cleared=false、model_calls=0。

资格须同时成立：

1. 受信 session 当前有效、core 模式、同 guard/candidate/场景和已核等价的模型；重新核候选来源、契约及中央位置。独立 control 与原 target location 不变；只收 primary_pending 原 turn/run/epoch，实际原话/依赖仍有效。
2. 已保存预算仍严格闭合且未耗尽；原 limit pin、deadline、monotonic consumed/has_text 不重置、不延长。无预算的 queued/legacy 只观察，不能纳入此资格。
3. 原 Journal 是完整连续前缀，最后只有一个 started model，原 request 快照、role/name/seq/input_fp/hash 相同。此前 completed model 的私密/中央成功证明完整；工具只观察实际完成行及摘要，不再执行。
4. 原 started model 的 attempts 非空、UUID 唯一且全部 finished。逐个重读同 account/UUID 中央 usage 与原 batch authorization 摘要、run/lane/scenario/provider/model/role/location/identity，完整 terminal hash 相同。最后必须双方都为 quota_5h、中央 finished_at 非空；同 run 的未锚定、reserved、unknown 或未闭合记录均拒绝。
5. 当前中央 account.stop_kind 恰 quota_5h，resume_at 明确且已到，时钟未回退；stopped_at 对应这次原 terminal.finished_at。绑定实际 stop/reset/clear_authorization 元组摘要，不虚构 account revision。读取结束再核 checkpoint revision/private hash 和停机元组；check 后任何改变均拒绝旧 witness。

若上述实现无法保持两个 helper 的单文件 ≤400 行、函数 ≤60 行，先报告真实结构问题再调整分片，不通过削弱资格或堆成大文件解决。

## Validation and Acceptance

仅新增 `tests/v4/agent/test_eval_quota_resume_eligibility_pg.py`。复用真实 Durable/独立控制库/模型 attempt 测试夹具，以实际 MockTransport quota 响应与 Retry-After 产生中央和私密证据，不构造假的 stopped 字典或替代 Journal/PG。只替代传输；固定候选的 clean-checkout 边界可按现有夹具显式隔离，实际 source digest/契约/账号/位置/业务原话保持核验。

必要三组行为：真实工具完成后遇 quota，闭合保存/detach/attach；恢复钟到期后 mint/check 成功但无新增 POST、中央仍停、旧 Journal/工具/usage 不改，退出失效。其次早于/缺 reset、Access、更强停机、intent/中央未知拒绝。最后实际 control/source/预算漂移与伪造/退出 witness 拒绝；attached send 保持硬关。具体参数按真实风险最少选择，冻结后授单槽，主线最多两个测试进程。

## Decision Log

2026-10-24 08:13 +08:00：第一片只证明“可以进入将来的受审恢复门”，不清 quota、不调用 resume_delegated 或 generic clear_stop、不 claim/execute/seed/receive/requeue，不把 check 的成功解释为并发无变化或持续执行权。后续真恢复仍须在实际 admission/claim/发送前重新核全部证据。

2026-10-24 08:26 +08:00：本片最后未完成模型的全部历史 attempt 限 quota_5h，不接纳历史 ok、其它全局停机或 transient，避免把未发布成功输出重发；此前 completed 模型仍核原成功终态。中央usage无epoch字段，当前原epoch的私密锚点必须覆盖这个run全部usage；含旧epoch实际请求的run保守拒绝，不靠run_id猜归属。原请求/attempt实体另核实际subject_id，工具前缀只做原ToolResult结构验证；witness失败后注销、返回前再核registry/当前ContextVar，不能由复制上下文复活退出后的资格。

## Surprises & Discoveries

中央 account 无 revision，单个 usage 无 provider reset；已被清停的 account 不能还原原 reset 绑定。guard 的结束失败仍可能优先传播原 quota 异常，故异常类型不足证明中央及私密 finished 已可信落库。业务时钟与中央额度时钟分别保存，不能以宿主时间推断累计执行预算，也不能使普通生产绝对 deadline 延期。

QuotaStore.finish 对这次 usage 与 stop 使用同一个 finalizing 时间，但同类旧 stop 且 reset 未延后时会保留更早 stopped_at。本片要求精确相等，因而只接纳该原 terminal 实际建立的当前停机；并发继承/聚合旧停机保守拒绝，不用时间先后猜因果。完成模型的高层 restore/verify 方法会核 lease 或写 ContextUsage，不能为只读资格直接调用它们；原始请求与终态须按实际行只读复核。

原互动/后台安全限额上限为 480/1200 秒，现实五小时停等通常已越过原绝对 deadline。本片用固定 core30 业务钟和独立额度钟核资格，不证明现实过期运行可继续；后续执行必须守原 deadline，不可自动延长。历史 completed 请求版本可早于后续合法工具自写，不能强求每份历史 snapshot 都等于当前 revision 或为此改写旧请求。

## Idempotence and Recovery

本片只读，不改 account/Journal/control/业务。读取事务结束后只返回短期进程资格，后续 check 完整重读；损坏、撤销、未知或上下文改变均拒绝，不能清记录、猜零、自动重试或从 JSON 恢复 witness。实际执行与清停必须留给独立后续里程碑。

## Outcomes & Retrospective

已推 e2af97d，两个只读 helper 的唯一首链9/9通过，实际3组1+5+3；新增CI待核，未合并正式集成。唯一证据为 `private/safe-narrow-dc23bc6ef43346039ca1cb56ef968c81/metadata.json` 和同目录pytest.xml/log；既有K3宿主、已安装公开本机分词器、隔离PG、清凭据关追踪、测试时区Tokyo。原业务钟保持固定场景，只有中央额度钟到实际保存的resume_at。

实际Mock403/Retry-After生成中央与私密finished终态后闭合保存、detach/attach；到期mint/check成功仍保中央停机，原run/Journal/工具/usage/control全态不变、无新增POST/claim。早于或缺reset、实际Access更强停机、未知/缺中央记录及control/source/budget漂移均拒；构造/复制/JSON、退出后旧witness和attached send也拒绝。未知/缺记录负例明确破坏自有测试账本，不构造假的成功终态。

这不是同run执行、自动清额度、CLI续作或现实五小时后延长deadline的验收。末步骤仅quota终态历史、当前epoch覆盖全run usage、同一terminal建立当前stop等保守限制保留；reserved/intent等其它形态本轮未增加实证，不把静态拒绝扩写成已测矩阵。原完整脚本仍69/81，最终候选、Linux应用恢复及发布门未解除，真实模型/服务器/外发为零。

## 修订记录

- 2026-10-24 08:30 +08:00：根复核首次9/9原始metadata/XML与真实3组参数，记录只读资格及未覆盖/未授权边界，冻结供小提交；不重复绿、不改旧金标或执行门。
- 2026-10-24 08:13 +08:00：先记录两个只读审阅的实际字段限制与最小分片，等待代码与必要真实 PG 验证。
