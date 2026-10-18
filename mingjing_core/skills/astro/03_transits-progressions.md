# 行运与次限推运：区间和技术分开

版本：p8-skills-draft-2026-10-18-v2；状态：待所有者抽查的解释草稿，不是模型或现实预测验证。

## 方法步骤

1. 先读 transits 的 sample_time、timezone_offset、orb_limit 与 precision_note。旧入口只是目标日UTC+8正午快照，不能把快照外推整月或精确日期。
2. 入相、精确、出相必须来自独立区间搜索产物，保留逆行多次经过、搜索边界与未闭合区间。没有该产物就明确只谈快照；不能模型自算插值。
3. 次限采用日返一年是另一个技术，需要出生时刻、目标岁数映射与独立推运产物。尚无核验字段时只解释技术区别，不给个人次限结论。

## 需要的盘面字段

根对象：CalculationArtifact。以下为 JSON Pointer；数组示例索引0仅演示路径，必须按实际对象检索。

- `/data/transits`
- `/data/transit_method`
- `/data/transits/aspects_to_natal`

可选能力：`P8ChartAdapter(..., transit_period={start_at, end_at, moving_bodies})` 已把连续搜索结果挂入同一CalculationArtifact；起止ISO时间必须含时区，moving_bodies例如太阳。默认不传时仍只有快照，以下字段为conditional_fields，不能强求默认产物拥有。

- `/data/p8_transit_windows`：feature_key为`astro.p8_transit_windows`，time_scale为`transit_interval`，对应profile保存方法与源哈希。
- `/data/p8_transit_windows/windows`：含entry_at/exact_at/exit_at、window_start/window_end、start_clipped/end_clipped与phases；保留多次经过。
- `/data/p8_transit_windows/requested_interval`、`/data/p8_transit_windows/limits`：分别是搜索范围与限制。

entry/exit为空表示被范围截断，exact_at可多次；2秒只是求根括区间，不是历表或民用时刻准确度。有限步长可能遗漏切触与极短窗口。已有CalculationFeature路径可供主线分配真实别名；本轮没有实际产物就不能编造〔c#〕。次限与太阳回归仍未实现。

## 各流派观点与分歧

行运是实际目标时刻天空，次限是符号时间映射，太阳弧又不同；不能把Book I入离相概念当作日返一年法的原始出处。日返一年法的历史出处参Alan Leo附录IV；平均日/真太阳日变体并不相同。当前尚无次限计算产物，不能据书中算法宣称已经算出。

## 适用前提

需要明确目标期间、时间标准与搜索精度。比较多技术时分别标方法，不因两技术提同一主题就宣布应验。

## 反例与常见误读

目标日orb小不证明该日精确；逆行可能三次经过。用未计算次限字段说“次限月亮已进某宫”属于编造。

## 表达示例

“若本轮〔c1〕已含区间结果，我会把每次进入、精确与离开分别列出，并标明被范围截断的部分；只有正午快照时，就只解释那个采样时刻。”


## 对应的规则命中 rule_id 列表

本章不新增八字条件规则；本批U12只有八字，不补算其他体系或民间口诀。

## 参考来源

- [Ptolemy, Tetrabiblos (Robbins 译本)](https://penelope.uchicago.edu/Thayer/E/Roman/Texts/Ptolemy/Tetrabiblos/1B*.html)，Book I §24：入离相概念，仅支持概念区分；不支持本项目次限算法。

- [Alan Leo, The Progressed Horoscope](https://www.astro.nu/wp-content/uploads/The-Progressed-Horoscope-Alan-Leo.pdf)，附录IV Summary of Measures of Time：One day measures a year；区分平均日/真太阳日变体，不继承宿命断语。

以上白话为项目原创概括；公开转录不等于原刊校勘。传统概念不证明现实预测有效。
