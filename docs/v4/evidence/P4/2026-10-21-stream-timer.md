# P4 M2b 切片回执：独立timer与有界PG候选

- 分支 / 起始基底：`v4/p3-wire-p4-20261021 @ 0af15deb17c19f7d7d0a983b69038764765903b2`，tree`49fcf1c2`。root随后在同树提交M3，收口时HEAD`31c49673f0b70de5b595a96d545a9b5a5c5c9603`；本片9个源/测试的原始SHA见下表，待root统一提交。Draft PR14仍未合并。
- ExecPlan：`docs/v4/execplans/P4_stream_timer_20261021.md`。
- 记录时间：2026-10-21 10:36，北京时间UTC+08。**仅M2b离线候选切片；默认关闭，不代表完整P4验收或部署许可。**

## 完成了什么

- 单actor独占buffer/metadata，队列上限2；producer和独立单调deadline都由同一线程串行调用原纯核。40字用原feed_delta，静默用原poll_delta，正常模型结束用原flush_delta。原12文件及manifest没有变化。
- 不足40字的真实合成供应商片段在供应商继续静默时先落真实PG，下一片/模型结束尚未到来；timer不靠下一片触发。测试实际观察阈值为50–750ms；150ms边界由原Clock纯核149/150ms目标单独证明，不能把阈值通过写成所有环境物理150ms SLA。
- 新仓储上下文拒已有外层事务，先50ms pool取连接，再SET LOCAL statement_timeout=100ms/lock_timeout=25ms，非阻塞try owner advisory。线程局部连接仅在仓储上下文注册/恢复，供原嵌套服务共享；通用repo.transaction未改。实际PG证明pool耗尽、owner锁竞争、行锁与语句超时拒绝/回滚，连接可再用，threadlocal恢复，局部timeout不泄到下一事务。
- 每次真实PG写仍核Journal model step、原RequestLedger、owner/subject/thread/epoch/lease/取消/期限、持久generation/offset；严格复用current_source_ids、turn_sources与prepared.versions。版本改变而lease未变、源撤销、DB取消、实际lease重领均拒旧timer；异常只保存固定领域错误并唤醒真实RunControl.cancel_event。
- failure finish先stop，既不join、也不等ack、不获取worker/owner I/O锁；已知actor失败或未确认write_inflight立即拒绝partial/fallback final。normal finish有界0.75s ack，不能略过既存失败。worker在begin/commit之前先set inflight再检查stop，错误先固定failure再清位；晚set marker反例证明finish先stop、看false之后的worker也不能再开始PG。
- inflight覆盖真实commit和事务外callback完成，回调未结束时不能final；正常finish回调/ack完成后才允许final，已stop/cancel时不开始新回调。任意已经开始的阻塞callback不能撤回，本片没有伪称解决网络外部行为；当前M3 HTTP从真实PG读取。
- critic/revise仍私有，沿原真实模型finally flush→工具/提问/review/reset顺序；Loop、ToolBatch、review、U41契约未改。真实供应商ModelUnavailable且无actor故障/在途的旧partial行为保留，并有对照；actor失败的普通与危机请求均拒绝partial及U41 fallback final。

## 首红与最小修复

10:28 timer首组**5 passed、1 failed / 4.42s**，`private/safe-narrow-e04198c3f32e4d2ab2e048788df82fc3`。实际owner try-lock失败设置actor.failure/cancel_event，但静默端口抛出的ModelUnavailable被原Loop转为可finalize outcome；当时失败finish只stop而未传已知actor错误，partial真的发布。root批准仅在facade失败finish传播已知固定错误，沿原CoreError无效依赖路径阻止发布，未改Loop/U41或原断言。

10:33新增相邻窗口单例**1 failed / 1.54s**，`private/safe-narrow-07f2b34a71f84e909509ed2aae7925c3`。真实Runtime/Journal/原请求账本/PG pending状态建立后，仅在timer的state.commit入口注入可控阻塞与最终失败；供应商独立ModelUnavailable时，failure尚未赋值，旧finish仍发布partial。这是提交边界故障注入，没有伪造PG结果，也不是网络黑洞实测。root批准inflight保守门，保留该反例并新增晚set marker、callback未完成反例，未知结果一律拒final。

这两次是真实待修行为，原始失败没有删除或改成xfail；最后仍断言result为空、0旧delta、失败finish不等timer。补充阶段的22/31/33/34目标绿只属于各自中间候选，不冒充最终成绩。

## 实际验证与评测分数

root安全runner使用既有P2 Python、真实隔离PG15与随机schema，限制继承环境、清凭据/隐式PG路由、关追踪，TZ=Asia/Tokyo，记录显式+08。HTTP/subprocess额外被目标fixture禁止，供应商只是QuietPort/ScriptedMeter。静默失败组使用BoundaryOnlyControl，仅关闭定期observer、保留执行边界poll；因此旧版本/DB取消等异步失败确由独立timer发现并唤醒静默port，没有定期poll替它掩盖缺失接线。

最终新/原M2a明确目标命令：

    C:/Users/Administrator/Documents/Codex/zhiming-v4-p2/.venv-core/Scripts/python.exe -X utf8 C:/Users/Administrator/Documents/Codex/2026-10-17/v4-ai-claude-c-users-administrator-4/work/b1_readonly/run_narrow_safe.py C:/Users/Administrator/Documents/Codex/zhiming-v4-p3-wire-p4 tests/v4/streaming_integration/test_stream_worker.py tests/v4/streaming_integration/test_stream_timer_pg.py tests/v4/streaming_integration/test_stream_transaction_pg.py tests/v4/streaming_integration/test_stream_candidate_scope.py tests/v4/streaming_integration/test_stream_candidate_runtime_pg.py

**37 passed / 11.82s**，exit0、0fail/error/skip；10:35:07.314905→10:35:20.042444，目录`private/safe-narrow-1c414eb2b9ae48899af3f1b11c445bd4`。组成：6个纯actor/Clock、9个真实Runtime timer、7个真实PG事务、原M2a15个来源/scope/Runtime目标。纯组件替身用于阻塞调度/回调/ack故障窗口；PG集成目标使用真实Runtime和数据库，不把纯替身结果冒充真实PG。

相关明确5文件命令：

    C:/Users/Administrator/Documents/Codex/zhiming-v4-p2/.venv-core/Scripts/python.exe -X utf8 C:/Users/Administrator/Documents/Codex/2026-10-17/v4-ai-claude-c-users-administrator-4/work/b1_readonly/run_narrow_safe.py C:/Users/Administrator/Documents/Codex/zhiming-v4-p3-wire-p4 tests/v4/streaming_integration/test_event_notify_pg.py tests/v4/agent/test_agent_runtime_pg.py tests/v4/agent/test_run_event_replay_pg.py tests/v4/agent/test_private_runtime_pg.py tests/v4/agent/test_thread_inbox_runtime_pg.py

**41 passed / 15.98s**，exit0、0fail/error/skip；10:35:46.591404→10:36:03.480468，目录`private/safe-narrow-ea2005c9254943fb90095212bcdd6a13`。原M1/Runtime/回放/无痕/inbox断言保留。所有目标单进程串行，未开目录全量；10:36释放窄槽。共享WIP中的窄组不能冒充不可变提交全量或CI成绩。

Ruff E/F/I/B/UP/SIM、120列format、AST/400行/函数60行、diff检查通过；最大源文件255行，最大函数56行。原12源码hash不变。未新增依赖或迁移、未改公共events_v1/core4 Schema。真实模型请求0、外部/飞书发送0、服务器访问0；本片未跑M8或实测模式，不给新的脚本百分比。

## 关键文件原始摘要

| 文件 | bytes | SHA256 |
|---|---:|---|
| repositories/streaming_transaction.py | 1804 | a5474fd5fcceae6fc4074dea907b2ad26abf39764ac13b2c5b73a447b4b1545a |
| application/run_event_stream_worker.py | 6938 | 938d7c0aef7416aff94d62ef06f6ea8c028e74758c290e4329a7d59599990479 |
| application/run_event_stream.py | 3606 | 5bb2f690d517fa6e8512c83bfe16413c967703e73fb1082f611f4c2db28cf125 |
| application/run_event_stream_state.py | 8136 | ea357754bd11c3d71a57d77807ef4e85cef6eab0ca1c3aea27148cef37f31943 |
| application/agent_runtime.py | 11782 | 28bb209f511ae0e7beb417bbc040f31bfcde08d3f48eadccf1dcd5914603bfa5 |
| tests/v4/streaming_integration/test_stream_worker.py | 5788 | 8e99c56c664d9e13ccb6baa8fc4c21991c66e0e4fb297289836fc4d789e60f48 |
| tests/v4/streaming_integration/test_stream_transaction_pg.py | 4871 | 8e870d8ae3bc5c76d2eda779a64952cd1c75daddf96dc5de697cfbfa20b8915f |
| tests/v4/streaming_integration/test_stream_timer_pg.py | 6539 | 531feaa80f45a1aa9eed52c9500be869cd280eed2633a023f2ed2f1af8f1e668 |
| tests/v4/streaming_integration/stream_timer_support.py | 3853 | 88e2a538a08d208ac200d17c47edbd08e901c52546a6fd84b0c2869df0637f08 |

非tests路径以`mingjing_core/`为根。当前只改3个既有文件：Runtime的可信cancel_event构造行、stream facade、stream state；新worker/仓储helper与4个测试/support为本片独占。M3文件未改。

| 安全原始产物 | bytes | SHA256 |
|---|---:|---|
| 首红e041 pytest.xml | 2057 | ed4a7182fbf4a750b691f8539badf61d571524163853b2a3ce001e78d7b96f88 |
| 首红e041 pytest.log | 773 | 1ea1c147555fc27aba3cd41f8ebc61e90dd68efaf9f29f555c7d5def701c853a |
| 首红e041 metadata.json | 446 | 74ae09f7f6f4e5e9003dbac790b33da29d658b75973b30c2936c4993d1c473a9 |
| 未确认写07f2 pytest.xml | 775 | 68e9af80c657a150eb5a552949bfffda37697bfac8517a7ee75320a3ed1ea0f3 |
| 未确认写07f2 pytest.log | 721 | 9c9bfc59788f0b4f1c091c2777d957d26cbf1843a7f7cb932826b33fdf165e01 |
| 未确认写07f2 metadata.json | 519 | 14d838d04eadc21df9806836a946a287b728b90e7e8813d6d906edc2aa7a1eb2 |
| 最终37 pytest.xml | 9380 | 46da5ef3269969857baff68f81645dfacfc16841551e79cf8f5aa0042ad7d329 |
| 最终37 pytest.log | 102 | 79aef0d119a50e4aaf2a02e6a941e66697a1e88b873e5a1eeb8d07262e5fe284 |
| 最终37 metadata.json | 721 | 3bbd2b20391cd1339187c3728bda795d7c69aab0c18a9d1cd4d41129440a6e62 |
| 相关41 pytest.xml | 9310 | f3725753a3ed7e973e42544ac6d91f323c3711d36890f9cc51965740c5dc4d8b |
| 相关41 pytest.log | 102 | 1d51824e87ceee4ffbf77f35419847bd4f8018c4d10baba536fcb447232fa597 |
| 相关41 metadata.json | 650 | 1fc5f87f1897a86b9cc5b30d21ce251c9a22e136783d9e971c59c96508b55279 |

## 数据库迁移、回滚与偏离

依赖/迁移0。继续使用原run.usage键、真实model Journal/请求账本、原event操作key；取消或失败不清除已提交证据，不新开generation掩盖恢复。可信开关默认关闭，关闭回M1原路径，不删除任何已有事件/metadata。原模块12源未修改，未来正式模块普通集成替换唯一导入接点后仍须复验。

本片按root批准拆出单actor和有界事务，未改通用repo.transaction、Loop/ToolBatch/review、Schema、前端或模块源。模型结束flush已覆盖普通工具/review顺序；其他非文本事件的全面桥接、完整resumed/reset恢复仍未完成。

## 未验证、待决与建议后续

SQL语句/锁/pool界限不等于同步PG客户端网络黑洞或COMMIT确认的严格端到端时限；本片没有运行该类黑洞实测，不以daemon冒充资源回收，也不宣称取消全边界2秒。未知写拒final是保守安全门，原unfinished fail closed仍在；完整恢复另审。任意已经开始的阻塞callback无法强制撤回，此时inflight门拒final；HTTP的真实取消/重放/跨进程与M3组合、24h清理、完整P4/旧DOM均另验。

本片没有新增要求用户即时回答的问题。建议root核上述11文件并小提交，再固定新头做窗口内组合回归；保留P3 X03、encoder、旧DOM与B1 No-Go，不能用本片窄绿解除。
