# 行运与次限推运：区间和技术分开

版本：p8-skills-draft-2026-10-18-v2.1；状态：待所有者抽查的解释草稿，不是模型或现实预测验证。

## 方法步骤

1. 先读 transits 的 sample_time、timezone_offset、orb_limit 与 precision_note。旧入口只是目标日UTC+8正午快照，不能把快照外推整月或精确日期。
2. 入相、精确、出相必须来自独立区间搜索产物，保留逆行多次经过、搜索边界与未闭合区间。没有该产物就明确只谈快照；不能模型自算插值。
3. 次限只读具名产物：历表推进日数为 `(目标JD_UT1−出生JD_UT1)/365.2422`，保留小数，不按生日整岁取整。象征历表时刻不是目标日实际天空。

## 需要的盘面字段

根对象：CalculationArtifact。以下为 JSON Pointer；数组示例索引0仅演示路径，必须按实际对象检索。

- `/data/transits`
- `/data/transit_method`
- `/data/transits/aspects_to_natal`

可选能力：`P8ChartAdapter(..., transit_period={start_at, end_at, moving_bodies})` 已把连续搜索结果挂入同一CalculationArtifact；起止ISO时间必须含时区，moving_bodies例如太阳。默认不传时仍只有快照，以下字段为conditional_fields，不能强求默认产物拥有。

- `/data/p8_transit_windows`：feature_key为`astro.p8_transit_windows`，time_scale为`transit_interval`，对应profile保存方法与源哈希。
- `/data/p8_transit_windows/windows`：含entry_at/exact_at/exit_at、window_start/window_end、start_clipped/end_clipped与phases；保留多次经过。
- `/data/p8_transit_windows/requested_interval`、`/data/p8_transit_windows/limits`：分别是搜索范围与限制。

entry/exit为空表示截断，exact_at可多次；2秒只是求根括区间，不是历表或民用时刻准确度。有限步长可能遗漏切触或极短窗口。没有本轮实际产物不能编造〔c#〕。

另一根对象为 `P8ChartAdapter.western_timing` 只读信封，technique须为`secondary_progressions`，以下不能拿旧快照冒充：

- `/data/progressed_planets`、`/data/natal_planets`：实际本命及次限十天体。
- `/data/mapping`、`/data/symbolic_ephemeris_at_UTC`：具名UT1日返一年映射。
- `/data/actual_UTC`、`/data/metadata`、`/data/method`：实际出生/目标UTC、历表与方法。
- `/data/aspects_to_natal`、`/data/progressed_aspects`：容许度见`/data/aspect_orb_degrees`。
- `/data/houses`：当前明确为null，不提供未定义的推运宫位。

西占始终从实际UTC转UT1，不套真太阳时。主线Agent工具和界面待接入；独立计算信封只读，不写命理档案。

## 各流派观点与分歧

行运是实际天空，次限是符号映射，太阳弧又不同。Alan Leo附录IV区分日返一年变体；固定365.2422个UT1日为本项目具名细化，不声称所有软件同法。Book I入离相概念不是次限算法出处。

## 适用前提

需要明确目标期间、时间标准与搜索精度。比较多技术时分别标方法，不因两技术提同一主题就宣布应验。

## 反例与常见误读

目标日orb小不证明该日精确；逆行可能三次经过。次限houses为null，因此说“次限月亮已进某宫”仍属编造。

## 表达示例

“若本轮〔c1〕已含区间结果，我会把每次进入、精确与离开分别列出，并标明被范围截断的部分；只有正午快照时，就只解释那个采样时刻。”


## 对应的规则命中 rule_id 列表

本章不新增八字条件规则；本批U12只有八字，不补算其他体系或民间口诀。

## 参考来源

- [Ptolemy, Tetrabiblos (Robbins 译本)](https://penelope.uchicago.edu/Thayer/E/Roman/Texts/Ptolemy/Tetrabiblos/1B*.html)，Book I §24：入离相概念，仅支持概念区分；不支持本项目次限算法。

- [Alan Leo, The Progressed Horoscope](https://www.astro.nu/wp-content/uploads/The-Progressed-Horoscope-Alan-Leo.pdf)，附录IV Summary of Measures of Time：One day measures a year；区分平均日/真太阳日变体，不继承宿命断语。

- [Astrodienst图种说明](https://www.astro.com/faq/fq_fh_owtype_e.htm)：日返一年原则；[Swiss接口](https://www.astro.com/swisseph/swephprg.htm)§3、§9：黄经、flags与UTC/UT1转换。历表版本及Moshier潮汐/Delta-T约定见产物metadata。

以上白话为项目原创概括；公开转录不等于原刊校勘。传统概念不证明现实预测有效。
