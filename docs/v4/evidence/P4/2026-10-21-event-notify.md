# P4 M1 切片回执：真实事件原子通知

- 分支 / 基底提交：`v4/p3-wire-p4-20261021 @ ff4b4f65d762c8eef33a6e557b003050a3a808fd`；本片待root审查提交，未推送/合并；没有新PR。
- ExecPlan：`docs/v4/execplans/P4_event_notify_20261021.md`。
- 时间：2026-10-21 09:47，北京时间UTC+08。本片是最小M1，**不是P4阶段完成或发布许可**。

## 完成了什么

新增`repositories/run_event_log.py`统一两处真实事件INSERT：同一owner/run事务中分seq、写冻结v1事件、可选写无正文operation元数据，再`pg_notify('mj_run',run_id+':'+seq)`。普通事件同样通知且全部保留，不根据相同文字去重。只有started的run/epoch身份和reader终态error的真实attempt/epoch/status/诊断版本自动使用稳定key；其他调用仅可由内部可信代码显式给key，公开HTTP/模型没有这个入口。

稳定key同内容重放返回原seq/ts，不重复通知；异内容、原件丢失/正文已清除拒绝，不从账本重造正文。owner/run/epoch纳入命名空间，subject/thread纳入完整性指纹；运行前复用Journal的租约、取消、期限、owner/subject/runtime门并核线程。原final/asked/options已提交结果精确核对保留，reader原error tag保留。

真实独立PG LISTEN证明：外层事务提交前无通知、别的连接看不到未提交row；commit后收到精确seq且row可读；rollback没有row/ledger/notify；两个并发写入者的相同稳定操作仅一份；同epoch真实过期lease/重新claim复用原started且旧token拒发。错owner/别名/subject/thread/epoch/lease、取消、真实来源invalidate拒发；普通重复片两份都存在，隐私清空与缺失原件不复活。

## 实际验证与评测

root既有安全runner使用已存在P2 Core Python、固定本机隔离PG15与每测试随机schema，限制继承环境、清供应商与隐式PG变量、关追踪、TZ=Asia/Tokyo；stdout只给安全metadata和汇总。测试没有真实模型或外部HTTP，PG保持实际业务服务/仓储权威。

    C:/Users/Administrator/Documents/Codex/zhiming-v4-p2/.venv-core/Scripts/python.exe -X utf8 C:/Users/Administrator/Documents/Codex/2026-10-17/v4-ai-claude-c-users-administrator-4/work/b1_readonly/run_narrow_safe.py C:/Users/Administrator/Documents/Codex/zhiming-v4-p3-wire-p4 tests/v4/streaming_integration/test_event_notify_pg.py tests/v4/agent/test_run_event_replay_pg.py tests/v4/agent/test_public_events_contract.py

首组63 passed/11.16s，exit0、0fail/error/skip；北京时间09:44:24.871711→09:44:37.126802。包括18新通知目标、4旧回放、41冻结契约。产物`private/safe-narrow-18ab609fdc92497199807a092496cfcf`。

随后只在新测试增加真实同epoch租约重领，生产三源未改；第二组覆盖实际调用链：

    C:/Users/Administrator/Documents/Codex/zhiming-v4-p2/.venv-core/Scripts/python.exe -X utf8 C:/Users/Administrator/Documents/Codex/2026-10-17/v4-ai-claude-c-users-administrator-4/work/b1_readonly/run_narrow_safe.py C:/Users/Administrator/Documents/Codex/zhiming-v4-p3-wire-p4 tests/v4/streaming_integration/test_event_notify_pg.py tests/v4/agent/test_run_event_replay_pg.py tests/v4/agent/test_agent_runtime_pg.py tests/v4/agent/test_private_runtime_pg.py tests/v4/agent/test_thread_inbox_runtime_pg.py

第二组41 passed/24.34s，exit0、0fail/error/skip；北京时间09:45:47.551857→09:46:12.837256。包括最终19新目标、4旧回放、7实际Runtime、9无痕Runtime、2 inbox Runtime；两组重叠不能相加。产物`private/safe-narrow-43963887e2ea4710a4df4cd964e87a19`。

原始JUnit第二组timestamp为`2026-10-21T02:45:48.357253+01:00`，对应北京时间09:45:48；安全runner记录显式+08起止。没有依赖主机默认时区断言。脚本X08/全量评测/真实模型首字测试本片未跑，不给分或虚报100%。

Ruff E/F/I/B/UP/SIM、120列格式、diff空白检查通过；生产新仓储101行，RuntimeEvents77行，reader116行，新测试270行，所有函数≤60行。未改任何旧断言。

## 关键产物与原始摘要

| 文件 | bytes | SHA256 |
|---|---:|---|
| mingjing_core/repositories/run_event_log.py | 4132 | e6979cfca97ba9d4653d927f083e1a3dc531924005ea50c785cffd8a6151906c |
| mingjing_core/application/agent_runtime_events.py | 4008 | d0ba6e5f19be228ef44227cf0b57fa0e4899bda1de2e028ec95fc4af55fa1814 |
| mingjing_core/application/run_event_read.py | 5572 | dae4655a5b45abc5be32bd355a1f9678726cccf76d92722ed1add0da0ab609b8 |
| tests/v4/streaming_integration/test_event_notify_pg.py | 12213 | 8965572a4e846bc0288f7d06a713139a97287188e1c223a0d554b1a79756e534 |
| 第一组 pytest.xml | 14090 | 95bb165566b8a991e27ecedd30dc150f2c52cc4ea0d1b5e1f5031929f530d699 |
| 第一组 pytest.log | 102 | 908fb4513f94f910b23516076f146c0b6cb009c2b53a8b1c1686adf352045dbd |
| 第二组 pytest.xml | 9310 | e461f5293c59f8daa79e0b0e854d099f843b566515d8403cb4365c4d00b7a3d0 |
| 第二组 pytest.log | 102 | 59eaf86d999a85e45882b207b0cd7cd861c0469c75071a3106bbda3d50da1577 |
| 第二组 metadata.json | 650 | aa1edbb75d6e7d6b2f449a7357c463f579ce727c703ee2b39cc6faca063360d4 |

冻结事件Schema原字节40498/SHA256 `fa42065d1baebb5b486283b073f4e141ead00d8b96538254c0a4b3112916a04d`；core4 Schema16869/SHA256 `03e6da90da64164c4dc76507632a25ef7f14ee5232066bbf236a481f0548c632`。不新增公开键、迁移或依赖，未复制模块源。

## 数据库迁移与回退

没有新迁移。复用core_operations已有文本列保存p4-event命名空间、内容指纹与seq，事件正文只在原core_run_events。代码回退不删除事件或账本，不重放模型/业务工具；切回既有PG轮询只读流不改变最终消息或隐私闭包。正式stage/生产没有执行，本片不涉及B1固定b9。

## 偏离设计与未验证

按root批准先做真实通知及可证稳定key，不将kind、正文hash或实例counter当跨崩溃身份。status/options/asked/final/普通delta的step/chunk稳定操作身份仍待后续；终态旧单份校验仅保原行为。最终助手消息提交仍与之后final事件分开，由既有reader安全修复，未声称二者已在一个事务。

模块PgEventStore为未合入的纯端口，本片只按其事务/字段约定接真实仓储；M2合并器/有界hub、M3单LISTEN lifespan/续传、M4旧DOM与JSON入队、M5清理、M6性能/跨进程SSE/X08仍未完成。P3 X03原四条断言待大脑、旧DOM回执、真实公开encoder与组合CI保持阻塞；不得称P3/P4验收、supplier ready或已上线。真实模型、服务器/SSH、飞书外发均0，未重试Docker/WSL环境。

## 需要大脑决定与建议后续

本M1切片没有新增用户待决。原X03/encoder/旧DOM待决延续；下一步按root分配在集成子分支接模块来源、可信step/chunk事件身份及M2/M3，不改评分、其他线源码或现有Schema。
