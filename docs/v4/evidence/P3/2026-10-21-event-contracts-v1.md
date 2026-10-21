# Z7 公开事件 / core4 契约冻结 v1

2026-10-20 23:15 +08:00，按28号第三节执行。范围为Core公开类型、SSE编码、两个JSON Schema、两份跨线契约文档，以及现有build_envelope构造器对齐。不是完整运行时/SSE订阅交付，不开启v4默认路由。

实际本机验证：

```text
pytest tests/v4/agent/test_public_events_contract.py tests/v4/agent/test_public_final_ask_pg.py tests/v4/agent/test_envelope_structural.py tests/v4/agent/test_agent_finalization_pg.py -q
89 passed in 6.15s
ruff check --select E,F,I,B,UP,SIM --line-length 120 <上述新改Python文件>
All checks passed!
```

使用仓库已锁Python依赖与本机回环PG15.19合成schema。测试清供应商凭据、关闭追踪/飞书，不产生真实HTTP/模型/消息。12类事件逐个通过同一JSON Schema和Core语义校验，编码后的SSE只有id/event/data三行；正文换行JSON转义。跨UTC/东京/负时区输入均显式转北京时间；不存在日期和+09:00事件时间拒绝。jsonschema锁没有可选RFC3339插件，测试用标准库fromisoformat注册date-time检查，不新增依赖。

Core4必需的asked/options显式null得到保留；公开receipt、usage及meta白名单不能携带reasoning/trace/工具参数。review改为28冻结的state/reasons；旧review.status单测随裁定更新，core3兼容和真实事务断言保留。新增真实PG闭环：ScriptedPort调用已注册ask_user → 持久步骤回执 →安全finalize → 稳定ask_id/选项ID公开投影 → 相同ask_user事件。修复旧构造器拒绝合法内部changes_conclusion的问题，不放松“提问必须来自真实步骤”的校验。

另外23:00按主线错峰启动的旧Core回归 **581 tests / 669.730s，OK**。该次从工作区启动，期间存在新文件和并行修改，不当作最终提交的全阶段回归或精确头CI。旧日报推送头dc574aaf的Core39442638366、时区39442638050已success；新B1头0df939e的Core39446105992仍进行中。

限制：事件seq持久分配/追加、订阅与重放、心跳调度、文本合并/清理、RuntimePort、评审一次修订与全部core3/core4读取端尚待主队列后续。当前build_envelope仅接受默认skipped受信状态，不能把模型自报passed当评审证据。JSON Schema不能表达跨字段message_id相等和按ID唯一，Core另做语义校验；客户端需同样核对。
