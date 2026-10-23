# 调度历法边界接线补充

本补充不改变[Q4原接线指南](Q4_scheduling_20261021.md)或产品入口；只记录28个新公开边界和一次模块兼容观察。
原1240项与新28项合计1268通过2.79秒；本轮没有产品、旧测试、黄金或P2假期数据修改。

- workday/offday依赖当前P2来源。未知来源、非真布尔、kind与休息标志矛盾，均不能生成可发送时间。
  资源OSError或缺方法返回固定不可用原因；普通daily不应因此读取不需要的假期端口。
- 农历端口只接受精确date；datetime/None不是可用日期。缺某个日期可跳过候选，端口不可用与年份越界要明确澄清。
  测试注入的合成换算并不替代真实农历质量验收，也没有复制任何假期表。
- owner的规则时区决定传给P2的日历日期；参考时间只改显示为Tokyo不能改变触发瞬间。
  DST不存在时刻按明确skip略过，不能平移分钟；重叠时刻仍遵守明确fold策略。
- UTC公历上界搜索耗尽应返回需澄清，不把不存在的日期截断成最近可发送日。
  公共合同拒绝多余字段、冲突过滤和假的clarification布尔；host不能自行填入缺失月/日来绕过确认。

三目标覆盖分别为：calendar行100%/分支95.4545%/综合98.5294%；civil行100%/分支85.7143%/综合95.9184%；
contracts行/分支/综合100%。仍有calendar 1个、civil 2个未执行分支，不代表穷尽验证或全PR覆盖。
覆盖报告包含13相关源及9份完整套件文件的前后哈希，均无漂移。

真实接线仍需当前owner/subject、来源/订阅版本、原始due、事务CAS和发送前freshness；next_trigger.at只是候选，
不授权保存或投递。没有实际cron、PG、多worker、锁屏或飞书验收，也没有新增性能数据。

证据：[独立首轮](../../evidence/MOD_2026-10-21/SCHEDULING_calendar_independent_first_20261021.json)、
[模块兼容与覆盖](../../evidence/MOD_2026-10-21/SCHEDULING_calendar_coverage_20261021.json)、
[阶段回执](../../evidence/MOD_2026-10-21/SCHEDULING_calendar_receipt_20261021.md)。
