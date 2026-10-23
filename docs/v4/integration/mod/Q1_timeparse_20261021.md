# U4统一时间解析：主线接线

本轮新增`mingjing_core/timeparse/`；没有改P2、ContextEngine、工具dispatcher或memory_write。它是纯解析模块，结果不是提醒已排程或事实已保存的回执。主线按Z6定义接口/替身后，可用此模块做实际适配。运行验收和源码提交号见本轮日报，未发布的里程碑不能仅凭本文称为验收通过。

## 入口与时间口径

```python
from datetime import datetime
from zoneinfo import ZoneInfo
from mingjing_core.timeparse import parse_time_range, absolutize

ref = datetime(2026, 10, 17, 9, tzinfo=ZoneInfo("Asia/Shanghai"))
result = parse_time_range("下周三面试", ref)
assert result.start.astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat() == "2026-10-21"
rewritten = absolutize("下周三面试", ref)
assert rewritten.original_text == "下周三面试"
assert rewritten.text == "2026-10-21（周三）面试"
```

同样的“下周三”在10月20日周二参考时刻，指10月28日；必须传本次真实`said_at/ref_time`，不能使用脚本运行当天或主机东京时区。参考时刻必须带时区；默认解释区为Asia/Shanghai，可明确传owner区。没有隐式读取系统当前时间。

`TimeRangeResult`含start/end、granularity、kind、confidence、candidates、needs_clarification、normalized_text、original_text、matched_text/span以及recurrence/reason。`.as_dict()`为JSON安全投影；正文、原文与span属于私人材料，不能写公共日志。start/end规范为UTC aware；normalized_text按owner区显示。

天粒度point用`[本地零点,次日零点)`，不把结束日也算进窗口；精确时刻point的start=end。range为半开区间。recurring只描述规则，真正next trigger由后续调度计算。低置信或有歧义的候选不能直接作为已确认event_at。

## 歧义与绝对化

- 裸“周三”当天、没标日期且已经过去的时刻、今晚凌晨、年前/年后和常见学期口径都可能需要确认；展示候选，不静默选择其中一个保存。
- `absolutize`返回`AbsolutizedText(original_text,text,result,replaced)`。只有唯一可确定的非循环表达式才替换；有歧义或多个独立时间时保留原文和解析结果，主线生成知识缺口。
- 时间提取不是语义事实授权。“如果明天搬家”仍要由记忆写入检查假设/来源；不要把解析成功当用户已决定或用户事实。
- 记忆应同时保留原始说法、said_at、明确的event_at/范围、时区与解析版本；更正/撤销必须覆盖派生字段。多个事件/时间不能用单个匹配结果冒充全部事件的日期。

## P2只读历法端口

`calendar_port.P2CalendarPort`调用现有`calendar_cn.day_status/statutory_dates/holiday_window`，并用已锁定lunar-python处理农历/节气。不复制年度假期表，不下载模型或历法数据。可注入相同CalendarPort做合成调休测试。

法定节日本身的历法日期与“已公布放假调休”分开。P2对未公布年份返回unpublished，假期期间与之后首工作日应要求确认，不能拿普通周末推断已公布安排。农历闰月不存在、非法日、模糊年前年后等不允许rollover猜测。节气从物理瞬间转换owner区一次，不能把旧年冬至误作今年冬至。

学期缺少学校校历时始终待确认；候选的常见开学区间只是估计，不是学校事实。公共日志不能记录整个`.as_dict()`，因为它有意保留私有原文供溯源。

## 主线需要接入的旧文件（本模块线未改）

| 边界 | 主线后续适配 |
| --- | --- |
| P3的TimeRangeParser协议/工具dispatcher | 把本函数结果映射到主线类型，固定一次ref_time；低置信走确认；同轮时间工具复用同一时刻 |
| `application/memory.py`及新memory_write/update工具 | 先验证用户原话/owner/撤销，调用绝对化，保留原文与时间双字段；不能覆盖旧原话 |
| `memory/retrieval.py`的未来新增实现 | 事件按event_at、其他按said_at做同样半开时间过滤，向量/全文共用相同过滤 |
| `application/report_schedules.py`及新P7调度 | 使用CalendarPort工作日/调休/农历；K1/K2仍由调度规则处理，不由解析器发送 |
| finalize/L1上下文与界面 | 展示normalized_text或候选，引用真实时间依据；没有排程/保存回执不得说已经提醒/记下 |

## 复现

在Core Python3.11，清provider keys并关闭追踪：

```powershell
python -m pytest tests/v4/timeparse -q --basetemp=private/mod-week/pytest-timeparse
python tools/mod_week/benchmark_timeparse.py --count 1000 --repeats 5 --output private/mod-week/timeparse-perf.json
```

以上只验证本地纯解析。HTTP/PG/工具/记忆写入、真实用户澄清和调度投递未接线；P2未公布调休需要新官方资料时记待决，不联网猜数据。
