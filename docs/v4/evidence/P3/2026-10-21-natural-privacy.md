# P3 M5 自然语言无痕组件证据

记录时区 Asia/Shanghai，2026-10-21 00:56 +08:00。工作树 C:/Users/Administrator/Documents/Codex/zhiming-v4，分支 v4/p3-agent-runtime。主组件复用原 M5 已提交4d89324；本片未自行提交，由root统一提交。没有SSH/服务器、真实供应商请求、真实飞书发送或合并。

## 已验证行为

严格当前用户原话中的完整命令分句“开个无痕/这段别记/本轮别记”进入临时线程；引用、代码围栏、Markdown引用、未闭引号、假设和他人转述不激活，包含父母/姐姐转述与“别忘记”反例。进入/退出同消息冲突在落原话前拒绝。正式P3提示词所规定的后续消息自动沿用到“结束无痕”或24小时无活动。

自动模式按owner/subject/channel/conversation隔离；选定private后才调用ThreadService.receive，提交时正文、policy.persist_allowed=False、incognito、thread_id在同事务，无已提交life来源搬移。life历史/搜索看不到私密正文；路由收据和模式记录无正文。重复事件固定原thread/source，不重触发模式，不延长TTL；更换原事件人物/线程/作者/会话/正文拒绝。等价UTC/+08时刻同一个事件，naive datetime拒绝，不依赖本机东京时区。

原 ThreadIngress.submit 会用调用方life排队，已改为实际source.thread_id；飞书以实际线程合并固定2.5秒批次。私密case绑定在单事务回滚，消息/模式/run都不留下。默认v3明示隐私拒绝为0消息/0run；原v4自动私密仍有效但owner改v3时，新的普通后续也不能降级落life。入口代理的runtime_assembly桥支持原private/多原话run按原身份重放，过期/清理不复活。

“本轮别记”对同owner/subject/thread既有queued/running/inbox_wait设持久禁写闸门；consumer从PG重读并核body-free控制收据，旧usage快照无效，真实prepare_retry新epoch仍保留。飞书旧life原话尚在缓冲、控制到达时还没有run，也会在之后flush入队时依据source.created_at继承barrier。设置与入队同事务，NOTIFY只在完整提交后可见；退出后的新life原话不被旧barrier误封。

自然语言退出停止自动路由，旧私密来源保持原线程并沿既有24小时清理。API close的明确立即清理入口不变；本片没有执行数据清理或删除既有资料。显式memory_forget不能被本轮新增禁写闸门误挡，工具副作用分组由root接入并另测。

## 测试

测试使用已锁定Core环境 C:/Users/Administrator/Documents/Codex/zhiming-v4-p2/.venv-core/Scripts/python.exe，本机隔离PG15回环55480/core_test_main，每例独立schema并清理。测试进程清供应商和追踪凭据、LANGSMITH_TRACING/LANGCHAIN_TRACING_V2=false，Clock固定UTC，不读密钥。

    python -m pytest -q tests/v4/agent/test_privacy_mode_policy.py tests/v4/agent/test_privacy_mode_pg.py tests/v4/agent/test_privacy_ingress_pg.py tests/v4/agent/test_thread_inbox_pg.py tests/v4/agent/test_feishu_ingress_pg.py tests/v4/agent/test_runtime_privacy_routes_pg.py tests/test_core_feishu_gateway.py

结果：**107 passed / 26.49s，0skip、0warning**。前一轮103/30.17s后增加父母/姐姐/写着转述4反例，再跑完整相同目标范围得107。未把未运行Linux/真实模型/CI称为通过。

本片8个源/测试文件通过Ruff E/F/I/B/UP/SIM（120列）与format；新源均小于400行、函数不超过60行。既有Gateway保护目标保留8项，没有为迎合实现删除旧安全断言。

## 文件归属与剩余边界

新增 application/privacy_mode.py、privacy_mode_policy.py、privacy_run_barrier.py；最小改 application/thread_ingress.py、feishu_ingress.py。新增test_privacy_mode_policy.py、test_privacy_mode_pg.py、test_privacy_ingress_pg.py；ExecPlan为docs/v4/execplans/P3_m5_natural_privacy.md。runtime_assembly.py与test_runtime_privacy_routes_pg.py由入口代理独立冻结；root独占agent_tools/Loop/Context/Finalizer。

root尚需单独证明 memory_write/update、note_write、profile_update_request、case写与长期任务在工具执行入口消费barrier，并保留经过原授权的memory_forget；本片已证明服务和持久闸门，不据此宣称全部长期工具已阻断。未跑完整P3/全量回归/真实评测或CI。
