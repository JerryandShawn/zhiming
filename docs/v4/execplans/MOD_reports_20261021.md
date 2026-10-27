# 33#5：周期报告纯编排（周报、月报、季报）

## Purpose / Big Picture

在只新增文件的模块线中实现三个周期报告的纯内容编排。输入当前仍授权的合成事实/安排/跟进和明确日期的象征素材，输出带真实期间、分区、来源引用及限制的报告；不会读取数据库、生成模型请求、创建通知或修改报告计划。已有晨报 `briefing_v2` 与 P9 官方协议源冻结，均只读复用。

## Context and Orientation

工作树是 `C:/Users/Administrator/Documents/Codex/zhiming-v4-mod`，分支由 root 统一管理。设计依据为大脑目录 `33_全量开发队列_本周.md` 第四节第5项、蓝图 §7.4、`05_Codex提示词/P7_主动性引擎.md` §D、P7增补防依赖以及用户 D4 关闭使用提醒的决定。周期报告是按一周、一个月或一个季度展示来源内容，不能把命理结构写成已经发生的用户经历。

只读复用入口及其当前位置：

- `C:/Users/Administrator/Documents/Codex/zhiming-v4-mod/mingjing_core/domain/report_schedules.py:97` 的 `report_period` 与 `:107` 的 `report_period_bounds`，获得原 v3 当前周期标签及包含末日的公历范围。
- `C:/Users/Administrator/Documents/Codex/zhiming-v4-mod/mingjing_core/application/briefing_v2/authorization.py:30` 的 `state_reason`，核对完整当前来源投影与 scope/revision/hash/撤销状态。
- `C:/Users/Administrator/Documents/Codex/zhiming-v4-mod/mingjing_core/application/briefing_v2/evidence.py:40` 的 `validate_transit`，验证 P8 文档、scope、日期、profile revision、JSON Pointer 与 claim 绑定。
- `C:/Users/Administrator/Documents/Codex/zhiming-v4-mod/mingjing_core/application/briefing_v2/transit.py:42` 的 `transit_section`，仅输出有具名口径的单日北京时间12:00结构说明。
- `timekit.clock.Clock` 获取现在；`organize.spaces.DEFAULT_SPACES` 提供七个区；不改以上文件。

原报告默认周日20:00、每月1日09:00、季度首月1日10:00，准备窗口15分钟。原函数给的是 anchor day 所在当前周期，月初报告并非自动回看上个月。本模块保持该事实，不另定“上一周期”或新发布日期；如果以后需要回顾上一周期，由主线显式选择 anchor day 或由大脑决定，不偷偷调整现有日程。

## Progress

- [x] (2026-10-21 07:40 +08:00) 完整阅读33#5、蓝图报告条款、P7 §D、原v3范围/计划函数和 `.agent/PLANS.md`；root确认仅纯内容编排，不另造订阅或推送授权。
- [x] (2026-10-21 07:53 +08:00) M1：严格期间/记录/单日素材/引用契约；六时区、日期边界及1000随机周期属性通过。
- [x] (2026-10-21 08:09 +08:00) M2：当前来源、撤销/过期、事实与象征分区、跨文档别名重编号与全batch同源状态一致性，公开组合函数可测；自有101项通过。
- [x] M3：实际路径性能、接线说明及零副作用自测完成；独立130项、合计231项通过1.15秒，root独立源码复核完成。
- [ ] 新增目录的错峰全量回归与最新远端CI仍待后续证据；提交推送号在日报独立记录。

## Surprises & Discoveries

旧 `report_period_bounds` 取当前周期，不是“刚结束的周期”。首次实现必须保留这个行为；不要根据月初发送时间自行推断回顾范围。现有 P8 契约只提供单日北京时间12:00快照，没有已冻结的完整流月/流季输出；一天资料不能代表整周、整月、整季。现有晨报本地 c/r 别名会在不同文档中重用，所以周期报告需要新的报告本地别名，同时保留完整原引用。

首轮64项中有23项在内容request key阶段失败，原因是新投影把Python tuple交给旧严格JSON canonical。改为JSON list后64项通过，没有放松通用指纹函数或测试期待。随后增加半开期间、跨文档别名、发送时刻历法、原始秒级时间和非法kind测试，自有82项通过。内容指纹同时保留原始event_at/said_at，避免只按分钟显示文本去重丢失原时刻差异。

独立验收在冻结契约时提出同batch的两个记录可传入同source_id却矛盾的当前状态。原逐行校验不能保证全batch一致，可能旧active条目仍可见；root授权在本轮新增源加固。新增manifest统一检查records/transits/synthetic，不改变旧briefing；六类状态变化跨三类输入的18反例和一致正例均通过，原82项也保持通过。

## Decision Log

root于本轮明确：只做纯内容，不新增订阅/推送授权。实际发送仍走原报告 worker 的当前设置、来源、run、Outbox 事务与外调门禁；返回报告不等于发送授权。

期间范围调用现有 v3 函数；内部 owner 当地日界转换为 UTC 半开区间，显示包含末日的原范围。周一开始，ISO周标签与跨年遵循原函数。主机Tokyo时区不参与计算。

每条记录只依据真实传入的原始 at/said_at 选择期间，保留原时刻，不用编排时刻覆盖。外 scope 记录整次受控拒绝且不携带该条ID/正文；失效、撤销、incognito、缺失当前manifest、非用户事实、过期/未生效记录省略。过期后作为“历史事实”的展示政策尚无单独契约，当前不自动复活归档/退役事实，限制写进报告与接线说明。

真实记录按事实/安排/跟进分开并按七区归组；无归属单独待整理。象征解释独立章节，只能显示已验证单日素材覆盖的日期，注明单日12:00瞬间与口径，不生成现实结果或期间趋势。缺少跨周期接口时允许显式 `synthetic=True` 注入素材，必须标“合成接口替身”，不能当成真实P8命中。

新引用 `ReportCitation(local_alias, source_alias, basis)` 同时保留本地唯一别名和原文档 alias/doc/path/claim/hash；`used_claim_ids` 只来自实际显示的验证引用。缺失、冲突和来源不可用都不能补造证据。原作者/助手建议不能通过记录字段变成用户事实。D4保持关闭，不生成使用提醒，也不加入打卡/依赖文案。

## Plan of Work

M1新增 `application/reports_v2/contracts.py`、`periods.py` 与严格校验辅助。通过公开 `period_for(kind, day, timezone)` 返回原v3标签、当地起止日与UTC边界。构造类型检查真bool/int、aware时间、深冻结集合以及跨scope拒绝。

M2新增 `records.py`、`symbolic.py`、`citations.py`、`compose.py` 和包出口。当前来源通过现有只读验证器核对，实际输出每行绑定来源；P8仍逐日验证并明确覆盖缺口。没有完整资料时输出限制，不把缺失解释为好坏趋势。全部函数纯计算，可重复调用得到相同内容与稳定 request key。

M3新增自有测试、性能工具与接线指南。独立测试由root协调已有代理，不读取整理盲评B或改任何冻结评测。性能使用全合成输入、FrozenClock、一次预热、五次计时、单独tracemalloc，明确准备是否计时；不声称PG、网络或模型速度。

## Concrete Steps

所有命令在本工作树执行，使用已配置Core解释器与root Ruff解释器，TEMP/TMP固定 `private/mod-week/tmp`，三类模型Key置空、tracing关闭。

    python -m pytest tests/v4/reports_v2/test_reports_mod.py -q -p no:cacheprovider
    python -m ruff check mingjing_core/application/reports_v2 --select E,F,I,B,UP,SIM --line-length 120
    python -m ruff format --check mingjing_core/application/reports_v2 --line-length 120

单个代理最多一个目标pytest，总并行≤4。全量由root在北京时间每小时45–59分启动，本模块没有运行live或旧runner的权限。

## Validation and Acceptance

日期测试覆盖2026-10-17当前周/月/季、跨ISO年周、2月闰年、季度末、至少六时区及DST日界，输出开始/结束日与原v3一致。原P7场景P07/T13保护的发送时刻和历法不被改动，本模块只新增内容层。

scope/currentsource测试覆盖外owner/subject零ID/正文泄漏、当前manifest缺/多/重复/哈希或revision变化、撤回/incognito、过期与未来生效；对应M/R/F/KU来源与删除不变量。重复记录幂等与同ID变更拒绝。AS02助手话语不会变用户事实。

象征测试验证同日P8所有doc/path/claim/hash绑定、不同日期重复c1/r1重编号、profile revision当前性、同一天不能外推整周期、未完整关系不能成立；对应CR01/CR06。合成注入必须标记，不算真实P8。PR03禁止依赖文案，D4保持不产生使用提醒。

报告无任何数据库、模型、通知或调度副作用；契约/局部合成测试不等于主线业务接线或真实预测质量验收。

## Idempotence and Recovery

输入不可变，编排无写操作，重复调用得到相同期间和来源绑定。request key绑定scope、kind、period及输入内容版本，不能当Outbox唯一发送账本。回退只需主线不导入新编排器，原v3和晨报路径完整保留；不删除任何数据，不重置未知投递。

## Artifacts and Notes

计划：本文件。产品：`mingjing_core/application/reports_v2/`。自有测试：`tests/v4/reports_v2/`。目标接线文档：`docs/v4/integration/mod/DAY_reports_20261021.md`。性能和证据另存新增文件，结果产生前不预写数字。

## Interfaces and Dependencies

`period_for(kind, day, timezone="Asia/Shanghai") -> ReportPeriod`。

`compose_period_report(*, scope, kind, day, clock, timezone="Asia/Shanghai", records=(), transits=(), profile_revision=None, synthetic_symbolic=(), calendar=None) -> PeriodReport`。

`ReportRecord` 包含scope/id/category/text/at/said_at/end/area_id/basis/source_states/status/valid_from/valid_to/origin。`DailyTransitInput` 是完整P8 payload及host当前来源状态。`SyntheticSymbolicInput` 为显式合成的接口替身，不持久化也不伪造专业claim。

复用已锁定库；不加依赖、路由、迁移、订阅实体或真实传输。完整公开类型落盘后向root和独立验收代理广播。

## Outcomes & Retrospective

已新增8个纯产品文件、101项自有测试、完整路径性能工具与接线说明。101项通过0.73秒，Ruff及格式检查通过，函数参数/返回类型齐全，单文件与函数尺寸受限。最终性能证据 `docs/v4/evidence/MOD_2026-10-21/DAY_reports_performance_final.json` 在全batch加固后重测；每样本90份（周/月/季各30），五样本中位2.8509153秒，单独Python分配峰值2,284,859字节。原07:52:55的 `DAY_reports_performance.json` 保留为加固前记录，不以其旧源hash冒充最终版。计时包括每份12条合成记录/当前manifest构造、P2计算、P8完整文档claim校验、编排及断言；fixture字节读取、导入、source hashing与报告文件写入不计时。数据全合成，无DB/模型/通知副作用。

当前是可测本地候选，独立130项与自有101项合计231项通过1.15秒，原冻结16实值/14语义真值未变。真实报告worker/线程归档、`/api/reports`适配、P8流月/流季权威契约、真实模型内容质量和发送均未接入。原周期时间未变；主线需在实际发送前刷新15分钟内P2快照并重新做来源/run/Outbox事务门禁。回退是不启用新增入口。

## 修订记录

- 2026-10-21 07:40 +08:00：创建计划；保留v3当前周期事实，明确只内容与跨周期资料缺口。
- 2026-10-21 07:53 +08:00：记录M1/M2、82项自测与真实性能证据；修正JSON投影发现，保留独立验收和主线接线未完成状态。
- 2026-10-21 08:09 +08:00：记录全batch同源当前状态加固，101项自测与新final性能；旧性能留存，待独立复验后交root发布。
