# P4 M2a 切片回执：原纯核与真实 Runtime 最小接线

- 分支 / 已提交基底：`v4/p3-wire-p4-20261021 @ 95df0f9ca850a4a52d821817c40ce3a1b9058a8f`，tree `e5b83229`；本片待root审查提交。既有Draft PR14依赖PR13，未合并。
- ExecPlan：`docs/v4/execplans/P4_stream_buffer_20261021.md`。
- 记录时间：2026-10-21 10:17，北京时间UTC+08。本片是M2a，**不是完整M2或P4验收，也不是部署授权**。

## 完成了什么

- [x] 使用模块线真实原纯核，固定来源`ebfa22f8f7c59e486c6632035ae6bc8307f0f438:mingjing_core/streaming/`，12原文件共27382 bytes；原始字节、SHA256与git blob全部逐项匹配。没有重写原算法或改模块源。
- [x] 在`integrations/streaming_candidate`隔离来源，唯一host导入接点核固定SOURCE_MANIFEST及源码hash；候选独有`.gitattributes`保留源字节。正式模块merge尚未发生，root提交时还须核git索引字节。
- [x] `HostStreamScope`用完整真实schema/owner/subject/thread/run的域分隔SHA256形成内部ASCII标签；真实PG门始终用原身份。Unicode owner的真实Runtime以及每个scope字段/分隔歧义反例均通过，hash不是授权。
- [x] 可信`AgentRuntime(streaming_candidate=True)`实际注入`LoopCycle→ObservedPort`文本消费；开关严格bool、默认关闭，不从模型/HTTP/环境任意输入打开。原关闭路径继续逐片公开，未改变正式程序集配置。
- [x] 实际Journal started模型、原RequestLedger/角色/input_fp、owner/subject/thread/lease/epoch/取消/期限门核验后开始流。generation、实际字符offset与text_delta/operation/PG通知在同一owner事务写入；原核40字与结束flush由真实PG目标证明。
- [x] completed结果重读不重发，两个真实model step有不同持久generation；critic与revision草稿不进入公开delta，受审revision仍走原text_reset。真实lease重领/来源撤销拒旧写，缺真实请求账本在物理ScriptedPort前拒绝。
- [x] 未完generation发生进程退出后保留元数据，重领不再调用模型或重发正文；当前明确fail closed，没有自动升代或恢复旁路。
- [ ] 独立150ms静默timer、受审resumed/reset恢复、hub/HTTP组合、完整P4门：本片未实施或未验。M3由另一代理独占，不能代报。

## 实际验证与评测分数

安全runner使用既有P2 Core Python、真实本机隔离PG15、每测试随机schema；限制继承环境、清供应商/隐式PG配置、关追踪，测试TZ为Asia/Tokyo。测试记录显式+08，未依赖主机默认时区。供应商只用本地`ChunkPort`/ScriptedMeter，测试额外阻止HTTP与subprocess。

新目标命令：

    C:/Users/Administrator/Documents/Codex/zhiming-v4-p2/.venv-core/Scripts/python.exe -X utf8 C:/Users/Administrator/Documents/Codex/2026-10-17/v4-ai-claude-c-users-administrator-4/work/b1_readonly/run_narrow_safe.py C:/Users/Administrator/Documents/Codex/zhiming-v4-p3-wire-p4 tests/v4/streaming_integration/test_stream_candidate_scope.py tests/v4/streaming_integration/test_stream_candidate_runtime_pg.py

**15 passed / 5.33s**，exit0、0fail/error/skip；10:15:54.634134→10:16:00.906483。3个来源/scope目标加12个真实Runtime目标。原始目录`private/safe-narrow-4a4fe747dd854a518633926f9b877d79`。

相关目标命令：

    C:/Users/Administrator/Documents/Codex/zhiming-v4-p2/.venv-core/Scripts/python.exe -X utf8 C:/Users/Administrator/Documents/Codex/2026-10-17/v4-ai-claude-c-users-administrator-4/work/b1_readonly/run_narrow_safe.py C:/Users/Administrator/Documents/Codex/zhiming-v4-p3-wire-p4 tests/v4/streaming_integration/test_event_notify_pg.py tests/v4/agent/test_agent_runtime_pg.py tests/v4/agent/test_run_event_replay_pg.py tests/v4/agent/test_private_runtime_pg.py tests/v4/agent/test_thread_inbox_runtime_pg.py

**41 passed / 17.14s**，exit0、0fail/error/skip；10:16:20.515041→10:16:38.598115。含19个真实通知、7 Runtime、4回放、9无痕Runtime、2 inbox；没有改旧断言。原始目录`private/safe-narrow-cb0ca9187cb8429dbf6d8f328d0e158c`。

相关组第一次误把最后测试路径写为不存在的`test_inbox_runtime_pg.py`：10:16:05.933796→10:16:06.814979，pytest exit4、0 collected，未执行测试。保留`private/safe-narrow-3244b94cab8449eba2d6d84f5c2d0194`；只纠正路径后重跑，没有产品失败或代码修补。上述新/相关目标按明确文件各跑一次，没有整库重试。

本片不重跑M8或实测模式，不产生新评测百分比；P3已有X03原失败与encoder/旧DOM阻塞保留。真实模型请求0、真实飞书/外部发送0、服务器访问0。10:00四宽时未启动pytest，获root在10:15释放单窄槽后串行运行，10:16释放该槽。

Ruff E/F/I/B/UP/SIM与120列format检查通过；自写源/测试全部≤400行、函数≤60行，AST通过；候选12原件没有format。`git diff --check`通过，公共Schema未改。

## 改了哪些关键文件

| 文件 | bytes | SHA256 |
|---|---:|---|
| agent/stream_events.py | 343 | 04efe1b0176229e37ddf7ac992e19d6b7591a8f71d360cce4a34a1e85c7982d6 |
| application/run_event_stream.py | 3428 | 89565a5df6baa921cd895efd92337bc6c65ffd7b355c1eec43dcd39f2d790e2d |
| application/run_event_stream_state.py | 7268 | a3f440efa04b65e2ab271cc9835c6631ba72c49dcc0fdeb234b65a75209b2a45 |
| application/streaming_kernel.py | 1742 | 83c78ceb4e274d200d35116231b90239a1cba4b9e71d1e631c6b5119a690da46 |
| application/streaming_scope.py | 1432 | 5ec3486a54e57e1c62435e8f3cb94e78fa0fedc49ada9fc7b6cc22ca869bde69 |
| agent/loop_cycle.py | 13711 | 23fac78654a2fb9500447fded88e92717674dcc056343bbe85f409eb08134b1a |
| application/agent_runtime.py | 11717 | 196ac06cf3058691f60d22c97793b05b0eca9c83048510faa54c8afa3aef6471 |
| integrations/__init__.py | 88 | 87e6ee72a112793bf09e0becf75c7771d5a5f3362b560731f7c6090694c8a6d6 |
| tests/v4/streaming_integration/test_stream_candidate_scope.py | 2380 | 6af2cfe9fa2ce9a8f6d9d3fb814c8b8f6ac1c606d3885df58f39e44bd4402455 |
| tests/v4/streaming_integration/test_stream_candidate_runtime_pg.py | 11137 | 6fcf0b05b046fedab883e2c07f98b4873b74ecd9bbb785ac7e5a7ad64a9dbe3e |

表中非tests路径以`mingjing_core/`为根。候选12源的逐项bytes/SHA/git blob见SOURCE_MANIFEST和ExecPlan，不重复抄表；其manifest raw SHA为`bb98bd12daafda15970d71ddb06c4600bad301889330531b144b03fd486bbd97`。原件`git hash-object --no-filters`逐项匹配来源blob；`.gitattributes`的`*.py -text`是host元数据，不冒充第13个原文件。root在git add之后须用`git show :<path>`再核原字节，提交后再核commit对象。

本片没有修改M3代理的hub/listener/service/thread_events/web文件。上述窄测试收集于共享WIP树，证明本片真实Runtime/PG路径；M3及10:00不可变全量成绩由其各自证据独立给出，不能把WIP窄测称冻结头全量绿。

## 原始安全产物摘要

| 产物 | bytes | SHA256 |
|---|---:|---|
| 新15 pytest.xml | 4085 | d9ac089c636c1e228f168646470a7b35a35be0011fe8483a8f74a55667c83d78 |
| 新15 pytest.log | 101 | f23d7246ce8db3198027afb0eb340b5d32d00f29a58650f304c11ac200b2f7f8 |
| 新15 metadata.json | 528 | 4d308820ffa9e3cbd89bc448e13d1b8244ad1a77d75bb3f6de8ecb62a34c1b9d |
| 路径错误 pytest.xml | 231 | fd5f0e3583da23713de92b3e7861039ec3efecceca02e05142733da2cd12584a |
| 路径错误 pytest.log | 104 | 02203bae1be2ea7f4fabdfc0028334d718a4da9abc5b68bdf317e6b6a7ef166a |
| 路径错误 metadata.json | 643 | b6f70996c11dcfc12ab374a385014e1517c47955337c3360c6a6368153a0dedd |
| 相关41 pytest.xml | 9310 | 0950d93e809795d88af6967c8e5699dcdffc6fa25417ec0a3a747c0abc2ec2cd |
| 相关41 pytest.log | 102 | 5da905802fe5ade9e5495669d2c2f630af9b55933556f4cf20809ac4aaf7ad89 |
| 相关41 metadata.json | 650 | 8a42f525dd2101ed2506317b13b329582a407bb6d25c9639d76e75e55668f1d8 |

## 数据库迁移与回滚方式

新增依赖/迁移0。流元数据只在现有run.usage私有键`p4_stream_candidate`，持久正文仍在原事件/Journal；操作账本只含既有指纹/身份/结果seq。候选关闭回到M1原事件路径，不删事件、ledger或已有generation。正式候选发布/打开尚未授权，不执行服务器切换或清理。

## 偏离设计的地方及未验证风险

root明确批准拆M2a：本片仅40字与结束flush；虽原纯核有poll_delta，供应商静默时没有独立150ms调度，不能冒称延迟达标。未完generation保守拒绝恢复；reset/恢复/ack未知后的安全继续需要后片。当前仍使用原普通repo事务，无timer有界连接/锁超时保证，不能据此声称取消最坏延迟。

150ms独立timer的锁/PG边界仅只读方案，未写入此片；M3有界hub/单LISTEN/真实HTTP、Last-Event-ID/24h清理、完整P4脚本/旧DOM仍独立验证。source pin证明原源码字节身份，不是供应商能力/真实模型或生产ready证明。正式模块普通集成后须替换唯一导入接点并复验。

## 需要用户或大脑决定的问题 / 建议后续

本片没有新增需要睡觉用户即时回答的问题。root先审本片并核索引12原字节，再小提交；随后单独审M2b有界调度/连接方案，执行静默timer、取消/撤销和review reset晚到反例。P3原X03、encoder、旧DOM及B1 No-Go均不由本片解除。
