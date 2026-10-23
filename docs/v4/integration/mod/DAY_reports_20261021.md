# 周报、月报与季报纯编排接线说明

本候选只生成报告内容投影。入口为 `mingjing_core.application.reports_v2`，不读数据库、不调用模型、不创建通知、不执行提醒、不改原报告时间。原晨报 `briefing_v2`、v3 worker 和 Core/Outbox 路径保持冻结。本说明的合成测试不是生产接线或报告预测质量验收。

## 公开入口

`period_for(kind, day, timezone="Asia/Shanghai") -> ReportPeriod` 接受 `weekly/monthly/quarterly`。调用现有 `domain/report_schedules.py` 的 `report_period` 和 `report_period_bounds`，返回当前周期 key、包含末日的起止日期，以及当地日界对应的 UTC 半开区间 `[start,end)`。周一为一周开始，使用 ISO 周年。主机时区不参与计算，DST 周可不是 168 个经过小时。

`compose_period_report(*, scope, kind, day, clock, timezone="Asia/Shanghai", records=(), transits=(), profile_revision=None, synthetic_symbolic=(), calendar=None) -> PeriodReport` 是纯函数。所有私有记录和当前来源状态均由可信 host 在权威事务中投影给它；不能把模型生成的结构当作这些输入。

返回值有 `period/generated_at/sections/citations/used_record_ids/used_claim_ids/omissions/warnings/coverage/request_key/effects`。没有 `delivery` 或发送许可字段；四项 effects 都固定为零。`request_key` 绑定 scope、周期、报告的分区/文本/原始时刻和完整来源引用，便于内容缓存去重，不能代替已有 Outbox 的业务 ID 或发送账本。

## 期间与原计划

当前 v3 的月初月报覆盖当月，季度首日季报覆盖当季；周报覆盖 anchor day 所在周。新模块保持该行为。例如 `day=2026-10-01, kind=monthly` 返回 10 月 1–31 日，不自动改成 9 月。若产品要回顾上一周期，须显式选择 anchor day 并由大脑/主线确定，不能根据“月初发送”推断修改。

原默认仍由 `ReportScheduleService` 和 `schedule_on_day` 管：周日 20:00、每月 1 日 09:00、季度首月 1 日 10:00，提前 15 分钟准备。本模块不处理订阅、停订、免打扰、全局静音、每日上限或实际发送；它也不凭报告内容获得这些权限。

## 记录和当前授权

`ReportRecord` 包含 `scope/id/category/text/said_at/basis/source_states/at/end/area_id/status/valid_from/valid_to/origin`。分类是 `fact/arrangement/followup`；按七个功能区分段，未知归属留在待整理。`said_at` 必填，`at/end` 保留事件原始时刻；没有事件时间时按原话时间归期并标“记录于”，不用编排时刻替换。输出 `ReportLine.event_at/said_at` 仍保留 UTC 时刻，显示按传入 timezone 转换。

输入应由权威记忆/事项实体投影，不能把助手建议或预测伪装成 `origin="user"`。`origin="assistant_claim"` 一律省略。事实、安排和跟进分别展示；安排明确标“结果未确认”，跟进只整理线索，不执行提醒。

每个 `BasisRef` 绑定原 alias、source ID、revision、owner/subject、内容 SHA256，以及可选 document/path/claim。`source_states` 是完整当前 `BriefSourceState` 集合，ID 缺失、多出、重复、scope 不符、revision/hash 变化、撤销、incognito 或 inactive 均不能输出正文。外 scope 记录整次受控拒绝，固定错误不带该条 ID 或正文；本 scope 记录带失效来源则省略，并在 omissions 给出本 scope ID 和原因。

这是一致性校验，不认证 PostgreSQL，也不证明输入 `text` 是真实原话。host 必须从权威来源验证原文/摘要与 basis 的对应关系，不能只填一个看似正确的 hash。来源的授权、归属、原话、当前 revision 与 hash 要在读取/渲染前重新核对；缓存内容不能绕过撤销。报告返回后的发送前仍须重新执行主线来源依赖和 Outbox freshness 门禁。

编排前还会跨所有记录、P8输入与显式合成素材核对同一source_id的当前状态。相同source_id若出现矛盾的scope/revision/hash/active/revoked/incognito，整批受控拒绝，不能先按旧active状态展示正文。各自单行校验通过不等于同批当前manifest一致。

当前实现只展示 active 且当前有效的记录。归档、退役、删除、过期、未来生效、未来原话、未来“已发生事实”都省略；未来安排可明确作为安排出现。跨期区间按非空交集归期，点事件遵守半开边界。未提供可用记录只表示资料不足，不声称本期没有事情。是否恢复展示“已归档历史事实”尚无独立授权契约，此候选不自动复活。

## 单日 P8 与跨周期缺口

`DailyTransitInput(day, payload, current_state)` 要求完整冻结 P8 `p8-daily-transit-v1` 文档。`profile_revision` 是 host 当前权威资料版本；缺失/不符或文档来源不可用就省略。复用晨报验证器核对 document hash、scope、日期、北京时间 12:00 与 UTC 同一瞬间、每个 JSON Pointer、c/r alias、value hash 和 claim ID，再格式化实际支持的结构。

每一天独立成象征章节，逐行带日期和“北京时间12:00快照”；不能写成当天已经发生的经历。`coverage.rendered_snapshot_days` 只列实际渲染成功的日期。只有 10 月 21 日资料时，月报不能外推全月；即使每天都有单日快照，也不把这些快照自动升级成流月/流季趋势。

报告本地 `ReportCitation(local_alias, source_alias, basis)` 为跨文档同名 c1/r1 重编号，同时保留原 document/path/claim/hash。相同文档 alias 发生换绑时整次拒绝。`used_claim_ids` 仅来自实际显示引用；查过但未显示的 claim 不算已使用。

现有实际跨周期流月/流季计算契约尚未冻结。`SyntheticSymbolicInput` 仅用于明确合成的接口演示，必须 `synthetic=True`，来源以 `synthetic-` 开头且不能带专业 claim ID；输出显式写“合成接口替身，不代表实际排盘”，另列 `coverage.synthetic_days`，不计真实 P8 覆盖。不要在正式报告中把该接口替身当专业依据。

## 编排此刻 P2 历法

可选 `CalendarSnapshot` 复用晨报 `calendar_snapshot` / `calendar_section`。必须属于同一 scope、同一 timezone 和编排时钟的当地日期；观察时间在现在之前 0–15 分钟内，否则省略并给 warning。此块标题明确是“编排此刻历法”，不是整周期历法。

该 15 分钟是保守附加限制。提前 15 分钟准备时生成的快照到实际发送可能已过期，须在发送前刷新 P2 快照再编排；不能声称旧 worker 的准备窗口可直接无缝接入。快照是纯 P2 计算投影，不需要私人来源授权；其 hash 也不是“已经完成质量验证”的证明。

## 主线接入位置

主线后续可在 `adapters/channels/reports.py::CoreReportAdapter.prepare` 准备报告输入时，先从同一 owner/subject 的权威记忆、事项和反馈构造当前来源投影，再调用本编排器作为内容候选或模型输入素材。原 `consult` 的完整 Core 验证、run 状态和依赖版本仍保留；不能把 `PeriodReport` 直接传给要求 Core 信封的 `prepare_delivery`。

`adapters/core_report_worker.py::CoreReportWorker.tick` 仍拥有原计划/静音、准备租约、业务 ID、已有发送未知状态保护和投递边界。`CoreReportAdapter.prepare_delivery` 仍需权威 manifest/run 与依赖门禁。此候选没有新增 `/api/reports`、线程归档、数据库表或迁移。真实报告线程/历史列表/API 的接线是后续主线工作。

P7 K2 的迟到提醒不能借本模块获得通知权限；跟进段只是纯内容，host 决定报告输入时仍须遵守明确提醒、超过 12 小时保留网页但不推送等政策。D4 使用提醒关闭，不生成使用时长、打卡、连签或催回对话文案。

回退只需主线不导入新编排器，现有 v3/晨报路径保留。不自动发送、不重置未知投递，不删除资料。

## 本地证据

最终独立130项与自有101项合计231项通过1.15秒，另有500随机周期与冻结16实值/14语义验收。
独立回执见同日evidence的DAY_reports_independent_calendar_mod.md；原真值未变。

自有目标测试 `tests/v4/reports_v2/test_reports_mod.py` 与 `test_batch_manifest_mod.py`：101 项通过，含 1000 随机周期属性、六时区、跨 ISO 年/闰月日、DST 周、半开边界、来源撤销/版本、foreign scope 零泄漏、分区、原始时间、P8 单日不外推、跨文档别名、全batch矛盾来源与 D4 零副作用。该测试不是独立盲评或实际内容质量评分。

性能工具 `tools/mod_week/benchmark_reports_v2.py` 对每样本 90 份报告计时，三类各 30。包括 fixture JSON 解析、每份 12 条合成记录及当前来源集合、P2 快照计算、完整 P8 文档/claim 验证、编排和输出断言；只有 fixture 字节读取、导入、source hashing 和证据文件写入不计时。一次预热、五次 CPU wall 样本、单独 tracemalloc，最终输出 `docs/v4/evidence/MOD_2026-10-21/DAY_reports_performance_final.json`，90份中位2.8509153秒、Python分配峰值2,284,859字节。旧 `DAY_reports_performance.json` 保留为全batch加固前证据，不能作为最终源hash。tracemalloc 是 Python 分配峰值，不是进程 RSS；没有数据库/模型/网络端到端耗时。
