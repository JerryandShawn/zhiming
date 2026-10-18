# 调候与喜用：三条思路并列

版本：p8-skills-draft-2026-10-18-v2；状态：待所有者抽查的解释草稿，不是模型或现实预测验证。

## 方法步骤

1. 先按 climate 的 day_master、month_branch、source_locator、table_version 说明摘表范围，再读 candidate_stems。表仅是开篇季节候选，不能跳过全文例外。
2. 分别展示 balancing、climate、pattern 三组候选与产生条件；扶抑依赖各自强弱算法，格局依赖候选是否过筛，三者不互相充当证据。
3. consensus_stems 只是集合交集；disagreements 逐项保留。可建议形成带版本的 U3 档案草案，列计算 revision、method、依据别名与改判理由，保存与确认交主线回执。

## 需要的盘面字段

根对象：CalculationArtifact。以下为 JSON Pointer；数组示例索引0仅演示路径，必须按实际对象检索。

- `/data/p8/climate`
- `/data/p8/useful_candidates`
- `/data/p8/patterns`
- `/data/p8/strength`

U3工程接口：`charts.profile_draft.profile_proposal(calculation, owner, subject, revision, previous_version=None, change_reason=None)` 已能从成功的具名P8八字产物生成只读提案。根对象为提案，不能把以下路径当作CalculationArtifact：`/schema`、`/version_id`、`/previous_version`、`/change_reason`、`/branches`、`/branches/0/judgments/0/path`、`/status`、`/writes`。分支内逐项保留格局候选、旺衰、喜用候选的实际值、artifact_id、JSON Pointer和actual_method。指定previous_version时必须给改判理由；status为calculation_proposal_not_persisted、writes=0。多分支与多口径并列，不宣称所有者已确认或数据库已保存。

## 各流派观点与分歧

调候、扶抑、格局是不同问题；不按多数票裁定唯一喜用。当前调候摘表未经原刊校勘，不能写成经权威审核的定本；没有共同候选时允许不确定。

## 适用前提

必须看到相应计算块与来源定位。寒暖燥湿是传统比喻，不是当地天气、体质、疾病或营养指标；不能据此给医疗和投资保证。

## 反例与常见误读

“命里缺金=喜金”“喜火=做火行业一定好”“候选交集为空=命不好”均不成立；实际职业选择还需能力、资源、价值取向与约束。

## 表达示例

“按扶抑思路与调候摘表，这次候选并不完全相同〔c1〕。我会把分歧记清楚；职业上我们仍先看你能验证的能力和工作条件。”


## 对应的规则命中 rule_id 列表

`u12-climate-candidate-missing`、`u12-wealth-multiple-weak`

`met=true`只表示该条件成立；未命中项在rule_assessments，不能把单条件命中写成成格或事件确定。〔r#〕须由本轮上下文实际分配。

## 参考来源

- [沈孝瞻著、徐乐吾评注《子平真诠评注》](https://www.anhappy.com/share/books/others/books/%E5%9B%BD%E5%AD%A6/%E5%AD%90%E5%B9%B3%E7%9C%9F%E8%AF%A0%E8%AF%84%E6%B3%A8.pdf)，第十四章论用神配气候得失、第十五章论相神紧要；这里只支持方法区分。
- [万民英《三命通会》](https://zh.wikisource.org/wiki/三命通會/卷二)，卷二论天干阴阳生死；具体调候摘表出处以计算块 source_locator 为准，未核刊。

以上白话为项目原创概括；公开转录不等于原刊校勘。传统概念不证明现实预测有效。
