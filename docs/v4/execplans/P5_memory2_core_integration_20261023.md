# P5：把记忆 2.0 接入 v4 新核心

本计划遵循 `.agent/PLANS.md`，四个活文档段落随里程碑更新。全部记录使用北京时间（Asia/Shanghai，+08:00）。

## Purpose / Big Picture

让新核心真正保存、检索、更正、撤销和归档用户授权的记忆，而不只交付纯函数候选。新核心既有 P3 的工具身份、原话范围、撤销和提交守卫继续作为权威。完成后，用真实隔离 PostgreSQL 与 scripted 模型复现指定场景；纯模块通过不代表产品场景通过。

## Progress

- [x] (2026-10-23 22:43 +08:00) 已采用指令板 v3，保存旧模块线 WIP，新建 `v4/p5-memory2`，重建每 20 分钟续作。
- [x] (2026-10-23 22:56 +08:00) 首片 `74360f4` 已推送；PR #17 已核实为 Draft，目标分支正确，无合并。
- [ ] 里程碑一：记忆检索相关测试通过；首轮全量和补证已完成，仍有一项未改动的评测 CLI 契约断言待主线协调，不能标全量绿。
- [ ] 里程碑二：已接保守去重、合并撤销、敏感提案确认/拒绝/撤销应用服务；单值槽更新、矛盾提案与认证渠道接线仍待完成。
- [ ] 里程碑三：事件过期归档、八节画像反思提案、精确撤销与派生引用传播。
- [x] (2026-10-24 00:07 +08:00) 到期归档/撤销本地应用服务及隔离 PG 检查；自动后台/认证入口与产品场景仍待主线接线，未把里程碑三整体勾选。
- [ ] 里程碑四：`--target v4` 全部指定 scripted 场景、里程碑全量回归、草稿 PR 与接线回执。
- [ ] 后续里程碑：记忆就绪后再做 P5b B 的实体、迁移、API、topic_route 和分区上下文；P5b A/C 分别留模块原任务与前端线。

## Surprises & Discoveries

新集成基线已有 V4FactMemory 的普通事实默认保存策略，不能再给旧 MemoryService 全局放宽授权。敏感工具入口仍无条件产出提案，因此类别授权需要在同一受信流程内补齐。新分支没有旧模块线的 memory2 候选包，只能逐项复用相关文件，不能合并 PR #10 或恢复整份旧 WIP。

当前进程、用户和系统未配置 CORE_TEST_DSN；核对后已连接现存回环 55480 的 core_test_p2，验证 PG15.19，测试使用每例独立 schema。最初 postgres/Administrator 两个角色连接失败，不算通过，也未修改数据库角色。测试子进程显式使用已有 core_test 测试角色，凭据未写入记录。

相关测试发现“失眠”和 M08“复诊”未进入健康敏感识别，现已补齐。首次新类别测试有五项失败：四项暴露漏识别，一项误把 stopped 安全回执期待为 ok=false；修复识别并按既有契约修正断言后，组合 67 项通过，新增复诊用例及上下文/时间检索组合 34 项通过（两批包含重复范围）。

23:04 +08:00：P3 的 mutation_request 回执只允许 ID/状态；合并撤销标识放在既有 ids 字段，没有扩大提交门或回执白名单。合并前态放入非 pending 的同类 proposal 记录，附 fact_ids 与 source_refs，因此沿用撤销级联自动清除快照；不能放到未纳入级联的独立 artifact。真实 PG 组合 48 passed / 12.13s，证明等价内容只剩一个活动事实、精确还原、派生笔记失效、重复撤销无新增写入、忘记后不能恢复。

23:25 +08:00：P3 敏感提案现在由 MemoryProposalService 消费，首次确认绑定原提案修订、原话范围和新的用户确认消息；不接收模型提供的授权布尔值。第三人健康同时要求 health/third_party。类别授权保留可撤销证据，后续自动保存也携带授权来源；撤销确认会恢复 pending 提案/原记忆设置、停止依赖的自动保存事实并使派生引用失效。v3 默认授权和事实 ID 不变；仅 P5 提案事实按确认凭据分隔身份，允许撤销后新的明确确认而不复活旧事实。

相关真实 PG/旧 Core 授权组合 77 passed、51 subtests / 23.83s；已有两个 test_dsn 被 pytest 收集的返回值告警，未改旧测试帮助函数。新增拒绝用例首轮只有异常类型预期错误（已删除实体按既有契约抛 EvidenceError），修正后单项通过，拒绝会清空 proposal 正文；不把失败首轮当全绿。

23:51 +08:00：首次全量在 23:30:08（v4）与 23:31:06（旧 Core）启动，共两个测试进程；v4 3963 passed / 18 failed / 72 skipped / 943.17s，旧 Core 584 项、1 failed / 846.498s。不能把 skipped 当通过。失败涉及旧 Core 环境的官方编码器依赖、缺少 Node22/jsdom/PG 备份工具路径、撤销后评测观察器读取已删除上下文，以及一项 CLI 文案契约。

仅作相关补证，没有重跑完整套件：复用现存 `.venv-k3`、Node22、前端线 jsdom 和现存 PG 工具（只读依赖，不下载、不改共享环境），并修复 `tools/eval/targets/v4_context_observations.py` 对已删除 runtime_step 返回空上下文。失败涉及的文件及 PG 备份恢复检查共 64 passed / 56.98s，包括模型/飞书的 MockTransport 和回环 DOM 测试，无真实外部请求。剩 `test_eval_v4_contracts.py::test_v4_cli_is_offline_only_and_default_fake_is_unchanged` 的旧 Supported modes 断言，实际走 Live preflight failed；该 CLI 和测试均非本线修改，交主线协调，不擅改非记忆评测入口。

## Decision Log

2026-10-24 00:07 +08:00 / Codex：到期不等于隐私撤销；归档保留历史原话、回答及用户编辑，依靠事实修订使旧依赖失效，当前事实及其派生检索按现有投影过滤。归档前态沿用 proposal 的隐私级联，忘记后不能从撤销快照恢复。日期事件到 owner 当地日末，时刻事件到明确时刻；有歧义不归档，单值槽历史前驱保持 active。后台触发归主线，服务不在查询路径隐式写入。

2026-10-23 / Codex：以用户新授权及指令板 v3 为准，允许修改记忆服务、memory_* 工具及上下文记忆检索已有文件。主线 Agent 循环、提交门、通道、调度器与模型层不改；所需配合写入日报。

2026-10-23 / Codex：D1 沿用 Kimi Code、D2 k3-256k、D4 不开使用提醒/不登记紧急联系人、D5 E2 仅 2025 子集作为既定产品约束保留。本线不发真实请求，不运行 E1/探针；上下文守卫与推理要求沿用 P3 主线实现，不在记忆接入时绕过。

2026-10-23 / Codex：最多两个测试进程；日常只跑相关测试，每个里程碑只做一次全量回归，开始时刻限制在北京时间每小时 30–44 分。不跑三轮稳定性，不做逐文件哈希盘点，不做无尽储备。续作到 2026-10-27 22:00 后保存安全断点并暂停任务。

## Outcomes & Retrospective

尚在接入，未达到“记忆2.0就绪”。真实写入已接保守合并，敏感确认和两类撤销服务在隔离 PG 验证，认证渠道/按钮仍需主线接线。槽更新及全部产品场景未完成。旧模块线的测试不能替代本分支验收。证据位于 `docs/v4/evidence/P5/` 的 first_slice、merge_slice、consent_slice。

## Context and Orientation

工作目录为 `C:/Users/Administrator/Documents/Codex/zhiming-v4-mod`。起点是 `origin/v4/first-release-integration-20261023` 的 `5474c0aa4afe4c3d7fd764ab27ea76a988c2507f`。旧 `v4/mod-organize` 的未提交内容保存在标注 P5 前 checkpoint 的 stash，禁止直接应用到本分支。草稿 PR 目标为 `v4/first-release-integration-20261023`，不得合并。

依据：脑目录指令板 v3、蓝图 §6/§16、P5 阶段提示词、P5 记忆时间与冲突增补、系统提示词记忆和沉思段。来源授权指 owner/subject/事项范围、原话区间、源修订及撤销账本均有效；排序必须在这些检查之后，不能恢复失效资料。

真实入口是 `application/agent_tools_memory.py`、`agent_tools_policy.py`、`agent_tools_reads.py` 和 `application/memory.py`；上下文入口为 `agent/context_time_retrieval.py`。旧分支 `memory2/scoring.py` 等可按依赖逐项复用。所有业务时间由 Clock 注入，存储 UTC，日期按 owner 时区解释。

## Plan of Work

第一里程碑把已有纯评分用于真实 memory_search 的授权候选，保留词法相关性、稳定排序、检索上限与时间筛选。分别证明半衰期、目标/约束不衰减、陈旧来源不出现；不声称已接入向量模型。第二里程碑在现有事务和 operation_id 幂等边界内实现写入与提案，确认必须绑定原提案内容及当前源修订，不靠新消息冒充原话授权。第三里程碑保留用户手改的画像，所有推断经确认；撤销恢复逐字段且不得复活已撤销来源。

## Concrete Steps

在上述工作目录使用现成 Core 环境 `C:/Users/Administrator/Documents/Codex/zhiming-v4-p2/.venv-core/Scripts/python.exe`；不安装依赖或下载模型。测试子进程清供应商凭据和追踪变量，显式配置通过 local_dsn/verify_local_postgres 验证的回环测试库。

    python -m pytest tests/v4/memory2 -q
    python -m pytest tests/v4/agent/test_memory2_retrieval_pg.py -q
    python tools/eval/runner.py --help

最后一条先核对当前选择场景参数，再以 `--mode scripted --target v4` 跑所需集合。每项测试后小提交、普通推送，40 分钟内保存有意义的受测进展。每两小时拉取主线并普通合并到自己的分支；不 rebase、不强推、不合并到目标分支。

## Validation and Acceptance

必验 M01–M13、R01–R09、F01–F04、Q06，以及附录 B 的 A01–A03、MS01–MS03、KU01–KU02、TM01–TM02。每个场景须在真实 v4 工具链和隔离 PG 上使用 scripted 模型，有未通过项就保留未完成；不得仅依赖 fixture 成功宣布就绪。敏感类别确认后同类不重复问，未知项不编造，更新与撤销保留原话链，过期事件不冒充未来。真实模型请求为零。

## Idempotence and Recovery

写操作沿用稳定 operation_id 和期望修订。涉及数据库结构时使用 `xxxx_memory2.sql` 临时名，由主线统一编号。迁移先验证隔离库，不动 stage/生产。撤销业务变更必须重新检查撤销账本；代码回滚用普通反向提交，不改写共享历史。旧 WIP 和 ignored private 数据保留。

## Artifacts and Notes

证据放 `docs/v4/evidence/P5/`；日报为 `docs/v4/daily/YYYY-MM-DD_mod.md`，22:00 汇总，每两小时写真实进展，不补造缺失时段。续作任务 ID 为 `p5-2-0-10-27-22-00`，旧任务已停。所有公开材料只含合成断言与聚合结果，无正文/密钥。

草稿 PR：https://github.com/JerryandShawn/zhiming/pull/17 。代码断点为 `74360f4badb53b8d52fbb5c61aac7911ee2ef679`。下一次从提案确认/去重接入继续；23:30–44 才允许启动本里程碑全量回归，避免为等窗口空转或提前跑。上次上游同步为 22:26 左右，最迟 00:26 核对并普通同步新主线提交。

当前断点：保守合并 `4782063`，敏感提案消费/撤销 `f2d2653`，主线接线说明 `f407017`。首轮离线全量及 64 项相关补证均已结束，不再启动重复全量；下一步推进单值槽/冲突独立服务及带日期事件归档。槽 updated 的提交门/外部 v1 映射待主线协调。全量使用 private/p5-offline-tests 的 loopback-only Python 网络守卫，禁外部连接和 DNS，允许本机隔离 PG；私有 checkpoint 标明已结束会话及日志。若下个里程碑要做新全量，使用新日志名，不能覆盖本轮结果。

合并接线：`memory2_merge.merge_written_fact(service, ctx, incoming)` 仅在原事实写入/日期/敏感检查完成之后调用，按人物、事项、类型、日期、字段和值精确匹配，文本只做规范化相等，不做模糊合并。`MemoryMergeUndoService(memory).undo(owner, subject, change_id, expected_revision=..., message_id=..., operation_id=...)` 要求认证 owner、指定变更版本及明确撤销原话。更新/撤销会让修订递增；逐字段还原指业务字段，不倒退审计修订或创建/更新时间。公开回执无快照正文。

## Interfaces and Dependencies

第一里程碑沿用 `memory_search(service, args, ctx)` 和 Clock，不改工具参数契约或提交门。普通 L4 检索最多 50 条消息、50 条事实；事实先经过当前来源修订、撤销范围、人物与事项检查，时间查询仍先排日期命中。评分使用词法分数乘重要度，不使用重建索引的 created_at 让旧资料变新。memory_search 输出明确标注 vector_available=false；没有宣称混合向量检索已经完成。提案消费入口、调度触发或最终工具回执契约若需跨所有权修改，记为主线配合，不自行改动。

敏感提案：`MemoryProposalService(memory).accept(owner, subject, proposal_id, expected_revision=..., message_id=..., remember_category=..., operation_id=...)`；`reject` 参数相同但没有 remember_category。撤销确认：`MemoryProposalUndoService(memory).undo(...)`。认证入口须把实际点击转成绑定同一 owner 的 user/web-action 原始消息，分别为“请保存这条记忆”“请保存这条记忆，以后这类都记”“不要保存这条记忆”“撤销这次记忆确认”；message_id 不是模型传来的授权旗标。严格校验角色、人物、原话修订/区间、状态、撤销账本和无痕。记忆设置的撤销只恢复两项 memory key，保留 runtime 等无关设置；记忆授权本身已再修改则拒绝覆盖。

## 修订记录

2026-10-24 00:07 +08:00：新增到期归档/撤销服务，相关组合 55 passed，新增守卫后的受影响文件 32 passed；记录历史保留与主线后台接线边界。无重复全量，下一步继续单值槽独立服务。

2026-10-23 22:43 +08:00：恢复后的首份独立接入计划，采用指令板 v3 并明确当前无验收结论。

2026-10-23 22:54 +08:00：记录真实 PG 验证、相关测试结果与首片接入；全量回归按错峰窗口待执行，不提前认定里程碑完成。

2026-10-23 22:56 +08:00：记录已推送提交、已核实的草稿 PR 与下一续作断点。

2026-10-23 23:05 +08:00：接入保守去重及撤销应用服务，记录 48 项真实 PG 相关验证及主线待接接口。

2026-10-23 23:26 +08:00：补充首次敏感确认、类别证据、拒绝与撤销服务及相关测试，准备首轮错峰全量回归。

2026-10-23 23:51 +08:00：如实记录首次全量失败/跳过与相关补证，修复撤销后的评测观察器；剩 CLI 契约与 updated 回执协调不阻塞独立记忆服务开发。
