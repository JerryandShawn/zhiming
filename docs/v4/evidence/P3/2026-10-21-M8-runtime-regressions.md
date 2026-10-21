# M8 运行时回归补充

记录时间：2026-10-21 00:54，北京时间。全部本机离线，供应商请求、远端服务器访问、真实飞书发送均为零。

## 连续自写

`tests/v4/agent/test_eval_v4_continuous_pg.py` 使用真实隔离 PG15 和实际 Runtime，空档案下同一用户原话的两项饮食偏好分别经 memory_write 写入。核验两个真实 mutation operation、两个可公开回执、最终 state_version 的两个事实版本、三个合成模型步骤和恰好一个助手消息。公开回执没有内部 operation 字段；重复读取已成功 run 返回同一信封，不再写入事实或助手消息。

    python -m pytest tests/v4/agent/test_eval_v4_continuous_pg.py -q

结果 **1 passed /1.63s，无 skip**，Ruff 和 format 通过。该项不改变原 47 或新增 13 项场景的评分契约。

## 目标故障独立失败

只读审计最初仅看到 engine 记录 target_error_code，继续沿调用读取后确认 `judges.check_assertions` 已主动追加失败的 target_error。原框架不存在“弱断言全过就掩盖目标故障”的问题；engine.py 最终没有改动。

新 `tests/v4/agent/test_eval_target_errors.py` 六个反例核验普通文本/禁用工具/零提问断言全部满足时，ModelUnavailable、EvidenceError 或不安全错误正文仍独立硬失败；不安全正文只留下 TargetFailure，不进入报告，也不调用评审。judge=None 的评分语义保持原状。

    python -m pytest tests/v4/agent/test_eval_target_errors.py tests/v4/test_eval_framework.py -q

结果 **54 passed /9.89s**，Ruff 和 format 通过。这里只增加回归保护，没有更改评分实现、基线或历史评测报告。

## 危机合并原话审计闭环

已向主代理提交合并入站消息的危机识别缺口：此前 Runtime 只检查 request.message，而合并入队的 message 为最后一条。第一条危机意图加后续普通补充的组合应只从本轮受信原话范围识别，不应扫描跨线程历史。

00:58 只读核对：主代理已在 `4ada72d` 接入本轮多来源识别和运行中危机补充；其独立证据 `2026-10-21-u41-turn-sources.md` 记录 **13 passed /6.52s**，含计量失败、取消/撤销和崩溃重放。此处引用主代理实测记录，不冒充本片新增或独立复跑的测试。
