# P3：v58记忆updated主线闸门

## Scope

当前main60/v59 R32优先：独立无P8树zhiming-v4-mem2-gate，v4/mem2-gate，从3b095f397568e783ec05454f855694456bbbca4d建立，H1公开416605312775597c2ba86607821aca7cc08f2053与L2保护d4344bdc保留。R32明确不等模块日报，精确合入f44f5dd45b1a51631712b00b93aafff61fa9b126；完成附加段2–5及主线评测契约失败修复，在本机候选跑完整回归/脚本门/CI，按46冻结记忆候选和执行单/受影响真实题。P8只在其集成树，首发e578冻结；无新迁移/undo_token/M6索引，R1/R2a服务器权限仍按直接授权和各Go窗口。49第一/二/三节已读，后续队列按R2a→P8→第三批→P7→P9→P10/P5b，R2b及以后部署仍需会话人类确认，不把总队列当服务器自动授权。

## Progress

- [x] 01:16实际读main58及41附加段1，独立工作树建立。
- [x] 完成updated精确版本/旧事实闭包及公开回执契约，01:24交付见下。
- [x] 定向真实PG、saved回归、迁移逐文件相同检查，提交推送并发布H1 SHA。
- [x] 05:00完成独立L2 field保护接口及实际构建调用，42项定向通过。
- [x] 08:16按R32精确普通合入f44f5dd45b1a51631712b00b93aafff61fa9b126，merge 6d5f35b3d78aed5b45e6816648141232d46d938a，无冲突，无P8。
- [x] 08:30认证提案确认/忽略/确认撤销、slot/confirmed_slot/merge/archive变更ID+revision路由，画像查看/编辑/删除，真实HTTP/PG及原生回归通过。其他冲突/事件日期撤销类别及网页展示仍待，不把API当按钮完成。
- [x] 08:47画像HTTP及真实profile_items/L2组合；原生03:00归档/空闲10分钟脚本反思/跨进程单线程锁/无痕排除，真实Web lifespan已注册。
- [x] 08:47按v59修主线needs_brain_review/C21/critic契约及汇总空分错误，R35/M05/M08定向复核；记忆撤销驱动补前轮真实回执/效果与断点保存。
- [ ] 46所有脚本门、一次完整tests/v4/CI及最终候选迁移相同回执；认证路由尚未配网页按钮，事件日期等额外撤销类别未扩展。
- [ ] 冻结v4/release-mem2，执行单/打包及46约20题真实评测，门齐前不读key/不接入。

## Surprises & Discoveries

slot更新的旧事实保持active但有valid_to/superseded_by，原生proposal变更记录含old_revision/new_revision和两事实ID。旧事实不能仅凭affected_ids信任，应核本轮实际mutation receipt、对应operation和变更记录的精确修订，禁止事后改动被旧前缀冒认。

## Decision Log

updated的主事实与saved一样核整数且相等的revision；旧事实额外凭原生变更记录核验。saved原有策略不放宽。ids是撤销变更标识，不能按模型输入构造，也不引入undo_token迁移。发布前保持原始机器分、历史失败不变。

## Outcomes & Retrospective

H1及独立L2保护已有原始证据；R32指定候选已实际合入，真实画像服务组合/路由/调度/R35与46完整门继续执行，不再因模块旧日报等待。SSH只读探测失败，v60称本机VPN路由原因，未修改网络/远端。主线全量关口未过，不称候选就绪。

## 2026-10-27 08:18 R32接线计划与原始事实

main60/v59与49第一、三节（及额度表）已实际读。文件自报08:50/08:45晚于本机当前08:16，照其明确内容执行，但日报用真实Clock时间，不补造未来检查时间。短SHA直接git fetch f44f5dd原生拒绝找不到ref；随后fetch其远端分支，解析到精确f44f5dd45b1a51631712b00b93aafff61fa9b126（远端tip已a8d662a3，未合tip），普通merge无冲突得6d5f35b3d78aed5b45e6816648141232d46d938a。

先接实际存在的MemoryProposalService/ProfileProposalService和变更撤销服务：认证owner只从X-Token取，严格修订/request_id/body白名单。点击动作在owner事务内绑定目标/动作/修订/remember_category，再由程序记录真实web-action用户消息，随后调用原生服务；每次重放重新调用原服务核来源/撤销，不仅返回外层缓存。跨owner/错误人物/陈旧修订整个事务拒绝，不创建孤立授权。服务缺口逐项实现/核验，不写占位路由或声称画像编辑/调度已完成。不重做H1/L2旧绿；合入后组合需要实际定向证明。

## 2026-10-27 01:24实际交付

H1实现已完成：updated公开事件和ids契约；loop_codec主事实精确整数revision核验、affected_ids旧事实加入完整来源闭包；_own_revision同时允许saved/updated，历史旧事实额外核本轮持久mutation receipt、原生变更记录精确old/new_revision及三项实际operation（旧fact/新fact/change）。旧前缀不能采用外部新修订；变更记录事后修订也拒绝。saved原路径未放宽。依赖采用仍走owner/subject/case、来源撤销、租约等原闸门。

公开envelope只展示从真实old/new fact重新读取的摘要，呈现“已更新：A → B［撤销］”；原Journal/mutation receipts保持原件，不把展示正文写回计量/操作凭据。static只增转义后的状态文字，没有捏造撤销端点；真正变更ID+revision撤销路由属于附加段2、待模块合入接线，不宣称此时已能点按钮撤销。新增PublicReceipt可选ids/summary与MemoryReceipt.updated同步机器schemas；原未设字段/原saved输出保持兼容。

最终完整定向轮private/safe-narrow-99fd6280f25f46dda0964e9f4fcd4770：106/106，13.82s，metadata/XML/log已根核；覆盖updated修订号布尔/错值拒绝、旧事实闭包、后续外部修改/变更记录修订拒绝、无原生证明拒绝，原saved own-writes/最终提交/连续脚本原有测试。此前6e6bfe258e3a4e0595152d3be56bf2f5为85/85、5.29s；16f2a7e07fed4ca0a97b6d0ccb575f8f为20/20、11.04s（增补精确证明前的原saved回归），均留原件，不拼接声称全量。Node原frontend检查及新增转义/updated状态断言通过，node --check通过。Ruff/check+format120及git diff --check通过。

private/v58_migrations_unchanged.json：8个SQL逐文件canonicalLF与冻结e578原Git字节相同，git diff migrations为空；无P8源码加入本分支，无新迁移/undo_token/M6索引。未跑完整tests/v4、KU01/KU02或CI，不能称模块/记忆候选就绪。真实模型/远端修改0。01:15 SSH探测仍banner timeout/native255，session95538已结束。

Progress以上本轮H1项均完成，推送后在DEV日报第一段写H1闸门已发布+精确SHA，供模块普通merge；不向其他聊天发消息。下一依据模块就绪状态做v58附加段2–5或继续P8，记忆一旦就绪优先合入此无P8分支；首发e578/r46保持冻结。


## 2026-10-27 05:00 独立附加段4：结构化资料与时辰提示保护

main58仍允许2–5并行先做。先核附加段2后发现当前无P8主线还没有memory2_slots_undo等原生模块服务；撤销依赖只存在未就绪模块树。没有提前合入/复制模块、没有写501占位端点或假服务，按同板切到能独立验证的附加段4。模块最新首段03cc0bb指定37/37+4/4过，但仍未记忆2.0就绪，9ef7262完整失败原件不改。

新增context_fact_guards.fact_item复用原始L2事实JSON格式，未知时辰提示条件/正文/alias/排序不变；build_layers在fact_layer画像投影之后调用preserve_field_facts，只从当前已授权SourceSnapshot.facts恢复有field的资料。已有结构化事实项按原位置重建，缺项追加且required=true，普通画像可代表的非field事实不重复添加；来源版本仍沿原injected_versions闭包。画像声称准确不能覆盖原生time_unknown/precision unknown，撤销或其他owner事实不能凭画像ID被恢复。fact_layer只是复用同一render helper，正常输出保持逐项相等，既有context cache/epoch前缀稳定性测试保留。

private/safe-narrow-66c5a397b8144dbeba5bf9cc097bd9d4实际42/42、12.69s，原metadata/XML/log根核exit0/fail0/error0，无skip/warning。含真实PG资料、存储画像的纯投影输入、unknown/False/exact/gender五边界、已被画像改写的资料恢复、撤销和跨owner不补回、实际ContextEngine调用及原fact/message版本闭包、原上下文/历史窗口/epoch兼容。Ruff/check/format120三文件与diff--check过；没有额外全量/真实模型/CI请求。

验证限度：当前主线没有模块的profile_items加载器，测试明确没有提前导入该服务；已确认画像作为真实PG存储行进入纯L2投影边界进行策略验证，不能据此声称记忆2.0整条画像产品路径已通过。模块就绪正式合入后，必须保留build_layers这个后置保护，并用真实profile_items组合再验。未新增migration/undo_token/M6索引，不覆盖H1原发布报告或其旧8 SQL相同证据；本轮只改agent上下文和测试/本计划，不需要刷迁移/treehash。

04:55一次SSH true仍banner timeout/native255，session39035已结束，无认证/远端命令/修改。原PG55480/PID50516只核存活未启停，无后台测试。batch2 P8头9ba30488、首发e578/r46未改，本树保持不含P8。下一模块一就绪立刻在此树普通merge后接附加段2–3/5与46门；若仍未就绪，切回P8缺资料确认等独立余项，不反复尝试不存在的模块API或重跑H1/本轮绿测。


## 2026-10-27 08:30 附加段2原生HTTP接线增量

MemoryWebActions将认证按钮转为原生web-action/user来源，稳定request_id绑定人物/实体/动作/修订/同类授权/变更类型；同key不同意图拒绝。敏感记忆确认的remember_category沿原生授权，不接模型consent。确认/忽略/确认撤销转原MemoryProposal及ProfileProposal服务；变更撤销按类型转slot/confirmed_slot/merge/archive原生Undo服务，精确变更ID+revision，无undo_token。每次重放仍走原生来源/结果复核，不能靠外层幂等绕过撤销；跨owner或错修订失败整个事务回滚，不残留授权消息。公开回执仅已有body-free字段。

ProfileWebService及认证GET/POST实际提供单条画像查看、编辑、删除。查看严格checked_profile与当前授权事实/原话版本，不回私有证明；编辑只改画像text并标edited_by_user，保留fact_versions及来源，追加真实点击来源；不创建或改写原事实，拒凭据及无效文字、section/owner等额外字段。命理第七节不能手工替换；删除只删画像，不删原事实。两动作原revision/request_id幂等，结果后改或来源撤销不能重放复活，GET无写。此轮是API接线，不宣称网页按钮已展示或整个附加段2完成；其他冲突/事件日期撤销类别、调度/R35/评测契约修复仍待。

最终扩展定向private/safe-narrow-c36e6909a8a34c10b61c4bc14dfe5338为125/125、39.08s，08:28:04–08:28:44，metadata/XML/log根核exit0/fail0/error0/skip0，既有Starlette/anyio弃用warning1。含新HTTP原生PG认证/隐私撤销/精确重放/各端点跨owner拒绝、画像无事实写入，以及原提案/画像/单值替换/确认替换/合并/归档撤销回归。939dbdcbdb8146a6b333dd13906ad6c4为27/27、10.60s属前轮。长度检查发现路由工厂含嵌套函数超过60行，拆出profile_router后d2bd7236b7344c26b3e010e625098d09真实注册再验27/27、11.29s；两分轮不拼125或全链。Ruff/check+format120五新文件、legacy web AST及新函数≤60通过。

失败原件均保留并已逐一根核：b13aac11ec6d485397ae0c615c49785c为6pass4fail（绑定回执自造family字段被原白名单拒绝，改用code，未放宽）；37d5ad89be21482ea37536e5f06a77aa为9pass1fail（测试时钟早于新事实，fixture前移7日，原未来事实拒绝不变）；e05ff7a59bf144adb66bd4f821ac8172为10/10初轮。7cd8b13089d3488b8c47f7862547bd26为113pass1fail，测试直接repo.delete来源却断言整条级联，改为原生retire_fact(scope=source)；79fd4b0411664422a76215a452dac9bb为113pass1fail，原生撤销已正确撤销当前run，fixture继续finish租约被正确拒绝，改断言run revoked，不重开租约或改产品闸门。

private/v59_migrations_unchanged.json实际比对8 SQL canonicalLF同e578，额外SQL为空，旧v58回执保留。首次写证据脚本误指不存在的mingjing_core/migrations路径，断言中止0写，随后改实际repositories/migrations后核8项。无新迁移/undo_token/M6索引/P8/真实模型/付费接入/新CI/全量/服务器修改。08:15唯一SSH仍banner timeout/native255，session38595结束；PG55480只核存活未启停其他PG。下一直接03:00归档/空闲10分钟脚本反思单线程调度及R35/M05/M08/needs_brain_review-C21-critic修复；真实profile_items组合与一次完整门仍待，不称候选就绪。


## 2026-10-27 08:48 原生调度、真实组合及主线评测契约

本wake main60未变，模块首段已正式记忆2.0就绪f44f5dd（原全量仍失败清单，不伪称绿）；先前R32精确合入已完成，不重复。08:35唯一SSH session99634实际banner timeout/native255，未认证/远端命令/修改0；原PG55480 PID50516单次核存活，未启停。

MemoryMaintenanceSchedule已实际注册原Web lifespan，原worker每轮经asyncio.to_thread调用，60秒节流、进程内非阻塞guard；不创建第二条常驻模型线程或新的生产模型配置。03:00采用owner IANA时区，服务启动晚于03:00做当日catch-up，既有runtime_step存当日游标/完成标识；每页最多100事实、每tick最多50owner，只将有原生明确到期依据且当前授权/来源有效的事实交MemoryArchiveService，不直接改状态、猜日期或删除历史；撤销服务仍原生。未知时区保守跳过，不用系统时区猜。线程扫描只选原生active/life且incognito严格false；空闲不足10分钟、在途queued/running（包括无thread_id的同人物旧run）不反思。每线程PG session advisory lock跨不同调度器互斥，另有持久running/complete/failed指纹标识，同一闲置输入失败或未知不自动重算。

IdleMemoryReflection准备当前授权事实版本，事务外ScriptedReflectionModel纯本地摘取原事实原文/原来源、至多20条，通过ProfileReflectionService.consume_patch生成待确认画像提案；不自动确认、写事实、调用provider/model factory或联网。模型阶段不持owner事务，完成后短事务重新核线程空闲/活动原值、当前事实与来源/同意版本；计算期间新来话或撤销依据不发布建议，错误仅持久固定MEMORY_REFLECTION_FAILED无正文。无痕线程不触发；不读取临时runtime结果作为事实。此为脚本摘录整理，不能冒称真实模型语义反思质量已验。

调度首轮b7719fa84b454bae8bb0c2f5bbc266dc为7/7、3.48s。扩展d501cf2a798749188e8e38db139aacda为43pass1fail，发现旧run原生request没有thread_id，初查询未挡；产品精确补同人物且thread_id缺失的旧run阻挡，不伪造fixture线程。最终ef5c8a4c3679406e8d5c25a0e9abdad0为62/62、21.95s（08:42:17–08:42:39），含实际Web lifespan注册/旧worker继续、03:00前后与幂等、空闲/无痕、跨调度器单在途、事务外计算/期间新来话或撤销拒绝、真实module profile_items/L2出生资料保护/Agent、HTTP认证及R35全兜底/M05。e7af7d746ee94bc88ebb31fb62a93ad7为10/10、6.90s，补M08原生授权和范围事件/原评分契约不变；分轮不合称全门。

路由按41精确补跨owner404固定消息，不更改旧全局403处理；认证仍先做，无正文回显。新增/api/proposals/{id}/confirm|dismiss兼容入口，冲突提案必须显式choice old/new，派发原MemoryConflictResolutionService，原记忆选择/敏感同类授权不改，模型不提供consent。冲突Undo走原MemoryConflictUndoService；fc8114b24983411ba6372e81908b68bf为18/18、5.83s含两选择、缺选择无写、确认/撤销精确重放。无新migration/token。

R32非记忆失败已实测并修：9188b4ef5b9649e0a7b63060e2e9faa1为1pass2fail，原生JudgeJournal已正确通过，两critic旧断言仍期judge_unavailable；改为needs_brain_review且额外核machine_status/原null分/原failed_assertions不丢，评分重试原停止/物理计数不改。fd2a9c7c4d43490b8884ccd7754c7386为1pass3fail，C21尚在评分前拒绝新packet缺旧seed.synthetic，evidence_full为空；judge_payload加入由严格Scenario.seed派生的fixture.synthetic布尔，EvidenceJudge按packet版本读真实标记/seed memories，保严格is True且无证标记不捕获全文/不调用provider，旧payload路径保留。5e29b36f7acb4ba5b8479fe25cdd2426为112pass1fail，发现report.summarize仍把待复核null分相加，已单列needs_brain_review_ids和category计数，从通过/失败分母排除、不改machine原分/原状态；新增null及非null待复核纯汇总断言。最终db41caa4be0f4eb8bcd0f4c217bb9e52为114/114、64.69s（08:42:27–08:43:32），完整C21/critic/framework/R33离线PG重试通过，无真实请求。

补评分包隐私回归时发现f44新MemoryWithdrawDriver取代旧NativePrivacyDriver后遗漏judge_action_history；a924e817e99b4352b8e5555cb918f465为19pass1fail、da359536c4bc4c858f72b306850cf942为0pass1fail（第二轮仅打印ID/状态诊断，无正文），F01原生删除已成功但前轮回执没入评分包，不能改断言放过。精确补删除前原生followup关联、删除后真实擦除/事实撤销证明才投影cancelled(native_status=deleted)，记录真实回执/原生效果，同turn重放一致且不追加重复历史；lifecycle_state持久保存/恢复观察历史，不重跑业务效果、不改F01金标。360f7bf963ae4c98912ab9c894571de6为24/24、10.51s初修；最终1638313d144c418c81ed9d5b59239ef8为26/26、10.50s（08:46:49–08:47:01），含真实F01原生删除前后/包中revoked@turn/关闭跟进、严格false/null/string/int标记拒绝、待审/接受门、原M08动作及持久断点回放。所有metadata/XML/log逐根核exit及计数，旧失败不删，分轮不拼全链。

18个新增/修改Python文件Ruff/check+format120通过；旧web仅AST，新业务helper及变更driver函数≤60、diff--check通过。无P8、付费请求、全量或新CI请求；8迁移未改、旧v59原件保留。下一直接本候选46指定脚本组（R11+M/R/F/KU/TM/MS/A+TA01/M01）及一次完整tests/v4/CI；仍未候选就绪，不读key、不部署。API并不代表完整网页提案/画像按钮界面已展示，事件日期等额外Undo类型没有假注册。


## 2026-10-27 11:12 R42 parallel repair on an independent worktree

- [x] Read main v63/R42-R44. Created `zhiming-v4-mem2-r42`, branch `v4/mem2-r42`, exactly from ca5a340d. Original gate worktree, HEAD, source and full process remain unchanged.
- [x] R39 red regression: real PG empty/future-only scans changed owner revisions, both new assertions failed before the fix (`private/safe-narrow-82d16e9efd964be5a3917ddc149d8209`, 2 failures, 2.54s). Raw metadata/XML/log retained.
- [x] Fixed empty scans to make no database writes. An in-memory, owner/day cursor preserves 100-fact page progress without creating a user revision; only actual successful archival persists its existing native record. Restart safely starts scanning again; no archive authority/source/expiry/409 guard changed.
- [x] Final native PG/HTTP suite: `private/safe-narrow-f4dccbdffeea477da0cfe7bd6ac0139c`, 35/35, 12.21s, metadata exit0/XML failures0/errors0/skip0/log checked. Includes no-fact/future-fact no-write, a later due fact after a full no-op page, actual HTTP GET -> no-op sweep -> profile/settings POST, deliberately wrong revisions still 409, original CI four failing tests, scheduler, and independent stage guards. Two existing warnings: Starlette/anyio and old pytest test_dsn returns-string collection. No models/external sends/server operations.
- [x] R37 independent `tools.memory2_stage` CLI supports closed copy/capture/restore/seal/exchange with fixed mem2 database/root/unit, distinct restore/failed database names and operation. No local_drill option; first-release operations and names rejected. Reuses unchanged native PG15, protected admin env, program/hash, metadata/owner/ACL/SET, new object, connection/seal guards. Original first-release modules unchanged. Cross-stage metadata rejected in both directions before I/O. No Linux execution or complete deployment receipt claimed.
- [x] Ruff/check+format120 four files, AST functions <=60, diff --check passed. Initial fixture import F811 was fixed with explicit fixture wrapper; no ignores. Earlier 23/23 (14.52s) and 10/10 (0.15s) rounds retained, not summed as one chain.
- [x] R44 `docker ps` read-only: existing container `8229833f5698`, name `zhiming-b1-linux-20261021`, publishes 127.0.0.1:55481->5432; listener PID15208. 55480 remains native PG PID50516. This is not a proven residual process owned by this wake; no container/PG stopped, no Docker launch/pull.
- [ ] Original ca5 full still running with one E, about78%; retain it until natural exit or v63/R43 Beijing12:30 hard stop of our own test only. Preserve original failure details and diagnose non-memory issues. No repeat full on ca5.
- [ ] After remaining failures and R37 binding review, run revised candidate scripts and complete tests/v4 on the new SHA, inspect exact CI, then freeze/runbooks/authorized real evaluation. Current narrow pass is not candidate readiness.

Original gate-tree H1/L2/current ca5 full evidence remains at that tree's private paths; this tree's inherited plan does not replace those originals. Independent stage entry is implemented locally and guarded, but final SHA/package/runbook commands and47 review remain pending. No migration, undo_token, M6 or P8 introduced.


## 2026-10-27 16:20 actual resume / old full result

The queued heartbeat carried11:47, but actual clock and shell were16:15 Beijing on resume. All following observations use actual wall time, not the queued timestamp. The old ca5 full had already exited naturally at12:36:48, exit1/head_unchanged:5064 passed,56 skipped,1 warning,1 setup error/0 failures,13608.73s. It exceeded R43's12:30 cutoff by6m48s; no stop action was executed by this wake and it is not counted as meeting that cutoff. Metadata/XML/raw/error stack and at-failed-gate session rows are preserved at the original directory, plus failure_receipt.json.

The one error is `test_real_capture_source_guard_is_readonly_and_holds_original_both_fences[7]`: INCREMENTAL_OTHER_SOURCE_SESSION. Original diagnostic records allowed client57972 plus extra autovacuum worker60340. The production exact-session gate correctly rejected this; no client/worker filtering, retry, server setting change, PG restart, or guard relaxation is appropriate.

Fixed only disposable fixture construction: after applying original migrations, set autovacuum_enabled=false on its own freshly created mingjing_core tables. Require actual database identity fr_source_<32hex> or fr_upgrade_<32hex>. Source creation belongs only to local test fixtures; shared PG configuration and original migrations/production code remain unchanged. This matches the existing CI dedicated restore-server approach while avoiding a global change to local PG. Original failed guard test [7] now passed once with its unchanged read-only/file/advisory fence assertions: private/safe-narrow-b31e433b9556473c9a5164855118873c,1/1,63.90s; metadata/XML/log root checked. Ruff/check+format120 and diff check passed. No repeat old full.

16366f0e R11 completed11:30:39 exit0/head_unchanged:48/48,7/7,approved69/69,core30 29/29,X02 equivalent passed. assessment/source digest15d26f641e47a6416873e308d9758ab0c8c927bb9c7a3d15150c02664d068181; raw core81 incomplete remains original. 163 memory37 completed16:16:52 exit0:37/37, original contracts preserved, judge_calls0 (scripted model counters are not paid requests). Reports under private/candidate-eval/163...; these are163 evidence, not the next fixture-fix commit. Its push CI40442893062 was read as completed/cancelled, not failure/green; no rerun requested.

Next exact SHA after this fixture repair needs fresh scripts/full/CI. Freeze candidate source and HEAD during those runs. R37 final bindings/47 review/Linux stage and46 real evaluation remain pending. No key/provider/server deployment occurred. Weekly usage freshly read28%, below85; no final-batch contraction triggered.
