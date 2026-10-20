# 2026-10-21 集成预检：只读快照

截至北京时间 01:54（UTC+08），供主线 02:00 回归之后安排 `v4/integration` 使用。**本片没有 merge、cherry-pick、rebase、fetch、切分支、推送或测试；没有访问服务器、模型或飞书。** GitHub 与其他工作树仍在变化，以下精确 SHA 是本轮明确读取的固定快照，并非原子同刻状态；实际集成前必须重新核对。

依据：33 号第一节 §2、`../merge_roadmap.md`、各线已提交的接线资料。只使用已提交 tree；所有 staged/unstaged/untracked 内容都不计入候选。此文不是阶段完成、CI 绿色或部署许可。

## 1. 精确来源与本机映射

六个 PR 在本次 GitHub 读取时均为 **open / draft / unmerged**。表中 tree 由 GitHub Git commit API 独立读取，不凭 PR 正文中的旧提交号推断。

| 顺序 / PR | GitHub 已核 head | GitHub tree | 本机可读提交映射 |
| --- | --- | --- | --- |
| P1b [#9](https://github.com/JerryandShawn/zhiming/pull/9) | `8087d7fa64839dc5a080491fd5db4e358f5814ec` | `20834794b6c454731c95b9e23a38540de20f8e9a` | 主仓 `v4/p1b-k3-hardening@6ec4ceeb20fa4e39642461d77e9a0ec105e85d74`，tree 完全相等 |
| P3 [#8](https://github.com/JerryandShawn/zhiming/pull/8) | `a228ffb000327f13bf1a5e9ef1c8921c82c56095` | `7a8d8bc7f4d4dc0cec6b227795fed6c7d54fe0a1` | 主仓 `fc69dbbf42e2c6b6beeaeaa7962b564c86339fa1`，tree 完全相等 |
| 模块 [#10](https://github.com/JerryandShawn/zhiming/pull/10) | `26779a1cbb3ae0918eca580b4ce2f3cb1d952fb6` | `677b300343944ab07f7a74bd3b5b687fb7ac1084` | 独立 clone `zhiming-v4-mod` HEAD 即此 SHA；其大量新暂存文件不在本表内 |
| 命理 [#5](https://github.com/JerryandShawn/zhiming/pull/5) | `3e02305d74e1d43ca9e91b88fefb264dfacdfa3d` | `75ba90c0f92bc756dc2d176436d663b82be6a5d6` | 主仓已有该对象，可精确 `git show`；命理工作树已继续到 `6292199d8fdb167d03fe54b07f74060cec59e101`，后者不冒充此 PR head |
| 前端 [#6](https://github.com/JerryandShawn/zhiming/pull/6) | `b7e92553af0c704b359029bfeb469e1a3bce7e8d` | `f5fb92c0bb5b95121823d218e3388419259d7ba1` | 本次读取过程中由 `6878469` 前进到此 SHA；本机已有相同对象/tree |
| 文档 [#7](https://github.com/JerryandShawn/zhiming/pull/7) | `2bcfda3e5e8794954bd8f3e3a206e7429005312b` | `4a9430729b0bc3dd47d997f49a55c499592fc6e2` | 本机已有精确远端对象；本地 research HEAD `462c4e4` 的 tree 不同，不能替代 |

真正远端 `refs/heads/v4/main` 另经 [GitHub ref API](https://api.github.com/repos/JerryandShawn/zhiming/git/ref/heads/v4/main) 核为 `b9a89b6f84f7bebb640de080548010859aae630c`、tree `8ed180539f655124fc76d8981df318a337292ff1`。本地 `v4/main` 仍是 `7fa5e10a4dbe0e2878e28c6f6a115f17d013aaa2`，不是当前集成起点。当前无本机 `v4/integration` 分支或工作树。

主仓 `origin/v4/p1b-k3-hardening=d9abee0`、`origin/v4/p3-agent-runtime=f49218b`、`origin/v4/mod-organize=ebfa22f` 在本次开始时均落后于表中 GitHub head。只读预检没有刷新这些 ref。PR #5/#6/#7 的 metadata.base_sha 仍显示旧 `7fa5e10`，不可据此覆盖独立 ref API 确认的 b9。

主仓快照的未提交内容包括 runtime 配置/限制器和后续塔罗血缘修改；它们不在 `fc69dbb` tree 中，不能引用在途目标测试就当该 PR head 已包含。模块 clone 新的 briefing/partition/supplement 暂存文件和未跟踪 DAY 文档也未纳入。各源工作树状态会继续变化，主线不得覆盖、暂存或清理它们。

## 2. P1b → P3：真实文件与语义接合

两份已映射本机提交的 merge-base 都是 b9。按 **merge-base 到各自 head** 取变更交集，唯一双改文件为 `tools/eval/targets/v3_target.py`；这只是同文件差异检查，未运行 merge，不能据此声称无文本冲突。

| 位置 | 已存在的两份改变 | 最小处理与组合验收 |
| --- | --- | --- |
| `tools/eval/targets/v3_target.py` | P1b 初始化 `ConfiguredModel(...,role="evaluation")`；P3 为 submit_turn 加 owner 原子事务/私有模式拒绝时避免孤儿原话 | 两项都保留；不能整文件选 ours/theirs。真实 PG 验证拒绝后零原话、旧模型角色仍 evaluation、重放同 operation 不重复 |
| `models/port.py` → P3 `agent/loop_codec.py`、`application/agent_snapshots.py`、`agent/context_k3.py` | P1b 添加 private_content、reasoning_present、reasoning_signature_missing、execution_meta，并用 deepcopy；P3 的 dataclass 私有 Journal 编解码、as_chat 和完整请求计量消费该类型 | 验证 Anthropic thinking/redacted/signature、OpenAI reasoning、工具循环、崩溃恢复及旧shape严格拒绝/明确新epoch策略；私有块不得进入 events/core4公开投影/诊断。不能删新字段换取旧 fixture 通过 |
| `models/registry.py`、`transport.py`、`quota_runtime.py`、`quota_http.py` ↔ P3 `LoopCycle`、`AgentReviewer`、dispatcher | P1b 在每物理 POST/重试持有中央 permit，角色由构造绑定，CallScope 是 ContextVar；P3 目前不导入这个中央 scope。critic 的 complete 已传 role=critic，但传入端口仍须独立可信构造 | 为 primary/critic 分别构造绑定端口；在实际执行线程内设置可信 run_id/lane/batch/auth/scenario scope，不能从 HTTP/模型参数授权。线程切换后不得假定 ContextVar 自动传播。run Journal 的 RequestLedger 不能充当第二套会员总账 |
| `config/models.yaml` ↔ P3 Runtime 装配 | P1b 默认主/critic 等锁 k3-256k、high、reasoning replay，删除 primary 隐式供应商 fallback；P3 是显式注入、没有自动 provider 工厂 | 普通 merge 保留新配置，不新增“缺 key 就换模型”。构造后证明实际模型/role/effort；配置有效不等于受信 K3 meter 或真实供应商 ready |
| `models/errors.py`/classification ↔ P3 U41、Loop 停止与 review fail-open | P1b 的额度/并发/Access terminated 会持久全停；P3 有危机模板、已流部分不可重播和评审只修订一次 | 用真实中央 PG + MockTransport 验全停跨入口、无下一 POST、取消/撤销不发布、critic 不可用仍保留草稿；未知异常只发脱敏 code |
| `tools/eval/engine.py`/judges/quota/runner_v2/subset 与 P3 runner/v4 target | 不同源目录都已有真实修改，合并后的 source digest 必然变；P1b 已接场景人工 scope，P3 增加独立真实 Runtime 的 scripted v4 | 新组合报告使用新 source identity；保留冻结 v2.1/k3 来源、80场景与历史报告。不能覆盖旧 manifest 续跑；P3 target 仍为离线候选，不能借 CLI 存在开启 live |

P1b 的 `quota_legacy`、probe、eval、retired-controller 入口和规范 ModelPort 都要保留同一个中央身份。不能只证明 Registry，再漏掉 ConfiguredModel 或旧入口。`httpx.MockTransport` 无显式 guard 时的离线豁免不能作为中央总账证明：组合测试须显式传真实隔离 PG guard，核≤2全局在途、角色份额、每物理重试一笔、SSE关闭/取消释放及错误持久停止。

特别是 `application/agent_snapshots.py:_decode` 要求 dataclass 字段集合**完全相等**，不会为旧记录自动补默认字段。P1b的字段增加会让合入前P3初始上下文/模型Journal快照被拒绝，这是已有失败关闭契约，不能删掉集合检查迁就。root须明确维护期间如何结束旧run或以受审的新epoch恢复，并保留已完成工具收据/全局预算，不自动重跑已发生的记忆/提醒副作用。新shape的同epoch重放、旧shape拒绝、撤销后拒绝和新epoch不重复写都需组合真PG证据。

`tools/eval/source_v21.py:assert_old_v3` 明确拒绝含 P2 的主树，并核 source/execution digest；P3 和 P1b 都基于 P2 后，**不能在 integration 上新冻或恢复旧 E1**。已有 pre-P2 脱离工作树继续独立保留；未来新 k3-256k 身份/受审桥与真人逐批开始另行处理，不改原拒绝条件。

## 3. 迁移与权限

| 轨道 | 已提交状态 | 集成门 |
| --- | --- | --- |
| 0001–0007 | P1b/P3 与 b9 七份原始字节逐一相同 | 不改 checksum；新隔离库初始化、schema7→8 前向、重复 verify 零变都另跑 |
| 0008 | 仅 P1b 有 `0008_model_usage.sql`，2729B，SHA256/LF SHA 同为 `5eef5d65363baa0ab4dc8ec9763b85136f4ba249688330b9cd8448f0b39ccbcb` | 中央 account/usage/batches/authorizations 四表及索引；`permissions.py` 新配额表权限收口必须跟入，不能只复制 SQL |
| 0009 | 六份已核来源均无；仅按 Z5 预留 P5b B 区/话题 | 仍未实现，不为了占号造空迁移；后续按合入顺序登记并测试checksum/权限 |
| B1 | 继续固定 b9，仅1–7，真实授权增量5–7 | 不把0008/0009或tzdata新锁放进B1包；不能借此次集成解除Linux/native恢复No-Go |

中央总账使用独立显式 DSN/schema/account/ledger_identity；集成库、评测库不可各自创建一套可独立放行的会员账本。组合测试用本机专用中央 fixture，验证错误地点/身份失败关闭、writer 无 DDL/不能改 schema_migrations、账户初始化与运行 DML 权限分离。此文没有创建任何库或表。

## 4. 模块线 P6 的确定 add/add 与其它接线

模块与 P3 在 `validation/__init__.py`、`validation/structural.py` 确有不同 blob 的 add/add；不是“模块只新增所以安全”。P3 `check_structure(text,alias_map,receipts)` 返回 used_fact_ids/used_claim_ids/cited_keys/warnings；模块 `structural_check(text,StructuralContext)` 返回 text/findings/ask_user_allowed，`StructuralResult` 同名但形状不同。P3 的 Finalizer、AgentReviewer、专业引用血缘不能被后者覆盖。

建议在集成分支保留 P3 的证据归约接口，并显式命名隔离/适配模块的结构检查；可移动实现并保留兼容导出，不能静默统一两种 StructuralResult。模块 ProgramIssue 还需按同一 Clock、当前草稿连续 quote 和真实 evidence_id 归并；legacy_lint 只告警，不能把纯 finding 直接升为可信修订授权。

主线已有独立干净草稿工作树 `zhiming-v4-p3-wire-p6`：commit `686521365b3b619db8bbf072799295f28d92d82c`，tree `1510c280228205e2f85962524987b3456adfbb29`。它用 `validation/p6_candidate/` 固定模块副本并接应用投影，**未在表中 P3 head 内**。后续应先核来源 manifest、解决和完整模块的重复模块身份，再按当前 Runtime 人生/无痕/撤销/一次修订行为重新接合；不要同时启用两个不同来源的结构实现。

已读模块已提交 `INDEX_20261021`、Q1时间、Q2记忆/旧P6指南、Q3 SSE、Q4调度、Q6 P9及 RC组合说明。明确的适配缺口：

- U4 返回额外 original_text/matched_text/span/recurrence，P3 `domain/time_ranges.py` 是 forbid-extra Pydantic 类型；须显式投影，不能 `**as_dict()`。天范围半开，精确 point 可 start=end；绑定原 said_at 和 owner 时区。无痕/敏感/假设授权仍由应用层负责。
- memory2、partition/organize 纯计划不等于已存；旧值CAS、原话撤销、assistant_claim不能变用户fact、PG幂等/undo/0009仍属主线后续。
- SSE `PgEventStore` 只接受事务端口，未实现真实连接；本表 schema 的 seq 非bigserial/无operation_id列，需要锁run→授权/lease→稳定操作账本→分seq→写入→NOTIFY同事务。P3已有事件不能并排再造第二套。
- P7 K1/K2 保留 original_due、领取前重核、sent/uncertain不重发；D4不启用使用提醒/紧急联系人。P9要求全部 reconciliation writer 保留 cardkit namespace，现 `adapters/delivery.py` 的整块覆盖不能继续使用。

这些是合并后逐片接线工作，不因一次 merge 完成而自动验收。

## 5. Charts、前端与文档：实际边界

P3/P8 的 merge-base 是 `7fa5e10`，按该真实共同祖先核，**没有双改路径**；P8旧树只有迁移1–4只是尚未合P1/P2，普通merge不会据此删除主线5–7。不要用 b9→P8 的双端 tree diff 把未继承文件误报为本线删除。

P3 `ChartsService.calculate/evaluate` 目前调用 v3 `ChartAdapter.calculate`，严格根为 profiles/artifacts/features/branches/errors；P8 calculate 可供此窄口适配，但新真太阳主盘来自单独的 `P8ChartAdapter.time_basis`，不能仅换 factory 就声称真太阳/诊断/行运已支持。P8 v1.1 有多 document 根、boundary_alerts、具名坐标/方法、真实 c/r Pointer；calculate 的旧平太阳/sect2不能冒充新主解读。P8四个只读工具是另外的 tool_evidence 信封，不能混读 preview 的 Ref。须专门 provider 适配、授权快照、取消/超时与事务前后复核、当前run/epoch内容血缘和别名重登记；固定阿远 validate_preview 不是任意用户通用校验器。原生 Swiss/pythonmonkey 不按共享线程并发安全假设调用。

P3/P10 的真实双改仅 `.gitignore`：P3/P1b 保留被全局 `models/` 规则误伤的 Core 源码和模型测试例外，前端新增 `/static/dist/`。两项都留；不能因为冲突选一边而令模型源码被忽略，或重新跟踪构建产物。GitHub本次#6标mergeable=false只是对当前base的状态，不是组合冲突清单或测试结果。

前端 `web/src/night/port.ts` 明确 `mode=local-demo`；recovery/port.ts 默认纯内存，仅显式loopback夹具才HTTP，不是真后端API。应逐个对齐 me/privacy/queue/settings/today/charts/recovery 端口与主线已冻结 API；事件Schema机械一致不等于已接真实PG/SSE。不要把前端演示数据改成用户数据或猜生产URL。

文档#7与P3同改的实质不同 blob 包括 `02_v4架构蓝图.md`、`16_算命Agent架构研究.md`、`prompts/P8_命理能力重建.md` 和主P3 ExecPlan；另06/07/P3/P5/P6/P7提示词在本次快照blob相同。最后合#7时必须保留后续“仅本人使用/时辰校正必做”等已同步决定和本夜真实Progress，不能用旧文档提交整文件回退。冲突按交付源与已提交设计同步证据核，不凭PR旧正文判断新旧。

## 6. root 的最小安全执行顺序（尚未执行）

先完成在途目标/02:00回归并提交需纳入的主线修改，记录实际源码tree与结果；不把本报告的 fc69 当未来头。保留各线原工作树，在新的独立目录操作。重新通过 GitHub/远端读取核 `v4/main` 与六个 head/tree；root 获准执行时再 fetch 明确 ref，这一步本片没有做。随后以已核远端 v4/main 创建或续用 `v4/integration`，不要从本地旧 v4/main、P3工作树或tree等价但历史不同的本机提交起步。

逐步普通 merge：**P1b → P3 → 模块 → P8 → P10 → 文档**。每步先解决上表冲突与语义接线，写独立回执、测试、提交推自身集成分支；本周绝不合并 v4/main/main、绝不 rebase/强推。若某步失败则保存明确失败与候选，不用下一条线的绿掩盖组合失败。已有 integration 时先核其前次回执，不 reset 或重建。

优先准备的组合窄门：P1b中央真实PG+MockTransport；P3 Runtime/Loop/Journal/Context/Reviewer 与新Port codec；真实HTTP取消≤2s和lease；core3/core4所有读端、来源撤销/无痕/Outbox；0007→0008/权限/重复verify；P6显式结构适配；Charts多根与真实method；API/前端端口与冻结Schema。宽回归仍只在北京时间每小时00–15分开始，总测试进程≤4。

完整回归使用合入后的CI和各线包脚本，不照搬旧成绩：

    python -m unittest discover -s tests -p 'test_core*.py' -v
    python -m pytest tests/v4 -q
    python tools/eval/runner.py --mode scripted --target fake --self-test
    python tools/eval/runner.py --mode scripted --target v4 --scenarios tools/eval/scenarios_v4 --output <新组合证据目录>
    python tools/eval/runner.py --mode scripted --target v4 --scenarios tools/eval/scenarios_v4_extensions --output <独立扩展证据目录>
    npm test
    node tests/dom.test.cjs
    node tests/report-settings.dom.test.cjs
    node tests/method-limits.dom.test.cjs
    node --check static/app.js
    npm run build
    npm --prefix web run typecheck
    npm --prefix web run lint
    npm --prefix web test
    npm --prefix web run build
    npm --prefix web run test:e2e

Core/Charts保持独立已锁解释器及明确CHART_PYTHON；Pytest默认单进程，Playwright workers≤2；启动前清凭据/关追踪，只用隔离PG与合成传输。Charts原生完整Golden/属性测试随P8目录合入后按其具体测试清单运行。不要安装新依赖；缺锁/缺运行环境记待决。上列仅为计划，**本片没有执行任何测试**。

原指定47脚本仍为46/47，X03四条旧发送断言待脑；独立扩展13/13不得拿来改分母。P3/K3 encoder、P1b组合、前端实API、Linux恢复和真实质量都有自己的门。本次没有重核精确头CI，PR的mergeable true/旧CI绿都不等于这次组合绿色；每个最终merge head还须独立CI与回执。

## 7. 当前需 root 先处理的清单

1. 固定02:00实际候选与工作树边界；根据GitHub远端tree重新核来源，不使用陈旧origin refs/本地旧v4/main。
2. P1b/P3保留v3_target两项改变，补真实CallScope/可信critic端口和新私有codec组合；保持单一中央账本、E1冻结源不变。
3. 决定P6两种structural接口的兼容命名及草稿p6_candidate来源归一，保护Finalizer真实引用血缘。
4. 按0008与权限一起做本机增量/幂等检查；0009保持预留；B1包继续b9。
5. P8只替换已实际支持的能力；前端只接已冻结真实API；文档合并不回退新设计/本夜进展；缺口留在后续阶段而不伪报已接线。

这是一份可继续工作的冲突清单，没有实际集成结果。没有联系其他聊天、触及其文件、执行服务器操作或扩大真实请求授权。
