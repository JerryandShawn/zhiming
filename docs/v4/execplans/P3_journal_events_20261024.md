# P3：同一步骤恢复时保留公开事件身份

本活计划遵循AGENTS及`.agent/PLANS.md`；北京时间，仅隔离本机PG与替身模型，真实模型/服务器/外发0。分支`v4/p3-wire-journal-events-20261024`从已推fa23a8b继续，不覆盖其CI，不修改模块记忆或暂停线。

## Context and Orientation

复用`mingjing_core/agent/journal.py`的真实JournalStep、租约检查及稳定run/epoch/seq，复用`application/agent_runtime_events.py`的run锁、公开事件验证与落库，以及`agent/loop_batch.py`的prepare/accept调用顺序。公开契约固定为`docs/v4/contracts/events_v1.md`和对应Schema：恢复保留原seq/ts，重复事件不新增seq；合法raw call_id必须原样保留，不能用它作为整个run的去重键。

当前prepare在Journal之前发tool_call，accept在completed步骤回放时仍发tool_result；因此崩溃可产生重复，也可在工具实际完成后缺result。不能整段跳过已完成工具，也不能靠模型重发或更改公开契约掩盖。当前RuntimeEvents仅对终止类事件去重。

## Purpose / Big Picture

让实际LoopCycle在同epoch恢复时只补缺失的工具事件，原先已提交事件的JSON、seq和ts保持；真实工具副作用仍由原Journal/业务幂等保证。新epoch即使使用相同raw call_id，也保留独立事件，不能误吞。事件与私密身份收据同事务提交，损坏或隐私擦除的旧事件不能复活。

## Progress

- [x] (2026-10-24 08:06 +08:00) 第二审窄修后，仅两个既有受影响目标08:05:26–08:05:30首次2/2通过、2.45秒：真实第二事项效果提交/未确认窗口可同epoch恢复且不重写proof/旧Journal/业务修订，外部同正文新revision仍拒绝且无新模型流。原三个新绿未重跑；两轮分开记，不称一次5/5。新helper264行/最大60、Ruff/format/AST通过，全部代码再次冻结，根已复核metadata/XML，等待小提交。

- [x] (2026-10-24 08:04 +08:00) 第二只读审阅发现实际恢复回归：case_update效果已提交、Journal确认前崩溃时，旧run版本尚未注册，新started直接verify会在既有快照精确自写对账之前误拒。原三组虽通过但不覆盖此窗口，不能称收尾。获批只在verify失败分支复用既有reconcile_versions及原生set_run_dependencies，仍核精确pending-effect链、外部修订和撤销；不改既有证明或业务测试断言。后续窄修及08:06补链已完成，历史发现保留。

- [x] (2026-10-24 07:59 +08:00) 六代码路径静态冻结，根已全文审阅。新helper259行/最大函数60，新测试290行/最大54；其余四文件仅窄接线，Ruff E/F/I/B/UP/SIM、120列format及AST通过。补齐新epoch marker在已有started收据回放路径的同事务持久化、非legacy缺started半态拒绝及UTC Journal时间摘要；没有运行pytest或collect。
- [x] (2026-10-24 08:01 +08:00) 根授单测试槽后的唯一首链，07:59:56.643–08:00:00.361首次3/3通过、2.77秒、0 skip；metadata/XML已由根独立复核。两次真实崩溃缺口、真实普通retry与撤销重生成、两并发result写入，以及原event/receipt/半协议篡改和原生来源撤销的拒绝均有实证。槽已释放，六路径冻结，不追加测试或重跑；新CI待提交后核。

- [x] (2026-10-24 07:51 +08:00) 根完整读实际Journal/ToolBatch/LoopCycle/RuntimeEvents/Runtime及finalization、regeneration、privacy调用；代理只读核完10处run usage写入，均从实际锁读行merge，正常finish/retry不覆盖未知顶层字段。先写最小计划，尚未实现或测试。
- [x] typed工具事件通路与body-free私密侧账，先静态冻结根审。
- [x] 三个必要真实PG行为首次通过；第二审另只验证两个直接受影响既有目标，分轮保留，不自动重试或重复绿。
- [ ] 完成测试/根审后小提交推自己的分支；完整脚本、CLI/attached send及真实评测继续关闭。

## Plan of Work

新增一个私密receipt helper；窄改`agent_runtime_events.py`、`agent_runtime.py`、`loop_cycle.py`和`loop_batch.py`，另新增一个PG测试文件。LoopCycle只增加可选typed `tool_emit(step,kind,payload)`接缝，保普通两参emit兼容；生产Runtime注入受信RuntimeEvents工具方法，其他纯循环替身照旧。

prepare先真实next_or_replay，再调用工具事件通路；accept完成实际Journal后取真实completed step发result，回放仍核事件缺口。回执键含epoch/Journal.seq/kind，稳定call身份摘要不含后续会变的status/output；result另外核actual completed output/finished_at。每次在同owner/run事务内重读当前lease/epoch/subject、来源、取消/deadline与实际Journal；外部构造JournalStep的字段不构成授权。

在core_runs.usage新增独立私密namespace，只放版本、身份摘要、原event.seq和完整event hash，不放参数、reasoning、正文或模型结果。写入从当前锁读row merge，与事件INSERT同事务。公开payload由受信LoopCycle固定安全白名单组装，通路不是独立工具授权入口；raw call_id参与完整payload比较，但不是去重键。

started按run严格复用唯一、完整相同原事件；旧仅started可核验后采用。旧已有tool事件而无新版本/receipt时拒绝，不认领或默默重发。若receipt存在而event缺失/被擦除/hash不符，拒绝且不补造。内部AgentRegenerator新epoch仍只发原text_reset，不再_start；跨进程遇已擦除started明确拒绝，不改变原生隐私清理。

## Validation and Acceptance

仅三个必要真实PG行为：

1. 同epoch真实崩溃/reclaim，分别出现Journal已写但call缺失、真实工具已提交但result缺失；只补缺口，原JSON/seq/ts保持，实际副作用一次。
2. 走真实合法重生成的新epoch，同一合法raw call_id两组事件均保留、started不重复；同step并发写仅一个receipt/event，不靠任意改epoch伪造。
3. 原event/receipt篡改、真实来源撤销及跨owner step均拒绝，不追加或复活。只修改新测试夹具观察，不弱化既有契约。

此片支撑P3 R类恢复与X08断线场景；不据局部通过改写原80题展开81项报告或解除完整脚本门。只替代模型/传输，不替代PG、Journal、工具业务、隐私或恢复服务。主线最多2测试进程，具体三个节点冻结后才授一个槽，不跑全量或重复稳定性测试。

## Surprises & Discoveries

事项效果事务先写真实效果及私密证据/marker，Journal.complete与版本注册在其后。原AgentSnapshotStore._load会精确reconcile_versions，新的started提前强制verify却抢在该对账前，形成合法自己写入也无法恢复的静态回归；这与外部改写不同，不能通过跳过版本核验解决。公开run DTO/thread projection/SSE及core4出口已只读核对，不直出新私密namespace。

首链同epoch两个缺口分别位于Journal创建后call提交前、工具完成后result提交前；真实Scripted模型流2次、memory effect恰1次，原已保存JSON/seq/ts保持。第二组真实prepare_retry/claim保完整旧事件，原生撤销后AgentRegenerator则清旧payload、保row seq并产生新epoch；两个并发result创建只落一条收据/事件，回调可重复递送同seq。不能把Scripted流数写成真实物理HTTP次数，或把局部三个目标写成全81通过。

`public_call_id`对合法raw ID直接返回，因此同run不同epoch可合法同名。Journal.complete精确比较usage，不能把新事件receipt塞进step.usage而改变其原语义。runtime_step会增长owner revision，并在stale retry/隐私/保留清理时删除；不适合保存run级started身份。

当前10处生产core_runs.usage更新包括runtime metadata/limits、case capability/effect、context epochs/usage、regeneration、terminal error、privacy barrier/maintenance；都从当前锁读行merge。原生privacy保留usage却清Journal output和event payload，因此新namespace只能含无正文身份/hash，发现指向已清正文必须失败关闭，不借hash还原旧事件。

## Decision Log

2026-10-24 08:06 +08:00：补链只验证已发现条件分支，使用原两个业务目标及断言，不改测试适配实现。新authority先原source/lease/cancel/deadline检查，只有verify失败才走既有精确reconcile→verify→原lease依赖注册；不承认外部修订，不制造Journal确认。原三个新目标走未改变的verify成功分支，不为“再稳一次”重跑。

2026-10-24 08:04 +08:00：只在当前verify_versions失败时，调用现有严格reconcile_versions，完整验证后的结果仍须verify，最后以原leased token注册并同步当前row.state_version；失败事务不改变事件/namespace。正常三个新目标的verify成功路径不变，不重复三绿。必要受影响验证限定既有pending_chain正例[True]和external_same_body反例；原测试/证明不改，先静态冻结根审再授槽，不引入新补丁矩阵。

2026-10-24 08:01 +08:00：唯一首链3/3已足以验证获批行为，不追加宽回归、稳定性重复或覆盖率任务。保普通generic emit两参路径仅兼容，不将其说成有Journal恢复证明；新事件存储身份不赋予执行工具的权限。根只对CI现有job预算60→90做YAML语法检查，原检查和阈值不变，旧取消原因不猜。

2026-10-24 07:59 +08:00：根静态发现并在测试前收紧两处：普通retry的新epoch不能只在内存加marker后复用旧started返回；现_event核原event/hash后，仅state区别于实际锁读usage时同事务保存，正常同epoch不重复UPDATE。非legacy marker存在却缺started receipt不是合法中间态，统一拒绝，不因行也缺失而补造。Journal摘要时间显式转UTC，不能依赖PG或机器时区。第三组事务回滚篡改核原timestamp、identity及缺started半态，成功路径仍仅三组必要行为，不扩宽测。

2026-10-24 07:55 +08:00：根审补普通retry边界：实际prepare_retry/claim产生新epoch后会重新_start，不能一律拒绝缺本epoch marker。仅实际新epoch尚无Journal、原协议与完整started相同时允许原run锁内初始化；有Journal仍拒，已擦除started不补造。内部撤销后Regenerator继续私密begin_epoch/text_reset，旧event行保seq但payload被原生清空是正确行为；测试不得为了保两组完整body而削弱privacy。当前恢复键严格核实际event/hash，旧epoch只保结构/归属且不能复活，不要求每个事件都扫描全历史正文摘要。

2026-10-24 07:53 +08:00：首次started在实际run事务内建立协议marker；真实Regenerator新epoch只做私密begin_epoch，不新增公开started，须已验证实际新epoch且尚无该epoch Journal。既有marker重核而不覆盖，缺marker却有旧Journal/工具事件继续拒绝，避免将已发未知步骤认领为新协议。

本分支继承的CI总预算仍60分钟；836的v4步实际4245通过/56跳过、2198.28秒，框架替身自测48通过，后续ModelPort在07:34被取消，未取得全CI绿。取消的直接原因没有可用annotation，不能仅凭接近60分钟就断言根因。为让全部既有检查获得与已审release-prep相同的90分钟总预算，根只改workflow job timeout 60→90，不取消/重跑旧CI，不删检查或降低阈值；本机测试仍仅本片必要目标。

2026-10-24 07:51 +08:00：根采用独立run usage侧账，不加迁移、不更改0009归属、公开事件v1或raw ID规则；所有新写入在实际run锁内merge，不能复制self.run的旧usage。保护原内部撤销后重生成，严格限制跨进程已擦除旧started不能恢复；旧未知工具事件不接管。先做这片事件身份基础，不开放CLI、attached send或自动清额度停。

## Idempotence and Recovery

事件和receipt同事务，要么都有、要么都无；实际失败保留原记录，不能清空receipt或改旧event来凑相等。无receipt却有旧工具事件属未知，拒绝并记待决，不按call_id猜epoch。事件delivery callback在提交之后，断线不能回滚已保存事件；重送可复用原seq，由既有SSE游标去重。

## Outcomes & Retrospective

六代码路径已静态实现并经根审；唯一首链首次3/3、2.77秒，证据仅在`private/safe-narrow-1af23b4415624d878b1d261c100622cf/metadata.json`和同目录pytest.xml/log，07:59:56.643–08:00:00.361 +08:00、真实隔离PG、清凭据/关追踪/TZ Tokyo。实际同epoch恢复两个缺口只产生一次memory effect，普通retry与原生撤销重生成正确区分旧完整事件和被擦除行，新epoch同raw ID保独立身份，两个并发result写只存一条；原timestamp/hash/半协议损坏、跨owner和真实来源撤销均拒且不复活。新CI待核，完整同run续作/CLI/attached send和真实评测仍关闭。

第二审发现上述三组未覆盖pending case效果先提交的窗口，先窄修条件对账，再仅验证原正反两目标2/2、2.45秒；唯一证据为`private/safe-narrow-7dff8f70fce64a5e908ed2c9a7a09647/metadata.json`及同目录XML/log，08:05:26.963–08:05:30.320 +08:00。两个分轮结果不合成同次5/5，未修改原证明/业务测试或重跑前三绿；另只读复核确认公开run DTO/thread projection/SSE/core4均不直出新usage namespace。新CI及旧未知协议的全部历史形态仍未整体验证，首发门继续关闭。

累计预算在fa23已有分轮实证，源M1限定统计观察另在89c9e2a推送（新CI run40041896351在途），不合并不同轮次为同次整体全绿。当前原81题仍69/81，最终候选/Linux/中央保全/全局writer与首发门未解除，真实模型/服务器/外发0。

## 修订记录

- 2026-10-24 08:06 +08:00：记录仅受影响兼容正反两目标2/2及原三绿不重跑，根复核原始元数据后冻结供小提交；不把两个分轮结果或静态复核说成全量通过。

- 2026-10-24 08:04 +08:00：诚实记录三绿后第二审发现的pending-case恢复回归，先写既有精确对账接线和受影响正反例计划；未先提交或宣称全通过。

- 2026-10-24 08:01 +08:00：根独立复核唯一首链metadata/XML，记录3/3、真实两种新epoch与并发/擦除边界；释放槽，不重复测试，准备小提交。

- 2026-10-24 07:59 +08:00：根完整静态审阅六路径并收紧marker实际保存/半协议拒绝/UTC摘要，冻结后仅授权三个必要PG目标，未补造通过结果。

- 2026-10-24 07:55 +08:00：审阅并保合法普通retry与内部撤销重生成两类新epoch边界，区分旧完整事件和隐私擦除行，不扩大热路径或复活旧正文。

- 2026-10-24 07:53 +08:00：收紧新epoch协议初始化边界，记录836精确已通过与取消步骤；CI仅对齐既有90分钟预算，取消根因仍未知。

- 2026-10-24 07:51 +08:00：先写工具事件身份、私密原子侧账及三行为设计，保公开契约与真实隐私边界；尚未实现/测试。
