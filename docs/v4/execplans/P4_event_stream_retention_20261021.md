# P4 M5整合补片：流缓冲不得回退水位，删除前必须校准

本ExecPlan遵循`.agent/PLANS.md`。创建于2026-10-21 11:31:26 +08:00（工具UTC换算）。工作树`C:/Users/Administrator/Documents/Codex/zhiming-v4-p3-wire-p4`。root在M5冻结12件静态复核发现两个遗漏，授权本片先真实红再最小修复，不提交/暂存，不触其他代理源码或修改既有时延阈值。

## Purpose / Big Picture

真正启用流缓冲的运行也必须保住每次已分配事件的序号水位。流状态保存只更新它自己的usage字段，不能把同事务append刚写入的保留水位或其他字段覆盖为旧值。清理即使遇到升级前落后的合法水位，也须在删除任何行之前，以锁内实际最大seq校准并持久化。否则删尾后新事件可能复用已经发过的序号。

## Context and Orientation

复用`application/run_event_stream_state.py::StreamState.commit/_save`、`repositories/run_event_log.py::append_event`、`event_retention_metadata.next_sequence/state/store`及`application/event_retention.py::EventRetentionSweep._one`。真实候选流使用原模块40字/150ms缓冲与持久Journal/RequestLedger，测试仅替代模型，不替代业务PG。旧timer、cursor、event replay/notify断言和阈值均保留。

`StreamState.commit`先取current快照，append_event会独立更新usage中的event_retention_v1；随后旧_save以dict(current.usage,p4_stream_candidate=...)整列写回，回退了水位。M5首片的新测试使用普通事件入口，没开启true buffer，未覆盖这个路径。另_one已锁run却直接信已有水位，漏了计划要求的“先核实际max再删”。这两项均是实际候选整合缺陷，不把旧29例绿当作已覆盖。

## Progress

- [x] (2026-10-21 11:31:26 +08:00) 收到root精确审查并完整读StreamState、ModelDeltaStream/worker、原timer/candidate runtime及retention调用方。
- [ ] 新真实PG反例在冻结M5源副本执行，保首红，不回滚共享树或污染root固定归档。
- [ ] 最小改_save仅jsonb_set自己的STATE_KEY；_one删除前锁内校准HWM，不改其他usage写接口。
- [ ] 新精确组及原timer/cursor/replay/notify明确文件串行验证，静态通过后独立证据冻结交root。

## Surprises & Discoveries

首片水位指纹仍可能合法但值落后：旧_save整列覆盖的是同run较早的合法metadata，不会触发指纹失配；只有真实append→save同事务观察及删尾重试才能暴露。成功结束后final事件常再次抬高水位，所以新反例须模拟缓冲已写出、模型随即中止，尚无final/error的运行，不能用成功终态掩盖。

## Decision Log

2026-10-21 / root：8生产+2测试+2doc的原冻结片暂不提交。授权本片独占run_event_stream_state._save最小字段更新及EventRetentionSweep._one实际max校准；增加新真实候选流和删前观察，不扩大到其他usage写入器，不改阈值/旧断言。全夜规则不变，单一窄测试进程，无服务器/真实模型/飞书/新增依赖。

旧_save改为数据库内仅替换p4_stream_candidate字段，保留当前行其他usage。_one在现有run锁及资格核验后、任何closed/删除操作之前取实际max，以max(stored,actual)写回。该校准与后续墓碑/DELETE同事务，异常回滚不能留下假水位或半删状态；保留原50run/1000事件边界。

## Plan of Work / Interfaces

新增`tests/v4/streaming_integration/test_event_stream_retention_pg.py`。采用真实AgentRuntime(streaming_candidate=True)与Scripted ChunkPort，触发40字同步flush；观察StreamState._save前后PG水位与另一usage字段；模拟模型中止后fail_run、无error/final、真实删尾，再claim新事件证明seq不重用。24h/30d参数例将合法旧水位调低模拟升级，在第一轮_rows之后/DELETE之前读取PG证明已校准。

仅生产`application/run_event_stream_state.py::_save`及`application/event_retention.py::_one`/短辅助函数需要修改。公开Schema、core4、旧迁移、b9、web/static、其他usage写接口均不变。原第一片证据不覆盖或删除，补片另写`docs/v4/evidence/P4/2026-10-21-event-stream-retention.md`。

## Validation and Acceptance

输入真实候选流40字→PG实际text_delta seq增加→保存流metadata后HWM不少于实际seq，别的usage字段逐字不变。模型中止、不发error/final后删tail→新claim事件seq严格大于曾发最大值。合法落后水位在24h/30d清理第一次实际DELETE之前已达到实际max，清理后仍保留。对应07场景X03恢复不重复、X04不修改停止阈值、X08续传序号稳定、F03隐私删除不复活；不声称跑了完整评测。

先在自己的private副本固定原M5冻结12件源加新测试保存真实红，后当前树绿；单一窄槽串行，原test_stream_timer_pg/test_stream_candidate_runtime_pg/test_event_cursor_pg/test_run_event_replay_pg/test_event_notify_pg不改。所有目标由清凭据/固定本机隔离PG/关闭追踪runner运行，不开全目录回归。

## Idempotence and Recovery

不重建既有事件、不变更operation身份。jsonb_set同事务重放只覆盖流自身字段；校准取max不减小水位。测试故障注入只触自己随机schema；异常或取消仍由原租约/步骤证明门处理，不为通过测试延长timer/取消上限。

## Outcomes & Retrospective

目前仅源码审计与新反例设计，尚未执行本补片红绿。原首片29+51通过保留为历史，不能覆盖两个新缺口；默认后台仍未启用。

## 修订记录

2026-10-21 11:31:26 +08:00 创建，记录root静态发现的实际整合缺口和最小授权范围，先红后绿。
