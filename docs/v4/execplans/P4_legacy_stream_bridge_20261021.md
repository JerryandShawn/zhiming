# P4 M4b：同一PG事件的旧SSE外层投影

本ExecPlan遵循`.agent/PLANS.md`。创建于2026-10-21 11:18:28 +08:00（工具UTC 03:18:28），工作树`C:/Users/Administrator/Documents/Codex/zhiming-v4-p3-wire-p4`，基准`9b4aa474bd1837702e8229284226921e04002136`。root已批准五生产接点与两处临时协议断言迁移。当前M5拥有唯一第4测试槽，本片只编码/静态，尚未运行新pytest；不改并行M5/Runtime/Loop/Schema/前端。

## Purpose / Big Picture

普通v4旧POST客户端能收到原来认识的平面data.type started/context/status/result/error/[DONE]，新JSON客户端继续从GET读取冻结命名事件。两种表示来自同一RunEventReader和同一PG日志，不再次consult、不新建run或预算。core4原件保持严格冻结，兼容层只在result的规范读取投影上提供已有answer；不加memory_receipts掩盖旧UI缺口。

## Context and Orientation

复用`adapters/thread_events.py::event_response`的游标解析、RunEventReader.validate_cursor/page、页追赶、事件提示订阅、15秒心跳和双finally释放；复用`application/read_result.py::read_result`严格core3/core4读取。GET/POST仍由现有X-Token及owner/subject/thread边界授权，通知只作hint。现web.stream v4直接返回named SSE是P3临时行为；P4正式提示词要求默认旧协议，同时GET冻结v1保持不变。

原断言保护有两处须明确迁移：`test_thread_routes_pg.py::test_compat_chat_opted_in_v4_uses_new_events_and_rejects_private_hint`对默认POST断言named final，本片拆成默认legacy与JSON→GET named两门，保留私密hint拒绝且零原话、同真实信封及单执行。`test_chat_acceptance_http_pg.py::test_json_ack_precedes_model_completion_and_get_replays_same_run`跨Accept那一行原断言named同帧，改为legacy result等于read_result同一原信封；保留ID/1调用/2消息。其它旧断言不删改，M4a原80成绩保留历史，不回签成新协议证据。

## Progress

- [x] (2026-10-21 11:18:28 +08:00) 完整读P4正式目标、现订阅/游标/PG读页和旧页面/新前端消费；root批准最小五接点与两处精确迁移。
- [x] (2026-10-21 11:27:30 +08:00) 新共享follower及legacy投影实现；新13目标+精确原GET游标/订阅/线程等组合58 passed/33.46s，1既有Starlette弃用warning。首轮11pass/2新夹具失败保留并说明，不改原断言。
- [x] (2026-10-21 11:29:58 +08:00) root额外批准DOM第3处临时观察迁移：先跑原counter保留1failed/3.86s（真实recovery=0）；仅1→0后两原DOM精确复验1passed+1strict xfailed/10.16s。原JS/probe、三轮/调用/回执断言均保留。
- [x] 真实旧DOM正文保持可读，回执仍按原LegacyReceiptMissing strict-xfail，当前/history皆0，不冒称全部DOM通过；P4完整验收未达成。

## Surprises & Discoveries

旧页面只读data.type，不识别命名事件；新React生产legacy解析器遇v字段会转严格named wire，不能把v=1加type伪装旧帧。它会把无版本tool_result.receipt交旧记忆卡解析，所以不能把generic PublicReceipt脱掉版本后塞入旧tool_result；本片工具进度只用安全summary映射status，不给工具名、arguments或generic receipt。

失败重试会保留旧error行。legacy客户端只记一条serverError，若把旧attempt错误重新投影可能在新final之后仍显示失败。因此仅当前终态、匹配usage.event_terminal_error的attempt/epoch/status/seq才映射error；final必须与当前已提交run.result逐字相等，不能把旧信封或已过期空事件历史补造为result。并行M5负责物理清理/过期证据，桥只遵循其RunEventReader返回和拒绝，不另补正文。

首轮两个新夹具前提有误：Loop实际tool_result当前不带可选receipt（信封确有真实saved回执），改为在实际完成回执基础上显式构造schema允许的可选字段投影反例，绝不声称producer已发此字段。源撤销首版只调repo.delete，未调HTTP既有同事务invalidate_derived闭包，run仍succeeded；改用既有完整delete+closure并先断言revoked，不放宽投影/旧测试。

## Decision Log

root于2026-10-21 11:18前批准：新增adapters/run_event_follow.py、adapters/legacy_run_events.py、application/legacy_stream_projection.py；最小改thread_events共享读取、web.stream v4委托legacy。v3原分支、冻结Schema/Envelope、Runtime/Loop及retention不变。JSON202/API原握手保持；本片只改变v4旧POST表示，与P4正式目标一致。

共享follower只返回已验证PG事件或心跳标记，游标只由数据库页推进；不按hint seq跳过，不存正文缓存。named编码仍调用原encode_sse；legacy格式无v字段、无冻结命名event，不能进入严格events_v1校验路径。只在当前原PG final事件真实存在且匹配原信封时发result；正常终态后一次[DONE]，断线不取消业务且双finally退订。未知/损坏内容不转换成供应商原文或假成功。

root追加批准只读复用M5的event_retention_metadata.is_closed(run)，在同owner事务先挡已关闭历史的缓存正文，新增真实30d sweep→legacy仅DONE/named空流/旧缓存final不出result反例。M5须先独立提交，本片不改其元数据或reader。过期后retry维持其保守拒绝，不自动新epoch。

第3处协议观察迁移为test_legacy_dom_runtime_pg.exercise_roundtrip的recovery_count 1→0：旧JS原来忽略named后额外GET查结果，现在从legacy result直达。root要求并已实际先红后迁，保post_count1、真实saved、2次scripted请求、v3→v4→v3/history3、owner隔离、receipt[1,1]与原严格raises xfail，未改static或probe。api_chat_acceptance_v1最小同步当前默认legacy并保留M4a临时named的历史说明。

## Plan of Work

先抽取现thread_events内部follower/响应关闭类，不改变GET字节编码或边界。新legacy编码器把started映射真实run/原话/线程与operation，context仅既有安全元数据，工具summary映射status；text_delta/reset保留已有公开文字，旧static会忽略而新legacy reader可读。ask/options只投影真实已提交卡，final用read_result原canonical得到answer，error只映射当前持久终态。schema仍冻结，桥不写PG新事件。

web.stream仅在v4分支换legacy_response；普通JSON已在chat返回，不受影响。retry/resume所有实际调用方走同一分支，读相同run；既有复杂v4 reading/报告拒绝保持，不能借换流解锁它们。v3段落原样保留。

## Validation and Acceptance

新目标将用真实隔离PG/ScriptedPort以及trust_env=False本机socket：默认POST旧result与JSON→GET frozen final指同一原信封、同ID和调用数；慢模型流首先出started/status而非等待final；工具摘要不夹工具arguments/推理/generic receipt；取消、撤销/私密关闭、旧attempt error与当前final不混、终态空历史不造结果。GET断线/游标/跨owner/提示退订旧断言保持。映射场景X03恢复不重复、X04取消、X08续传及F03撤销，不以本片目标绿宣称原评测全绿。

获root放槽后只跑新专属文件，再串行指定旧thread_routes、M4a验收、cursor/replay/M3 HTTP目标。清凭据/追踪，TZ=Asia/Tokyo、PG仅本机随机schema；当前0pytest/0真实模型/0服务器/0飞书。

## Idempotence and Recovery

桥仅读取持久run/event，不consult、claim、retry或补存别名。终态缺事件的修复继续原reader受信规则；正常过期清理不能由桥补正文。订阅只唤醒，响应断线或ASGI取消均释放hint订阅；不保留无界缓存或连接。原同request预算/来源/pin和取消租约门不改，无数据库迁移。

## Outcomes & Retrospective

M4b后端桥已实现并目标验证：58项明确组合通过，真实旧DOM正文1pass且真实回执仍1strict-xfail。原13首轮的2夹具失败、原DOM counter首红、原M4a80与11点宽验均保持历史，不回签绿。运行环境Node实测24.15.0，读取P2根node_modules已锁jsdom；并非CI Node22验证，不安装/修改依赖或他线。M5候选的is_closed/真实sweep是先行依赖，root须先发布它再发布本片并从组合固定头宽验。详见docs/v4/evidence/P4/2026-10-21-legacy-stream-bridge.md。

旧DOM真实回执、memory_receipt生产、固定reading桥和完整P4仍独立未完成；前端/旧static未改，不能用core4别名绕过严格卡片投影。GET冻结帧/游标与同一PG序号保持原行为，v3原分支未改；无迁移、无真实模型/服务器/飞书访问。

## 修订记录

- 2026-10-21 11:18:28 +08:00：按root批准创建M4b活计划，列共享读桥、原断言精确迁移及旧attempt/隐私限制；尚未运行pytest。
- 2026-10-21 11:29:58 +08:00：完成58项明确PG/socket组合与两原DOM实测；记录三处协议观察的批准迁移及首红/M5依赖/仍缺回执，不改旧业务安全断言。
