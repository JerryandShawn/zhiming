# P4 M4a：普通chat的真实JSON接收回执

记录时间2026-10-21 11:09:11 +08:00（工具UTC 03:09:11），独立目录`C:/Users/Administrator/Documents/Codex/zhiming-v4-p3-wire-p4`，实现基准`a1270174e6f64cfe1abe915a09836647c1da3484`。本片依root批准，只实现普通v4 JSON握手及线程API真实message_id，不修改默认/SSE协议、模型执行、冻结Envelope/events、前端/旧static、固定reading或其它代理游标/保留逻辑。最终提交由root统一处理，本证据不预填SHA/CI结果。

## 可观察结果

已持久选择v4且显式安装受信AgentRuntime/meter与dispatcher时，`POST /api/chat`的`Accept: application/json`返回202。实测用真实socket/Uvicorn/PG及有限WaitingPort，在脚本模型尚未放行、run尚无result时已拿到响应；另一连接查到真实原话与run，证明不是临时ID或事务内未提交收据。放行后GET原events URL读取同一个冻结final；改变Accept重复POST读取原final，不增加source/run/模型调用。

回执精确字段为`run_id/message_id/thread_id/status/runtime/events_url/run_url`；没有lease、请求正文、推理或临时request_id替代message_id。JSON带`Vary: Accept`、`Cache-Control: no-store`。所有ID/线程/状态由当前owner持久行重读，source须属于同subject/thread、active当前用户、允许run_context、原话投影一致且未撤销；存在source_segments时与实际当前版本/范围一致。线程API复用同一个可信回执并增加真实message_id，v3线程回执不冒造冻结events URL。

operation的原runtime pin优先于当前owner设置：v4完成后owner改v3，同request仍返回原v4/succeeded回执；旧v3 pin在owner改v4后JSON-only仍406，原run不变。自然语言无痕激活返回真实incognito线程；不能拿先前请求的life线程冒充。运行中补充在实际HTTP下返回自己的source/子run、status=inbox_wait以及自己的events URL，绝不冒父run或父final。

## 内容协商与拒绝边界

Accept最多4096字符/32项，标准q取0–1且最多3位小数；显式JSON与可用SSE同最高质量时JSON优先，仅实际v4可用JSON。未给Accept、通配或显式SSE保持原路径；application/*和vendor+json不隐式启新握手。具体媒体q=0优先于通配，不能恢复被禁表示。非法/重复q只给固定中文406，不反射header内容；未认证畸形Accept仍401。

实际v3 JSON-only及不可用媒体在任何ensure_owner、原话、run和media目录写入前拒绝；新未建owner同样没有被检查过程创建。实际v3同时接受SSE时，由真实原LangGraph+FixtureModel返回旧data.type result/[DONE]，没有假events URL、没有改持久runtime或改走Agent。缺agent、meter或受信容量导致dispatcher未安装时，JSON在入库前失败，不回退旧模型。

精确负例覆盖foreign subject/owner原话、改source_segments、改request原话、源删除后ACK/重导入拒绝；没有用调用方的run字典或字符串自报授权。原tool/entity/lease/撤销契约没有放宽。

## 真实测试与静态检查

所有测试使用本机隔离PG15的随机schema，显式本机回环PG15、端口55480、DSN只在私有runner中、`TZ=Asia/Tokyo`，清供应商密钥与追踪，transport只允许loopback，socket Client均`trust_env=False`。没有真实供应商、服务器、飞书请求，也没有Docker/WSL探测。原纯/PG目标先跑59 passed/17.04s；补两个协议/实际inbox目标后再组合原两个文件，最终：

    python -m pytest tests/v4/streaming/test_http_negotiation.py tests/v4/streaming_integration/test_chat_acceptance_http_pg.py tests/v4/streaming_integration/test_chat_acceptance_replay_pg.py tests/v4/agent/test_thread_routes_pg.py tests/v4/agent/test_runtime_assembly_pg.py -q --tb=short

结果**80 passed/25.86s，1既有Starlette/anyio BlockingPortal弃用warning**，0fail/skip/xfail。新61项=40纯协商+21真实PG（其中14实际socket），原thread/runtime19项全部保留、无删改断言。原日志`private/p4-chat-acceptance-20261021/{initial-target,final-target}.log`保留，不覆盖历史宽验报告。唯一测试进程结束后已向root归还测试位。

新源/专属测试Ruff check及format通过，两个旧现代模块按原120列格式核查；web.py仅最小chat分支，无整文件重排。新模块93/67行，专属HTTP文件325行、函数均不超过60行。原SSE默认named final临时断言仍通过，未借本片更改它。

## 仍未完成 / 不可宣称

本片没有完成P4 M4。默认v4 POST仍是原P3命名SSE，M4b旧data.type投影待独立批准；旧DOM当前/history回执缺口、即时memory_receipt生产、固定塔罗reading真实来源/调度完成桥均未改。inbox_wait备用run可能在父实际采用后cancelled，本ACK未提供父采用/跟随关联，客户端必须按真实status处理，不能假设该子URL必有final。GET events的既有取消/权限/游标规则不变。

目标绿不能替代整库、GitHub CI、跨线前端联合DOM或真实服务验收。本片无迁移、无运行时配置变更、无owner版本自动切换。关闭客户端JSON opt-in即可继续现有SSE行为；代码候选的回退由root在独立草稿分支处理，未合并v4/main或main。
