# 跨线契约有限只读核查

读取时间：2026-10-21 00:50起，北京时间（UTC+08:00）；00:53完成主要字段核对。
范围为本机已有Git对象及root随后普通fetch更新的remote refs。只用 `git show/ls-tree/grep` 和JSON读取，
没有切分支、merge、读取其他工作树、启动Charts/测试/数据库或发送跨聊天消息。
本子任务未联网；root负责00:52的普通fetch。没有修改任何共享源码或U12/skill冻结资产。

## 固定快照与材料边界

| 角色 | 本次最终读取的固定提交 | 本机来源 |
| --- | --- | --- |
| 命理线 | 45006aae5b98adea781c704335eb4080ee775aba | 本工作树当时HEAD；新增U12契约另按当前未提交草稿读取 |
| 主线 | f49218bc5630501ec9339e2b63b7fc0c31eaf16c | root更新后的origin/v4/p3-agent-runtime |
| 模块线 | ebfa22f8f7c59e486c6632035ae6bc8307f0f438 | root更新后的origin/v4/mod-organize |
| 前端线 | 01e592537be4a9bc583939e5bf7517841a0755ed | origin/v4/p10-frontend |
| 基础v4/main | b9a89b6f84f7bebb640de080548010859aae630c | 本机origin/v4/main旧快照，只用于盘点 |

首次本机模块缓存为8c554bd、主线缓存为064954e，不能当作实时远端状态；
初读主线本地555d44b后来继续变化，因此最终结论固定在普通fetch取得的f49218b。
root查询未取得v4/integration；本机也没有这个命名的ref，不擅自把它等同v4/p3-agent-runtime。
本报告不是对这些提交之后、尚未发布改动或部署状态的判断。

## 已证实的接线差异

以下为真实接口形状不直接兼容或尚缺接线，**不是声称已在线上触发故障**。

### 1. 同名chart_compute的应用信封与P8预览根不同

主线f49218b的 `agent/tools/computation_parameters.py:14–17` 只接受模型能力意图
`system/target/scale`，出生资料由已授权应用状态读取；这个原则与命理线契约一致。
但 `application/agent_tools_charts.py:138–153` 返回的是 `ToolResult`：
`data.calculation/claims/persisted/adapter_mode=legacy_v3`，并在第18行明确列
`true_solar_time_basis/boundary_alerts/western_timing/transit_interval_search` 为unsupported。
命理线 `chart_compute.md` 的 `p8-chart-compute-preview-v1.1` 则使用
`scope/documents/view/aliases/boundary_alerts`，不同根不能直接赋给对方。

`agent_chart_lineage.py:48–60,129起` 继续核真实完成步骤、旧CalculationArtifact/claims、PG缓存及
`KnowledgeRegistry.load_builtin().revalidate_claims`，依据basis为legacy_validated_artifact/rule。
P8预览的demo-claim、原生time_basis及临界r不能绕过该流程假称已登记。
这需要主线新增受信provider/授权/版本/撤销复核与原生文档到运行账本映射；
仅将适配器换成P8、改adapter_mode文字或把两份JSON拼接，都不构成接线证据。

### 2. chart_skill已有可见性规则，但默认注册表尚无该工具

主线f49218b的 `agent/prompts/system.md:59` 指示需要细节时调用chart_skill；
`agent/tool_visibility.py:34,74,85` 也将其列为chart_computed时的条件能力。
实际 `agent/toolkit.py:42–87` 的默认DEFINITIONS由基础、interaction、tarot、computation列表组成，
三份definitions均无chart_skill；在取得的 `mingjing_core` 中搜索该名字也只有上述提示和可见性声明。
`select_visible` 只选已注册定义，故可见性开关不会自行创建工具。

命理线已交 `chart_skill(system,topic)` 与32章/5500字节本地预算，
但主线参数契约、执行handler、真实tokenizer及来源/上下文注册尚不能据这些材料视为完成。
这是本次直接读到的提示/可见性与默认工具注册之间的差距，不是推断P8 loader有计算错误。

### 3. 两个almanac属于不同接口，不能按函数同名互换

模块线ebfa22f的 `timekit/almanac.py:15–28,42` 是
`almanac(aware_datetime, tz) -> Almanac`，有 `solar/weekday/period/lunar/ganzhi/jieqi/yi/ji/`
`chong/sha/xiu/zhixing/zi_hour_note`，可按明确时刻和展示时区计算。
P8的 `charts.almanac.almanac(day_string)` 固定北京时间民用日正午，返回
`p8-almanac-v1` 信封，相关内容位于 `data.date/chong_sha/duty/mansion/pengzu/method`，
另有来源、文档ID与c/r。直接 `to_dict()` 不能得到P8信封，P8信封也不能直接当P2时间上下文。
这只是形状与采样语义差异；本次没有实算并发现两者同日数值冲突，也不建议改旧P2口径。

### 4. 前端流日公开投影有意不同于原生P8结果

前端01e5925的 `web/src/night/today/types.ts:2,12起` 是公开
`DailyTransitView`，使用 `date/documentId/snapshotAtBeijing/basis/highlights/evidence/provenance`。
`projection.ts:47–48` 明确只接离线公开格式，严格精确键校验会拒绝原生P8的
`version/scope/data/rule_hits/aliases/...`，不是一个raw-to-public转换函数。
`port.ts:26–27` 也明确未来要以已鉴权适配器替换本地日期port。
因此实际HTTP接入要提供公开投影并核脱敏/来源，不可将P8原对象直接塞给该port。

另一方面，前端依据键是 `(date,documentId,alias)`（projection.ts:30），
resolveEvidence按同键查找；这与P8“短别名仅同文档有效”的约束一致，本次没有发现跨日短号混用。

## 实际逐份核对：七日流日没有证实过期

前端projection固定sourceCommit为 `b51470b8e32eb72b8151df4eca7eee2e1584bee5`。
不能仅因其早于命理线HEAD就断言内容过期。本次从Git blob读取该提交七份完整raw样例，
逐份比较前端声明的sourceSha256/documentId与本工作树当前对应文件，结果如下：

| 日期 | sourceSha等于b514 blob | documentId等于当前 | sourceSha等于当前文件 | 前端引用均存在于当前文档 |
| --- | --- | --- | --- | --- |
| 2026-10-21 | 是 | 是 | 是 | 22项 |
| 2026-10-22 | 是 | 是 | 是 | 22项 |
| 2026-10-23 | 是 | 是 | 是 | 22项 |
| 2026-10-24 | 是 | 是 | 是 | 22项 |
| 2026-10-25 | 是 | 是 | 是 | 22项 |
| 2026-10-26 | 是 | 是 | 是 | 22项 |
| 2026-10-27 | 是 | 是 | 是 | 22项 |

七份前端documentId也都等于其b514来源，snapshotAtBeijing与两份raw均为日期当日
`T12:00:00+08:00`，contractStatus全部aligned。引用项包含evidence和highlight refs，
核date/documentId/alias实际存在，不把154次检查冒充154个独立测试用例。
这次只读比较没有运行TypeScript投影器、浏览器或验证文字摘要的完整语义。
本轮无需因commit号单独重算这七份流日；以后内容真的变化才须同步公开投影与provenance。

## 其余接口：已交命理契约与未取得对接材料

| 命理能力/版本 | 本线字段与引用关键点 | 取得的跨线材料 |
| --- | --- | --- |
| daily_transit / p8-daily-transit-v1 | natal四键scope+birth；正午快照；自包含工具c/r | 前端已有上述专用公开投影；模块线新晨报消费契约未取得 |
| window_search / p8-window-search-v1 | 全区间排序摘要、offset/limit≤31、当前页候选/命中/局部c/r；每页重编号 | 主线注册、模块/前端对接port未取得；不能据其最多366日查询就假定支持全部明细单页 |
| almanac / p8-almanac-v1 | 北京正午日历、data各字段、真实库规则及c/r | 已取得P2同名接口，差异见上；新信封消费者未取得 |
| synastry / p8-synastry-v1 | 双natal+kind+精确user_confirmed+as_of_date；双scope数组与两盘依据 | 三线新授权/消费port未取得；不推断已有他人同意持久化服务 |
| learning_outline / p8-learning-outline-v1 | points及原aliases投影，原documents没有复制；source_document_ids仍指原信封 | 主线/前端学习卡消费port未取得；单传learning结果不足以resolve原盘引用 |
| glossary / p8-glossary-v1与sources-v1 | 212术语+source_id/locator；不是当前盘面c/r | 主线/前端术语数据port未取得，不把静态定义注册成用户命中 |
| 20课 / p8-learning-curriculum-v1、p8-learning-lesson-v1 | 20课40题；6输入SHA、case+operation隔离、relative_path相对原c值 | 前端课程读取/进度port未取得；单独短号不能跨case共享 |
| 六类checker / p8-chart-consistency-preview-v1 | data.input_aliases为原盘；顶层c/r为文本比较，码点span | 主线review实际消费契约未取得；core4结果有review状态不证明接入checker |
| U12checker / p8-u12-rule-assertions-preview-v1 | 独立u12_rule枚举、原生38条件；顶层比较r与原盘r分离 | 主线/前端新入口消费契约未取得；不能把新枚举塞给严格旧六类v1读者 |

在主线f49218b的相关源码/契约树中，未取得上述daily/window/synastry/learning/两个checker的独立工具注册。
旧 `daily_transit_snapshot` 是legacy西占快照的字段/scale，不是本次三体系 `daily_transit` 接口。
前端01e5925的web/src中未取得window_search、synastry、p8-glossary、p8-learning、learning_outline标识的消费定义。
这仅描述当前取得的快照；不判断其他未提交工作、另名未读实现或后续提交。

模块线ebfa22f已取得 `BriefSubscription/next_brief`（scheduling/brief_schedule.py:13,33），
这是K1订阅时刻与触发计算，输出NextTriggerResult，不是流日+提醒的晨报内容编排契约。
其计划仍列白天追加晨报编排；本次未取得可对照P8 data/c/r的实际内容port，记录缺材料后停止扩查。

## 有限结论与后续边界

优先由主线确定受信P8 provider、账本映射和公开投影；保留其现有owner/epoch/版本/撤销复核，
再增加四工具和两checker的显式注册，不能用本报告绕过既有授权或直接merge。
前端七日来源与P8样例当前一致，这项可以作为继续接线的离线基础，不是HTTP已贯通。
其余缺port事项按缺口交接，不阻塞本线独立开发，也不推断对方已承诺的功能失败。

未验证：最新远端后续变化、其他工作树未提交内容、真实HTTP/PG/Registry/模型流程、运行时脱敏、
浏览器交互、部署状态与专业预测效度。测试数为0；154次JSON引用读核不是端到端测试。
本轮只新增本报告，没有修改计算、技能、schema或任何其他线文件。
