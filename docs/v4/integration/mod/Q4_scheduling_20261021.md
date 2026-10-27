# P7调度核心纯模块接线

本轮新增`scheduling/`，分开计算“下次规则时间”和“当前是否允许推送”。没有改旧followups规则、数据库定时任务、发送入口或既有设置。本地验收状态和源码提交见Q4回执/日报，不能据本文认为已经上线。

## 时间规则

`recurrence_contracts.RecurrenceRule`描述daily/weekly/monthly/yearly/workday/offday/lunar_monthly/lunar_yearly及local_time、time_zone、缺日与DST策略。`next_trigger(rule,after,calendar=None,inclusive=False)`返回UTC at/candidates/needs_clarification/reason/calendar_source；默认严格晚于after，同刻重算不会再次命中。

日期规则和时刻分别确认。U4机器串不包含确定的几点，桥接必须补用户已确认local_time，缺失时刻要澄清，不默认9点。工作日/休息日和调休只读P2CalendarPort；未公布年份不把普通星期几当成调休依据。普通每天/每周规则不依赖假期公布状态。

31号、非闰年2月29、农历缺少的30日采用skip。每月农历初一默认包括闰月；农历年度闰月循环由规则明确leap。DST不存在/重复时刻默认澄清，不能用主机时区或UTC往返静默挪钟。主线应把reason/candidates生成可见的确认问题，不能把at=None当成提醒已排程。

`brief_schedule.BriefSubscription`默认Asia/Shanghai 07:00，用户自选时刻直接传入。`next_brief`只给规则时间，关闭订阅返回未订阅，不生成任务。所有输入来源于已认证的用户设置投影，模型JSON不能自称已订阅。

## K1/K2投递计划

`delivery_contracts.DeliveryRequest(occurrence_id,candidate,original_due,brief_subscribed=False,not_before=None)`固定原始到期时间，candidate.due_at必须与original_due一致。not_before/plan.next_attempt_at仅用于下次尝试，不能覆盖original_due清除迟到年龄。每次循环的occurrence_id必须稳定；下一期循环使用另一个稳定ID。

`delivery_rules.plan_delivery`先复用旧decide_delivery的归属、来源、active、静音、接收度、每日上限与预览脱敏。只覆盖明确的K1/K2时间规则：

- 已订阅晨报按设定时刻发送，默认07:00，豁免quiet；关闭/来源撤回/静音仍阻止。不能把晨报伪装成explicit reminder绕其他规则。
- 明确提醒到点发送，即使quiet；迟到不超过60分钟可推送并带“晚了 X 分钟”。比较用精确秒，展示分钟向上取整。
- 超过60分钟且在quiet时顺延到quiet结束，默认08:00；超过12小时只给app_inbox计划，领取前仍复核来源/静音，不能绕授权展示私人内容。
- 普通followup保留旧日上限、接收度暂停、quiet与默认08:30恢复；明确提醒不计入followup每日2条额度，与旧规则一致。

自定义quiet_end的K2行为暂保守遵守用户设置，默认精确08:00。28号只明确默认08:00，未明确用户自定窗口的口径；已列日报待大脑确认，不能为了固定08:00违反更长的用户免打扰。这里没有联系离线用户，也不扩大外部操作授权。

## 领取与幂等

`recheck_delivery(old_plan,current_request,current_settings,current_state,scope,clock,sent_today)`核对occurrence/original_due及不可变业务payload，再用当前全部输入重算。权限flags、订阅、设置、静音和计数必须在领取时重新取值；旧allowed不是永久发送许可。

主线必须在同一owner事务/运行lease下校验来源epoch、原子领取occurrence、计数与Outbox意图。纯计划器不保存已发ID、不取得数据库租约、不原子扣额度。两个worker同时取得push计划不能分别直接发送，需主线唯一键/lease/CAS与旧unknown不重发规则。

用户D4已关闭使用时长提醒；本模块不创建这种触发源，不重开设置。主线不得按旧P7增补默认on把usage提醒重新入队，也不登记紧急联系人。

## 主线待接与验收边界

需要主线改已有schedule/followup repository与claim入口，把规则时间持久化成明确due_at及原始original_due，保存subscription revision，并在发送前走recheck与安全预览。本线不改这些旧文件。

FrozenClock合成验收覆盖调休、农历闰月、未知年份、UTC/DST、K1/K2端点与领取时的权限变化；不证明真实cron、PG并发、锁屏系统投递或飞书已可用。性能只报本机纯计算与Python分配峰值，无网络/模型/服务器调用。
