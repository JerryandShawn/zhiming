# P4 M2a：原模块合并器的真实 Runtime 最小候选

本 ExecPlan 遵循`.agent/PLANS.md`，四活节持续更新，所有记录为北京时间UTC+08。**当前已按root批准实施M2a原核/可信范围/真实Runtime最小候选，15个新增目标与41个相关目标通过；默认关闭、待root提交。** M1已由root提交`95df0f9ca850a4a52d821817c40ce3a1b9058a8f`，tree`e5b83229`，Draft PR14依赖PR13；未合并。P3 X03、旧DOM、受信encoder与P4其余门仍保留。

## Purpose / Big Picture

完整M2目标是将真实模型文本按40字或从首片起150ms合并为持久事件，供应商下一片静默时仍准时刷新；旧租约、旧generation或已撤销来源的定时器不能写新正文。当前M2a只实现原核40字/结束flush候选，独立timer未实现。浏览器有界hub/PG回补由M3独立片接线，不能把此目标当当前完成事实。

本片使用模块线原纯核，不另写一套近似合并算法，也不靠只在测试调用的桩声明接线。启用候选时，真实`AgentRuntime→LoopCycle→ObservedPort`流与PG持久化已经经过桥接；真实`thread_events`订阅与hub由M3另片验证。默认关闭时保持M1普通事件路径。完整模块按既定P3→模块顺序普通集成后，替换唯一导入接点并复跑，不覆盖原模块或改公共Schema。

## Context and Orientation

独占树`C:/Users/Administrator/Documents/Codex/zhiming-v4-p3-wire-p4`，分支`v4/p3-wire-p4-20261021`，当前已提交头`95df0f9`。root10:00的不可变archive回归不包含此WIP；当前禁止新pytest占位。只读模块来源固定`origin/v4/mod-organize@ebfa22f8f7c59e486c6632035ae6bc8307f0f438`；当前P4树无`mingjing_core/streaming`，本计划不授权原位置复制或模块整分支合并。

复用函数与不变量：M1的`run_event_log.append_event`在受信owner/run事务写row/可选元数据operation/同channel通知；`RuntimeEvents.send`在Journal租约/epoch/取消/期限、subject/thread和最终真实信封门后调用它。`LoopCycle._model`先由Journal分配真实model step，再reserve请求账本，然后`ObservedPort`调用真实port.stream；completed step直接回放不会重新流式。当前`_text_delta`无step参数，只在非revising时发text_delta；批评模型没有公开文本，revision稿也在受信review之后才以整段reset公开。不能因合并器把这些私有文本放出。

`thread_events.event_response`已有真实鉴权reader、冻结SSE和每150ms PG轮询；当前无hub、无事件LISTEN lifespan。dispatcher只监听mj_run_queued/cancel，不能冒称已监听mj_run。RunEventReader终态error和嵌套事务仍可能在外层事务中，本地hub不得因savepoint完成就把未提交内容当可见。最终助手消息/final事件分开的安全修复口径沿M1保留。

## Progress

- [x] (2026-10-21 09:51 +08:00) 完整读原coalescer、模型/clock/reducer及其依赖，读ObservedPort/LoopCycle/RuntimeEvents/RunControl/当前SSE消费者；确认模块没有hub。
- [x] (2026-10-21 09:54 +08:00) 静态AST递归得到保留原__init__时的12文件闭包、27382原始字节；记录raw SHA/git blob与外部imports。没有执行原模块。
- [x] (2026-10-21 09:54 +08:00) root要求先交精确候选隔离/真实消费者设计，不复制源码、不编码、不pytest。
- [x] (2026-10-21 09:57 +08:00) root批准后原字节提取12源/27382 bytes并生成SOURCE_MANIFEST；独立内部scope适配完整真实范围，hash只作原纯核标签。
- [x] (2026-10-21 10:09 +08:00) root批准具体Runtime/Loop函数后接原纯核40字/结束flush；实际Journal/RequestLedger证明与generation/offset同事务核验；旧unfinished候选fail closed。Ruff/AST/400-60与12个rawSHA+hash-object静态通过，未pytest。
- [x] (2026-10-21 10:16 +08:00) root释放窄槽后，新原字节/scope/实际Runtime目标15 passed/5.33s；M1/旧Runtime/回放/无痕/inbox相关目标41 passed/17.14s，全部0fail/error/skip。中间误写测试路径导致一次exit4/0 collected，保留原日志，纠正路径而未改代码或断言。
- [ ] root核索引12源原字节并审查提交；当前未提交WIP，不合并。
- [ ] 独立150ms timer与受审resumed/reset接线；本M2a未实施，不能称150ms达标。
- [ ] M3代理独占hub/listener/thread_events/web接线及其实际PG/HTTP证据，本M2a不写、不代报其完成。
- [ ] 完整组合回归、撤销/取消、旧DOM/X08及M3跨进程；未通过不能宣P4验收。

## Surprises & Discoveries

模块没有hub文件；已有源码是coalescer/reducer、纯存储端口与计划。`__init__.py`原字节导出codec/envelope_reader，保留它就需要相应依赖，不能只拷coalescer三文件却改__init__掩盖来源。闭包全部相对导入，唯一项目绝对导入是现有`mingjing_core.timekit.clock.Clock`；第三方只有已锁pydantic，不需要迁移或新增依赖。

模块`RunScope`把owner_id限定为ASCII标识，而真实repo owner只限制非空/长度，可为Unicode。hub/鉴权必须始终使用真实owner，不能偷偷改用户身份规则。root随后批准并已实现HostStreamScope：完整schema/owner/subject/thread/run经域分隔完整SHA256形成仅原纯核使用的ASCII owner/run标签；host另持完整真实scope，在每次PG提交核实际Journal/lease/subject/thread。不能把hash标签当认证，也没有放宽原模块源码；Unicode和跨scope测试尚待执行。

现有两个公开调用缺稳定信息：ObservedPort只回调text；ToolBatch在分配tool step之前发tool_call。因此M2只扩文本的真实model-step边界，ToolBatch/其他事件稳定化另片。纯coalescer支持generation拒旧state，但不会替主线做当前PG租约和generation CAS；仅通过其纯测试不能证明旧timer被阻止。

有界asyncio.Queue仍可能被无限`call_soon_threadsafe`回调淹没。hub必须在入loop之前把同订阅者pending提示压成一个，不能只把queue设maxsize就声称总有界。持久PG事件不丢弃，hub只承载seq高水位，不承载正文/回执/工具结果。

2026-10-21 10:16：相关目标首命令把实际`test_thread_inbox_runtime_pg.py`误写成不存在的`test_inbox_runtime_pg.py`，pytest收集exit4、0 tests；这是命令路径错误，没有产品失败栈。原始目录`private/safe-narrow-3244b94cab8449eba2d6d84f5c2d0194`保留；纠正路径后同一5文件目标41/41通过。测试环境显式Asia/Tokyo，记录与业务断言不依赖主机时区。

## Decision Log

2026-10-21 09:54 / root：先设计原字节候选隔离，原路径copy或模块merge另批。参照既有P6候选：保存原源文件的raw字节、source_commit/source_path/git_blob/SHA256；主线host适配只在另一个包实现，不改模块相对imports。替身只用于供应商/外部传输，必须有真实Runtime/PG/SSE消费者证明。

2026-10-21 09:54 / Codex初始提案，root随后已批准M2a：候选目录`mingjing_core/integrations/streaming_candidate/`，12源原字节加SOURCE_MANIFEST；`integrations/__init__.py`只作主线namespace，不能伪称模块原件。SOURCE_MANIFEST状态明确“isolated dependency, not module merge”。后续模块普通集成后只替换host唯一导入接点，并以相同契约/属性/运行时目标复验再退候选，当前不删任何目录。

2026-10-21 09:54 / Codex初始提案，root随后已批准M2a：可信装配默认关闭，启用只由受信Runtime构造参数决定，禁止模型、HTTP字段或用户任意文件路径开关。已在真实AgentRuntime/Loop路径接入，实际运行仍待测试；HTTP/hub由M3另片。正式程序集配置/打开功能和部署是后续受审门，不能写成生产已可切。

2026-10-21 10:09 / root批准实施M2a：12源保留原字节，候选独有`.gitattributes`写`*.py -text`防根text=auto/eol=lf在git add时改CRLF；它是host元数据，不伪称原模块文件。SOURCE_MANIFEST raw SHA固定`bb98bd12daafda15970d71ddb06c4600bad301889330531b144b03fd486bbd97`；root提交后还须核索引/commit原blob。独立内部范围使用完整schema/owner/subject/thread/run的域分隔SHA256映射，PG仍核原身份，不以hash授权。

2026-10-21 10:09 / root批准具体函数：AgentRuntime.__init__严格bool默认关`streaming_candidate`、_cycle注入ModelDeltaStream；LoopCycle增加内部text_stream、_live_model在真实Journal+reserve后begin/finally finish、_text_delta委托。首片仅40字/结束flush；任何未结束或同step重新开始均fail closed，不自动升代掩盖恢复。每次PG提交同时核当前真实step/lease/epoch/input_fp和原RequestLedger，offset只从实际text长度累计；metadata和event同事务。中途未知commit/进程退出也保持原数据拒新流，下面M2b的完整resumed/ack恢复是未来目标，当前未实现。

2026-10-21 10:09 / root分工：hub/listener/thread_events/web由主线另一代理独占；本片不修改这些消费者/生命周期，只通过M1真实mj_run排通知。先写测试，10点四宽占位期间不执行pytest。

2026-10-21 10:15 / root释放单窄槽：先3个scope与12个真实Runtime目标，再明确5文件M1/Runtime相关目标串行。10:16全部完成即释放；未扩整库、未执行M2b timer或新恢复旁路，root正在运行的不可变archive仍不含本片WIP。

## Outcomes & Retrospective

本片已由root批准实施M2a最小候选：12原源原字节/manifest、opaque内部scope、可信严格bool默认关、真实Runtime/Loop文本消费和PG generation/offset/事件原子写入。新原核/Unicode/真实Runtime15个目标与M1/相关Runtime41个目标通过；细节见`docs/v4/evidence/P4/2026-10-21-stream-candidate.md`。没有新增依赖/迁移，真实模型/服务器/飞书0。独立150ms timer与恢复reset未接，旧unfinished generation明确拒绝新生成而保留原数据。M3 hub/listener/thread_events/web归另一主线代理独占，本片不改这些文件。后续必须有HTTP消费者与组合门证据，不能把默认关闭候选当P4完成。

## 精确候选来源与imports

根为`mingjing_core/streaming/`，固定ebfa22f8。下表为raw blob计算，CRLF/LF保持源原字节，不能对候选运行format改其字节。闭包由`__init__ / coalescer / text_projection`的AST相对imports递归求得；12文件共27382 bytes。

| 文件 | bytes | SHA256 | git blob |
|---|---:|---|---|
| __init__.py | 445 | 1e871da7c671c946162f9c0f1c2a3afdd445936cc21bc955b112443072c5d8b9 | 689d46b35fbc263a4712f24993b7c118bc71e6b8 |
| coalescer.py | 4364 | 6fe6d4cdb28f580ce9c483f16c20117e93915f9fb7ab6256cc8cd82485dfdc09 | 258111b949f17b30d37c27364cb9c4768641291b |
| stream_clock.py | 748 | 0ff56d38e8a1c22d01003e8fb03500b76d0b79d7d9ae1ba27478bbb152776971 | a796706259b20410007cb37403ce9f99c3f052b7 |
| text_projection.py | 2604 | 961f794eb8e660f79a0a9f74359ea37ffe6365ca4382cd4af19f488e51f95200 | 829988a67be6f100af516aec93cc776fb4cded24 |
| event_models.py | 2763 | 7ad964b2f5d8fc13ba6565ef3132a391e11f729d3969caf06b6b14535706382e | 502347a3a92c786366722781ecf77a098060572c |
| event_payloads.py | 2968 | 54561e6cfef3ff8353abbac64c2f850bfda6b7820b9e831680040ae8b5716eff | 36107203501615b309228e45b117f2024b92c86a |
| event_nested.py | 3176 | 95658a4cb869ed25b15ae1717a659fe4facaa3626c465051a6f8cd1d3fa5c941 | bd59b96740a786c61072dff9ab2592f36cf45dff |
| public_shapes.py | 1955 | e9f2705c18acf8cff2654f757ce7485d1ad8e0a70ec294a6bfdc4cd206bd1ffb | 3a812234e44ee91a84e3371817bff289e1813d7f |
| event_errors.py | 276 | 7697b637fa19df6ac35c2abdfa50856ae20c09061f4b74f6b27077d8c1baec18 | 060eb17219ab8e1f8ab5b6a0b081d6d62fae7b8a |
| json_values.py | 1618 | ae18a6b0288f0c5cc16498cbd7503d3177c1f0b31dbceb2735de32afdf06902e | 0bd55a165c254cb2af2388ed62b44f57adb0a488 |
| codec.py | 4315 | a58e8a0f995599fcaba61aba35801ff37a46a5f99bdd4a64a06d52603bce8992 | 72887bb826815fd5a976b33a90c634fbac81793f |
| envelope_reader.py | 2150 | c791c59983163f92100635b2afbe38e74e1051eeb8a47ea53713079f48f9c7a3 | 106ae4370a0d0e3c33991d657e4f8712f7a6a270 |

内部图：`__init__→codec/envelope_reader/event_models`；`coalescer→event_models/stream_clock`；`text_projection→event_models/stream_clock`；`codec→event_errors/event_models`；`envelope_reader→event_errors/event_payloads/json_values`；`event_models→event_errors/event_payloads/json_values`；`event_payloads→event_nested/public_shapes`；`public_shapes→event_nested`；`json_values→event_errors`。timekit.clock仅coalescer/stream_clock使用；pydantic由models/payloads/nested/shapes/envelope_reader使用；其余仅标准库collections、dataclasses、datetime、hashlib、json、math、re、types、typing。没有SQL、驱动连接、网络、线程、timer、文件写入或依赖安装；这些I/O全由主线host承担。

原纯核接口不改：

| 接口 | 参数/结果与主线责任 |
|---|---|
| DeltaPolicy | max_chars=40/max_delay_ms=150，严格正整数上界 |
| DeltaBuffer | scope/text/opened_at/last_observed_at/generation；不可变，无租约权力 |
| feed_delta | buffer, chunk, generation, Clock, policy→DeltaEmission(state,drafts)；先检查旧缓冲超时，再接新chunk |
| poll_delta | buffer, Clock, policy→到达150ms时吐draft，不负责自行启动timer |
| flush_delta | buffer, Clock→剩余所有text_delta，空buffer无事件 |
| replace_text | buffer,text,reason,revison_id?,Clock→丢未发旧buffer，generation+1，单个reset |
| RunScope/EventDraft/RunEvent | 深冻结公开payload，owner不进wire；seq/ts由主线持久层权威分配 |
| TextProjection/reduce_event | 更大seq追加/替换；旧seq不倒退、同seq异body拒绝；final以已提交text收尾 |

reducer是行为oracle和未来消费者的来源，主线不拿它绕过真实PG授权。现有core3/core4历史读取继续使用已验证read_result，不因候选__init__导出envelope_reader就替换历史入口。

## Plan of Work

### M2a：原字节来源与唯一接点

root批准后已提取12源至候选包并写SOURCE_MANIFEST（完整source_commit、source_path、git_blob、raw SHA/bytes）；没有运行候选format或改imports。主线`application/streaming_kernel.py`为唯一导入接点，在启用时先核固定manifest原字节及12源码hash，再导入原纯核；原模块普通集成后只改此接点并复验。候选包不是新的Schema真相源，最终出站仍用既有events.py校验/编码。工作区rawSHA及git hash-object --no-filters均匹配原blob，索引/commit原字节待root提交时复核。

### M2b：真实step、generation与片段身份

最小新增主线`agent/stream_events.py`协议、`application/run_event_stream.py`服务和必要独立state helper；小改`AgentRuntime._cycle`可信注入、`LoopCycle._model`的真实model step开始/结束、`_text_delta`委托。保留原二参emit用于其他事件/既有测试，生产候选开启时必须走实际新服务；不改ToolBatch。

服务从JournalStep取owner/run/subject/epoch/model_seq/input_fp/lease；PG中复核实际started模型与已reserve RequestLedger，再开始流。completed模型回放不重新输出delta；revision/critic不公开草稿。每个实际chunk的Unicode字符区间只由服务器顺序累计，不能由模型自报。持久generation在run.usage的独立键中由短owner/run事务CAS更新。当前M2a遇到旧unfinished、同step重进或lease替换均保留数据并拒绝新流；下一恢复片才能在受审resumed reset后升generation。真实regenerator现有reset与review revision_id桥接、旧timer拒写均为后续目标，不能当当前完成。

事件操作key由受信epoch/model_seq/generation/字符起止组成；正文hash只检内容完整性，不当身份。一次已提交flush在本地状态确认前失败，可用相同key返回原seq/ts；换分片边界/旧generation不得改写。未完成流在新generation重生不能凭key抑制不同文本；必须reset后重新展示。稳定流元数据仅含标识/计数/指纹，不另存私人正文，正文仍在现事件与模型Journal中。

### M2c：独立timer与安全结束

从首个非空chunk起安排独立150ms调度，不等待下一chunk。pure Clock决定149/150ms边界，真实受控调度验证供应商静默时刷新；producer/timer共用短状态锁和generation CAS，PG事务外才等调度器。禁止持PG owner锁等待timer，也不能持buffer锁长等网络。timer异常只能固定安全code，停止旧写入并丢不安全缓冲，不输出供应商异常/正文。

普通非text事件前先flush当前安全buffer，模型正常结束/工具/提问/final前完成有序flush。reset丢缓冲再换代；取消、撤销、private close、旧租约时丢未提交正文，不为“完整文本”强发。关闭timer立即取消后续任务，不在2秒取消路径无限join。已在PG事务里的旧timer必须靠当前lease/epoch/generation再次核验才可commit；不能只信内存cancel标记。具体锁顺序和终态drain实现须经root实现审查与并发反例后再定，不在本计划伪称解决。

### M2d：有界hub实际消费者

新增`application/run_event_hub.py`，scope键为受信repo/schema、真实owner、run_id。每订阅者保存asyncio loop、maxsize=1高水位queue和pending标记；publish先在短锁里更新最高seq，只有从无pending到有pending才call_soon_threadsafe。loop回调只放当前高水位，queue满时合并旧提示。这样模型线程不会等待客户端，loop待处理回调也不随事件数无界增长。unsubscribe/loop关闭移除所有引用，不缓存正文。

必须小改真实`thread_events.event_response`：先现有reader鉴权/游标，注册hub后回读PG，再等唤醒并从cursor补足；分页读完才前进/关闭，保持150ms有界PG补读兜底和15秒心跳。M2不能凭只测hub纯类就勾完成。

本地producer正常最外层事务提交后才发布高水位；嵌套owner事务仍未commit时抑制本地publish，依原PG轮询兜底，避免savepoint“假提交”。此方式需明确可核的事务边界，不随意把threadlocal测试假设当领域契约；若需要仓储正式on_commit钩子先扩大范围报root。M3单LISTEN才统一覆盖其他进程和reader/nested通知。hub提示本身不授予owner/正文读权，每次发送仍走真实reader；断线只退订，不取消run。

## 具体文件与批准边界

候选12源及SOURCE_MANIFEST、主线namespace`integrations/__init__.py`；主线唯一导入`application/streaming_kernel.py`；可信流协议`agent/stream_events.py`；实际流/状态服务`application/run_event_stream.py`及必要短state helper；有界hub`application/run_event_hub.py`。最小既有接点为`application/agent_runtime.py`、`agent/loop_cycle.py`、`application/agent_runtime_events.py`、`adapters/thread_events.py`；若flag需程序集注入则先报`application/runtime_assembly.py`/from_base具体范围，不改已冻结RuntimeConfig v1结构蒙混通过。

新测试只放`tests/v4/streaming_integration/`；不改模块测试或原旧断言、Schema、前端、迁移、ToolBatch、P5b。每份自写源≤400行/函数≤60，不新增依赖。root已批准M2a排他范围，其他部分仍须先报范围。

M2a已获批并已写：候选12源+SOURCE_MANIFEST+候选`.gitattributes`/主线namespace；`streaming_kernel.py`与`streaming_scope.py`；`agent/stream_events.py`；`run_event_stream.py`及`run_event_stream_state.py`；既有只改`agent_runtime.py`和`loop_cycle.py`上述函数，未改RuntimeEvents/ToolBatch/RuntimeConfig/正式程序集。新`test_stream_candidate_scope.py`和`test_stream_candidate_runtime_pg.py`尚未执行。hub与thread_events/web现归M3代理，以上M2d为整合目标，不是本片可写清单。

## Concrete Steps / Validation and Acceptance

当前M2a两份新测试15 passed/5.33s，相关明确5文件41 passed/17.14s；完整命令、时段、原始产物摘要见本片evidence。10:00四宽期间没有新增pytest，10:15 root释放单窄槽后才执行，10:16释放。AST/hash/Ruff/120列/400-60通过。下面完整M2/P4门仍为后续目标，不能混入本片已验证成绩。

必须证明原字节manifest全部匹配；候选边界39/40字、149/150ms、中文/emoji/换行随机分片、超200k拆分、时钟倒退拒绝、空flush无事件。真实慢ScriptedPort一个字后静默仍150ms落库，不能仅手动poll pure函数冒充调度。实际model-step/ledger绑定，completed回放不重复流，ack前崩溃、相同key重放、lease重领/resumed、旧timer晚到、评审reset、取消与真实来源撤销/private关闭均有反例。不能为全绿改原断言或放宽正文清除。

真实消费者门：同一FastAPI/SSE+PG，订阅建立/快照/publish竞争不丢事件；同owner不同run、跨owner同数字seq不串读；slow loop不运行时pending回调数仍有界，恢复后PG补足所有seq；断线退订不取消运行，无cache正文；final/error真实发送后关闭，不能仅看到status终态就早退。公开frame仍严格events_v1，TS/旧DOM未接则保持未完成。

候选默认关闭行为需保留原Runtime事件与PG轮询目标；开启目标必须实际注入AgentRuntime和thread_events，不只测试Factory。M3跨进程LISTEN、Last-Event-ID完整X08/旧DOM、24h清理和真实模型首字仍独立未验。F03/F04撤销和X04真实HTTP取消原门不能退化。

## Idempotence and Recovery

候选只新增独立路径，不修改原模块/主Schema；manifest不匹配拒启，禁止fallback到另一个不受信版本。flag关闭回到M1普通追加/轮询，不删事件/ledger或运行元数据，不重执行工具。buffer/reset失败依真实PG当前generation停止旧timer；正文清除后不从内存、hub或operation账本重建。正式合并模块后须过同一测试门才替换导入，不以“同名字”假定等价。

## Artifacts and Notes

当前产物为本计划、本片evidence、12个原字节候选源及SOURCE_MANIFEST/候选.gitattributes、主线namespace、streaming_kernel/scope、内部ModelTextStream协议、run_event_stream/state、Runtime/Loop最小接点和两份新测试，均为未提交WIP。root已批准候选目录、opaque Unicode范围适配和严格bool默认关的Runtime开关，不再作为待批项；模块正式merge、独立150ms timer/resumed恢复与正式程序集配置仍后续受审。本片15个新增与41个相关窄目标实际通过，未执行HTTP/完整M2验收。私有原日志只留安全计数/hash，0真实模型/服务器/飞书，不扩大权限。

## Interfaces and Dependencies

coalescer/reducer原接口与导入不变，pydantic/标准库/timekit已存在，新依赖/迁移0。没有改变events_v1/core4形状；内部step/offset/generation不会进wire。模块纯核是算法，不授予lease、owner或发布权。Hub只传高水位，PG仍为唯一运行权威。

## 修订记录

- 2026-10-21 09:54 +08:00：按root只读要求建详细M2计划，列12源原字节闭包、真实Runtime/PG/SSE接点及候选flag/线程/权限未定边界；未复制代码或测试。
- 2026-10-21 10:09 +08:00：按root后续批准写原字节候选/内部scope/真实Runtime最小接线与未执行测试，补CRLF保留、明确旧unfinished/ack未知fail closed及M3独占边界；不把静态绿写成运行完成。
- 2026-10-21 10:17 +08:00：补获槽后15新增/41相关目标实际结果及命令路径收集错误，更新当前WIP/批准/索引原字节待审口径；完整timer/恢复/HTTP/部署继续独立未验。
