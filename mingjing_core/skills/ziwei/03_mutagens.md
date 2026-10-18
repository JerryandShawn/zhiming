# 四化与飞星：起点、落点和时间层

版本：p8-skills-draft-2026-10-18-v2.1；状态：待所有者抽查的解释草稿，不是模型或现实预测验证。

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

各版本四化表存在差异，飞星与三合重心不同；《全书》生年口诀是出处，不等于所有版本相同。采用实际 profile 版本，缺完整飞化图就不称飞宫已完成。

## 适用前提

明确人物、资料 revision、目标日期和运限层；若同一化星出现多处须检查数据结构，不把重复文本当两颗实体星。

## 反例与常见误读

化忌不是灾祸日期，化禄不是保证收入；忌落夫妻宫不能指控伴侣。生年化忌与流年化忌也不是同一个时间事件。

## 表达示例

“这里记录的是流年四化落在本命某宫、对应当年某宫的结构〔c1〕。我会把它当作需要留意的议题，不把‘忌’翻成一定会出事。”


## 对应的规则命中 rule_id 列表

本章不新增八字条件规则；本批U12只有八字，不补算其他体系或民间口诀。

## 参考来源

- [《紫微斗数全书》](https://zh.wikisource.org/wiki/紫微斗數全書/卷二)，卷二安禄权科忌四星变化诀（论生年干）。
- [iztro具名宫干表](https://raw.githubusercontent.com/SylarLong/iztro/v2.5.0/src/data/heavenlyStems.ts)、[宫位飞化接口](https://docs.iztro.com/posts/palace)：本实现只选该程序表与同宫定义，不称其为所有流派共识。

以上白话为项目原创概括；公开转录不等于原刊校勘。传统概念不证明现实预测有效。
