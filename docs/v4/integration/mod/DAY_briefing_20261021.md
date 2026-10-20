# 晨报编排器接线指南（2026-10-21，北京时间）

## 交付范围

新增入口为 `mingjing_core.application.briefing_v2`。它把 P2 历法、已绑定的 P8 当日流日快照、当前有效的安排与到期跟进编排为不可变晨报投影，返回投递**计划**，不会创建通知、写数据库、修改调度或请求模型。本交付尚未接入原 worker、PG 或飞书。

scope 最后收紧前主线目标测试为 170/170 通过（含独立验收）；收紧后自有目标 48/48 通过，最终整组复验由主线记录。这些结果证明本地合成输入下的规则与边界，不能据此声称生产接入、真实命理质量、飞书送达或定时作业已验收。

## 最终公开 API

```python
from mingjing_core.application.briefing_v2 import (
    BasisRef, BriefSourceState, BriefItem, CalendarSnapshot,
    BriefLine, BriefSection, BriefOmission, BriefEffects, BriefingResult,
    BriefingError, calendar_snapshot, subscription_basis, compose_briefing,
)

calendar_snapshot(
    *, scope: FollowupScope, clock: Clock,
    timezone: str = "Asia/Shanghai", calendar: CalendarPort | None = None,
) -> CalendarSnapshot

subscription_basis(subscription: BriefSubscription) -> BasisRef

compose_briefing(
    *, scope: FollowupScope, subscription: BriefSubscription,
    settings: FollowupSettings, receptivity: ReceptivityState,
    calendar: CalendarSnapshot, clock: Clock,
    transit: Mapping[str, Any] | None = None,
    profile_revision: int | None = None,
    items: Sequence[BriefItem] = (), sent_today: int = 0,
    subscription_state: BriefSourceState | None = None,
    transit_state: BriefSourceState | None = None,
) -> BriefingResult
```

`BriefSubscription` 来自 `scheduling.brief_schedule`；`FollowupScope`、设置和接收度来自 `application.followups_contracts`；`DeliveryRequest` 来自 `scheduling.delivery_contracts`。所有时刻必须 aware，业务日期和时区显式传入，不读取主机默认时区。

| 类型 | 主要字段与含义 |
| --- | --- |
| `BasisRef` | `alias, source_id, revision, owner_id, subject_id, value_sha256`；可选 `document_id, path, claim_id`。别名为本次上下文引用，不是全局授权。 |
| `BriefSourceState` | `source_id, scope, revision, value_sha256, active=True, revoked=False, incognito=False`；必须来自可信 host 当前快照。 |
| `BriefItem` | `request: DeliveryRequest, basis, area_id=None, source_states=()`；不允许省略来源当前状态后仍显示正文。 |
| `CalendarSnapshot` | `scope, day, timezone, observed_at, almanac, day_status, revision=1`；P2 数据深冻结，历法与日期一致。 |
| `BriefingResult` | `sections, basis, delivery, omissions, warnings, request_key, preview, effects`，并携带 scope、日期、时区、生成时刻。 |

每个 `BriefSection` 包含 `id/title/lines`；每个 `BriefLine` 有正文和绑定依据。`BriefOmission` 只返回条目标识及原因。锁屏预览固定为“明镜的晨报到了”。`BriefEffects` 四项始终为 0：`model_calls/writes/notifications/scheduler_mutations`。

## host 当前状态与授权边界

接线方必须在权威作用域内读取当前订阅、设置、接收度、资料版本及完整来源 manifest。纯函数只检查输入之间的一致性，无法判断调用者伪造的“当前状态”是否来自 PG；解析成功、schema 通过、hash 一致和布尔开关都不能替代授权。

1. 用 `subscription_basis(subscription)` 得到订阅内容摘要；从当前存储构造 `source_id="brief-subscription"` 的 `BriefSourceState`。订阅版本、归属、摘要必须匹配，且 active、未撤销、非 incognito。缺失或失效会阻止晨报投递，返回空正文。
2. 每项私有安排的 `source_states` 必须与其依据所引用的 source_id 集合完全一致；多项、缺项、重复、跨 owner/subject、版本或摘要变化都会拒绝或省略整项。被省略的正文和依据不进入输出。candidate 本身跨 owner/subject 时整次固定错误拒绝，连外 scope 业务 ID 也不能进入 omissions；本 scope candidate 的失效依据可按规则省略。
3. `profile_revision` 必须是 host 此刻权威资料版本。`transit_state.source_id` 必须等于完整 P8 `document_id`，摘要等于该 `tool-` 文档 ID 后的 SHA256，版本等于当前资料版本，并满足相同来源状态守卫。
4. 真正 claim/发送前仍要在原有主线事务里重查来源、订阅、依赖、run、daily count、静音与撤销状态，绑定稳定业务标识并原子 claim。先前编排结果不能证明发送时仍有效。

同一个本地别名若被重新绑定至不同依据，整次编排受控拒绝；相同依据可去重。调用方应捕获 `BriefingError`，记录 `reason_code`，避免把私有正文写入错误日志。

## P2 与 15 分钟快照限制

`calendar_snapshot` 只读调用已有 P2 `almanac` 和 `day_status`，可注入只读 `CalendarPort`；未复制节假日表。历法日期、星期、农历字段、休息日状态与节气 aware 时间均校验；未公布年度调休只显示“安排尚未公布”的限制，不臆定真实调休。

编排要求 `0 <= now - observed_at <= 15 分钟`，并且快照与用户当前业务日期、订阅时区、设置时区完全一致。未来快照和过期快照均拒绝。这是新增的保守限制，不是原 v3 准备流程已经兼容的结论。

原计划 06:45 准备、07:00 投递：精确 15 分钟边界可通过，但任何实际发送延迟都可能过期。接线时应在 07:00 实际投递前重新生成 P2 快照并重新编排，同时重查当前来源；不能把 06:45 的结果原样当作发送授权。

## P8 文档与 claim 绑定

当前支持 `p8-daily-transit-v1`。校验 scope、资料 revision、目标日期以及北京时间 **12:00 瞬间**与 UTC 表示一致；它不是全天区间，也不是用户任意时区的正午。正文明确标注“按当日北京时间12:00快照”。

验证器按 `version/scope/data/rule_hits/sources` 重算文档 ID，再逐项重算 JSON Pointer 对应值摘要、`c`/`r` 原始别名、`claim_id` 与 rule evidence 关联；输出依据保留完整文档 ID、path、claim、scope、revision 与摘要，不能仅靠短 `c1/r1` 拼接其他文档。

只渲染支持的具名结构描述，每体系最多两条；不完整关系明确说成员未齐，不断言完整成立或合化，不把结构命中写成现实预测。错误文档降级为不显示整个流日段；不支持的个别上下文有受控 warning，不生成推测。

这些校验只证明内容引用的一致性，不认证引擎来源、天文算法、流派质量或真实用户授权。主线仍需把输出别名登记进本轮有效上下文；`transit_aliases_local_registration_required` 明确提示这一点。没有完成登记时不能把临时别名当持久证据。

## 分区与 K1/K2

晨报包含今日历法、按区排列的当前安排/跟进、可用流日结构和中性收尾。区域使用已有七区 ID：`daily/career/relationships/family/wellbeing/finance/metaphysics`；`area_id=None` 单独显示“待整理”，不默认归入日常。

K1 保留用户订阅时刻，默认 07:00。已订阅晨报可以豁免普通 22:00–08:00 免打扰；全局停用、静音、来源失效仍优先。每日主动上限只约束 followup，不因晨报或明确提醒消耗该额度。DST 时刻缺口/折叠由已有 `next_brief` 返回待澄清，不按主机时区猜选。

条目逐项复用既有 K2 `plan_delivery`：明确提醒到点可遵守其显式例外；迟到不超过 60 分钟可带迟到说明，超过 60 分钟遇免打扰顺延；超过 12 小时仅 App 收件箱，**不借晨报正文再次推送**。deferred/blocked/app_inbox 条目不显示正文。未来且尚未到期的当前周安排可展示为安排，不执行提醒；当前周以外不显示。到期 followup 在本次展示预算中逐项计数，仍受 daily cap 和免打扰约束。

`delivery.disposition="push"` 是当前输入下的建议，不能直接调用 transport。`request_key` 是稳定编排请求键，不替代原 outbox 操作账本、发送意图和 CAS。

## 原 v3 worker 的实际接入位置（本次未改）

| 既有文件/入口 | 主线接线工作 |
| --- | --- |
| `adapters/core_report_worker.py:CoreReportWorker.tick` | 在 daily 分支准备/实际投递前加入可信输入投影与编排开关，保留原 report scope、schedule revision、protected period、租约及已发送/unknown 保护。weekly/monthly/quarterly 不由本模块替换。 |
| `adapters/channels/reports.py:CoreReportAdapter.prepare` | 目前仍会调用 `ConsultationService.consult` 生成报告；纯编排接入必须由主线明确选择另一条合法准备路径，不能因引入本模块就声称旧调用已消失。 |
| `adapters/channels/reports.py:CoreReportAdapter.prepare_delivery` | 原函数要求权威 run/manifest 和完整已验证载荷；`BriefingResult` 不能冒充原信封，不能直接作为 outbox payload。需主线定义可信报告投影与已验证运行的关系。 |
| `domain/report_schedules.py:schedule_on_day` | 原准备时间是用户投递时刻前 15 分钟。保留用户计划，发送前刷新历法和授权；不要把准备完成等同投递完成。 |
| `adapters/channels/cards.py:brief_card` | `BriefSection` 为两套不同类型；需显式映射编排的区标题/行到卡片 `cards_contracts.BriefSection`，保留区与依据详情，避免重复旧 plans 内容。外部卡字段仍待对照飞书官方文档核实。 |
| `adapters/channels/delivery.py` 及原 outbox | 保留完整 freshness、稳定 business/target、来源/依赖版本重查、持久化意图先于 transport、unknown 不重发；本模块没有放宽任何门禁。 |

落库 manifest、上下文别名登记、revision/CAS、真实发送与 ack 均是主线尚需完成的接线工作，本模块没有创建任何数据库迁移或通知记录。

## 降级与回退

缺失/失效 P8 仅省略流日段并返回 warning；失效私有条目整项省略；订阅失效或全局禁止则不交付正文；历法不一致、过期或别名冲突则受控拒绝。禁止用缓存私密正文补齐被撤销资料。

接线建议以默认关闭的 host 开关引入。回退时关闭该编排路径，继续使用原已验证报告机制与原 outbox 安全规则；不要清除发送账本、重置 unknown 状态或为绕过旧状态创建新 business。真实模型及发送仍须另有授权，模块回退本身不会发起这些动作。

## 性能证据边界

已有固定证据：`docs/v4/evidence/MOD_2026-10-21/DAY_briefing_performance.json`；工具：`tools/mod_week/benchmark_briefing_v2.py`。该报告冻结的是最后 scope 收紧前源码，不能当作收紧后源码的测量；主线另存 final 报告，不覆盖旧证据。

一次 workload 连续编排 100 次，使用完整已发布的合成 P8 fixture、可信状态替身、三个分区条目（其中一个超过 12 小时的提醒必须省略），并核验六条流日输出、分区、迟到屏蔽与零副作用。一次预热、五次墙钟观测，中位 **1.8116074 秒/100 次**；独立 tracemalloc 峰 **1,650,760 字节**。源码与 fixture SHA256 在报告中冻结。

fixture 文件读取、参数构造及 P2 历法快照生成发生在计时外；100 次计时包括每次编排的完整内容摘要/引用校验、状态匹配、K1/K2 选择及输出断言。重复输入可能受缓存影响。tracemalloc 是 Python 分配峰值，不是进程 RSS。以上不含 PG、并发 claim、实时排盘、真实通知、网络或模型，也不证明端到端时延与真实内容质量。

scope补丁后的最终证据是`DAY_briefing_performance_final.json`：100次中位1.729275秒、峰1648242B，源码前后hash一致；最终套件172项通过。旧报告保留历史身份。01:45窗口全部离线完成模块9102项连续三遍通过，详见DAY_pipeline_stability_receipt.md。
