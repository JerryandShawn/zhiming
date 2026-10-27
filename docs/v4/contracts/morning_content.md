# 晨报命理内容 v1

纯函数 `mingjing_core.skills.morning_content.morning_content(result, *, expected_scope, target_date)`。
输入为可信计算的 `p8-daily-transit-v1` 完整结果及调用方独立给定的scope、ISO目标日；调用前由主线核owner、可信来源、当前修订和撤销状态。
函数重建原内容指纹与全部c/r映射，拒绝错人、错修订、错操作、错日、改值、假命中或丢出处。指纹不是签名，不能识别主动重算指纹的伪造来源。

输出version=`p8-morning-content-v1`，status=`ready`或`insufficient_evidence`，scope/date/source_document_id/snapshot_at、points[]、所用aliases及rule_hits、effects和limits。
points每项含system、observation（计算观察）、reflection（可选自我整理建议）、text、c_aliases/r_aliases、school/source。
每体系至多一条，优先实际daily层，再按原规则顺序；未命中体系不补造。返回顺序为八字、紫微、西占，不把三体系合成吉凶或概率。输出不复制出生原文或全盘。

白话规则：八字十神先说明与日干比较，关系只说成员齐否、不推合化；紫微说清实际流层映射本命宫；西占给实际两天体、相位与容许度。建议只涉及整理日程、核现实条件和当事人意愿，不推断事件已发生，不承诺结果。
依据别名沿用原日结果，未重编号、未登记全局账本。正文适用于内部晨报组装，主线必须在当前上下文登记这些引用后才向用户呈现；不得跨日直接合并局部别名。

晨报可以在早晨准备，但结果标明当天北京时间12:00单点快照，不能写成早晨已经发生或全天区间。无模型、写入、发送或调度；免打扰、每日上限、投递和晨报其他段落由模块/主线负责。
`ValueError('morning_content_input_invalid')`为输入信封不符，`morning_content_context_invalid`为所选规则无支持解释；错误不带私有输入。

出处沿用daily_transit的实际school/source：子平五行阴阳比较、安装py-iztro默认运限、地心热带黄道主要相位与项目容许度。说明见daily_transit.md。原典页码校勘、跨流派一致性和现实预测效度仍待核，不把库一致称为独立实测。
