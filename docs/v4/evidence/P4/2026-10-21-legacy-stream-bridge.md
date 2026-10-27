# P4 M4b：同一PG事件的新旧SSE读取桥

完成记录2026-10-21 11:29:58 +08:00（工具UTC 03:29:58），独立P4工作树`C:/Users/Administrator/Documents/Codex/zhiming-v4-p3-wire-p4`，基准M4a `9b4aa474bd1837702e8229284226921e04002136`。本片依赖并行M5候选的`event_retention_metadata.is_closed`及真实手动sweep；root要求M5先独立提交，再提交本片。本结果来自当前组合工作树，**不是单独9b4代码的结果**，最终组合提交/CI由root另核，不预填SHA。

## 实现与边界

新增`adapters/run_event_follow.py`把原GET的同一RunEventReader.page、游标核验、持久页追赶、hint等待、15秒心跳和响应/generator双finally提取为共享读取器。hint不推进cursor、不带正文/授权；没有第二个listener、正文缓存或consult。`thread_events.py`只以原encode_sse编码这些相同事件，冻结GET字段/编码、Last-Event-ID/after/after_seq、owner/subject/thread门不变；原GET HTTP/游标/关闭生命周期等明确目标均继续通过。

新增`adapters/legacy_run_events.py`和`application/legacy_stream_projection.py`将相同PG事件转换为旧平面data.type帧，web.stream仅v4分支改用它，v3原段落不改。legacy没有v=1或named event，保留实际seq对应的id；started/context来自真实run/原source/线程，status/tool只给安全summary，text_delta/reset沿已公开文字，正常终态一次[DONE]，断线不取消业务且释放订阅。

final需当前PG状态succeeded、事件envelope逐字段等于原run.result、消息ID匹配，再用原read_result产生含answer的规范读取投影。原core4不回写、不加memory_receipts。error只可为当前持久终态，精确匹配terminal-error证明的attempt/epoch/status/seq与固定code/message；旧失败attempt的错误不能污染当前重试成功，同code的旧attempt也不算当前错误。

30d已闭历史同owner事务先核M5 is_closed，禁止缓存final/正文再输出；正常空事件历史不按run.result补result。真实手动sweep后的legacy仅DONE、GET命名流为空，原run.result保持。缺失/损坏原件仍沿reader原拒绝/受信修复，桥不伪造正文或开启新epoch。源撤销/取消后旧缓存事件不出正文，来源闭包与租约逻辑未改。

generic PublicReceipt不会被丢掉版本后伪装成旧记忆卡：tool_call/result只投影安全status，不转发name、arguments、reasoning或receipt。实际Loop当前没有把可选receipt塞入tool_result；测试用**真实完成写入回执**填schema允许的可选字段作为投影反例，不冒称当前producer已发。真正memory_receipt若将来由独立可信producer写入仍遵冻结类型，不从“保存宣称”猜造。

## 三处协议观察迁移：保留业务断言

root逐项批准，并非删除失败测试：

1. `test_thread_routes_pg.test_compat_chat_opted_in_v4_uses_new_events_and_rejects_private_hint`原默认POST断言named final，现迁为默认legacy result；另加JSON202→GET frozen named门。私密hint拒绝且零原话、原真实PG core4结果、同ID/1模型执行/2消息和legacy零调用均保留或加强；冻结GET逐事件validate_event仍核。
2. `test_chat_acceptance_http_pg.test_json_ack_precedes_model_completion_and_get_replays_same_run`原跨Accept那一行比较同named final，现只改为legacy result等于read_result同一原信封。JSON早于模型完成、真实source/thread/run、相同run、1调用、2消息及原GET final全保留。
3. 原实际DOM `exercise_roundtrip`曾观察new.recovery_count=1，是旧JS忽略P3 named后额外GET恢复。本片先不迁counter实际运行，保留**1failed/3.86s，post_count=1/recovery_count=0**首红；root批准只1→0后复验。static/app.js与legacy_dom_probe.cjs没有修改。原三轮v3→v4→v3、真实saved/2次scripted调用/旧模型4次请求、history3、owner隔离、receipt[1,1]与原strict raises LegacyReceiptMissing全部保留。

API合同`api_chat_acceptance_v1.md`仅同步当前默认v4为legacy、记录M4a初版临时named历史；冻结Envelope/events Schema没改。旧P3线程API文档的临时描述作为历史由该最新合同明确补充，不把旧协议假装永远未变。

## 真实测试、首轮失败与环境

全部使用显式本机回环PG15、端口55480、可丢弃随机schema；DSN只在私有runner中，本文不提供。TZ=Asia/Tokyo且业务日期通过项目Clock，清供应商密钥/追踪。实际socket均httpx trust_env=False/仅127.0.0.1，Node probe只接本机原页面；没有真实供应商、服务器、飞书请求或WSL/Docker探测。

首轮新两文件为**11passed/2failed，8.27s**。两个失败是新夹具的错误前提：当前Loop tool_result未附可选receipt；单独repo.delete未执行实际HTTP源撤销的同事务invalidate闭包。后续明确可选字段反例并调用既有delete+closure、先断言revoked；不改生产门或旧断言。原日志`private/p4-legacy-stream-20261021/initial-target.log`保留。

明确九文件组合：

    python -m pytest tests/v4/streaming_integration/test_legacy_event_projection_pg.py tests/v4/streaming_integration/test_legacy_event_bridge_http_pg.py tests/v4/agent/test_thread_routes_pg.py tests/v4/streaming_integration/test_chat_acceptance_http_pg.py tests/v4/streaming_integration/test_event_cursor_pg.py tests/v4/streaming_integration/test_event_cursor_http_pg.py tests/v4/streaming_integration/test_event_http_pg.py tests/v4/streaming_integration/test_event_http_lifecycle_pg.py tests/v4/agent/test_run_event_replay_pg.py -q --tb=short

结果**58 passed/33.46s，1既有Starlette/anyio BlockingPortal弃用warning**，0fail/skip/xfail。新两文件13项为9真实PG+4实际socket，含提示开/关、慢模型未完已started、断线退订、当前持久取消错误、跨表示同一次模型/原件、篡改/跨owner拒绝、旧attempt隔离、源撤销、真实30d关闭与缓存final拒绝。原明确GET游标/跨进程提示/同进程双app连接/损坏原件/终态重放等保护均继续；不是整目录宽验。

真实DOM先红后迁的精确复验：

    python -m pytest tests/v4/agent/test_legacy_dom_runtime_pg.py::test_legacy_dom_real_http_v3_v4_v3_and_committed_history tests/v4/agent/test_legacy_dom_runtime_pg.py::test_legacy_dom_displays_actual_core4_memory_receipt -q --tb=short

结果**1 passed + 1 strict xfailed/10.16s**，没有把回执缺口签成绿。当前/history实际receipt DOM计数仍为0，恰是原LegacyReceiptMissing预期；最终[1,1]断言未改。原counter首红与迁移后日志分别为`dom-original-counter-red.log`、`dom-migrated-target.log`，与58组合日志都保留在同一private目录，未覆盖原历史宽验/M4a80报告。

Node实际版本**v24.15.0**，只读复用P2根node_modules的已锁jsdom，不是P2/web/node_modules；未安装依赖、未修改P2或前端线。该成绩为本机Node24，不冒称CI Node22或当前GitHub头绿。新源/测试Ruff/format、旧现代测试120列格式、AST新文件400行/函数60行与diff检查随后随清单冻结；没有git add/commit/push，均交root统一发布。

## 未完成与回退

普通旧DOM正文兼容恢复，不代表旧DOM回执全绿；current/history记忆展示、可信即时memory_receipt生产、固定塔罗reading来源/完成桥、新前端生产JSON接入与完整P4仍未验收。没有给core4加别名、修改web/**/static/**/Schema或解除复杂输入拒绝。取消实测是本机通道，不宣称黑洞网络硬时限或真实供应商行为。

无迁移、无owner runtime切换、无调用预算变化。M5先行依赖及本片候选仅独立草稿分支，回退本片web.stream委托即可回到P3临时named行为；数据/原信封/事件不重写。正式默认legacy由P4目标驱动，回退后的旧协议限制须明确。任何整库/CI/真实部署状态均由后续固定组合头另行给证据。
