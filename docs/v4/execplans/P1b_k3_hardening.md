# P1b：加固 Kimi Code 错误、协议、额度与调用入口（离线首切片，阶段未完成）

本 ExecPlan 遵循 `.agent/PLANS.md`，四个活文档段落随实际证据更新。正式分支`v4/p1b-k3-hardening`于2026-10-18 17:34 +08:00从P1/P2均已合并的`v4/main@b9a89b6f84f7bebb640de080548010859aae630c`创建。工作树`C:/Users/Administrator/Documents/Codex/zhiming-v4-p1b`。已实现U37离线首切片与禁关思考配置闸门；完整阶段未完成，真实请求0。

## Purpose / Big Picture

让会员调用具备一致的错误动作、可追踪的真实 POST 计数、跨进程在途限制，以及完整工具循环推理回传。模型、评审、后台、评测和探针共享入口；错误或风控不能靠换同一会员的模型绕过。默认 v3 路由与旧业务预算保留。真实请求只在用户在本聊天明确启动相应批次或探针后执行。

额度账本是只记录时间、模型、状态与用量的持久表；在途槽位是一次HTTP请求期间占有的跨进程许可；工具循环是模型请求工具、收到结果后继续回答的同一运行。它们不改变来源授权、固定塔罗、owner隔离或送达不明不重发契约。

## Context and Orientation

设计来源：原 P1 提示词、17 号研究 §6、`docs/v4/prompts/supplements/P1b_增补_K3会员端点加固.md` 与同目录 `00_索引.md` §4a。正式基底及P2合并号为`b9a89b6f84f7bebb640de080548010859aae630c`；P2候选1444a49的CI 39114527541所有步骤成功后才合并。P1 已于 2026-10-18 合入 `v4/main@7b45a781921e6fa2e875319a12af433f0cf505b4`；P2已合并，原P1、P2阶段分支保留。

复用 `models/port.py` 的规范消息与 tool_cycle、`models/transport.py` 的 HTTP/SSE、`models/provider_diagnostics.py` 的受限公开诊断、`models/metering.py` 的物理 POST 前计数，以及 Registry 的角色解析。P2 已有迁移校验/权限授权；迁移 0008 为本阶段预留。

文件归属：主线修改已有 models/config/runner/probe 与迁移和接线；独立模块线拥有新增 `models/quota_guard.py` 核心及其单测，主线消费真实实现、审查接口、做集成，不另写假守卫抢占。P3 的上下文压缩、危机兜底、工具循环与上下文 token 守卫属于 P3；不改 web/**、P10、P8、charts/skills/knowledge。

## Progress

- [x] (2026-10-18 23:34 +08:00) U39规范消息/角色策略子片：私有完整content原序回传、独立签名/空thinking/redacted、双协议真实user边界、Kimi缺签名诊断、绑定角色与默认high未实测元数据已实现。新增5模块74项，定向363/1.36s、最终models+foundation810/65.66s通过；12Python文件静态边界通过，源码冻结。旧两fixture仅补stop，原断言不变；U38冻结13/13源hash不变。
- [ ] (2026-10-18 23:34 +08:00) U39剩余：YAML配置/采样能力启用、准确effort wire/low效果探针、用量账本effort持久字段、probe/eval报告头和P3私有消息接线尚未完成；真实供应商0，不切换实际主模型。U38中央入口/部署与人工启动门仍未闭环。

- [x] (2026-10-18 23:02 +08:00) U38中央核心首切片：0008、显式账号位置/UUID、真实PG双槽/滚动预算/份额、持久全停、逐批一用授权、人工unknown恢复已离线验证。新增79项（48真实PG/31纯契约）包含在最终models+foundation共736通过/74.13s内；Ruff指定规则、format、AST限制、UTF8 LF、diff通过，源码冻结。
- [ ] (2026-10-18 23:02 +08:00) U38集成剩余：中央DSN/schema/账号身份部署、runtime配置装载、所有物理POST入口/重试/评测/探针接线和用户在线逐批启动入口尚未完成。U39完整回传及真实256k等价仍未完成；夜间真实调用（含探针）为0。详见[核心子范围证据](../evidence/P1b/2026-10-18-u38-central-core.md)。

- [x] (2026-10-18 16:50 +08:00) 阅读 P1b、P3 增补及索引 §4a；先建立 task 草案，真实请求为 0。
- [x] (2026-10-18 17:34 +08:00) M0：P2精确头CI绿并合并，建立`v4/p1b-k3-hardening`与独立工作树，正式落盘本计划。
- [x] (2026-10-18 17:58 +08:00) M1离线首切片：78项HTTP/SSE合成分类与真实adapter边界、统一类型/动作、受限公开诊断、单层retry/fallback、typed eval停止兼容；真实供应商行为未验证。
- [x] (2026-10-18 17:58 +08:00) M2配置子项：会员K3禁关思考的静态/effective env/resolve/直接adapter闸门，合法None与非会员/非K3契约保留。
- [ ] M2剩余：U39完整推理/签名回传、effort锁定、采样移除、工具选择及1.8MB体积守卫未完成。
- [ ] M3：0008、真实 PG 用量/停止状态、消费模块线 quota_guard、所有调用入口接线。
- [ ] M4：人工分批评测与探针启动门、报告身份与 k3-256k 候选配置。
- [ ] M5：用户明确开始后运行获授权的探针/等价子集，再决定是否具备实际切换证据。
- [x] (2026-10-18 17:58 +08:00) M6本地证据：Core553/638.777s、models511/75.04s及903/944约95.66%、v4918/153.58s零skip、脚本80+48/10.72s、transport+PG92/2.72s；已写离线回执。Core时点早于最终非会员402窄改，最终models/v4另覆盖，不把日志绑定同一源码瞬间。
- [ ] M6阶段门：代码与证据由root统一发布至草稿PR #9，精确头CI未核实；保持阶段未完成，不自行合并。

- [x] (2026-10-18 18:22 +08:00) M2a离线请求预检：K3 named/none（含无tools）零POST拒绝、单工具required、纯文字省略tools、sampling_fixed最终体过滤，以及httpx实际JSON字节>1,800,000预发拒绝已完成；新增122/0.30s与8个相关既有模块244/1.22s通过。六源码/测试冻结，证据见[请求预检子范围](../evidence/P1b/2026-10-18-request-policy-slice.md)。
- [ ] (2026-10-18 18:22 +08:00) M2闭环剩余：此前17:58记录中的工具选择/体积预检已由M2a覆盖，固定采样仅能力开关实现完成、YAML启用未做；完整推理/签名、缺签名回传与计数、effort、U38/0008/全部入口、人工批门、真实探针及实际256k切换仍未完成。未重跑全量/覆盖率/CI，P1b阶段未完成。

- [x] (2026-10-18 18:29 +08:00) M2a兼容收窄：root采纳独立复核，默认1.8MB仅K3（与工具选择共用is_k3）；非K3无显式配置保留旧大包行为，显式限额/无效值仍零POST拒绝。两协议补对照后新2模块138/0.31s、相关旧8模块244/0.96s；Ruff/format/AST/diff通过，最新六文件hash见M2a证据文末。
- [ ] (2026-10-18 18:29 +08:00) M2a后续阶段边界不变：仅本子范围382项，未跑coverage/整库/PG/CI；完整U39、YAML/模型配置、U38/0008/全部入口、人工批门、真实探针及实际256k切换仍未闭环，P1b阶段未完成。

## Surprises & Discoveries

2026-10-18 / U39规范消息发现：旧flat reasoning与signature会合并多块签名、丢start初值/空文本签名/redacted/原内容顺序，不能无损重建。新增private_content规范回执作为回传依据，flat兼容视图保留，私有字段与StreamEvent数据不进入repr；原text/tool_calls与规范回执不一致时发送前拒绝。单凭cycle字符串相同仍可能带回最新user之前的旧推理，因此双协议再加真实user位置边界。

2026-10-18 / U39夹具：test_protocols.anthropic_record缺thinking stop、test_request_policy_wire.wire_model缺text stop。root逐类批准只补两条官方SSE闭合事件，全部旧断言保留。首轮343/363非全绿，补后363/363；最终810包含全部相关原保护与74新增。官方通用Anthropic签名格式不证明Kimi会员缺签名已实测接受，二者在证据中分开。

2026-10-18 / U38开工：运行配置中尚无runtime.yaml，因此先提供显式DSN/schema/account_id/ledger UUID的核心接口，不从任意业务库推断中央身份。账本部署拓扑及所有HTTP入口接线仍待后续交付；现有eval MemberBudget不冒充生产中央守卫。物理发送前持久reserve，即使进程崩溃也保守计入窗口；reserved并不谎称已确认供应商收到POST。

2026-10-18 / U38恢复发现：被杀进程的PG session锁会释放，但已reserve的结果无法确定，必须保留预算。新增显式人工close_abandoned_batch：同时持有两个空闲槽才把旧pending记unknown并结束批，不退款、不重发、不清全局stop，20分钟间隔仍持久生效。首轮Windows强杀用例清理Event曾阻塞测试退出；只停止本次pytest进程，修测试清理后多进程回归通过，未停启共享PG；两份严格匹配本次合成case/初版0008校验和的遗留schema已清理。

P1 的实际物理 POST 计数由 ContextVar hook 提供，旧 ConfiguredModel 仍是 E1/v3 默认路径。仅给 Registry 加守卫不能据此声称所有会员入口已覆盖；必须列出旧适配器、重试、评审、探针和 runner 路径并实际验证。若最窄接线超出增补列出的文件范围，先写清设计冲突与候选改法，不暗中放开范围。

旧 E1 已准备的 k3 冻结清单是历史准备物；未运行、没有成绩。新 D2 及唯一守卫生效后需重新准备可验证执行身份，不把旧清单改名为 k3-256k 实测，更不把不同模型分数直接相减。原无人值守 coordinator 已禁用。

自定义factory曾让adapter四次重试乘以Registry四轮，纯MockTransport复现16POST。现在Registry每次调用暂时将StreamingHTTP.max_retries置0并finally恢复，失败4次、成功2次、取消1次均有回归；visible后不重播、仅显式非会员fallback与总deadline保留。

HTTP402会员专项重试最初扩大到非会员，最终窄改保留非会员BadRequest/no-retry并加反例。最终models511/v4918在窄改后重跑；Core553是同切片回归过程、在该窄改前完成，不能把各日志宣称为同一瞬间源码。覆盖以903/944精确语句数记录，显示96%，95%门通过。

合成矩阵正式从ignored的tests/v4/models/fixtures候选路径移至AGENTS允许的tools/eval/fixtures/u37_error_matrix.json，78项已跟踪。内嵌source_design_sha256实际绑定task的84项派生离线设计矩阵前身，已核实92396c...；大脑原P1b提示词hash另列，不能混称。

2026-10-18 / M2a请求边界发现：JSON字符数或消息正文大小不能代替真实HTTP包体大小，中文UTF-8、转义、图片与工具schema都要计入。现在先client.build_request生成httpx最终JSON字节，再检查request.content，最后client.send同一个Request；体积拒绝、序列化失败在before_provider_request与request_count之前发生，122项新增替身测试含精确边界与零计数断言。非K3的原none/named、普通采样协议契约由相关旧测试继续保护。六文件的完整hash与具体覆盖见M2a证据；这些结果不是U38中央PG守卫证据。

2026-10-18 / M2a独立只读复核补充：共用transport默认1.8MB限额当前覆盖非K3，非K3原先的大包行为因此改变；现有非K3测试仅保护工具选择/采样字段，没有非K3大包负对照。增补D共用保护与“保留非K3旧契约”的范围由root核对；若后者含体积行为，应另行收窄并补测试。本子任务保持六文件冻结，未自行扩大修改。

2026-10-18 / M2a兼容复核已解决：首轮共用transport无条件加默认1.8MB会改变非K3原大包行为。root明确要求保留该旧契约，因此默认限制现按K3身份收窄；两协议新增“非K3默认大于1.8MB可发送”与“显式限制/无效值零POST”对照。最终httpx字节→size→meter/count→send顺序保留；源码再次冻结并通知eval只读复核。此修正没有改变缺签名、完整推理、effort或中央守卫的未完成状态。

## Decision Log

2026-10-19 07:15 +08:00 / Codex：精确头ee2e6de的Core CI唯一失败为旧test_core_memory版本断言仍固定7（553项，552通过/1失败，658.242s）；迁移0008后预期改8，迁移序列追加8，原64位checksum检查、篡改version1后initialize/verify均拒绝及fact为空断言全部保留。定向真实PG复验1 passed/0.90s；这不代表完整CI已恢复绿，修复头需另等结果。

2026-10-18 / U39决定：内容按原index/原block类型与字段保存，thinking签名不解释不拼接后重建wire；原flat拼接仅兼容旧读取方。仅会员k3/k3-256k强制同循环回传，缺/空signature按增补原样保留并计响应缺签名与出站待回传计数；非K3仍缺签名拒绝。只接受本项目使用的text/thinking/redacted_thinking/tool_use，未闭合/重复index/错类型delta不能形成完整回执。OpenAI保留reasoning字符串及显式空字符串，供应商原tool ID不改。

2026-10-18 / U39 effort决定：已核Kimi会员模型页默认high；开放平台默认/Claude工具映射不能冒充会员Anthropic准确wire实测。暂不发thinking、旧1024 budget或猜测effort参数，primary/critic及其他角色统一server_default/high，记录effort_verified=false。Registry绑定角色，K3运行前再拒禁思考/低档或未知effort/角色越界；非K3维持旧配置合同。声明是离线请求策略，不称low/high已测；low档、实际wire与报告/账本接线保留未完成。详见[独立决策](../evidence/P1b/2026-10-18-u39-decisions.md)。

2026-10-18 / U38夜间最新授权覆盖前述模块线分工：root委派本P1b工作树独占实现中央guard及真实隔离PG单测，root不写此树；发现模块树同名文件即停该文件并切U39。核心必须显式核验数据库位置与固定ledger UUID，运行角色不可建账号或删除用量。默认60/20/20：critic占critic池，eval/probe与background共用后台池；交互可借空余额，非交互不可借。配置装载与可信角色路由尚未接线，测试中的低限额只收紧80上限。停止只人工解除；明确5h停止至少5h且仍需人工，风控/Access永久全停直到人工核准，不降并发继续。

2026-10-18 / U38幂等与兼容决定：本地80上限触发亦持久停止，窗口到期不自动发起新请求；人工clear/recovery与批次授权共用append-only一用ID账本，旧clear重放不影响后来新批/新stop，恢复ID不可跨batch复用。已观察到终止错误时，即使本机时钟回拨也先持久记录stop与结果，后续准入仍拒回拨。root批准只将test_p2_foundation两处当前升级预期7→8：保护的是保留旧数据和升级幂等，不是冻结发布版号；其余断言不改，新用例另保留schema7发行版拒schema8负例，0001–0007的Git对象和规范化校验和不变。

2026-10-18 / 用户明确决定与索引 §4a：D1 继续全部使用 Kimi Code 会员端点；总在途≤2。`concurrency_limited` 或 `Access terminated` 立即全局停止并置顶通知，优先于增补默认的仅降至1/暂停后台24小时。停止必须持久化，不自动换 key/同会员模型或定时探针恢复。

2026-10-18 / 用户决定：E1/E2 只在用户在线且本聊天明确“开始 E1/E2 第 N 批”后执行，每批≤10；夜间不发任何真实模型请求（含探针）。探针同样等用户“开始”。旧15号的自动续跑不能替代逐批授权。窗口仍≤80真实POST/5小时，目标、评审、探针、内部重试共同计数；20分钟间隔仍执行。没有授权只做离线 MockTransport 和真实隔离PG检查。

2026-10-18 / D2：主模型与评审目标均为 k3-256k，保留独立上下文。切换前要求≤20次等价子集；当前未获探针启动授权，因此只准备配置/验证门，不能宣布已实测等价或已在网站切换。新模型/effort/协议作为独立报告身份，P0 k3 成绩不直接相减。

2026-10-18 / D2上下文附加要求写入P3：目标约30k token，>120k压缩旧层，输入硬上限180k，单工具>8k摘要；每次写用量账本，连续3次>60k在汇总提醒。P1b提供输入/缓存/输出用量与错误，P3负责装配/压缩与不丢关键约束；缺供应商用量记null，不伪造精确token数。

2026-10-18 / D3-D5：准确时辰优先time_basis核对，事件反推低优先且不外部名人评测；使用时长提醒默认关闭，不登记紧急联系人；E2只跑2025子集。P1b不越界实现P7/P8，只在报告与调度入口保留这些边界。

2026-10-18 / 迁移：0008_model_usage由P1b独占，P5对应0009/0010，退役LangGraph0011。只新增顺序迁移，不修改0001–0007；若已知链机制出现真实冲突，记待决并切换其他里程碑。

2026-10-18 / Codex离线首切片：旧“一律会员429/正文quota即额度停”的断言按P1b§A替换为状态/type优先；继续保留严格403公开句1POST、隐私、取消/deadline、visible不重播、旧v3一次业务charge与repair不重开。PG shim分别测403=1物理POST、429=4物理POST；初跑430通过/1失败不计绿，修后全量重跑。非会员HTTP402保留旧BadRequest，不把会员60秒重试扩散。

2026-10-18 / Codex验收边界：本切片仅完成离线U37和U39禁关思考子项。U38中央PG账本/槽位/持久stop、U39完整回传、effort/采样/体积/工具选择、人工批次代码门、探针和实际256k切换均未完成。ErrorActions标记并非PG执行结果；最终分支ref/PR/CI由root发布后核实，不能以本地成绩宣称整阶段完成。

2026-10-18 / M2a子范围决定：只新增request_policy.py与两个test_request_policy*.py，窄改两协议和transport，不改errors/YAML/Registry/旧适配器、U38、迁移或冻结E1来源。K3工具选择在消息编码前检查，即使没有tools也拒绝非法choice；单工具required仍服从原caps，不伪造能力。sampling_fixed=true才过滤最终temperature/top_p，不在本子项翻YAML。体积默认按十进制1,800,000字节，正整数settings.max_request_bytes可配置，非法限制失败关闭；采用httpx实际序列化而非近似估算。文件首次exclusive创建、后写先核SHA256；源码验证后冻结，提交/发布归root，未经真实探针不宣称供应商协议与模型切换已验收。

2026-10-18 / root决定：P1b K3专项的默认体积保护与工具选择必须共用同一is_k3谓词，不无声新增全供应商默认限制。非K3仅显式max_request_bytes才检查；显式None等无效值不能被当作缺失而放过。按此最小改动补两协议对照，不改YAML/Registry/旧适配器/模块守卫；此前默认全端口的解释作为历史保留，当前以兼容收窄为准。

## Outcomes & Retrospective

2026-10-18 23:34 +08:00 / U39子片可独立审查：以U38本机提交2cb0277a282431ddcf7d8392fd885ce1c8eff41b（远端等价18352da4）为基底，5端口/codec/helper、2旧fixture闭合增补与5新测试已冻结；最终810/810通过65.66s，新增74项均在内，Ruff完整规则/format120/AST/UTF8 LF/diff通过。精确来源见[结构化记录](../evidence/P1b/u39-turn-validation-2026-10-18.json)，命令/§11边界见[子片回执](../evidence/P1b/2026-10-18-u39-turn-slice.md)。没有修改模型YAML、旧适配器、U38源码、P3或服务器；probe/eval头/账本effort/真实效果/全入口/部署仍未完成，不能宣称整个U39或P1b验收。当前未提交，由root统一发布。

2026-10-18 23:02 +08:00 / U38核心可独立验收：最终P2 Core解释器在P1b cwd运行models+foundation为736/736、74.13s、0skip，其中新增6模块79项（48真实隔离PG、31纯契约）。同账号三进程/第三个零POST拒绝、进程重启stop、滚动80保守reserve、降权角色、迁移8、人工unknown恢复和操作ID重放均有证据。源码/测试13文件hash与静态核验见[结构化记录](../evidence/P1b/u38-central-core-validation-2026-10-18.json)，命令和边界见[§11子范围回执](../evidence/P1b/2026-10-18-u38-central-core.md)。此前42/33.45和733/70.15是中间源码验证，不能替代最终身份。未跑整库Core/v4、coverage、scripted评测、CI或真实供应商；全入口/中央部署/人工启动入口/U39/256k切换均未完成，不把U38核心成绩称整阶段完成。未提交/推送/合并，交root统一核对发布。

离线首切片已有生产代码与证据：本地代码2cf6b1f1edefac46e2b5d035484713326eacf7d0，等价远端不可变代码对象be8119e475034306681b6d168ab49073b2a23b76，代码tree ff652a9d1e4a8b64cd83e364aebf10be1234cb47。U37分类/当前链动作、统一retry/fallback、typed eval停止及禁关思考配置闸门已离线验证。Core553、models511/约95.66%、v4918、脚本80+48、transport/PG92的结果与源码时点见 [离线验证说明](../evidence/P1b/2026-10-18-offline-slice.md) 和 [结构化证明](../evidence/P1b/offline-validation-2026-10-18.json)。

阶段未完成，当前没有新迁移、U38中央持久守卫、完整U39或真实探针结果；没有实际256k切换。旧E1自动入口仍禁用，旧k3冻结仅历史未运行；后续新256k来源另建身份。代码与证据随本提交统一发布至草稿PR #9，精确头CI待核验，当前不合并。回执 [receipt-daytime-2026-10-18.md](../evidence/P1b/receipt-daytime-2026-10-18.md) 逐项列明剩余，避免离线全绿被误读为完整验收。

2026-10-18 18:22 +08:00 / M2a新增结果：基底及测试时HEAD为a0788aaf86fb278e95cd9a9c174b8fa877862dde，六个未提交源码/测试hash锁定在[2026-10-18-request-policy-slice.md](../evidence/P1b/2026-10-18-request-policy-slice.md)。新增122项/0.30s、相关既有244项/1.22s及Ruff/format/AST限制/UTF8 LF/diff检查通过；仅MockTransport、指定P2 Core、清空凭据并关追踪。未跑coverage，本次无新增覆盖率数字；不能借用先前95.6568%或全量日志作为M2a后的重新证明。U38、完整U39、YAML/模型配置、人工批门、探针与实际256k切换仍未闭环，P1b阶段未完成。

2026-10-18 18:29 +08:00 / M2a最新复验：默认体积限制已收窄至K3，非K3默认大包兼容与显式限制失败关闭均有两协议证据。新2模块138通过/0.31s、相关旧8模块244通过/0.96s，Ruff/format/AST/UTF8 LF/diff均通过；最新六源码/测试hash和具体结果追加在[M2a证据文末](../evidence/P1b/2026-10-18-request-policy-slice.md)。首轮122/244及旧hash保留为历史，不当作最新源码身份。未跑coverage/整库/PG/CI，U38/完整U39/人工批门/模型切换仍未闭环，阶段未完成；提交发布归root，独立eval复核已通知、结论待回报。

## Plan of Work

M1以官方原文或历史受限公开诊断为错误夹具依据。403保留严格permission_error+usage limit规则并扩展monthly/concurrency/access terminated；402一次60秒重试、429按rate/overload退避、400区分reasoning/size/token/content，流式同分类。诊断只留允许字段与审核过的公开提示，不能把任意响应前240字带出边界。所有终止型错误不重试/不换同会员模型。

M2先查官方 Kimi/Anthropic effort 字段；不能凭猜测新增参数，缺文档且无授权探针时采用服务端默认high并明确fast未验证low。会员k3*禁关思考；固定采样不发temperature/top_p。工具循环回传原始完整规范助手消息及推理/签名，新真实用户轮关闭旧循环；缺签名只计数，真实效果等待授权探针。禁止named/none且0请求，纯文字不带tools，单工具强制required。请求序列化>1.8MB预发拒绝。

M3用量表每个物理POST一次（含失败与重试），无正文；PG专用连接持有会话advisory槽，交互预留一槽，其他通道一槽，总在途≤2，不能持owner业务事务跨网络。预算份额/借用用真实并发PG验证；monthly、风控、Access terminated全局持久停，人工解除是显式操作。部署授权同步新表。接口guard.acquire/status/critic_allowed/background_allowed，与模块线真实代码核对后接线，不编造通过。

M4评测执行单批即返回，不通过--follow或定时器继续下一批；用户授权批号、场景上限、已完成场景、执行身份和共享账本绑定，重启不自动开新批。替身测试证明无启动授权0POST、批≤10、批间隔及80窗口保护。旧报告/基线不可覆盖。新增background角色仍用会员；主/评审256k候选有明确验证门，环境model覆盖不得静默退回k3或关思考。

M5用户明确启动后，按每次具体授权执行探针，非自动串跑所有suite。E1-E4总上限40、等价子集≤20且合计真实窗口≤80，所有探针经过守卫。正文不入探针日志，只记工具完成/参数核验/签名/缓存/用量。没有结果写未验证；变差/缺签名失败记待大脑，不私换模型。

## Concrete Steps

本切片已执行离线检查，以下为可复验入口；精确结果与源码时点见evidence/P1b，不将命令列表当额外成绩：

    python -m pytest tests/v4/models -q
    python -m coverage run --source=mingjing_core.models -m pytest tests/v4/models -q
    python -m coverage report --fail-under=95
    python -m unittest discover -s tests -p 'test_core*.py'
    python -m pytest tests/v4 -q
    python tools/eval/runner.py --mode scripted --target fake --self-test
    python -m ruff check <新增和修改的现代文件> --select E,F,I,B,UP,SIM --line-length 120
    python -m ruff format --check --line-length 120 <新增和修改的现代文件>
    git diff --check

PG明确core_test_main/127.0.0.1:55480，测试每例独立schema；Core/Charts环境隔离，清空Kimi/Moonshot钥及追踪。以上测试不能触发真实HTTP。任何真实探针命令只在用户明确开始后记录具体批次，不在计划中放自动可运行循环。

## Validation and Acceptance

增补八项逐项保留：错误→类型→动作实测表；真实PG三调用最多两在途（风控后全停）；月额度跨进程持久全停与人工解除；禁关思考拒启动；E1–E4探针真实结论；所有runner物理调用在用量表且lane=eval；CI及模型覆盖率≥P1约95%；计划与§11回执。D1持久全停/人工批门、D2新模型身份及上下文账本映射还须分别落地并补回归。未获得真实启动授权时第五项标未验证，不能宣布整阶段完成。

对应19号候选场景K01–K03、K05的端口/守卫部分；07原有L01、X03–X05保持旧协议、恢复、取消回归。真实场景新定义归v2.3候选，不修改已冻结v2.1八十场景或分数。

## Idempotence and Recovery

后续M3的用量写入与请求预留必须有稳定attempt_id，崩溃不能释放预算重发绕计数；在途槽由PG连接死亡释放，停止标志持久保留。重试每次都单独记数，排队未POST不当作已完成请求。这些PG守卫与迁移要求尚未实施；迁移只能先在合成库前向验证，旧版本拒不认识schema。回滚先停新入口/owner回v3，实际stage迁移与生产回滚另需具体授权，本轮不执行。

## Artifacts and Notes

正式产物为本ExecPlan及evidence/P1b/2026-10-18-offline-slice.md、offline-validation-2026-10-18.json、receipt-daytime-2026-10-18.md；探针报告尚未生成。task旧草案保留为历史。最终提交/发布/PR与CI由root负责，文档编辑者不自行操作。待用户：每次探针/评测开始；待大脑：实际协议/范围冲突及探针变差；待模块线：quota_guard核心接口交接。所有问题写汇总后继续独立离线工作，不等待。

## Interfaces and Dependencies

依赖P1/P2合并；与P3并行，P3的正式守卫接入里程碑要等P1b合并。quota_guard核心由模块线供给，主线负责真实PG集成、迁移、Registry/物理POST接线及人工执行门。模型用量与安全错误不包含任何用户原话、思考正文、请求/响应、key或完整DSN。

## U37首切片接口与旧测试替换依据

统一纯分类器`classify_error(status, payload, membership=..., surface=...)`返回旧ModelUnavailable兼容异常，新增受控kind与不可变ErrorActions。只读取完整嵌套error外壳；HTTP与SSE共表，SSE没有状态不捏造429。ModelPermissionError采用旧ModelPermissionDenied同类别名。公开诊断只保留审计句，不把任意响应前240字导出；新错误的原始正文不留在异常/日志。

主线拆分所有权：分类代理只改errors.py/provider_diagnostics.py/error_classification.py及新矩阵测试；root改transport.py/registry.py及下游eval兼容。模块线独占quota_guard.py。重试只在一个层执行：Registry构造adapter max_retries=0；直用adapter按同一ErrorActions执行。会员HTTP402最多2尝试（60s一次），非会员HTTP402为BadRequest且不重试；429/5xx/网络最多4尝试（1/3/9加抖动），总deadline/取消/可见输出进一步收紧。global_stop优先，无自动同会员fallback；没有PG接线时不能声称跨进程全停已经实施。

Decision Log补充（2026-10-18/Codex）：旧test_membership_quota_never_retry的429和500正文quota、streamed membership rate-limit和unreadable429断言保护旧“一律额度停”行为。P1b §A明确替换为状态优先的rate/transient动作；只修改这些已被新设计替代的断言，保留真实403额度1POST、隐私、取消、总deadline、不在已可见输出后重播的保护。Registry旧503两尝试用例按同一明确退避预算更新，不保留嵌套两套重试。84个先行矩阵中的未官方证实文案标格式推定，不称录制响应。

中心账本拓扑（后续M3）：所有业务库/评测/探针明确共用同一ledger DSN/schema/account scope；PG advisory锁仅DB内有效，不能各业务DB建独立守卫。拟用独立本机无正文账本数据库，配置固定ledger identity，缺配置失败关闭。每个物理attempt先预留、结束后终结，不能一complete只算一次或多层重复acquire。具体数据库/迁移安装仍未实施；不把方案当验收。

2026-10-18 / Codex：旧Anthropic流式quota正例只有无类型message=quota，按新状态/error.type优先及回显隐私规则不足以证明额度。正例换成保留已审计的permission_error+5h公开句；新unknown SSE含quota/429回显的负例单独断言不猜状态、不重试。旧probe额度夹具由429换成真实403公开额度句，仍保护恰1POST和无正文输出，429退避另由新动作测试覆盖。

2026-10-18 / Codex：合成78项HTTP/SSE矩阵放tools/eval/fixtures/u37_error_matrix.json，遵守AGENTS合成夹具路径；不强制加入被gitignore保护的tests/v4/models/fixtures。其余6项transport/local归实际执行测试，不能把纯分类通过当成PG持久全停完成。

2026-10-18 / Codex：完整模型覆盖初跑430通过/1失败，失败为旧真实PG shim仍用429冒充quota。将其参数化为403公开额度句=1物理POST、429 rate=4物理POST，同时都保留1个旧v3业务charge、失败终态、repair不重开；这区分供应商物理重试与旧业务预算，不削弱预算或服务真实路径。初次96%覆盖不计作通过，修后完整重跑。

2026-10-18 / Codex：402会员验证60秒重试仅限membership提供方，非会员402保留原ModelBadRequest且不重试；避免把Kimi专项动作扩到其他供应商。新增非会员反例；真实供应商兼容/探针仍未执行。

## 修订记录

- 2026-10-18 17:11 +08:00：建立并补全task草案，纳入18索引§4a与明确人工开始门；P1已合并、P2尚在完整回归，不抢先建正式分支。
- 2026-10-18 17:34 +08:00：P2合并后M0完成，补U37接口/动作与旧测试替换依据，中央账本仍等模块接口接线，真实请求0。
- 2026-10-18 17:58 +08:00：更新Progress、Surprises、Decision Log、Outcomes及离线首切片证据/§11回执，记录553/511/918/92/80+48和903/944语句覆盖；明确Core与最终非会员402窄改的时点差异、78项夹具迁移/派生来源、U38/U39剩余与发布CI待root，不宣称整阶段完成。
- 2026-10-18 18:22 +08:00：追加M2a请求预检子范围的四个活节及独立证据：122新增、244相关既有、六文件hash与实际命令；保留此前历史，明确U38/完整U39/模型切换、全量覆盖率及CI仍未闭环。
- 2026-10-18 18:24 +08:00：追加独立只读复核发现的非K3大包默认限额兼容边界，交root核对；源码保持冻结。
- 2026-10-18 18:29 +08:00：追加root采纳的M2a非K3兼容收窄、最新138+244复验与六文件hash；保留首轮历史，默认全端口问题已解决，完整阶段仍未完成。
