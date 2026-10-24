# P3 M7：双通道调度候选与本机静默 HTTP 取消

2026-10-21 00:15（北京时间）。真实供应商请求 0、飞书发送 0、服务器访问 0；无新依赖或迁移。下面的物理 HTTP 是 127.0.0.1 的合成 SSE 服务，共 1 次，不能作为任何线上性能或供应商证明。

## 验证结果

新增 AgentDispatcher、DispatcherClaims、NotificationBridge、RunSignals 和 DispatcherCancellation。默认总容量 3，交互保留 2、后台最多 1；所有 v4 的 `claim_run` 共用 PG 容量及 owner/thread advisory 栅栏。队列候选过滤活跃线程，100 条扫描有上限；旧 v3 调用预算和 claim 行为保留。queue 的 NOTIFY 在事务提交时生效，消息仅有 schema/run ID，无正文。listener 按 schema 过滤；取消通知必须再核 PG cancel_requested_at，通知本身没有取消权。

取消接口先写 PG 权威标记，保留活跃租约至流关闭。真实 loopback HTTP 先产生一段合成文字，然后完全不发字节或心跳；取消后 **0.047 秒**运行变为 cancelled，已生成内容保存成 status=interrupted 助手消息，result 仍为空，物理请求没有重发。再次完成取消不新增消息；随后撤回其来源，partial 正文被删改且不复活。测试使用显式 HTTPTransport 防止环境代理，网络断言只放行 `http://127.0.0.1`。

RunControl 在 20 秒单调时间阈值后把真实 PG 租约续至 150 秒。M6 的一次来源撤销会换租约，Runtime 通过私有 `service.agent_lease_changed(old_run,new_run)` 同执行栈回调交还受信 worker；代理核 owner/run/subject/epoch/token 与 PG 新租约，不从 SSE 接收 token。撤销之后再取消的 PG 集成已通过，伪造和多次移交拒绝。

## 检查

    pytest tests/v4/agent/test_dispatcher_pg.py tests/v4/agent/test_dispatcher_http.py tests/v4/agent/test_dispatcher_handoff_pg.py tests/v4/agent/test_loop_cycle_pg.py tests/v4/agent/test_agent_runtime_pg.py tests/v4/agent/test_agent_runtime_recovery_pg.py tests/v4/agent/test_private_runtime_pg.py -q --tb=short -o junit_family=legacy

结果：38 passed in 13.39s（此后增加候选 SQL 过滤，并修复旧组件 fixture）。最终改动对应目标复验：

    pytest tests/v4/agent/test_context_epochs_pg.py tests/v4/agent/test_incognito_reminders_pg.py tests/v4/agent/test_dispatcher_pg.py tests/v4/agent/test_dispatcher_http.py tests/v4/agent/test_dispatcher_handoff_pg.py -q --tb=short -o junit_family=legacy

结果：**30 passed in 8.94s，无 warning**；Ruff E,F,I,B,UP,SIM、format120 与 400/60 尺寸检查通过。仅 1 个目标 pytest 进程；JUnit 原件保存在不提交的 private/p3-m7-dispatcher.xml。

## 已知边界

这是可注入的调度服务候选。FastAPI lifespan、web cancel route、飞书排队入口仍需由对应接线切片安装；不宣称生产入口已替换。现有历史默认只投影 active，interrupted 展示仍需调用方补齐。所有 worker 必须使用一致的 CORE_RUN_CONCURRENCY；旧入口默认 1，Dispatcher 明确拒绝小于 3。v3/v4 同时运行的入口选择由受信配置接线控制；v3 原行为没有为本片改变。本机一次 47ms 不代表目标服务器或真实模型表现。
