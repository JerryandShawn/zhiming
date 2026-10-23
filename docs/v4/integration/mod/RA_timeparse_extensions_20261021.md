# 储备a：英文、混写与资料日期接线

只新增`timeparse/*_v2.py`；原Q1 `parse_time_range/absolutize`入口、P2数据、既有测试均保持。主线要使用扩展时显式导入`extended_v2.parse_time_range_extended`和`absolutize_extended`，不要悄悄替换旧入口。

## 统一入口

两个函数都接`text, ref_time, tz='Asia/Shanghai', calendar=None`，以及可选keyword `profile_scope=None, profiles=None`。返回原Q1的TimeRangeResult/AbsolutizedText；start/end UTC aware，展示按显式owner时区。ref_time必须是原话发生时刻，不能用抽取任务运行时刻来解释“明天”。

英文与原中文互相补充；同一date+clock的完整跨度优先于单独clock。多独立表达式、相同星期的语义歧义、未知数字日期区域习惯、DST gap/fold和未确认资料都要求澄清。不能将“下个周五”或04/05的某一个候选暗选成事实。

英文every/each与资料“每年生日”等明确周期保留recurring且待确认，不会当作单次。未支持英文机器循环或资料过法时recurrence为None，不能据候选直接排程。即便profile资料缺失，已经识别的周期意图也不丢成单次kind。

absolutize仅在唯一、非周期、无澄清且原文span一致时替换该片段，保留前后正文与original_text。日期与clock之间夹有事件正文时不把整段当纯时间删掉，保守保持原句待确认。`.as_dict()`和original_text含私人输入，不能整包进公共日志。

## 英文策略

`english_dates_v2.parse_english_date`无匹配返回None，匹配但非法/歧义返回澄清。包括相对日/周/周末/时长、ISO及英文月名、12/24时、显式时区、季度、中英混写和中国七节日常见英文标签。节假日日期全部委托原U4/P2，不复制数据或猜未公布调休。

裸weekday当天、next weekday、yearless跨年和斜杠日期采取候选口径；明确UTC/IANA等优先于默认tz解释该时刻。CST等不唯一缩写不直接选一个国家。词边界避免把tomorrowland、3pm-style识别成真实时间。

## 资料策略及授权

`profile_dates_v2.parse_profile_date`使用ProfileScope(owner_id,subject_id)和ProfileDatePort.lookup(scope,key)。没有资料表达式返回None；有表达式却缺scope/port返回澄清，不猜默认owner、不实际查库。

ProfileDateRecord提供生日/结婚/入职/自定义纪念日、solar/lunar、原资料source_id/revision/current_revision与active/current/confirmed/revoked/incognito。confirmed默认False，可信host必须显式确认；parser逐记录核对scope/key/状态/当前版本，不信port已替它过滤。未绑定他人生日不能因子串命中而使用self生日。

普通“生日那天”包含今天；“下个生日”严格将同日转到以后。非闰年2/29、当年不存在的农历闰月以及周年资料缺年等情形需要确认过法，不擅自选2/28或平月。农历转换只调用P2。

纯port是已授权资料的投影，不能由模型JSON自行授予confirmed/current。持久化用资料推导的事件或提醒时，主线还必须将实际使用的profile source/revision加入完整依赖清单，提交/发送前重新查当前版本；仅保存原提醒消息的source anchor不足以覆盖生日资料后来被更正/撤回的情况。本解析结果本身不是持久授权或来源账本。

## 主线待接

主线在当前owner事务取profile投影和原话时刻，再调用扩展；歧义走一次ask_user。事实记录保持原话anchor、绝对event_at/end与解析口径/时区，确认后才保存；不能用absolutize返回值声称已保存。记忆及Outbox依赖继续使用Q2/Q6的完整来源与版本闸门。

本轮全部为本地合成测试，未读真实个人资料、未改数据库、未访问服务器/模型。测试、冻结独立矩阵、性能和提交号见RA回执及日报。
