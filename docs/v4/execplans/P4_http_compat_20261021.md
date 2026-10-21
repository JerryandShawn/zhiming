# P4 M4分片：JSON入队收据、旧SSE投影与固定reading

本ExecPlan遵循`.agent/PLANS.md`。创建记录2026-10-21 10:56:29 +08:00（工具UTC 02:56:29换算北京时间）；独立P4目录`C:/Users/Administrator/Documents/Codex/zhiming-v4-p3-wire-p4`，审计基准`a1270174e6f64cfe1abe915a09836647c1da3484`。首轮仅只读代码和契约，新增本计划；随后root批准M4a并分配唯一第4窄测试位，当前已实施普通v4 JSON回执并用真实隔离PG/loopback HTTP验证。始终不修改web/**、static/**、冻结Schema或模块文件，不做真实模型/飞书/服务器操作；M4b/c/d仍只计划。

## Purpose / Big Picture

真正的新客户端可先取得本轮已持久化的user message、run、实际thread与events URL，再接冻结v1事件；Accept不能改owner运行版本或另建一次执行。旧POST流仍给旧客户端能消费的data.type形状，同时与GET冻结流读取同一PG事件，不能重复consult。core4真实回执可以有独立的legacy展示投影，但不往冻结信封里硬加memory_receipts，也不能用一个“降级对象”绕过前端对generic receipt的安全过滤。固定塔罗解读需绑定原draw/reading及真实来源、同一执行的成功结果；当前诚实拒绝只有在完整桥验证后才能解除。

## Progress

- [x] (2026-10-21 10:56:29 +08:00) 完整读P4提示词、28§3冻结表、core4/events契约、chat/stream/retry/resume/reading路由与相关持久调用方。
- [x] 同时核对旧static sendChat/recoverTurn/evidenceHtml/history/tarot reader，以及前端线实际生产transport/normalizeEnvelope/严格wire与模拟followV2；只读，不发跨聊天消息。
- [x] 列出原断言保护与一处P3临时协议断言/P4目标冲突、最小分片、内容协商和前端交接边界。
- [x] (2026-10-21 11:09:11 +08:00) root批准并实施M4a最小后端：纯Accept协商、只读运行pin共用解析、真实source/run/thread回执；默认/SSE行为保持原样。其它分片未解锁。
- [x] 新三目标首轮59 passed/17.04s；增加实际v3回退与inbox socket后，新目标与原thread/runtime两个文件合计80 passed/25.86s，1既有Starlette弃用warning。新61项中40纯、21真实PG（其中14实际socket），全部TZ=Asia/Tokyo/Scripted或FixtureModel/loopback trust_env=False。
- [ ] M4b旧流投影、M4c真实memory事件、M4d固定reading与实际DOM联合验收未实施；M4尚不验收。

## Context and Orientation / 当前事实

`adapters/web.py::chat`完全未读Accept，submit后总调stream；runtime v4时stream直接返回冻结命名事件，v3仍旧data.type started/context/status/result/error/[DONE]。`thread_routes.run_projection`已返回run_id/thread_id/status/runtime/run_url，v4另有events_url，缺本轮原话message_id。`RunEventReader`明确只支持v4；现v3没有可诚实填入的冻结events URL。RuntimeAssembly根据已存在operation的pin或owner持久settings选版本，普通submit继续拒v4附件/固定draw/reading/报告/parent输入。

`ThreadIngress.submit`先以真实用户输入/隐私路由保存source，再原子queue；返回的run.thread_id可能已由“开无痕”改成新实际线程。运行中补充会得到自己的inbox_wait备用run，主run真正采用后recover把备用run标cancelled，未采用则queued；目前公开run投影没有“采用到哪个父run”的语义。不能把parent run_id冒充这个新消息的run_id，也不能假造一个永远没有final的跟随URL。

`read_result`严格区分core3/core4；core4通过EnvelopeV1后仅允许answer等已冻结兼容字段，没有memory_receipts。history_window、GET chat.meta、GET run.result、Tarot.finish_reading、Outbox/Hermes分别使用这个真实投影或原已提交信封。旧static evidenceHtml只看memory_receipts，sendChat只解析data行中的event.type；命名事件data没有type时会忽略，再经recoverTurn查完整结果。旧DOM现真实正文恢复可用，真实回执仍strict xfail，不能说“整页不显示”，也不能删除这个缺口。

前端线只读HEAD `7d8e26d93b2dd35106d6a740255d822febb5ccca`：`web/src/chat/useChat.ts`生产仍调executeV3；transport POST显式Accept:text/event-stream，consumeV3不把frame.event交chatEvent。followV2注明候选、尚未接生产，night/recovery为合成端口。`normalizeEnvelope`对core4的generic PublicReceipt有意不造记忆卡（缺summary/授权/undo上下文），真实memory_receipt事件才是卡片上下文。新tarot/readings同样消费旧started/status/result并靠reading_id/持久版本确认。10:56只读status显示前端日报/周计划与Stability证据在途，未见这批已读消费源变更；不把本机HEAD当GitHub/CI新结论。

当前主线全树除Schema/encoder注册外没有memory_receipt事件生产者，Loop/Runtime只发tool结果/正文/final等；不能把“类型存在”或core4 receipts列表当即时记忆事件已接。固定reading路由在begin_reading前明确拒v4；即使删此拒绝，通用submit_agent仍拒draw_id/reading_id/mode。v4 dispatcher调用RuntimeAssembly.execute，绕过web.execute的finish_reading回调，故只改HTTP不会产生成功reading。

## Surprises & Discoveries

有三处必须保持诚实：默认v3没有新events端点；inbox_wait的实际子run不能简单套“queued→final”；generic core4 PublicReceipt不够授权前端的富记忆交互。M4a能先做普通v4入队收据，但这些边界须显式拒绝/表示真实状态或另片补，不用Accept偷偷升级runtime、不给消息/URL编造来源。

旧static历史只用m.meta/context_meta；现读取端测试明确要求chat.meta/history.meta与规范core4结果相同。在这些对象里加memory_receipts会同时破坏冻结Schema和原读取断言。新加outer legacy_view也不会自动被未修改的旧JS读取，所以“当前流看得到回执、历史看不到”仍不算修复。旧strict xfail只有current/history两边都0时是预期，部分修成[1,0]会是实际失败；两边真实通过后也需root审核移除期待失败标记，保留[1,1]断言，不能先删它美化分数。

另一处原临时协议断言：`test_thread_routes_pg.py::test_compat_chat_opted_in_v4_uses_new_events_and_rejects_private_hint`默认POST期待named final；这与P4明确要求旧POST保留旧data.type协议冲突。将来实施必须请root批准把此测试拆成“默认legacy result”与“显式JSON→GET冻结final”，保留隐私提示拒绝/零原话落盘/单次真实执行/真实core4结果断言。当前不改旧测试来迁就新代码。

## Decision Log / 拟技术裁定，待root批准

2026-10-21 11:09:11 +08:00实施裁定：root批准M4a限于普通chat的实际v4 JSON202与线程API消息ID。JSON/SSE同最高q时显式JSON优先；非法或重复q固定中文406，具体q=0不会被通配复活。认证先于Accept解析保持原401；实际v3 JSON-only在ensure_owner、图片目录、原话/运行写入前406，混合可接受SSE则照原v3流。持久operation pin优于当前设置，Accept绝不修改runtime；只读preflight与submit在同owner事务锁内以防并发切设置。仅已安装dispatcher、真实受信meter/显式离线Scripted才能接JSON；未配置不落原话且不退回legacy。

接收回执在source/run/thread事务真实提交后返回，当前status为该事务快照，不承诺HTTP到达瞬间后台仍停在queued。回执只给body-free ID/状态/相对URL，来源由PG重读并核subject、thread、原话policy、撤销及source_segments。运行中补充的inbox_wait明确返回**自己的**message_id/run_id/status/events_url；其父真正采用后这个备用run可被cancelled，当前ACK不提供adopted_by或父final跳转，不能由客户端把自己的events_url视为必得final的承诺。自然无痕返回实际新thread；幂等旧run依旧原pin/原source不重建。

分成M4a入队协商、M4b旧协议/展示投影、M4c真实memory事件、M4d固定reading。原提示词要全部完成才能P4验收，先做小片不把余项消失。HTTP纯解析不触模型，所有runtime/owner/subject/source/reading来自服务端持久状态；Accept只选择表示格式。

M4a建议JSON只对实际已安装的v4运行返回202（新请求先核runtime/dispatcher/meter；幂等旧请求尊重原run pin）。实际v3暂不支持新冻结events URL，若客户端只接受JSON则在保存任何原话/图片之前406固定提示；v3默认/显式SSE完全保持。此为范围建议，不是已落实产品行为，root也可批准另做v3新事件适配；不能用本片默默代替该工作。

回执JSON必须为已提交run里的source_message_id/实际thread_id，不能用request_id或模型字段充当message_id，不预先分配临时ID。incognito切换、幂等、原source撤销、subject隔离都重核；failed/stale/succeeded幂等请求如返回回执要给实际status，不自动retry。inbox_wait返回真实状态/本消息ID，父run关联与实际follow策略须独立受信投影、同owner/subject/thread验证后root冻结ack草案；未解决前不把它算普通跟随已完成。

## 内容协商方案 / 不改变执行选择

GET `/api/runs/{id}/events`始终冻结v1，不接legacy格式。POST chat/未来reading/retry/resume共用受控协商器；必须在save_images/receive/begin_reading/submit之前判断不支持的表示，防“报406却已写入”。建议有界解析Accept（固定小长度/数量）、标准q 0–1且最多3位小数，不用substring匹配json或接受NaN。错误只固定中文，不回显原header。

| POST Accept | 拟表示 |
| --- | --- |
| 缺省、`*/*`或显式text/event-stream | 默认旧data.type SSE |
| 显式application/json且q>0、其质量最高 | v4持久入队202 + run_id/message_id/thread_id/events_url/status/runtime |
| JSON与SSE同最高质量 | 显式JSON代表新客户端opt-in，建议选JSON；root可裁定，必须测试固定 |
| application/json;q=0 | 不选JSON；若SSE仍可接受则旧SSE，否则406 |
| SSE明确q=0且无可用JSON，或只支持其它media | 406且零写入 |

更具体media的q=0不能被通配符重新开启。application/*、vendor+json不能靠包含“json”自动启用新握手；不能因Content-Type=application/json把所有旧客户端误切到JSON。重复/格式非法q采用固定拒绝策略，不记录header正文。JSON带Vary:Accept与Cache-Control:no-store，SSE保留原no-cache/X-Accel-Buffering:no，鉴权不变。旧客户端当前不会发JSON opt-in，不能靠User-Agent或测试transport特判它。

## Plan of Work / 最小backend接点建议

### M4a：真实入队收据

建议新`adapters/http_negotiation.py`处理纯协商；新`application/run_acceptance.py`构造body-free受信ack，按当前owner/run/source/thread/原operation重核。最小改web.chat返回分支和thread_routes.run_projection共用ack，增加真实source message_id；唤醒已安装dispatcher但不在请求内等待结果。v3旧队列仍由原worker负责，不被新分支关掉；owner设置不修改。

`runtime_assembly.route_submit`已有幂等pin选择，不复制一套可能分叉的规则；如需零写入preflight，新增只读受信resolve helper并两处共用。POST header不准绑定eval/probe scope或开启真实provider；所有测试只显式ScriptedPort+合成meter。ack拒缺失/已撤source，不从请求正文猜ID。前端获得明确信号后才可切新transport，backend不编辑其文件。

### M4b：旧SSE与信封外legacy view

建议新`adapters/legacy_run_events.py`和`application/legacy_result_view.py`，最小抽出thread_events已有授权page→hint→page循环为共享迭代器；named encoder与legacy投影共用同一事件/游标/退订门，不能再consult/claim一次，不再造第二正文Hub。root需另授shared-reader接点，不碰已冻结源码直到批准。

started从持久run投影run_id/turn_id、可用thread/message以及真实reading/draw IDs；context只给原许可安全元数据；status/tool进度用原人类摘要。final在真实提交后转`data:{type:'result', result:<规范读取结果>, reading_id?,draw_id?}`，停止后error用固定中文；结束一次[DONE]。中间text_delta/reset等可作为额外legacy平面type事件供新React reader消费，旧static会忽略，不能向它发送“未提交result”来骗出逐字效果。平面事件不能保留v=1再硬添type，否则新FE会按严格wire解析却缺named event，仍被拒；冻结GET帧不受影响。

legacy_view只从已验证core3/core4和真实提交回执生成，作为**外层展示对象**，例如HTTP outer `legacy_view`或history row的并列字段；canonical envelope/meta/result保持原值，不加memory_receipts，不把core4重标core3。对旧显示的memory_receipts只允许真正fact/proposal记忆回执，不能把case/note/draw/profile等所有saved命令算“保存长期记忆”，没有summary/undo授权就不补造。是否对旧view加具体安全summary须单独受信证据，不能从模型保存宣称推断。

因为现旧static不读外层view，历史展示适配必须交前端/旧页面所有者改调用点并共同实测；本backend候选不能宣称单独修好了strict xfail。保持GET chat.meta、GET run.result、history.meta、Tarot/Outbox/Hermes的规范对象原样；不要为了让UI出现按钮改变这些已保护的读取契约。

### M4c：真实memory_receipt生产与展示交接

这是独立技术缺口，建议新受信`application/memory_receipt_events.py`：只在当前run/epoch、真正completed工具步骤/精确mutation回执及实体/原话授权核验后发送已冻结memory_receipt。saved、pending_confirm、undone、rejected要由实际状态映射；summary来自经核的安全公开投影，sensitive来自可信分类，undo_token仅已有真实能力才给，绝不造token。工具自写导致clean epoch、崩溃恢复、源撤销与取消都要与原Journal/lease门协调，不能无证重放成saved。

不让普通tool_result的generic PublicReceipt自动变富记忆卡。实时事件与最终规范receipt仍是不同投影；历史没有实时上下文时要有受审展示来源或明确缺失。新FE现有过滤是安全边界，不通过删schema标识伪装legacy绕它。此slice可能需要Loop完成后的小接点，但当前只计划，Runtime/Loop/timer仍归root/对应作者。

### M4d：固定塔罗reading真正闭环

建议新`application/tarot_reading_ingress.py`及`tarot_reading_completion.py`，先读真实TarotService.get_for_reading并核owner/subject/case、ready/完整揭牌、deck/meaning/cards/版本/未撤销；保留当前旧v3路径，v4通用submit仍拒客户端任意draw/reading字段。专用受信入口才可把服务器核过的draw_id/实际begin_reading ID装入run，原操作稳定指纹必须包括supplement与depth等实际输入，重复不同输入冲突而不是变版本。不得重新shuffle/create_draw或绕U7。

来源桥不能把服务端拼接的“请解读+旧问题+背景”冒充新的用户原话。实际补充保存原文，question/source_refs/fact_ids来自原draw snapshot且逐项核版本/撤销；无补充的显式点击应有受审web-action来源契约，或安全引用已存在的真实问题来源，后者要核对history同source多run归属，不能随便复用导致by_source覆盖。这里需root审具体消息/来源接口后实施，不预填假source IDs。

旧draw snapshot常含background/facts、缺精确range，现question_sources会拒注册c/r并保留legacy只读；不得重写冻结snapshot来假造完整专业依据。专用reading最终提交应要求真实当前epoch完成tarot_read与原固定牌面匹配，不能只把draw ID塞request就当模型确实用过牌。完整来源不足时沿既有诚实无c/r边界或拒需要专业引用的输出，保留TA02真实恢复约束。

完成钩子必须覆盖dispatcher实际RuntimeAssembly.execute与直接执行（不是只web.execute）：core4真正提交后将**原始持久信封**交finish_reading；当前finish已经核同run/reading/draw、result逐字相等、依赖当前有效，不可传legacy view。postcommit失败可幂等修复同reading而不再发模型；cancel/failure保留牌、回写真实失败/停止状态。HTTP断线不能停掉后台完成或新开reading；重试恢复原version/id。服务端reading ID放legacy started/JSON ack外层，冻结started Schema不加reading_id。

## Validation and Acceptance / 尚未执行

M4a用真实阻塞ScriptedPort证明202在模型放行前到达，ID能在PG逐项查到、源/线程/subject正确、无临时ID；同request不同Accept仍单source/run/预算，inbox/自动无痕不会返回旧thread或伪父run。无agent/meter/dispatcher、JSON-only v3、unsupported media、图片/固定draw通用输入在预定零写入门诚实拒绝。Accept质量/通配/显式q0/边界与Vary/no-store有纯测试。

M4b用真实socket同一个run的旧POST流、GET冻结流、recover与history，证明相同最终原件、无第二provider调用、原取消/撤销/Last-Event-ID门未回归；既有legacyDOM实际v3→v4→v3正文/历史继续，receipt current/history皆1才报告修复。前端未接外层view前维持缺口/strict xfail，不用API列表断言冒充DOM。

M4c以真实memory_write/update/forget、敏感proposal、无授权/credential拒绝、失租/旧epoch/源撤销/恢复证明事件四状态来自真实效果；多次订阅补发不能重复写或重造undo能力；profile/case/draw不误生成普通记忆卡。新增行为只在root批准最小文件后测，不用schema绿代替。

M4d本机PG+ScriptedPort端到端：原draw/cards/deck/meaning不变，始终同reading/version；首读/重复/并发/不同supplement/错误后retry/断线/取消/手动更正/删除/跨owner/源span撤销均真实核验，失败后0新抽牌、0伪c/r、0旧正文复活；未知postcommit只修reading，不再调用模型。比较v3固定牌契约和`finish_reading`伪造结果拒绝原断言。

所有后续测试需root授窄位，TZ=Asia/Tokyo、显式本机随机隔离PG、loopback HTTP trust_env=False、清凭据追踪；11点固定宽验由root负责，本设计不启动测试或外部动作。

## 原测试与调用方保护清单

| 位置 | 保留或需root明确批准的迁移 |
| --- | --- |
| `tests/test_core_web.py::test_chat_memory_sse_replay_and_foreign_operation` | v3旧result/[DONE]、真实saved、幂等不增模型调用、参数冲突409、外人404全部保留。 |
| 同文件`test_cases_tarot_fingerprint_reading_replay`；`test_core_pg_channels.py::test_reading_resume_keeps_version_and_only_accepts_its_persisted_result` | 固定牌、原版本恢复、重复不调模型、伪结果拒绝；v4专用桥不重写v3。 |
| `test_runtime_assembly_pg.py::test_uncovered_v4_inputs_are_refused_without_legacy_fallback` | 通用submit仍拒附件/draw/reading/报告/selection/parent，零原话写入，不靠删guard接专用reading。 |
| `test_thread_routes_pg.py` | 入队单执行、无痕隔离、跨owner、取消保lease保留；其中默认chat named final是已识别P3临时断言，迁移须root批准新旧两份协议目标而不是删隐私/结果断言。 |
| `test_result_readers_pg.py` exact meta/result/history；Tarot同信封finish | 规范core4对象原样，外层legacy_view不侵入；不把展示投影送给验证/持久化/投递。 |
| `test_legacy_dom_runtime_pg.py`与原JS probe | 真实三轮/一次POST/回执DOM/完整history；strict xfail缺口保留到联合真实修复，不改JS测试去模拟不存在的回执。 |
| `test_tarot_snapshot_lineage_pg.py`、professional/legacy_read lineage、tool_tarot_guard、delete_propagation | 精确range/step/native卡、旧无c/r诚实读取、U7/来源/lease/epoch/删除清输出保护全部保留。 |

所有web.stream调用方为chat、reading、retry、resume；改变协商要同时查其实际幂等与状态，不只改chat一个分支。所有规范读取端为chat恢复、run状态、memory.history/thread_history、tarot readings、Hermes与Outbox；不修改规范读取器为展示加字段。frontend transport/recover/reading查run使用既有operation别名，JSON回执应同时保留真实run_id与稳定request关联，不能改变原retry预算规则。

## 前端交接与所有权建议

前端线需要接JSON握手到真实followV2/冻结wire，处理inbox_wait/采用或下一轮、current/history同源legacy_view（若选用）、真实memory_receipt富卡上下文与普通PublicReceipt区分、固定reading的JSON或旧SSE收据及状态。旧static逐字展示不支持delta/reset，backend不能用未提交result假装完成；若要旧页逐字/回执，旧页面文件需由其所有者另片更改。这里只列API/来源/安全约束，不设计新UI，不发跨聊天消息。

建议M4a先授新http_negotiation/run_acceptance与web.chat/thread_routes最小接点及新目标；M4b/c/d分别另授源文件，避免覆盖正在冻结的M2timer或M3。公共Schema/core4、web/**、static/**、模块树、Channels投递规则均不在本片可编辑范围。

## Idempotence and Recovery

相同request只读原pin/source/run，representation改变不能重建输入、开新预算或重抽。POST断线可以GET原run；补发只读已提交PG事件。legacy_view是临时只读结果，原信封、reading、Outbox不回写它。来源撤销继续清原事件/步骤/结果，无外层投影缓存可复活。reading完成repair只验证原持久结果、重做同一幂等finish，不补造未来结果或再次模型调用。

## Outcomes & Retrospective

M4a已独立实现并目标验证，规范core4/events Schema无改、web/**及static/**无改、原测试断言无改。80项目标绿仅证明本片及两个原明确目标，不代替11点固定源宽验/CI或全P4验收。JSON与SSE跨Accept读取同一真实run不增模型调用；正式默认/SSE迁移仍是M4b，现保留原P3临时named流，旧UI回执缺口仍在。完整命令、原59/最终80与边界见`docs/v4/evidence/P4/2026-10-21-chat-json-acceptance.md`，原始日志在private/p4-chat-acceptance-20261021/，不提交私有日志。

10:56首轮历史：审计/设计完成时仅新增本计划，实施与测试结果0；此记录不代表11:09实施后的当前状态。首轮明确可先做M4a、需要前端配合的receipt/历史展示，以及不能靠去掉拒绝解决的固定reading来源/调度完成桥。后续按root批准分片推进；用户不在线不等待，不进行本范围之外操作。M4仍未完成，不能借既有M3/游标目标或前端合成演示宣称验收。

## 修订记录

- 2026-10-21 10:56:29 +08:00：只读原提示词/28冻结/全调用边界/前端真实消费，新增最小分片与内容协商设计；生产、测试、他线文件均未改。
- 2026-10-21 11:09:11 +08:00：root批准M4a后实现并目标验证80项；记录真实postcommit ACK、原pin/无痕/inbox跟随边界；M4b/c/d仍独立未完成，未改旧SSE或前端。
