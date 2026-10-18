# 行星、星座与宫位

版本：p8-skills-draft-2026-10-18-v2；状态：待所有者抽查的解释草稿，不是模型或现实预测验证。

## 方法步骤

1. 先核对热带黄道、地心黄经、Placidus、Moshier以及显式民用时间减UTC偏移；不再对西占重复经度太阳时修正。高纬失败须报告，不能默换宫制。
2. 逐个读取相关行星的 longitude/sign/deg/house/retrograde；星座是表达方式、宫位是讨论领域的项目解释框架，不把它们当现实因果。
3. 先整合与提问有关的两三项，再用实际经历检验。古典七曜与现代外行星体系有时代差异；不把冥王星性质归给托勒密原书。

## 需要的盘面字段

根对象：CalculationArtifact。以下为 JSON Pointer；数组示例索引0仅演示路径，必须按实际对象检索。

- `/data/planets`
- `/data/houses`
- `/data/asc`
- `/data/mc`
- `/data/method`
- `/data/calculation_flags/natal`

## 各流派观点与分歧

整宫制、等宫制与Placidus可能给出不同落宫；本项目采用实际 profile。古典尊贵、接纳与现代心理读法不同，当前没有完整尊贵评分不能自行补。

## 适用前提

出生地纬度、经度、时区与时刻明确；宫位/上升对时刻敏感。行星逆行是视运动字段，不是道德、能力或灾祸的标签。

## 反例与常见误读

《四书》Book I 的 houses of planets 指守护星座，不能当作本项目12宫宫制的原文认证。太阳星座也不能概括所有人格与经历。

## 表达示例

“〔c1〕显示的是这颗行星的落座与落宫。我把它当作一个讨论方式；你实际在什么情况下这样反应，比星座标签更值得核对。”


## 对应的规则命中 rule_id 列表

本章不新增八字条件规则；本批U12只有八字，不补算其他体系或民间口诀。

## 参考来源

- [Ptolemy, Tetrabiblos (Robbins 译本)](https://penelope.uchicago.edu/Thayer/E/Roman/Texts/Ptolemy/Tetrabiblos/1B*.html)，Book I §§4、10–11、17：行星性质、季节与星座守护；不提供Placidus或外行星依据。

以上白话为项目原创概括；公开转录不等于原刊校勘。传统概念不证明现实预测有效。
