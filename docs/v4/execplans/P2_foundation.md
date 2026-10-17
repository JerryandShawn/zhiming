# P2：建立时间引擎、可检索线程与 v3 连续上下文

本 ExecPlan 为活文档，遵循 `.agent/PLANS.md`。Progress、Surprises & Discoveries、Decision Log、Outcomes & Retrospective 随工作更新；时间使用 UTC+08:00。

## Purpose / Big Picture（目的与全局）

让原有 v3 获得程序计算的日期、农历、节气、假日和调休信息，并能接续自己此前的回答及其他渠道的同一人生话题。数据仍以 PostgreSQL 为唯一权威，所有已有授权、撤销、固定塔罗、预算和送达不明不重发契约保留。本阶段增加未来 Agent 所需表，但不实现 Agent 循环。所有验证使用合成数据、本机隔离数据库和模型替身；夜间不执行真实模型比较或 stage/生产操作。

## Context and Orientation（背景与定位）

目录 `C:\Users\Administrator\Documents\Codex\zhiming-v4-p2`，分支 `v4/p2-foundation`，起点 `7fa5e10a4dbe0e2878e28c6f6a115f17d013aaa2`，是 P0 合并后同步八份设计文件的 v4/main。设计来源为 `docs/v4/13_夜间并行指令.md` WS2、`docs/v4/prompts/P2_数据底座与时间引擎.md`、蓝图 §4、§5、§6.3、§15、§16 及场景集 T/M/R 类与历法附录。

复用 `mingjing_core/timekit/clock.py` 的 Clock、FrozenClock、get_clock；`application/memory.py:56 receive`、`:177 save_fact`、`:298 retire_fact`、`:370 snapshot`；`repositories/postgres.py:53 transaction`、`:71 initialize`、`:91 verify_schema`、`:165 list`、`:282 invalidate_derived`、`:528 commit_run`；`adapters/web.py:31 history_instant`；`domain/report_schedules.py:96 report_period`；`adapters/channels/reports.py:38 prepare`；`tools/deploy_core.py:786` 运行角色授权。行号为起点快照，后续修改以函数名定位。

人生线程即同 owner+subject 的跨渠道历史，ID 为 `life:<subject>`；旧 conversation_id 继续保存作来源话题。搜索 tokens 是本地分词后的空格连接词，PostgreSQL simple 全文索引据此查询。助手历史只是助手输出，不能变成用户事实。consultation.py 限于 today、payload、SYSTEM_POLICY、_phase_commit；from_base 与模型构造属于 WS1，不修改。

## Progress（进度）

- [x] (2026-10-17) 完整读取原始夜间指令、P2 提示词、蓝图相关章节及 T/M/R 与历法附录；只读研究现有实现。
- [x] (2026-10-17) 取得独立 worktree 与同步后基线，确认干净分支。
- [x] (2026-10-17 23:04) 里程碑一：独立 Core 环境与 P2 数据库；时间引擎、覆盖导入工具和历法金标 22/22，通过格式与静态检查。
- [x] 里程碑二：0005–0007、迁移链验证、检索/倒序查询、批量撤销及授权验证。
- [x] 里程碑三：人生线程、助手消息、撤销传播与 300 轮幂等回填。
- [x] 里程碑四：v3 此刻块/双向历史、记忆策略误伤、危机配置与报告期间。
- [ ] 里程碑五：一万条消息 p95 测量、旧 Core/前端、新测试与 scripted 全量验证；提交及草稿 PR 回执。
- [ ] 夜间后续：真实模型 T/R/M/S 对比与 stage 执行，按夜间指令留待用户/大脑决定。

## Surprises & Discoveries（意外发现）

现有依赖锁仅固定版本，无哈希；P2 提示词“与现有哈希方式一致”的前提不符。新依赖不能只加两条 pip hash，否则 pip 会要求所有依赖都有 hash。保持既有版本，优先完整生成 Core 哈希锁；若索引不支持则记录精确受限项，不声称已哈希锁定。

已完成 Core/Test 两份完整哈希锁，原有版本逐项一致，仅新增 lunar-python 1.4.8 与 jieba 0.42.1；隔离环境 `uv pip install --require-hashes` 检查 64 包通过。PG15 实际旧约束名为 core_runs_check，旧 0001–0004 合成 schema 已成功迁到 7，数据库细节回归正在补齐。

当前 report_period 返回周期标识而非起止日期；新增期间边界计算，保留现有标识接口。历史回填的 created_at 是回填时间，因此线程最近历史必须按原始 at_ms 排序，不能用写入时间代替发言时间。

现有 sources 对每条消息再次读取完整撤销账本；将同次读取按消息 ID 分组后投影，保留多事项原话只展示所选事实片段的隐私契约。现有 receive 禁止同身份替换正文，助手修订使用独立方法，不放宽此规则。

## Decision Log（决策记录）

决定：完整旧553首轮949.569s报告7 failures/6 errors，绝不记为通过。两项背景receipt由句界误读引起，已保留旧断言修实现；history四项只在fixture更新run.updated_at、未更新新增权威助手message.at，现仅同步合成助手at/at_ms，所有原排序/分页/渠道断言保留。memory_proposals一项仅用户计数改精确核对用户+成功助手，重放事实/模型调用计数不变。旧无效迁移时间保留原始at文本，at_ms使用同PG事务now()，与原created_at回退完全一致。history+proposals原13项15.143s通过。日期/作者：2026-10-18 / Codex。

决定：同运行epoch的程序时刻以现有runtime_step/program_time持久化Clock.now ISO，只存时间；intake/synthesis/review/repair的now与intake.today复用该时刻，并尊重FrozenClock及owner timezone。stale新epoch不复制program_time，重新取时；不改repair_identity/hash/预算/合法重试guard。理由：真实旧repair恢复5个error由每次重建now的微秒变化造成合法同轮identity漂移。原repair模块11项9.453s通过，新PG两项4.15s证明未变化输入下完整repair payload/identity相同、累计4calls，以及新run/新epoch新时刻。事实有效期仍读当前Clock，未冻结整个snapshot；真实依赖改变仍应触发原严格校验。日期/作者：2026-10-18 / Codex，独立审计真实函数复现并确认。

决定：假设判断保留同一硬句内逗号前置条件/后置问号，不因逗号把“如果…，我…”变成既成事实；硬句界支持句号/问号等以及尾随空白/闭引号。与蓝图“分句”含逗号的字面解释有保守偏离，理由是避免放宽隐私写入；真实语料是否进一步细分留大脑/P5，不夜间擅自弱化。日期/作者：2026-10-18 / Codex。

决定：非上海时区的年/月干支使用与节气相同的物理交节时刻，日/时干支依owner当地日时；否则纽约已显示立春却仍是旧年/月。新增上海/纽约立春前后4项金标，timekit26项0.60s通过。日期/作者：2026-10-18 / Codex。


决定：完整旧 Core 发现背景声明 quote 以句号结束时，新的片段函数误吃下一句疑问，导致 pending_confirmation 变 rejected。保留旧断言并修正硬句界，末尾空白和闭引号不改变完整句语义；逗号不切掉同一句条件或问号。授权先对完整原文中的引用内容等长掩码，再按原文范围切片，防止引号内跨句片段丢失开引号变成保存病历授权。新增10项句界/引用回归；最新策略56项通过。日期/作者：2026-10-18 / Codex，独立审计确认新边界必须继续保护隐私。


决定：fact-only、部分原话、完整来源删除及恢复账本都按实体/运行迭代闭包传播；助手脱敏后其 ID 与 originating run 均进入污染集合，包含无 lineage 的旧 legacy_derived 兼容分支。note/profile_doc 等显式删除也作为 typed seed，清空派生实体、运行结果、步骤、事件和 outbox 正文。理由：独立审计复现原仅一层传播会残留后续笔记。correction 仍保留 request 并标 stale 供合法重算，不误作彻底来源删除。日期/作者：2026-10-17 / Codex，无新增产品功能。

决定：回填优先使用 request.source_message_id/message_id，并核验 owner/subject/user 角色及原话相同；operation 精确匹配为次级，未提供明确 ID 时只接受唯一正文匹配，否则跳过。理由：Feishu 的 om-id 与 feishu:message:om-id 不同，set 顺序不能决定来源渠道；损坏或歧义历史不得猜测。日期/作者：2026-10-17 / Codex。

决定：历史 API 去掉 created_at 前一万条截断，SQL 按 at_ms/id 流式候选，最终以原始 at 完整微秒、turn_id、role 生成兼容窗口与 cursor，保留旧运行补答及 meta。理由：回填写入时间不能挤掉真正近期用户，同毫秒不同微秒不能漏页。为兼容未回填/无效时间旧行，当前扫描所有已筛选候选；只保留最多500条消息窗口，但运行元数据仍 fetchall，故不声称整个接口常量内存或大规模查询性能已验收。日期/作者：2026-10-17 / Codex。

决定：既有测试仅三处按明确 P2 契约更新：schema 校验 4→7 且仍验证篡改拒绝；渠道测试保留两条用户原文，新增精确一条成功助手及重放无额外模型调用；P0 brief 测试精确区分入站原文与成功助手。理由：阶段明确增加三迁移与助手历史，不能用旧计数阻止新行为，也不能削弱授权、来源、只读校验和幂等保护。日期/作者：2026-10-17 / Codex。

决定：不把 P1 合入本线。P1 的 requirements-test.lock 新增 coverage==7.11.0 与本线完整哈希锁存在预期合并冲突，待 P1 验收合并后 rebase 时保留 coverage 并重生成完整哈希，无既有版本漂移。日期/作者：2026-10-17 / Codex。


决定：本线使用独立数据库 core_test_p2 与唯一测试 schema，环境变量明确覆盖为回环连接，模型凭据在测试子进程清空；不修改共享 venv。理由：四线并行隔离，避免共享 schema/checkpoint 或依赖变化。日期/作者：2026-10-17 / Codex，无需大脑确认。

决定：已知迁移链保持连续版本与逐文件校验和验证，拒绝未知更新版本、缺口与漂移；仅 migration 初始化角色补执行缺少的已知后缀，运行角色不执行 DDL。理由：只前进不等于接受不认识的 schema。旧代码面对新版本必须明确拒绝。日期/作者：2026-10-17 / Codex，实现解释在回执中保留供大脑复核。

决定：owner timezone 缺省为 Asia/Shanghai，以代码默认值兼容已有 owner，不主动更改用户设置；未知年度仅计算节日本日，不推测调休。日期/作者：2026-10-17 / Codex，采用设计默认。

决定：助手消息与业务成功提交同一事务，稳定 ID 去重，保留来源/事实/声明依赖；助手上下文写入不授予保存用户事实的权限。日期/作者：2026-10-17 / Codex，无需大脑确认。

决定：P0 brief 测试原“只有一条系统入站 source”改为精确核对一条原入站及一条成功后的真实助手输出；模型执行前不得凭空出现助手来源。理由：P2 明确新增成功助手历史，原防虚构来源保护必须继续成立。当前烟测 38 通过、该项预期语义差异 1 项；修改和新增回归后重跑。日期/作者：2026-10-17 / Codex，属于阶段明确行为变更。

## Outcomes & Retrospective（结果与复盘）

时间、迁移、检索、线程、助手持久化、撤销闭包、幂等回填和 v3 接线已实现。此前全套 v4 335 项通过，新增审计定向与报告期间测试通过；最终全套及旧 Core 553 正在独立数据库并行运行。一万条消息 snapshot 100 次实测 p95=4.155ms，小于150ms。P2 尚未整体验收通过。夜间禁止的真实模型比较、stage/生产、真实飞书不会执行；最终结果、计数、证据及待决问题在本节与阶段回执同步更新。

## Plan of Work（工作计划）

首先在 timekit 下实现类型化历法、节假日来源、节气时刻、晚子时说明及逐字段此刻块。节假日覆盖导入只发生在显式管理命令；对话不联网。使用固定 lunar-python 1.4.8，jieba 与命理词典仅本地分词。

接着建立三个只前进迁移。0005 查询旧预算约束的实际名称，仅移除数据库 calls 上限而保留 v3 应用预算；建未来运行表及列。0006 建线程时间索引；0007 建全文生成列、GIN、向量表及删除触发器。仓库新辅助逻辑拆成小文件，旧大文件只作必要接线。运行角色授权在迁移后重做并验证新表可访问、迁移账本只读。

然后让新消息记录 life 线程、UTC at/at_ms 与原话题；最近历史按原始时刻倒序取 30 条再转正序。助手消息稳定写入并参与撤销。回填工具支持只计数及样例 ID 的 dry-run、显式 apply、撤销过滤和幂等重放；不打印正文。搜索以参数化 tsquery 和 owner/subject 范围限制实现。

最后将此刻与角色/时间/渠道历史接入 intake/synthesis/review/repair，4000 字/条、默认上下文 400000 字节，保留裁剪优先级。提取记忆误伤策略，正反例各至少 15 条，同时保护敏感授权。报告传入实际日期和期间，增加危机配置与版本记录。全部业务直接 Python 取时改接 Clock，SystemClock 自身除外。旧 API 历史返回结构保持兼容。

## Concrete Steps（具体步骤）

所有命令在本 worktree 运行。Python 指向本线独立 `.venv-core\Scripts\python.exe`，CHART_PYTHON 只读复用主仓 Charts 环境，Node 使用主仓本地 Node 22，PG bin 加入本进程 PATH。测试子进程显式清空 KIMI_API_KEY/MOONSHOT_API_KEY。

    python -m pytest tests/v4 -q
    python -m unittest discover -s tests -p 'test_core*.py'
    npm test
    node tests/dom.test.cjs
    node tests/report-settings.dom.test.cjs
    node tests/method-limits.dom.test.cjs
    node --check static/app.js
    npm run build
    python tools/eval/runner.py --mode scripted --target fake --self-test

数据库迁移和回填使用显式 core_test_p2 回环 DSN；不得改为默认环境中的未知库。格式/静态检查只针对新增修改代码，旧仓 Ruff 存量单独列明。

## Validation and Acceptance（验证与验收）

历法附录每行均作参数化金标；覆盖 T01–T14 所需字段、23 时晚子时与时区跨日、2027-01-01/02-06 未公布标记、覆盖文件优先级和无网络对话。空库及已有 0001–0004 合成库迁移后功能相同，重复初始化不重跑，篡改/未知/缺口迁移拒绝；授权测试以非超级运行角色验证。

300 轮合成历史 dry-run 不改行，apply 两次计数/正文/来源相同；已撤销或已删除运行不能复活。跨渠道 R03、新话题 R06、助手方案 R02 以真实服务与模型替身核验 payload 与稳定提交，助手事实写入仍拒绝。M03/M09/M10 正例和拒绝、引用、假设、第三人、敏感反例同时验证；S01 验证配置进入真实模型边界，不把替身回答称为真实模型通过。

一万条消息预热后重复测 snapshot，记录样本数量、p50/p95、机器/数据库版本及最新消息 ID；目标 p95 小于 150ms。旧 Core、旧前端、全部 v4 与 scripted 必须通过或明确记录有依据的历史契约更新。真实模型至少 9 个 T 场景及 R02/R03/R06、M03/M09/M10 的成绩夜间不测，待 WS1 契约 v2 基线完成后由大脑安排。

## Idempotence and Recovery（幂等与恢复）

迁移全部事务化、校验和稳定；不修改 0001–0004。回填以稳定 message ID 与 operation_id 去重，拒绝替换原始用户正文，尊重撤销墓碑。只有本线合成数据库可重建；不删除共享库或用户数据。stage 只写备份→迁移→dry-run→apply→冒烟及维护恢复文档，只前进迁移后不能直接启动旧代码，需要新版本修复或经授权备份恢复并重放最新撤销。

## Artifacts and Notes（产物与备注）

公开证据位于 `docs/v4/evidence/P2/`；阶段回执为 `docs/v4/evidence/P2/receipt.md`；stage 计划为 `docs/v4/release/P2_stage_plan.md`。原始日志与临时 SQL/环境只放忽略的 private/，不含真实用户数据。最终草稿 PR 由 root 发布，目标 v4/main，夜间不合并。

## Interfaces and Dependencies（接口与依赖）

新增 day_status(date)、next_holiday(date)、almanac(datetime,tz)、render_now_block(owner_settings,clock,last_interaction_at,upcoming_events)；MemoryService.record_assistant_message；repository list 的 order/before/limit 与全文 search(owner,subject,query_tokens,kinds,limit,since,until)。新实体种类 thread/thread_summary/note/profile_doc/knowledge_gap/followup/reminder/proposal；不启用新 Agent 表的运行使用。无新增外部服务或对话时联网。

## 修订记录

2026-10-17：建立 P2 执行计划，记录夜间边界、独立环境、复用位置、现状差异、实现顺序和可观察验收。

2026-10-17 23:04：完成时间引擎首里程碑与哈希锁，记录真实旧迁移约束及助手历史测试变更理由；数据库/线程接线仍在后续里程碑。

2026-10-17：完成后续实现与独立审计三项修复；记录 API 精度/扫描边界、损坏来源跳过、typed 撤销闭包、合法旧测试契约更新及 P1 哈希锁后续合并要求。旧 Core 553 与最终 v4 分库并行运行，当前不提前声称通过。

2026-10-18：旧553进行中发现2项同源句界错误，保留旧断言修实现；新增完整句/逗号/引用授权边界回归。最终v4首轮350通过138.59s，扩展句界后354通过149.95s；最后引用边界增量仍需再跑全量，当前不混称这些轮次。

2026-10-18：修复首轮全部已定位回归；中止被首轮后续修复取代的第二轮553，保留日志、不计成功。新增program_time、原始无效时间与时区交节回归；固定最终代码后重新完整553与v4。
