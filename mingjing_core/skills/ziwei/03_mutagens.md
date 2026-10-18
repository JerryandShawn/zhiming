# 四化与飞星：起点、落点和时间层

版本：p8-skills-draft-2026-10-19-v2.2；状态：待所有者抽查的解释草稿，不是模型或现实预测验证。

## 方法步骤

1. 读取实际 star.mutagen 与所选运限层的 mutagen_links，按 star、mutagen、natal_palace、scope_palace、palace_index 展示，不靠星名猜落宫。
2. 生年、流年、大限、流月四化分层陈述；同一颗星在不同层的作用不混成一条。先标起化来源，再说落点主题，最后看与本宫/对宫结构的关系。
3. 宫干飞化、自化、化忌冲需要明确宫干与飞化规则产物；现有数据未核验这些新增字段时，只解释已经计算的四化，不让模型补算。

## 需要的盘面字段

根对象：CalculationArtifact。以下为 JSON Pointer；数组示例索引0仅演示路径，必须按实际对象检索。

- `/data/palaces`
- `/data/horoscope/yearly/mutagen`
- `/data/horoscope/yearly/mutagen_links`

新增具名图：`/data/p8_flying_transformations`。`edges`给出来源宫干、四化星、实际落宫、`self_transformation`和`ji_opposition`；`nodes`记录入出边，`natal`保留实际生年标签，`temporal_layers`分列真实运限。缺星/重星保留missing/ambiguous，不补造；化忌对宫仅几何关系。API/UI及Agent别名待主线接入。

在time_basis只读信封中，图位于`/charts/0/ziwei_column/p8_flying_transformations`（按实际索引）；证据路径已重定位到完整信封，不能按普通Artifact根解析。不能把这张图加进已冻结的倒推分数。

新增P8接口字段：`/data/p8_time_interactions` 含 `links`、`complete`、`yearly_ganzhi` 与 `target_date`；每条link保存status以及实际本命/流年宫位。缺失或歧义项不能自行补宫位。

## 各流派观点与分歧

默认`table_id=iztro`，壬干化科取左辅；24号据《全书》口诀“壬梁紫府武”裁定的可选`quanshu`取天府。该选项只改变宫干edges，不重写引擎实际生年标签或运限四化；`matches_named_table=false`保留差异。纯函数可选表尚未接公开工具参数。其他派别庚干异表另立口径，不改默认庚干太阴化科。飞星与三合重心有分歧，不把任一表当统一传统。

## 适用前提

明确人物、资料 revision、目标日期和运限层；若同一化星出现多处须检查数据结构，不把重复文本当两颗实体星。

## 反例与常见误读

化忌不是灾祸日期，化禄不是保证收入；忌落夫妻宫不能指控伴侣。生年化忌与流年化忌也不是同一个时间事件。

## 表达示例

示例是措辞模板：〔c1〕/〔c2〕须替换成本轮已注册的计算依据别名；未注册就不引用，不制造〔r#〕。

“这里记录的是流年四化落在本命某宫、对应当年某宫的结构〔c1〕。我会把它当作需要留意的议题，不把‘忌’翻成一定会出事。”


“若这条已算出的飞化落在你关心的宫位〔c1〕，咱们先把起点、落点和年份对上，再找一个可观察的小变化。一个‘忌’字还说不清你的现实处境。”

## 对应的规则命中 rule_id 列表

本章不新增八字条件规则；本批U12只有八字，不补算其他体系或民间口诀。

## 参考来源

- [《紫微斗数全书》](https://zh.wikisource.org/wiki/紫微斗數全書/卷二)，24号定位卷二安禄权科忌四星变化诀；本轮在线正文未定位到该段，原刊与全部表格待核，不能称本轮独立校勘。
- [iztro具名宫干表](https://raw.githubusercontent.com/SylarLong/iztro/v2.5.0/src/data/heavenlyStems.ts)、[宫位飞化接口](https://docs.iztro.com/posts/palace)：本实现只选该程序表与同宫定义，不称其为所有流派共识。

以上白话为项目原创概括；公开转录不等于原刊校勘。传统概念不证明现实预测有效。

存疑/待核：古籍原刊校勘、解释的现实预测效度未验证；字段与版本以本轮实际产物为准。
