# 储备c：原话日期到记忆、提醒和归档的组合接线

`memory2.event_time_extended_v2.absolute_event_candidate_extended(fact,snapshot,tz='Asia/Shanghai',calendar=None)`是新增薄适配；不改旧event_time.py。它先调用Q2 authorize_fact核对owner/subject、原话角色/版本/撤销/无痕/拒存与锚点，再用primary原话及其source.at调用RA绝对化。抽取任务晚了40天也不能把“明天”解释成任务运行日的明天。

返回ExtendedEventCandidate，含original/projected/time/wording/needs_clarification/reason，以及original_source_text/normalized_source_text。所有正文repr隐藏，仍不能把对象或异常上下文整包写公共日志。

只有唯一非周期的明确时间才有projected。精确point的start=end合法；range需要正跨度。已有event_at或event_end任一冲突不覆盖。只在fact.text与单个原话quote完全一致时改写其text；模型摘要从不参与解析，也不被重写得像用户说过的原句。多分离anchor保持展示顺序，保守不拼成一条新断言。

原SourceAnchor、quote、source_ids、source revision和said_at保持；normalized_source_text只能用于展示或候选事实文本，不能拿改写后的hash替代用户原话的授权指纹。敏感内容/用户拒存仍必须由Q2 plan_write/apply在当前snapshot与Clock重查；有projection不等于已保存，更不授予通知权限。

英文条件/假设/示例采用保守澄清，避免把if/for example中的未来日期当已确定事件；这不是完整英文语义理解或对旧memory policy的替代。周期需要独立规则，不把每周一塞成单次。资料日期故意不注入profile port：当前MemoryFact没有承载生日资料依赖的ledger，生日继续问，主线先设计profile source/revision的完整依赖再接。

## 组合顺序与主线依赖

1. 取得当前原话及可信MemorySnapshot，以source.at解析；候选需要确认时停止投影，不能继续构造定时提醒。
2. 调用Q2 plan_write/apply，拿到主线真正提交成功的receipt之后才显示“已保存”；重放稳定operation_id不重复效果。
3. 用户原话确实明确要求提醒时，由主线再授权来源并构造FollowupCandidate/DeliveryRequest。到期依据original_due，按Q4 K2重新计划；到点/迟到/quiet/超过12小时不能借晨报改变规则。
4. 到明确event_end或valid_to后调用C2 plan_archives/apply；仅归档metadata，不删除原话。精确point按契约可在其时刻到期，不能据此声称业务面试已经结束。
5. undo仅恢复匹配字段。snapshot审计revision与operation记录增加是正常的，fact字段应逐项还原；原话后来撤销不能被undo复活。

事件归档不等于原话撤销。来源活性要从当前原话读取；已归档事实也不能当作新发送授权。新提醒必须先由主线核对原话scope/状态，并在claim/实际发送前重查；组合测试中的authorize_fact只是纯host示范，不代替PG当前事务。

## 验证边界

组合验收实际运行日期→写入/重放→K2到点/60/61分钟/12小时→到期归档→undo，包括1000随机参考日、时区和日界。真实保存、租约领取、来源撤销事务、重启worker、系统通知与飞书均未接线。完整数字、冻结46矩阵hash、源码hash和性能见RC回执及原始证据。
