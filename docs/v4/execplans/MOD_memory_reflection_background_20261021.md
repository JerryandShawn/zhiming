# MOD：记忆后台反思与“关于我”纯投影

## Purpose / Scope

承接33号第四节第7项。只新增纯模块，后台工作只产生计划/候选，不创建真实run、调用模型、保存事实、改画像、发提醒或删数据。复用已完成memory2的授权、反思候选、日期、冲突、去重和归档规则，不改其冻结入口。只在zhiming-v4-mod工作；用户离线时将决定缺口记日报并继续独立部分。

## Context and Orientation

依据蓝图5.3/6全部/16、原P5及18/P5增补、33模块第7项。触发口径为线程空闲10分钟和owner本地03:00兜底，后台通道且同线程仅一个运行；“关于我”固定8节。反思不是绕开默认记忆策略的第二条写入路径，用户拒记、无痕、来源撤销、敏感先确认、出生资料专用确认与助手话语不变成用户事实始终保持。

现有只读入口：memory2.reflection.reflection_candidates及ProfileItem/ChartSummary；memory2.guards授权；event_time_extended_v2原话日期；conflicts/dedup/archive候选。旧ChartSummary.trusted不是实际P8计算/claim账本证明，不能因此自动渲染为已确认用户事实。

## Progress

- [x] (2026-10-21 07:59 +08:00) 阅读33#7、P5增补全文、蓝图6全部及原P5相关要求；读现有反思/记忆契约，先登记计划。
- [x] (2026-10-21 08:06 +08:00) M1：纯调度/幂等工作意图，idle10分钟、03:00兜底、当前后台许可、scope/thread/无痕与已有运行门禁；41项通过，含1000 FrozenClock随机。
- [x] (2026-10-21 08:29 +08:00) M2：当前来源绑定的抽取式情景/滚动摘要、去重/可能冲突、日期修复与缺口、画像提案及归档/跟进候选已实现；未执行写入或调用模型。
- [x] (2026-10-21 08:29 +08:00) M3：八节“关于我”typed/Markdown投影，当前来源/原话/事实/分析分开，pinned和手改也受撤回过滤；第7节明确未验证。
- [x] M4本地：自有97+独立143合计240项通过，性能/3合成metadata样例/接线和回执齐，root源码与源hash复核完成。
- [ ] 错峰完整回归、新HEAD CI与真实主线接线另待后续证据；Git提交号在日报单独记录，不预报上线完成。

## Surprises & Discoveries

现有ProfileItem没有内嵌owner/revision，需要新增显式host文档快照并绑定MemorySnapshot/current source版本。pinned不等于撤销豁免，手改条目也不能继续展示已撤回来源。既有reflection候选可以复用，但不是可信host批准或实际profile patch。

M1复用已冻结Q4 `wall_instants` 检查当地03:00。Helsinki的03点可能缺失或重复，当前无主线DST策略时输出结构化blocked，不默认选早/晚瞬间。普通idle触发按UTC经过600秒计算；03:00按注入timezone而非Tokyo主机时区。

root复核补齐同operation/input却不同thread_id的误重放边界；现在整次固定错误。独立review还要求epoch变化后所有授权源消失时只产生失效候选；已显式早返回，不能借其他全局事实重生summary/profile/newfacts。自审补齐注入“遗漏事实”与当前授权事实的去重/否定冲突桥，避免重复提出或将可识别冲突作为普通事实候选。

一次Ruff目录范围误用触及独立代理正在新增的两个测试文件，仅换行格式，没有改断言或矩阵；已立即告root与代理，不恢复以免覆盖并发编辑，随后只枚举自有文件检查。独立代理确认无真值改变。除此之外没有修改peer或冻结产品。

## Decision Log

模块必须以显式输入取得当前background许可、scope、线程活动、运行/租约与当前来源；不查凭据、环境网络或数据库。没有许可/来源时只返回blocked/noop，不能“默认允许”。03:00/空闲触发只输出待主线原子入队的意图；P1b额度停止与持久锁仍归主线。

BackgroundPermit是主线当前明确配置的纯投影，不是用户审批步骤；缺失返回结构化blocked，不向睡眠中的用户索要确认。当前source cursor绑定ID/revision及原文、原始时刻、role/origin摘要；operation绑定当前snapshot revision、source epoch、thread revision、permit revision、trigger、timezone与cursor。同线程已有queued/running账本不新增意图，持久锁与队列CAS仍需主线事务完成。

纯规则只能产生抽取式摘要，不能冒充LLM情绪判断/专业结论。新事实候选若需模型抽取，用显式注入的候选接口并再过原话/敏感/拒记策略；缺少接口时报告未接，不放桩返回当完成。日期歧义形成知识缺口，不暗选候选；跟进只是计划，不主动联系用户。

用户手改或pinned条目只给建议；所有新增/更新候选须source_ids/fact_ids及当前版本。渲染不能把assistant_claim/note说成“你说过”；没有权威P8字段映射时，第7节保留未验证状态，不凭trusted布尔字段生成盘面事实。

ProfileEntry正文和origin须由可信host审核；原话anchor、类型与hash只证明当前来源绑定，不证明自然语言归纳必然成立，用户手改也不自动为真。没有增加用户审批。缺当前画像文档时不补造更新目标；来源撤销后pinned也省略。MemorySource不含thread_id/区间撤销账本，主线须在权威投影前核对线程关联与原话撤销区间，纯类型不能认证数据库权限。

调度意图、工作候选与画像视图都没有实际队列或写入。当前worker自身租约所有权尚无投影口径，running/活跃租约仍保守阻止工作计划，不能主张已可直接部署真实反思worker。使用提醒D4保持关闭，候选不是用户下次开场的“已补记”回执。

## Outcomes & Retrospective

root专项覆盖于08:25:26启动，报告+反思471项通过3.11秒；反思18源行930/1017=91.4454%，
分支250/322=77.6398%，综合1180/1339=88.1255%。只行覆盖超过90，分支/综合仍有缺口；
源快照另存MORNING_candidate_coverage_boundary_0825.json，没有读取Q5 B或75条私有校准正文。

已新增18个纯产品文件和配套自测、独立验收、性能工具、接线说明、三份可重生成的合成场景metadata摘要。自有97项0.68秒与独立143项合计240项0.95秒通过，包含1000自有FrozenClock随机和500独立随机；Ruff/format及产品类型标注/400行文件/60行函数检查通过。最终18源aggregate为`2eee084f643e38d0e32d918e52ecc93c7ce1564558332419a94ffa3321ef390d`（逐相对路径、NUL、文件字节拼接SHA256）。

完整路径性能在08:26:03+08真实产生，每样本100次M1→M2→八节renderer中位0.6199911秒、Python分配峰369,493字节；1000次撤源epoch→仅失效候选中位0.3992524秒、峰44,335字节。计时包含输入构造、当前源校验与输出断言，不包含导入/fixture字节读取/hash/证据写入。没有实际模型、队列、数据库或通知速度验证。

三组合成metadata样例final在08:29:03+08产生，展示完整候选、用户编辑protected与撤源只失效三路径；没有私人正文，没有情绪/结论推断，没有任何已保存回执。实际LLM沉思、画像/摘要写入、真实dispatcher/线程锁、PG撤销传播、P8命理档案和用户便签尚未接入；root覆盖/回归/Git/CI状态由root后续记录。本模块不冒充原P5全阶段完成。

## Interfaces / Recovery

拟新增application/reflection_v3与独立profile renderer；最终API在M1前冻结。主线需提供当前权威快照/来源查询、后台guard、thread锁/租约、幂等队列、profile编辑与提案确认事务、撤销传播。没有数据库迁移，不改现有worker或API。

现已提供 `schedule_reflection(...)`、`plan_reflection_work(...)` 和 `render_about_me(...)`；准确参数、返回字段、边界与主线位置详见新接线文档 `docs/v4/integration/mod/MOD_reflection_background_20261021.md`。其中 ProfileDocument绑定profile revision、snapshot revision和source epoch，所有候选仍需主线写入前重新授权，不可直接当apply请求。

每个工作意图绑定owner/subject/thread、source epoch、snapshot revision、已处理游标和内容fingerprint。同operation同输入可安全重放；任一来源撤销/版本变化必须重新规划，不能复活旧提案。所有对外异常只固定中文/原因码，不含私人正文。

## Validation / Handoff

重点验证：10分钟/03:00边界与时区、未来/回拨时钟、无痕/停止/已有运行、撤销/跨owner/过期/双当前事实、敏感拒记、助手来源、pinned/手改保护、source-less条目、Markdown字面渲染、同输入幂等及source epoch变化。主线接线指南须列实际入口、依赖端口与需改哪些已有文件，并明确没有执行实际反思/画像写入/通知。

## 修订记录

- 2026-10-21 07:59 +08:00：root创建，定义只候选、八节画像及当前来源边界。
- 2026-10-21 08:06 +08:00：接管维护；记录M1的41项/1000随机与DST保守门禁，M2/M3仍未完成。
- 2026-10-21 08:29 +08:00：记录18源最终候选、240项独立合测、真实完整路径性能与三组合成metadata；保留host权威/语义审核、实际模型/存储/调度未接线限制。
