# window_search v1 接线契约（草稿）

这是命理线只读纯计算接口，供主线接入。日期与排序使用显式北京时间日历日，不读取宿主时区或当前时刻。它把已计算的盘面条件按公开的项目权重排序，不能据此保证某日签约、面试、搬家、出行、表白或开业的现实结果。

入口为 `window_search(natal, date_range, purpose, *, offset=0, limit=31)`。`natal` 沿用 P8 已确认时刻的请求对象，含 `owner_user_id`、`subject_id`、`revision`、`operation_id`、`birth`；不含 `as_of_date`。`date_range` 为 `{"start_date":"2026-10-21","end_date":"2026-10-27"}`，两端均包含，最多 366 天。`purpose` 精确取六项之一：`签约`、`面试`、`搬家`、`出行`、`表白`、`开业`。

默认路径只准备一次本命资料，其后逐日调用 `daily_transit_prepared`。每个候选日都是该日北京时间 12:00 的晨报用快照；没有扫描全天时辰、不会输出精确吉时。出生时刻默认真太阳时，本命与北京时间的差异由 daily_transit 保留。西占的相位容许度明确使用 daily_transit 默认 2 度；排序不会偷偷扩大容许度。

返回采用 `tool_evidence.evidence_result`：`version`、`scope`、`document_id`、`data`、`rule_hits`、`aliases`、`sources`、`effects`、`limits`。所有依据都在当前结果内解析，短别名仅本次结果有效。主线需要登记到会话的依据账本后才能跨工具共享，不可将不同日结果的 `c1` 混用。

`data` 包含 `purpose`、`range`、`method`、`candidates`、`observations`、`weights`、`pagination`、`ranking_summary`、`trace`。全区间全部日期先计算评分，再按总分降序、同分按日期升序；`candidates` 返回当前明确页。每行有 `date`、全区间 `rank`、`score`、`positive_hits`、`negative_hits`、`neutral_hits`。各命中项的 `rule_hit_index` 是本页根 `rule_hits` 的零基索引，也对应本页 `aliases.r[rule_hit_index]`；前端据此显示真实的 `〔r#〕` 和其 `evidence_aliases` 的 `〔c#〕`。实际无加分或减分条件时保留空数组，不制造命中。

`offset` 为非负整数，`limit` 为 1–31 的整数，均拒绝布尔值。`pagination` 明示 `total/offset/limit/returned/has_more/next_offset`。默认 7 日调用仍全部返回；较长区间逐页取明细，没有静默丢日。`ranking_summary` 始终列出全区间每一天的 `date/rank/score/positive_sum/negative_sum`，可核算总分。跨页短别名重新分配，只在本页有效；相同查询和相同页的内容、排序稳定。

请求超过末页时正常返回空 `candidates/observations/rule_hits` 和空别名表，同时保留全区间摘要、来源与 `trace` 的查询/摘要/权重哈希。空页不编造加减分命中；追溯信息明确标为查询事实而不是方向规则。

分数可重算：每条已识别盘面条件对应 `base_weight × layer_factor`，总分等于所有 `contribution` 之和。层因子为流年 1、流月 2、流日 3；跨多层的八字关系只取涉及目标层的最大因子，避免同一条关系重复计算。西占当日相位因子为 1。不完整的三合、三会或刑组权重为 0；没有把缺少成员的组合当作完整条件。负分只是提示值得核对的传统结构，不能说当天会发生事故、灾祸或关系失败。

权重属于 `project-six-purpose-ranking-v1`，明示为产品启发式，未验证预测效度。合相、天干相克和自刑等没有统一吉凶解释的条件默认不作方向分；六用途的十神、四化、相位基准权重在版本化 JSON 中完整公开。十神的表达不绑定性别，也不把六亲象征自动解释为现实中的某个人。关系仅说明实际成员成立，不声称自动合化。

每条根 `rule_hits` 带 `rule_id`、`met=true`、`school`、`source`、`context`、`contribution` 和 `evidence_paths`。`observations` 保存原 daily 结果的 `document_id`、规则与实际证据值、证据 SHA；排序命中的 `c` 指向这些内容的副本，保留同源血缘，又不依赖外部可变盘面。

错误码：`window_purpose_invalid`、`window_range_invalid`、`window_range_too_large`、`window_date_invalid`、`window_daily_scope_mismatch`、`window_daily_date_mismatch`、`window_daily_evidence_invalid`。归属、资料精度或引擎依赖错误沿用 daily_transit；不自动补出生地点或时刻，不把异常的日子默默丢掉后仍宣称完成全区间。

内部daily聚合也逐scope字段核类型和值，revision的true/1.0不能替代整数1。
已识别八字关系的complete须为真正布尔值，并与实际引用关系fact相同；缺少、0、字符串或互相矛盾均报
window_daily_evidence_invalid。原生关系fact未提供complete时沿用其既有True约定；明确False仍计0分。
这些拒绝不证明任意自报JSON的provider可信，主线仍须验证授权与实际计算来源。

请求缺少归属标识或修订版本另报 `window_natal_scope_invalid`。`observations.kind=derived_copy_of_actual_daily_evidence` 明示派生复制；其中原 daily 的路径只用于外部溯源，不能对当前 window 根解析。新窗口的 `rule_hits[].evidence_paths` 才是当前结果可解析的路径。

分页参数错误为 `window_offset_invalid`、`window_limit_invalid`，在本命预计算之前拒绝。资源决定：实际年度 366 日全明细紧凑约 33.7 MB，超过既有 worker 8 MB，所以采用最多 31 日一页；没有扩大共享输出上限。一次排序仍覆盖整个声明范围，当前页只携带自己的必要观测和局部依据。

出处：

- 项目《28_夜间作业提示词_2026-10-20.md》命理线第 3 项：六用途、每候选日正负规则命中、排序透明。
- `daily_transit` 及其具名八字关系、紫微四化与西占相位来源。排序引用实际盘面条件，不把计算条件的出处偷换为项目分值的古籍依据。
- 分值、层因子与并列排序：项目 `p8_windows_v1.json` 明示规则，属于产品启发式。

实际合成样例：[`samples/window-search-ayuan-contract-20261021-27.json`](samples/window-search-ayuan-contract-20261021-27.json)，完全合成的阿远、7 日签约排序，由实际三体系计算产生，267 条命中；Schema 为 [`window_search.schema.json`](window_search.schema.json)。定向脚本 40 项通过，其中 Charts 子进程含 5 项实际计算检查，检查结果与单独请求的 daily_transit 逐项相符。它验证数值、血缘、排序和接口，不验证预测。

前端可直接使用同一实际查询的[第二页](samples/window-search-ayuan-page2.json)（offset3/limit3，114命中）
和[末尾空页](samples/window-search-ayuan-empty.json)（offset7/limit3，0命中）；它们共享全区间排序与查询hash，
但短别名按各自页面重新分配。空页的0命中不等于所选区间无条件，只表示没有下一页。
重放命令为Charts解释器下：

    python -m mingjing_core.adapters.charts.benchmarks.window_search_samples --mode scripted --offset 3 --limit 3 --output <样例JSON路径>

独立实际32日闰年区间检查31/1/0页及完整排序拼接，详见`night28-api-independent-review.md`；
样例静态检查另保护Schema、页内Pointer/内容hash、r→c血缘及当前页分值，未将静态结构检查当再次排盘。

存疑/待核：本排序未纳入独立命理师盲评、实际事件结果或传统择日全套神煞、通书体系。没有证明正分日比负分日更适合现实事务。原典择日体系的版本、页码和流派冲突仍需逐项核查。31 日一页仍保留 worker 输出保护；阿远单例测量不等于证明所有本命数据的最坏体积。全区间重新计算的成本需要在前端明确表达，不承诺缓存或毫秒响应。
