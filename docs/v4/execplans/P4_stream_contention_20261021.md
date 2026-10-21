# P4：瞬时合法读锁与流式写入的有界协调

遵循`.agent/PLANS.md`，四活节持续更新，记录北京时间UTC+08。树`C:/Users/Administrator/Documents/Codex/zhiming-v4-p3-wire-p4`，本片基底`a1270174e6f64cfe1abe915a09836647c1da3484`。root11点不可变archive不含本片或联合5件；本片窄测试在工作区运行，联合5件是未提交、按原字节hash冻结的源码，不能冒充该archive。已完成窄验证，待root审查提交；联合5件继续冻结，不从一次绿推断旧跨进程超时原因。

## Purpose / Context and Orientation

真实SSE reader的authority/page与RunControl周期检查都可能短暂持有同schema/owner advisory锁；修复前timer的pg_try一次False就永久失败。这里“重试”只指同一短事务获取同一owner锁，未开始Journal/正文写，不重新请求模型、重跑工具或重造事件。目标是在既有25ms锁预算内，合法短读释放后继续真实timer提交；长占锁、取消、旧租约/版本、未知写仍fail closed。

复用`repositories.streaming_transaction.streaming_transaction`、原`StreamState._proof`、actor/inflight/stop门；只允许该仓储文件的最小修改。通用repo.transaction、Loop、Runtime、源检查、预算、联合5件及旧测试断言均不改。池50ms、语句100ms、行锁25ms、normal ack750ms与<2秒取消门不增加。

## Progress

- [x] (2026-10-21 11:00 +08:00) 只读确认合法reader/Control同owner锁与一次try永久失败机制；Clock当前为SystemClock，旧两红仍无足够时间/PG数据归因。
- [x] (2026-10-21 11:02 +08:00) root释放单窄槽后，原一次try实现上跑新增真实PG3项：2失败、1通过/2.63秒。短读释放及真实timer两例失败，首红原件保留；stop一例已通过。
- [x] (2026-10-21 11:02 +08:00) 最小实现25ms单调deadline、每次最多1ms停止Event退避；新3项与原7项合跑10通过/5.23秒。原长期占锁仍LeaseConflict/<0.3秒，旧测试原字节不改。
- [x] (2026-10-21 11:03 +08:00) 明确5文件串行窄组33通过/21.05秒，包括未提交、hash冻结的联合5件消费者；不等同11点a127不可变候选或CI成绩。随后释放测试槽，不再pytest。
- [x] (2026-10-21 11:07 +08:00) 收口时已收到root对生产helper和3新PG反例的认可；整理首红/10项/33项及源码对应证据。
- [ ] root独立提交推送本片4件，联合5件另一个提交；不合并、不部署。

## Surprises & Discoveries

RunEventReader.ensure_terminal在running时也使用owner事务与run行锁，page/authority另有短owner读事务；RunControl每250ms亦持同锁。非阻塞try第一次False可能是正常读，而非撤销/租约失效。新增透明游标只转发实际PG结果，在真正False后通知读事务释放：原实现直接LeaseConflict，真实Runtime的150ms刷新因此无delta并取消；重试后两例通过，证明本机制的可复现性。历史联合两次跨进程首delta超时没有owner acquisition记录，仍不能把它们归因于本机制。

## Decision Log

2026-10-21 11:00 / root：优先try重试、总预算不超过现25ms；停止Event.wait做小退避，到期保持原LeaseConflict。阻塞advisory超时会被现psycopg异常映射EvidenceError，不能悄悄改变旧long-lock测试的异常类型。池/语句/行锁阈值均不增加。

2026-10-21 11:00 / Codex方案：deadline在第一次真实try之前建立，后续每次尝试前/返回后均检查单调时间和stop。第一次实际False后，测试只记录该真实结果并通知合法读事务退出；不修改SQL结果，不用任意sleep制造“短”。在预算内用最多1ms Event.wait退避；超时/stop拒绝而不进入Journal或写正文。SQL/网络单次调用的绝对截止仍受既有100ms服务器语句与网络黑洞限制，不能把重试预算称全链严格25ms。

2026-10-21 11:03 / Codex：原7项文件raw SHA256仍为`8e870d8ae3bc5c76d2eda779a64952cd1c75daddf96dc5de697cfbfa20b8915f`，不以异常类型替换/阈值放宽凑绿。相关33项消费工作区中hash冻结的联合5件，记录它们的未提交身份及原件hash；不把工作区结果写成a127不可变archive或远端CI。

2026-10-21 11:07 / 收口记录：root已读生产helper和3新PG反例，认为10+33结果足够收口，不再测；先独立提交重试4件，再另交联合5件。历史两次超时未实证根因继续保留。

## Outcomes & Retrospective

真实PG首红2失败/1通过已保留；修复后10/10及相关33/33通过，Ruff/格式/尺寸和diff静态核验通过。合法短读不再由一次busy永久失败，停止第一次busy后仍不再重试或进入写入。原长锁/取消/租约/来源/未知提交门未放宽。默认候选仍关，未解决历史联合间歇的归因、取消状态不主动通知mj_run的差额，未证明网络黑洞下COMMIT绝对截止，也未宣P4完整验收、部署或供应商ready。root待提交本片4件，联合5件另交。

## Plan of Work / Validation

新增`tests/v4/streaming_integration/test_stream_contention_pg.py`。受控真实reader持owner锁并执行实际scope读；连接/游标只透传真实PG对象，在真实pg_try返回False时设置测试Event，reader据此释放。断言真实发生过busy，然后同次调用/实际actor150ms刷新继续成功、0额外模型请求。另在第一次False时设置stop，要求不再尝试、不开始写入。

原`test_stream_transaction_pg.py`长期持锁仍LeaseConflict/<0.3s、池/row/statement/stop回滚原断言保持；原timer取消/租约/来源、未知write/fallback拒绝门保持。获槽后仅上述3项→新3+旧7→worker/timer/scope/Runtime/joint明确5文件，一次一个窄进程，没有目录整库。11:03:16结束并释放槽，root禁止继续pytest。

## Idempotence / Artifacts / Dependencies

锁尚未取得前没有领域副作用，重复try不修改Journal/usage/event/operation或模型账本。锁取得后仍进入原完整证明与原子提交；取消/到期回滚释放锁。新增依赖/迁移/公开接口/Schema0。证据`docs/v4/evidence/P4/2026-10-21-stream-contention.md`列实际日志/JUnit/metadata的字节和hash，联合5件仍原样冻结。真实模型/服务器/飞书发送0；测试Asia/Tokyo，记录统一北京时间。

## 修订记录

- 2026-10-21 11:00 +08:00：root批准限25ms try重试后建独立计划，列真实PG False→读锁释放的握手反例、原长锁/取消/未知写保护和未获槽不测规则。
- 2026-10-21 11:07 +08:00：如实补首红、10/33结果、原7项未改、工作区联合5件hash冻结身份及未证明范围；交root独立提交，不追加测试。
