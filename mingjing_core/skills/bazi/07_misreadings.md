# 常见误读、边界与档案一致性

版本：p8-skills-draft-2026-10-18-v2；状态：待所有者抽查的解释草稿，不是模型或现实预测验证。

## 方法步骤

1. 回答前核对主体、资料 revision、branch_id、actual_method 与产物 warnings；把计算值、传统解释、用户自述、现实未知分开。来源缺失时删去具体断语。
2. 遇到与已有 U3 档案不同的判断，先核查输入或流派是否变化，再形成新版本建议，写明旧结论、改判理由及所依赖字段；未有保存回执不能说已更新档案。
3. 旧月运、应验率、关系图和征兆分析不转成事实。只回到可溯源的用户原话与事件；无法追溯的历史分析不用于证明新结论。

## 需要的盘面字段

根对象：CalculationArtifact。以下为 JSON Pointer；数组示例索引0仅演示路径，必须按实际对象检索。

- `/data/method`
- `/data/p8`
- `/warnings`
- `/revision`
- `/branch_id`

U3工程接口：`charts.profile_draft.profile_proposal(calculation, owner, subject, revision, previous_version=None, change_reason=None)` 已能从成功的具名P8八字产物生成只读提案。根对象为提案，不能把以下路径当作CalculationArtifact：`/schema`、`/version_id`、`/previous_version`、`/change_reason`、`/branches`、`/branches/0/judgments/0/path`、`/status`、`/writes`。分支内逐项保留格局候选、旺衰、喜用候选的实际值、artifact_id、JSON Pointer和actual_method。指定previous_version时必须给改判理由；status为calculation_proposal_not_persisted、writes=0。多分支与多口径并列，不宣称所有者已确认或数据库已保存。

## 各流派观点与分歧

神煞与格局的重要性各家不同；可报告辅助神煞，但不以单个符号压倒其余条件。项目明确拒绝恐吓、宿命、化解推销，古籍断语不自动继承为产品规则。

## 适用前提

危机、医疗急症和现实安全优先按实际情况处理，停止命理解读。未复核的原文与现有引擎差异写待决问题，不能擅改 v3 计算。

## 反例与常见误读

“三次说中所以科学有效”“公开题库高分证明能预测人生”“校正分最高就是实际出生时间”都不成立。采样点相同也不证明连续范围稳定。

## 表达示例

“这次结论与旧记录不同，原因是采用的资料版本和口径变了〔c1〕。我先把差异列出来，等确认后再按流程更新；现在还没有写回。”


## 对应的规则命中 rule_id 列表

本章不新增八字条件规则；本批U12只有八字，不补算其他体系或民间口诀。

## 参考来源

- [沈孝瞻著、徐乐吾评注《子平真诠评注》](https://www.anhappy.com/share/books/others/books/%E5%9B%BD%E5%AD%A6/%E5%AD%90%E5%B9%B3%E7%9C%9F%E8%AF%A0%E8%AF%84%E6%B3%A8.pdf)，第二十一章论星辰无关格局、第二十九章论时说拘泥格局、第三十章论时说以讹传讹。

以上白话为项目原创概括；公开转录不等于原刊校勘。传统概念不证明现实预测有效。
