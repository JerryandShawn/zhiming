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
- [ ] 画像查看/编辑/删除及真实profile_items组合复核；03:00归档/空闲10分钟脚本反思/同线程单在途/无痕排除。
- [ ] 按v59修主线needs_brain_review/C21/critic契约失败，R35/M05/M08、46所有脚本门、一次完整tests/v4/CI及迁移相同回执。
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
