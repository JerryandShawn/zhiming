# P4 M4c：只从真实记忆写入证明生成公开回执

本ExecPlan遵循`.agent/PLANS.md`，四活节持续更新，时间为北京时间UTC+08。当前只读方案与未运行验收例；未获root对生产接点的另行批准，不修改Loop、Runtime或事件生产代码，不启动pytest。

## Purpose / Big Picture

普通记忆真正保存后，网页能立即收到与实际事实ID对应的`memory_receipt`；敏感资料只有真实确认提议时显示待确认，不把模型声称“记住了”当成功。公开文案由服务器固定生成，不转发原话、模型摘要、内部凭据或输入参数。事件与工具完成确认在同一事务落库，页面回调在真正commit之后才调用；崩溃重放使用同一seq，不重复写事实或发新通知。

## Context and Orientation

工作树`C:/Users/Administrator/Documents/Codex/zhiming-v4-p3-wire-p4`，方案基底`844daac05c655075a7ff955fdad7ec9359d5f313`。M4a作者独占`adapters/web.py`、`application/runtime_assembly.py`等HTTP接线；M5作者处理retention/log/reader，当前不与其竞争。本片不改这些文件、不改模块原件、不占迁移号或改冻结Schema，不把P4分支候选称为已合入integration。

术语：“完成确认（ack）”指`core_run_steps`已有真实`completed`记录；“写入收据”指`core_mutation_requests`中与准确operation/request_key对应的无正文结果；“savepoint”是外层事务内的嵌套保存点，退出它不代表数据库已经commit。

复用且保留的接点如下。

| 文件 / 函数 | 已读事实 / 必须保留的行为 |
| --- | --- |
| `agent/loop_batch.py:ToolBatch.accept` | `Journal.complete`与`_register`在同一owner事务；工具效果可能已在此前提交，不能把事件当作重新执行效果的理由 |
| `agent/journal.py:Journal.complete/_leased/_read` | owner/subject/runtime/epoch/lease/cancel/deadline、实际持久步骤身份与输出一致性；不能仅相信传入JournalStep.status |
| `application/agent_tools_memory.py:execute_write/save_memory/proposal/forget_memory` | 真实来源检查与精确mutation_request；saved事实、pending_confirmation提议、无实体拒绝、forget撤销各有不同实际语义 |
| `application/agent_tools_updates.py:execute_update` | memory_update/profile_update_request是精确更正或提议，不把敏感确认当saved；真正更正可能使原run stale |
| `application/agent_tools_contracts.py:ToolContext.operation_id/tool_input_fingerprint` | 稳定`run:<id>:e<epoch>:s<seq>`与规范参数+原source_versions输入指纹，不从摘要/正文去重 |
| `application/agent_runtime_events.py:RuntimeEvents.send` | 现公开事件身份/线程/epoch门；当前send的callback在其自身transaction退出后立即调用，不能嵌套进accept外层事务复用这个callback时机 |
| `repositories/run_event_log.py:append_event` | 实际INSERT、稳定operation证明与单`mj_run`通知同事务；重放验证原件、保留原seq、不重复通知 |
| `repositories/postgres.py:transaction/mutation_request` | 嵌套共享同连接但只退出savepoint；写入收据只有标识/状态，不能存新的原话或引用正文 |
| `application/agent_current_sources.py:current_source_ids`、`agent_crisis_sources.py:turn_sources` | 只认可排队原话与已证明的inbox来源；不以模型提供的source_ids扩大授权 |
| `agent/events.py`、`agent/event_contracts.py:MemoryReceipt` | events_v1现有校验；恰有fact_id/proposal_id之一，状态saved/pending_confirm/undone/rejected，不增加私有字段 |

## Progress

- [x] (2026-10-21 11:14 +08:00) 只读核对真实工具、Journal、mutation、RuntimeEvents与append_event，确认尚无memory_receipt producer。
- [x] (2026-10-21 11:14 +08:00) 已收到root确认：默认P3 generic cycle不装hook；安装P4可信hook时拒绝pre-existing外层事务，savepoint退出不能冒充commit。真正forget导致stale继续原失效/恢复，不绕`_leased`。
- [x] (2026-10-21 11:14 +08:00) 新建验收例源码，覆盖真实fact/proposal、独立连接观察commit、append后崩溃原子回滚、同epoch重领重放、无实体拒绝、默认P3保持；尚未运行，不声称已经实证红或绿。
- [ ] root批准下述精确生产函数/新文件与可信开关后才实施。
- [ ] 获单窄槽后先在原producer缺失状态记录真实首红，再最小实现与旧回归；不得用未运行例冒充失败证据。
- [ ] 生产接线、真实PG反例、回执以及root审查提交全部完成后，才标M4c完成；现只是设计切片。

## Surprises & Discoveries

`RuntimeEvents.send`外观看似“commit后callback”，但在`ToolBatch.accept`已有owner事务中调用时只释放savepoint，callback仍早于外层commit。这会让页面看到随后回滚的假成功，因此需要专用record/dispatch两段；本片不重写通用repo.transaction或添加全局postcommit系统。

公开枚举为`pending_confirm`，工具真实枚举为`pending_confirmation`；只有已查到真实pending proposal才做这一投影。凭据/退出保存/无授权拒绝经常只有`write_status/code`，没有fact/proposal，无法合法套Schema；正确行为是保留已有安全tool_result而不生成memory_receipt，不造空ID或假proposal。

`note_write`真实类型为note，公开回执只允许fact/proposal，因此不把note ID塞fact_id。`memory_forget`真实结果可只有fact_id而无id/revision；删除和更正均会调用invalidate_derived，若当前run采用该事实会stale或撤销，不能为了发undone而把旧epoch恢复成running或伪造完成Journal。

## Decision Log

2026-10-21 11:14 / 收口前设计：接线候选只在可信程序集明确启用P4时安装。初版建议复用现有严格bool `AgentRuntime.streaming_candidate=True`以限制候选；最终开关由root另批，绝不从HTTP/body/模型参数决定。默认false维持现P3 generic Loop无专用hook。

2026-10-21 11:14 / root确认已记录：不改变通用事务机制。装hook的`ToolBatch.accept`进入自己的owner事务前，若`repo._local.connection`已存在则明确拒绝；正常Loop实际在事务外执行。这样外层with退出才是本接点可证明的真正commit，不能仅在hook内部查询一次连接后假定调用者无外层事务。

2026-10-21 11:14 / 设计：事件key采用`memory_receipt:v1:s<真实seq>:<真实input_fp>`，append_event再绑定真实run/epoch，完整operation为`p4-event:<run_id>:e<epoch>:<key>`。不按summary、payload内容或实例counter去重，不把内部operation/request_key/input_fp/source_versions公开。无撤销令牌签发/消费能力时省略undo_token，不造token。

## Outcomes & Retrospective

当前只新增本Plan和`tests/v4/streaming_integration/test_memory_receipt_producer_pg.py`未运行源码。生产0改、pytest0、PG操作0、服务器/供应商/飞书0，未提交推送。已识别savepoint早回调与forget stale边界；尚未证明新producer，因为没有实现或运行。P3 X03、旧DOM、受信encoder与B1 No-Go不因本计划改变。

## Plan of Work

### M4c.1：专用事务record及提交后dispatch（待root批准）

拟新`application/agent_memory_receipts.py`（必要时再拆一个私有proof helper，均≤400行/函数≤60）承载真实证明与公开投影。`RuntimeEvents.memory_receipt(step,result,*,arguments,context)`只允许在accept已建立、已验证的同一owner事务内执行：保存事件并返回仅含公开事件的待派发句柄，绝不在此调用UI callback。`RuntimeEvents.dispatch_memory_receipt(handle)`只在accept最外层with成功退出后运行，沿用callback异常不回滚已提交结果；hook不在最终信封或ToolResult里增加私有keys。

拟在`LoopCycle.__init__`增加可信可选memory hook，默认None。拟在`AgentRuntime._cycle`按批准开关注入专用record/dispatch。拟在`ToolBatch.accept`保留原顺序：检查无已有外层事务→进入owner事务→真实Journal.complete（或严格重读已完成步骤）→原_register→专用record→事务成功退出→dispatch→原receipts/messages/tool_result。不是把通用emit('memory_receipt',...)塞进现事务。record失败则ack、注册变化、事件、operation和notify一起回滚；此前真实工具效果仍由原mutation_request幂等恢复，不重复写入。

当前这3个生产接点及任何新helper都未改。M4a的web/runtime_assembly、M5的retention/log/read不在本片范围。若root希望只扩RuntimeEvents签名，仍须提供ToolContext+原arguments以核两种指纹，不能仅靠step/result猜规范参数。

### M4c.2：可信证明与投影（待实现）

在真正写事务内先复用Journal._leased、assert_thread/thread_id与scope门，严格绑定owner、subject、thread、run、epoch、lease、cancel/deadline。再FOR UPDATE读精确tool step，要求completed、finished_at非空、error_code空、kind/name/input_fp精确匹配，持久output与本次ToolResult完整一致；started、清空输出、缺完成证明都不能生成事件。传入snapshot.status不是证明。

用现有MemoryWrite/MemoryForget/MemoryUpdate/ProfileUpdateRequest模型规范化实际arguments，重算`tool_input_fingerprint(name,values,context.source_versions)`与真实step相等；查`core_mutation_requests`必须精确owner+`agent_<真实工具名>`+`run:<id>:e<epoch>:s<seq>`，`fingerprint(values)`须等于其持久fingerprint，receipt与Journal.output.receipt逐JSON值相等。实际来源仅来自current_source_ids及原source_versions；复用原source_policy/check_span/版本/撤销检查，不遍扫owner相似变化来归因。不把工具英文名、私人args、输入hash或mutation keys塞公开event。

saved只接受当前真实fact active/consent granted、同owner/subject/可见case、revision与原收据一致，原话refs/版本/区间有效且未撤销。pending_confirm只接受真实proposal status pending、revision一致及实际本轮原话来源；敏感确认、资料变更、目标澄清的proposal都不是saved。ordinary low-sensitivity saved公开固定文案“已保存这条记忆”；pending固定“这条记忆等待你确认”；不使用ToolResult.summary、模型summary或原话拼文案。sensitive从已验证实体/原话经现可信分类函数判断，不信模型reported值；资料提议以及不能证明低敏者保守true。

memory_update保存的新fact按真实新ID/版本投影，原fact superseded不复活。memory_forget只有精确真实收据表明deleted/stopped、目标确属本owner/subject/case、实际fact/撤销账本状态吻合，而且Journal与run仍合法时，才建议映射undone并固定“已撤销这条记忆”；如果原工具已使run stale/revoked，保持原重生/停止安全路径，不在旧epoch额外ack或发receipt。拒绝/停止且无真实实体的情形不生成此事件；未知状态、凭据拒绝、无授权、note、纯读工具均不得凑Schema。现尚无可信实体拒绝动作，rejected分支不凭空发事件。

### M4c.3：稳定重放与安全回调（待实现）

在同一owner事务中用上述key调用原append_event，已有operation仍须由append_event核原件与payload指纹。已存在且一致时沿用原seq，不INSERT、不notify、不按新revision重写旧receipt；原件已清理或撤销就拒绝重造。派发只对新提交事件执行；是否已有operation在同一owner锁下精确读，不能凭可变进程缓存决定。commit后callback断线不影响PG原件，客户端靠现seq/Last-Event-ID回放，不补造第二个事件。

## Concrete Steps / Validation and Acceptance

目前仅AST/静态核验新例，不运行pytest。获root批准和一个窄槽后，先在未加producer的源码上跑新例，记录真实红与源码hash；后按批准范围实现再串行复验。命令工作目录是本P4树，继续用root已审安全runner：

    <现有P2 Core Python> -X utf8 <root安全run_narrow_safe.py> <本P4树绝对路径> tests/v4/streaming_integration/test_memory_receipt_producer_pg.py

初版源码8个参数化验收例（尚未运行）：真实normal fact与sensitive proposal各1；callback用另一pool连接实际看见completed Journal、精确mutation和event已提交；append真实event后SystemExit应回滚ack/event/operation而保留唯一已提交工具效果；final前崩溃后同epoch旧lease过期重领，保原receipt/seq且0新模型请求；凭据/退出保存各1，无实体无假ID；默认P3不开可信hook保持既有安全tool_result。测试只替换模型；事实、mutation、Journal、event、重领与查询都走实际隔离PG。新例中append拦截器明确绑定拟复用的`agent_runtime_events.append_event`，不是伪造数据库结果。

生产批准后还须补窄负例：伪receipt/错误mutation fingerprint或request_key、cross-owner/subject/thread/epoch、租约/取消/来源撤销/区间撤销/版本变化、pending→已拒绝或fact已撤销、伪completed/缺finished_at/started、同step不同输入、已有外层事务拒绝与0callback、重复重放无新mj_run通知、无痕0长期事件、forget stale与memory_update真更正保持原契约。不能删除现completed_step防篡改或own-effect恢复反例。目标映射07场景M类保存/敏感确认、F02/F03/F04撤销、Q06更正、X03重放及X08回放；只测本片不改原47或v2.1基线断言，不宣脚本100%。

## Idempotence and Recovery

领域效果先由原mutation_request恰好一次提交，本片只使Journal ack与receipt event原子。效果后ack前崩溃继续原工具幂等重放，不用新epoch掩盖重复；ack/event后final前崩溃读取真实completed步骤并复用原operation/seq。来源撤销、旧租约、外部修订一律原门拒绝，不生成新“自愈”证明。没有Schema或迁移；候选开关默认关即可停新producer，不删除历史事件或回执。

## Artifacts and Notes / Snapshot

本片只有Plan与未运行红例源码，无测试日志、分数或实证首红。下列为11:14只读生产快照，不是新实现或最终候选，避免并行WIP被误计入完成：

| 文件 | raw SHA256 |
| --- | --- |
| `agent/loop_batch.py` | `5b9c7e6485b5838c2398e773874327ab30a2e655d3d45844123e381fca4e4e79` |
| `application/agent_runtime_events.py` | `d0ba6e5f19be228ef44227cf0b57fa0e4899bda1de2e028ec95fc4af55fa1814` |
| `agent/journal.py` | `b9a00e4999cb6041a11c9597a8f787f3e66afe7bd30c37a762d96becc53e49a3` |
| `application/agent_tools_memory.py` | `03c8042f194b476f3fc1e00b543ec7771aeb7f4722bda0be3ffc04c748205930` |
| `application/agent_tools_updates.py` | `83a7e0db4a20a8c1f07dd06ec9e95ec93957d6de4e1129f2757f91c712c16295` |
| `repositories/run_event_log.py` | `e6979cfca97ba9d4653d927f083e1a3dc531924005ea50c785cffd8a6151906c` |

## Interfaces and Dependencies

待批私有接口为可选trusted memory hook、record返回公开event句柄、外层commit后dispatch；不改events_v1字段或外部API。无新增依赖/锁文件/迁移。旧RuntimeEvents.send的现有调用者行为不改，专用producer不复用其嵌套早callback。无undo token系统、真实供应商或服务器接线；任何新功能文件须root先批再写。

## 修订记录

- 2026-10-21 11:14 +08:00：创建只读M4c设计与8例未运行验收源码，明确真完成/精确收据/当前实体授权链、外层事务拒绝、record/dispatch两段、无实体不凑Schema、forget stale不绕门；生产与pytest均0。
