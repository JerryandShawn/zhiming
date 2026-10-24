# P3：额度恢复资格与独立精确清停转换

本活计划遵循 AGENTS 与 `.agent/PLANS.md`，北京时间，沿用指令板 v8。原资格分片分支 `v4/p3-wire-quota-resume-20261024` 从60eb8e4继续并已推e2af97d；新增精确转换在 `v4/p3-wire-quota-clear-20261024` 从ddbdc8c继续。只做本机隔离 PG 和 MockTransport，不改暂停线、模块记忆服务或金标，不发真实模型请求、访问服务器或外发。

## Purpose / Big Picture

为明确五小时额度恢复后从原场景继续建立可核验基础。已验收原片仅回答“原物理请求已可信结束为 quota_5h，明确恢复时间已到，原检查点和累计预算仍相同”这一资格问题；其eligible/check始终纯读。新增独立显式转换只消费该活资格并在精确中央事务内清同一停机，10个不同定向节点已有分轮通过证据。清停回执不授执行权，原 run 不 claim，Durable 的 attached send、普通 StepAttempts.begin 和 CLI 继续关闭。

## Context and Orientation

复用 `LifecycleControl.load`、`v4_lifecycle_state.read_private`、`BudgetStore.read_closed`、原 RequestLedger 与模型私密 attempts，以及中央 `QuotaStore.verify`。资格读取只读，不能使用会更新 last_clock_at 的 locked；新增转换在双slot之后对verify(lock=True)加账户行锁，所有断言成立后才显式写时间和清停。实际每次 usage 只有状态和 finished_at，reset_at 在 account 上，因此只接受中央仍停在同一 quota_5h 的 pre-clear 观察；已经清停不能从历史 usage 猜恢复窗口。

StepAttempts 的 authority 依赖有效 lease；本片不借用它 mint 执行权，也不为了核历史申请新 lease。必须按实际请求/Journal/中央字段只读比较同样锚点，不能把 ProviderStopped 的异常或零计数当未发送证明。

## Progress

- [x] (2026-10-24 09:52 +08:00) 唯一首链7/7、201.702秒、无失败/error/skip：09:48:55.852923–09:52:18.541869，根独立核metadata、全部7个XML节点/属性及log。唯一原件 `private/safe-narrow-d540e6a81fe348dab14723fe881ec698/metadata.json` 与同目录XML/log；Tokyo测试时区、原业务冻结钟、独立额度恢复钟、隔离PG和MockTransport，真实模型/服务器/外发0。新5节点全部成立，受重构clear影响的原rollback/commit_unknown两节点也通过；不重复原5/10其它绿。测试槽已释放，完整脚本仍69/81，未推进正式integration/feed或真实评测门。
- [x] (2026-10-24 09:48 +08:00) 8生产路径与新5节点/54行支持文件静态冻结，根及R3独立审完成，R3发现的Clock倒拨已删除并有真实到期负例；R7修累计计数/真实撤销privacy契约。新测试400行/最长48，生产最长45、均不超400；已授主线slot1唯一首链新5+原clear SQL rollback/commit_unknown两节点，普通send/CLI仍关闭，尚无测试结果。根初用K3 python跑Ruff因该env无ruff而未启动检查，已切实际core环境的ruff.exe，10文件规则/format均通过，不安装依赖。

- [x] (2026-10-24 09:36 +08:00) 新heartbeat核指令板仍v8，从已推cb2b53f clean开v4/p3-wire-quota-execute-20261024，直接做actual resume_pending。生产实现交timeparse代理，新E2E独立交R7，R3只读审接口；根持计划/Git。当时无pytest，主线两槽空；真实请求/服务器/外发0。该片已于09:52完成下面限定本机验收。
- [x] (2026-10-24 09:14 +08:00) 下一独立片在v4/p3-wire-quota-clear-20261024（ddbdc8c之后）补一次性exact-clear转换；先记设计再编码。旧eligible/check继续纯读，新增转换须先消费活witness，核原session和完整原证据，在中央同一account锁中对比原stop/reset/terminal UUID整行、原run usage/batches摘要；只清同一已到点quota_5h，不调用generic resume_delegated/clear_stop。所有实际旧batch须可信completed、无recovery关闭、session无活receipt；全账户无active batch或未闭合/unknown usage，两个中央slot均须可非阻塞取得。失败与提交结果未知均烧毁witness，不补偿、不自动重试；即便清停成功也无claim/执行/CLI权限。
- [x] (2026-10-24 09:22 +08:00) 四授权路径静态冻结：evidence328/最长44、witness165/31、新clear187/45、新测试304/36；Ruff E/F/I/B/UP/SIM、120列format/AST/尺寸均通过。根全文及最终差异审阅完成，R3独立审转换、R7独立审真实夹具均无实质阻塞。已明确stop截短batch期限，核原grant有效窗并容许同取时相等，不改原账本。仅授slot1首验1+3+4+2共10必要节点，旧9绿不重跑；尚无结果，不作已验收。
- [x] (2026-10-24 09:26 +08:00) 唯一首链9通过/1失败、无error/skip，194.933秒，09:22:13.555266–09:25:30.718734；根独立核 `private/safe-narrow-45e46776976a4633938834b9626fb190/metadata.json`及XML。唯一新成功组夹具在嵌套other.activate入栈时被原quota_mode.delegated_session拒为batch_conflict，尚未调用新clear或正常成功段；不能把9拒绝/故障绿扩成正常清停验收。原9已触达各拒绝/rollback/已COMMIT后丢ACK断言，保持证据不重跑。仅准该新测试用ExitStack保活原eligible并真实退出原session后再进入另一session，禁止patch ContextVar/生产门或放宽异常断言；静态审后只复验原1红。
- [x] (2026-10-24 09:28 +08:00) 根核最小fixture改动，生产3路径及原9节点不变；新测试311行/最大36，静态检查通过。仅原1红复验1/1、22.425秒，09:27:29.002903–09:27:52.459059，无失败/error/skip。唯一原件 `private/safe-narrow-56b805e9d02949a3839b8e0c1c395148/metadata.json`及同目录XML，根已独立核。正常真实clear、正确会话负例、一次消费与attached send拒均执行到，原状态及0新增POST断言通过。10个不同节点分两轮成立，不称同次10/10；原失败保留，槽已释放。
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

原片新增 `tests/v4/agent/test_eval_quota_resume_eligibility_pg.py`。复用真实 Durable/独立控制库/模型 attempt 测试夹具，以实际 MockTransport quota 响应与 Retry-After 产生中央和私密证据，不构造假的 stopped 字典或替代 Journal/PG。只替代传输；固定候选的 clean-checkout 边界可按现有夹具显式隔离，实际 source digest/契约/账号/位置/业务原话保持核验。

必要三组行为：真实工具完成后遇 quota，闭合保存/detach/attach；恢复钟到期后 mint/check 成功但无新增 POST、中央仍停、旧 Journal/工具/usage 不改，退出失效。其次早于/缺 reset、Access、更强停机、intent/中央未知拒绝。最后实际 control/source/预算漂移与伪造/退出 witness 拒绝；attached send 保持硬关。具体参数按真实风险最少选择，冻结后授单槽，主线最多两个测试进程。

新增转换只验 `tests/v4/agent/test_eval_quota_clear_pg.py` 的10节点：真实原session.close在mint与基线前完成，成功仅增加一个clear授权及账户停止/单调clock字段，原usage/batches、10张业务表和独立control不变；伪造/退出/非原session/重复及attached send拒。stop/terminal/source真实漂移三例、另一run七小时前reserved/已finished unknown、真实active batch污染及独立连接slot占用四例均拒且无新增写；两项故障分别在真实授权INSERT后用原PG除零回滚，以及真实COMMIT后丢ACK，后者保实际已提交状态、烧资格且不再UPDATE。反例污染只在自有测试PG，成功路径不手填终态；不复跑原9绿或扩全量。

## Decision Log

2026-10-24 09:47 +08:00：根审将成功TurnResult的model_calls/physical_model_requests定为原turn全部可信中央UUID累计数（夹具3旧+1新=4），segment_model_requests单列本段新增1，不把新port计数当原run总量。来源删除反例改走真实SourceWithdrawalService，合法清空request/私密数据后的实际Core快照是拒绝续作后的不变基线，不要求已撤销正文或旧私密证据保留。独立R3审发现resume入口回拨业务Clock到保存时刻可越过原绝对deadline；删除该回拨，沿当前原业务Clock校验，不延长原pin/deadline，并加mint后真实推进Clock过deadline的唯一必要反例。正例夹具原有冻结历法钟保持，额度钟仍独立到原reset。新增5节点加受重构clear影响的原2个SQL故障节点为拟首链，静态冻结和根审前不启动。

2026-10-24 09:36 +08:00：独立入口沿真实clear后的同call私有活opaque handoff，允许application仅在该eval恢复分支lazy引用工具侧type/消费函数，普通运行时不导入tools；公开receipt、caller dict/布尔或序列化对象不能mint执行scope。实际COMMIT和专用连接关闭/双slot释放后才能进入后续物理guard，任一不确定不补偿clear或重POST。原CoreError停止/最终提交可能触发AgentRegenerator.restart并推进epoch，因此在restart函数入口加活resume scope的NEVER拒绝，早于任何UPDATE/prepare_retry，普通无scope路径不变。

2026-10-24 09:36 +08:00：历史proof在事务外取得并不自动保障随后锁内版本。授权dd历史helper最小新增actual current_versions tuple、current_entities_sha256、revocations_sha256（仅规范键/revision及hash，无正文、始终无执行权）；双遍真实核验后返回。completed专属read token须绑定selected实例/原request+Journal/newlease，锁内重新核实际实体整行/撤销hash和真实中央UUID；begin/prepare/admitted/before_send/finished保持严格当前版本，不给普通authority历史豁免。新E2E增一个proof后真实变更反例，4个必要节点，原5/10绿不重跑。
2026-10-24 09:14 +08:00：把精确中央转换与下一执行协调器隔离实现，但不把只读资格check改为隐式写入。新增helper仅受活witness入口调用，中央事务内在所有断言与跨库重读之后才记录clear授权并更新account；批次不自动关闭、不启动新批次、未知记录不恢复。账户锁/两slot保护中央正常写入，与场景/控制库没有原子性；后续任何claim/执行仍须独立重验，不能把clear回执当permit。只做相关PG定向验真，静态审阅及根授槽之前不启动测试。
2026-10-24 08:13 +08:00：第一片只证明“可以进入将来的受审恢复门”，不清 quota、不调用 resume_delegated 或 generic clear_stop、不 claim/execute/seed/receive/requeue，不把 check 的成功解释为并发无变化或持续执行权。后续真恢复仍须在实际 admission/claim/发送前重新核全部证据。

2026-10-24 08:26 +08:00：本片最后未完成模型的全部历史 attempt 限 quota_5h，不接纳历史 ok、其它全局停机或 transient，避免把未发布成功输出重发；此前 completed 模型仍核原成功终态。中央usage无epoch字段，当前原epoch的私密锚点必须覆盖这个run全部usage；含旧epoch实际请求的run保守拒绝，不靠run_id猜归属。原请求/attempt实体另核实际subject_id，工具前缀只做原ToolResult结构验证；witness失败后注销、返回前再核registry/当前ContextVar，不能由复制上下文复活退出后的资格。

## Surprises & Discoveries

actual恢复设计确认两处额外风险：辅助来源被撤销而primary尚有效时，原Runtime的CoreError catch可合法走普通重生成并改epoch，不能靠新epoch之后拒HTTP保护同run契约；另历史proof之后仍有跨事务漂移窗口，必须锁内重读其具体当前实体与撤销摘要，不能把proof.success当持续权能。两项分别用前写拒绝与专属completed-token对齐，尚未验证。R7新fixture将既有观察测试的目标工厂换成真实Durable类，不能用观察目标换壳或手填预算；外部源撤销故障放在clear后、fresh owner事务之前，避免伪造同一持锁事务中的跨进程插写。
中央 account 无 revision，单个 usage 无 provider reset；已被清停的 account 不能还原原 reset 绑定。guard 的结束失败仍可能优先传播原 quota 异常，故异常类型不足证明中央及私密 finished 已可信落库。业务时钟与中央额度时钟分别保存，不能以宿主时间推断累计执行预算，也不能使普通生产绝对 deadline 延期。

QuotaStore.finish 对这次 usage 与 stop 使用同一个 finalizing 时间，但同类旧 stop 且 reset 未延后时会保留更早 stopped_at。本片要求精确相等，因而只接纳该原 terminal 实际建立的当前停机；并发继承/聚合旧停机保守拒绝，不用时间先后猜因果。完成模型的高层 restore/verify 方法会核 lease 或写 ContextUsage，不能为只读资格直接调用它们；原始请求与终态须按实际行只读复核。

原互动/后台安全限额上限为 480/1200 秒，现实五小时停等通常已越过原绝对 deadline。本片用固定 core30 业务钟和独立额度钟核资格，不证明现实过期运行可继续；后续执行必须守原 deadline，不可自动延长。历史 completed 请求版本可早于后续合法工具自写，不能强求每份历史 snapshot 都等于当前 revision 或为此改写旧请求。

## Idempotence and Recovery

原eligible/check只读，不改 account/Journal/control/业务。读取事务结束后只返回短期进程资格，后续 check 完整重读；损坏、撤销、未知或上下文改变均拒绝，不能清记录、猜零、自动重试或从 JSON 恢复 witness。独立clear入口一次消费活资格；任意失败、已提交但结果未知或退出上下文都不能复活。成功只写精确中央clear事务，不修改旧usage/batches/next_batch，不能自动关闭批次或领新批次。中央与业务库非原子，最后重读后撤销仍可能发生；后续claim/执行必须重新验真，不能拿无执行权回执豁免，更不能失败后补偿清停或重POST。本片显式resume_pending已接实际执行，只有本call真实clear提交/连接关闭、新claim与私有活scope才能进入；普通send和CLI仍关闭。

## Outcomes & Retrospective

已推 e2af97d，两个只读 helper 的唯一首链9/9通过，实际3组1+5+3；新增CI待核，未合并正式集成。唯一证据为 `private/safe-narrow-dc23bc6ef43346039ca1cb56ef968c81/metadata.json` 和同目录pytest.xml/log；既有K3宿主、已安装公开本机分词器、隔离PG、清凭据关追踪、测试时区Tokyo。原业务钟保持固定场景，只有中央额度钟到实际保存的resume_at。

实际Mock403/Retry-After生成中央与私密finished终态后闭合保存、detach/attach；到期mint/check成功仍保中央停机，原run/Journal/工具/usage/control全态不变、无新增POST/claim。早于或缺reset、实际Access更强停机、未知/缺中央记录及control/source/budget漂移均拒；构造/复制/JSON、退出后旧witness和attached send也拒绝。未知/缺记录负例明确破坏自有测试账本，不构造假的成功终态。

以上是原只读片结果。新增explicit exact-clear已有上述分轮10节点证据：真实原close→原活资格→精确清停，只增唯一clear授权及停止/单调clock字段；10业务表/control/usage/batches/旧grant不动且无新POST。另一run历史reserved/finished unknown、active batch和真实slot占用拒绝；真实SQL除零撤回授权与clear，真实COMMIT后ACK未知则保已提交事实、不补偿、不再UPDATE，两者均烧资格。正常清停后attached send仍拒绝，不能把clear回执当执行许可。

前述clear-only结果当时不包含同run执行。本片09:52的新5+原2故障首链7/7现已验证显式同run方法：两次真实case_update回执、revision+2、旧模型/工具/事件保持，原pending只新增一个真实UUID；成功原turn累计4、本段1，预算原段保持且新增闭合第二段，唯一native final与completed_result只读吻合；再次quota则同run/epoch原pending、新stop/闭批/两段closed/新检查点吻合。真正SourceWithdrawalService删除之后0claim/0POST、合法私密清空保持；历史证明后真实case revision漂移及活scope下再生首写前拒，0新POST/epoch；mint后当前Clock过原deadline则0clear/claim/POST、Core/中央/control全态不变。

仍未接CLI或整套core30生命周期driver，不证明现实五小时后可延长deadline。末步骤仅quota终态历史、当前epoch覆盖全run usage、同一terminal建立当前stop等保守限制保留，未验证形态不扩写成已测矩阵。原完整脚本仍69/81，最终候选、Linux应用恢复及发布门未解除，真实模型/服务器/外发为零。新增CI另核，正式integration/feed未前进。

## 实际执行里程碑（本机限定验收，CLI未接）

直接做 `DurableCore30Target.resume_pending(witness, control,binding,guard)` 独立入口，普通send/CLI仍关闭；不再增加无调用的纯证据层。拟最小接线：v4_durable薄方法、新v4_resume_pending协调器、新application/agent_model_resume活不可序列化scope，以及agent_model_attempts的completed/pending窄接缝。clear工具只增加同call私有after-commit交接，公开回执始终无权；真实clear COMMIT且专用连接关闭、双slot释放后才允许未来物理admission，不能持双slot再调用guard.acquire。是否需要RequestLedger完成验证位置或再生前拒绝接缝，先核真实调用栈再改，普通执行不变。

顺序为原session真实close→活资格fresh check→原中央exact-clear→跨库重新核原private/control/来源/epoch/完整Journal/预算/原deadline→业务事务内确认旧lease自然过期，实际claim原run并核新lease与旧request/epoch/pin/deadline不变→只在此路径mint本次执行scope→原core_observation/execution_scope与真实runtime.execute。同run不reset/seed/receive/requeue或推进epoch。跨库及claim任一未知即停，不补偿clear、不自动再claim/重POST。

完成前缀仅在本次scope内、seq小于原pending且新lease/原Journal/中央UUID全部匹配时接历史版本证明；dd helper拒外层事务，须在进入原authority事务前核，再以同一selected/newlease绑定，不给prepare/send历史版本豁免。原pending begin/prepare仅一次许可、原seq/input_fp/request hash/原logical revision及全部旧quota终态成立时追加一个真实新UUID；其它新步骤仍走旧begin。直接复用原累计BudgetStore/open、EventReceipts与工具回执，不重写旧请求/历史结果、不重做case写。成功用native_answer建真实TurnResult后冻结完成checkpoint；再次quota必须真实闭合预算与批次后保存原turn pending，未知闭合不保存假断点。

上述设计现以新5个端到端节点完成本机验证：两次case_update→quota→detach/attach/租约自然过期→同run新增一个pending UUID成功final，原工具/终态/事件身份保持且预算第二段累加；同路径再quota仅新增一个UUID、两段closed与新pending检查点/新stop吻合；clear后claim前实际来源撤销0新POST/0claim且保中央已clear事实；另核历史证明后漂移/再生拒和clear前真实deadline到期。只允许显式同call方法，不开放普通send/CLI/真实模型。

下一片直接接指定已存session的core30当前轮driver，不能把它交给会reset/close删除场景的旧evaluate_scenario路径；旧--resume报告缓存硬拒保留。待实现attach→primary_pending调用本方法/primary_complete只读→真实JudgeJournal→detach；不initialize控制库、不以report JSON作权能、不假称未来轮/整套考题已接好。报告计原run累计UUID，批次必须只加实际前后集合差与judge真实新增，避免旧3+累计4误计7，也不能将本段1标整case reused漏算；未有代码或测试。

## 修订记录

- 2026-10-24 09:52 +08:00：显式同run恢复唯一首链7/7，记录真实clear→claim→pending追加、历史只读例外、累计预算、成功/再次quota检查点及撤销/漂移/到期拒绝；Clock倒拨在运行前被独立审发现并删除。CLI仍未接，真实评测门未解除。
- 2026-10-24 09:28 +08:00：独立exact-clear分轮9+原1红通过，完整保留首夹具失败、真实回滚/未知commit及无执行权边界；根核全部原件，下一片直接接真实同run执行，不重复旧绿。
- 2026-10-24 08:30 +08:00：根复核首次9/9原始metadata/XML与真实3组参数，记录只读资格及未覆盖/未授权边界，冻结供小提交；不重复绿、不改旧金标或执行门。
- 2026-10-24 08:13 +08:00：先记录两个只读审阅的实际字段限制与最小分片，等待代码与必要真实 PG 验证。
