# P4 M1：把真实事件写入与通知放在同一事务

本 ExecPlan 遵循 `.agent/PLANS.md`，四活节持续更新，所有时间为北京时间 UTC+08。当前完成 M1 最小通知切片与两组窄验证，待 root 审查提交。原总计划 `P4_sse_integration_20261021.md` 的 M2–M6、P3 X03/旧 DOM/受信 K3 encoder 阻塞不因本片消失。

## Purpose / Big Picture

实际执行产生的每个公开事件落库后，都在同一 PostgreSQL 事务排队一条 `mj_run` 唤醒通知；其他进程只在提交后收到通知，失败回滚时什么也收不到。只有具有真实稳定身份的内部事件操作才去重，重放保留原 seq/ts 且不重复通知。通知仅为 `{run_id}:{seq}` 提示，不含正文或 owner 授权，不用它替代鉴权和回读数据库。

## Context and Orientation

独占树 `C:/Users/Administrator/Documents/Codex/zhiming-v4-p3-wire-p4`，分支 `v4/p3-wire-p4-20261021`，基底 `ff4b4f65d762c8eef33a6e557b003050a3a808fd`。它来自 P1b/P3 wire，尚未合进 v4/integration；不合 v4/main/main，不提交/推送，由 root 审查。模块只读来源 `origin/v4/mod-organize@ebfa22f8f7c59e486c6632035ae6bc8307f0f438`；本树没有 streaming 包，本片不复制、修改或假称已集成模块代码。

已完整读 P4 原提示词、冻结 events_v1/core4 文档、原 P4 集成计划、模块 Q3_sse/端口类型，以及 RuntimeEvents、RunEventReader、finalizer、Journal、模型请求账本、inbox 采用/恢复和取消调用。既有 `core_operations(owner,operation_id,fingerprint,kind,result_id)` 可容纳无正文事件账本，不新增迁移。`core_run_events` 真实列仍为 owner/run_id/seq/kind/payload/created_at；没有默认 seq、epoch 或 operation 列。

复用 `PostgresRepository.transaction` 的 owner advisory lock/嵌套事务、`_leased`/Journal._leased 的租约与 epoch/取消/期限检查、`assert_thread` 的私密线程校验、`make_event/validate_event` 的冻结公开形状、既有 terminal 单份真实提交核对和 reader 的 error tag。不能弱化来源撤销、lease、owner/subject/thread、最终提交或隐私正文清除；不改 Schema、抽样/评分、前端、模块源、P5b、B1 固定 b9。

## Progress

- [x] (2026-10-21 09:38 +08:00) 只读新工作树精确头和现有真实事件/事务调用；发现两处 INSERT 与仅 error 的 mj_run 通知。
- [x] (2026-10-21 09:40 +08:00) root 批准最小范围：统一落库/通知、内部可选 operation_key；生产稳定接点只限 started 与 reader terminal error。
- [x] (2026-10-21 09:44 +08:00) 新增统一事件仓储与最小 RuntimeEvents/RunEventReader 委托，保存全部普通事件。首组63 passed/11.16s，包括18新目标、4旧回放、41冻结契约。
- [x] (2026-10-21 09:46 +08:00) 新增真实同epoch过期lease→重新claim反例；第二组41 passed/24.34s，包括全部19新目标、4旧回放、7实际Runtime、9无痕Runtime、2 inbox Runtime，0fail/error/skip。
- [x] (2026-10-21 09:47 +08:00) Ruff E/F/I/B/UP/SIM、120列格式、≤400/60尺寸、diff检查通过；写真实证据，测试进程已退出，10:00宽门不占窄槽。
- [ ] root 审查/提交/推送与组合CI；本片不自行提交。M2–M6与公开稳定分片身份仍待后续。

## Surprises & Discoveries

普通 RuntimeEvents._append 没有通知，reader._error 有单独通知和第二套 seq/INSERT。AgentFinalizer 安全事务只提交助手消息与 result，final/asked/options 由之后 RuntimeEvents 或 reader 修复；本片不移动信封提交边界，也不宣称终态事件和最终消息已在同一事务。

RuntimeEvents.send 当前没有稳定 operation 参数；ToolBatch 在 Journal.step 分配前发 tool_call，text_delta 只有文本，没有可信 model step/chunk offset。不能用实例计数器、事件 kind 或正文 hash 假装跨进程/崩溃稳定身份。started 可由 run/epoch 绑定；reader error 有 attempts/epoch/status 固定诊断 tag。其余仍为普通追加且全部保留，同事务通知，但恢复去重留后续。

模块 PgEventStore 的协议顺序已明确 lock/assert→find operation→allocate→row/ledger→notify→commit；模块本身不连接 PG。此片依其字段/事务约定实现真实仓储接点，未导入模块之前不能称模块集成通过。未来引入必须由 root 普通集成保留来源。

实际两组证明独立 LISTEN 在外层 owner 事务提交之前收不到通知；回滚同时移除 row/operation/notify。真实过期lease后重新claim仍复用原started seq/ts，旧token拒绝发片。JUnit原始timestamp是`+01:00`，安全runner另以显式UTC+08记录起止；不能把JUnit本机时区标签当北京时间。测试运行TZ配置为Asia/Tokyo，事件序列化仍固定+08。

## Decision Log

2026-10-21 09:40 / root批准：新 `repositories/run_event_log.py` 统一 INSERT 与唯一 mj_run 通知；应用层维持当前授权/租约/terminal 权威判定，小改 RuntimeEvents/RunEventReader 委托。operation_key 仅内部显式可信标识，不允许公开 HTTP/模型字段直接传入；kind/text 不作稳定身份。

2026-10-21 09:40 / root批准：started 使用 run/epoch，reader terminal error 使用 run/epoch/尝试/状态和固定诊断版本；status、options、asked、final 与 text_delta 不擅自推断单次。旧终态单份核验/错误 tag 幂等仍保留；有账本但原事件缺失/正文已清的显式操作拒绝恢复，不重造正文。

2026-10-21 09:40 / Codex：保留全部普通 delta；暂不做 40字/150ms 合并、hub、LISTEN lifespan、清理或游标迁移。窄测试使用真实隔离 PG 的独立 LISTEN 连接，观察事务提交/回滚而非 mock notify。没有新依赖；凭据清空/追踪关闭，0模型/服务器/飞书。

2026-10-21 09:47 / Codex：把原非终态 `_leased + epoch` 委托既有 Journal._leased，保留租约/epoch并补其owner别名、subject、取消、期限与runtime门；另核当前thread身份和assert_thread。未做全面版本自愈或移除来源撤销。实际Runtime/无痕/inbox目标均通过；没有改旧测试断言。显式操作原件缺失/正文清空时拒绝重建，普通无key片仍分别追加。

## Outcomes & Retrospective

M1最小片已实现并通过真实PG通知窄组：首组63/11.16s，增加真实同epoch重领后第二组41/24.34s；两组重叠，不相加。最终新目标19/19；0fail/error/skip。生产三文件从首组后未改；Schema原字节不变。M1只解决通知原子性和两个可证稳定接点，不等于所有普通事件恢复去重、跨进程SSE、首字指标、旧DOM、X08、24h清理或P4验收。P3 X03、旧DOM、真实encoder与组合门继续保留。无模型/飞书/服务器请求，未合并或部署。

## Plan of Work

仓储新增 `append_event(repo, connection, run, kind, payload, *, operation_key=None)`，在已有受信 owner/run 事务中分配 seq、构造冻结事件、写 row、可选写仅包含 fingerprint/seq 的 core_operations 记录、调用 pg_notify('mj_run', run_id+':'+seq)。稳定 key 命名空间绑定 owner/run/epoch；重放核原 payload 和原 event row，返回原事件、不通知；内容冲突、空 payload 或原 row 缺失拒绝。

RuntimeEvents 的非终态使用实际 Journal 租约/epoch/取消/期限与 thread 范围；terminal 保留已提交 result 精确核验。started 内部给稳定 key，其余默认无 key。RunEventReader error 保留原 usage tag，并委托同一 append；首次排队通知与 row/tag 一同 commit，重复 error 不再排通知。

拟改文件仅新增仓储 `mingjing_core/repositories/run_event_log.py`、小改 `application/agent_runtime_events.py` 与 `application/run_event_read.py`，新独占 `tests/v4/streaming_integration/test_event_notify_pg.py`、必要新测试支持、此计划和 `docs/v4/evidence/P4/2026-10-21-event-notify.md`。不改 finalizer/LoopCycle/ToolBatch/inbox/dispatcher/模块/Schema。若实际检查需要扩大，先报告 root。

## Concrete Steps

确认独占目录/新随机 schema 后，用现有 P2 Core Python 与只指向本机可丢弃 PG 的 CORE_TEST_DSN，清供应商/飞书凭据、关闭追踪；本片至多一个窄 pytest：

    ../zhiming-v4-p2/.venv-core/Scripts/python.exe -m pytest tests/v4/streaming_integration/test_event_notify_pg.py tests/v4/agent/test_run_event_replay_pg.py tests/v4/agent/test_public_events_contract.py -q

Ruff 用既有主树解释器，规则 E/F/I/B/UP/SIM、120 列，新文件≤400行、函数≤60行；不安装依赖。10:00 宽回归时让位；没有整库、真实供应商或服务器测试。

## Validation and Acceptance

真实 LISTEN 连接必须观察：事务内无通知、commit 后仅一条且 row 已可读；rollback 后无 row/operation/notify；同稳定 key 同内容返回原 seq/ts 且第二次无通知；同 key 异内容整事务拒绝。无 key 的重复正文必须仍分别追加，不能偷偷删采样。双连接同 owner/run 序号不冲突；错 owner/subject/thread/epoch/lease、取消/撤销不能新增正文事件。terminal 修复与 error 重放旧目标保持原断言。

冻结 Schema/序列化原文不变；F03/F04 来源撤销/区间清理、X04取消、X08重连是后续组合门，不由本片 LISTEN 测试冒充通过。终态 error 只用实际状态和固定诊断，不输出供应商异常/正文。

## Idempotence and Recovery

无 key 仍追加；稳定 key 查重在同 owner/run 锁内，与 row/operation/notify 原子提交。异常整事务回滚，不重试网络或业务工具；事务外 callback 不授予发布权。隐私清空事件正文后不从账本恢复正文；后续24h清理需墓碑方案，当前不执行删除。

## Artifacts and Notes

只留合成计数、时间、精确源码/Schema/log摘要，不入真实正文/DSN/口令。原 P4 总计划保持历史只读事实；新实施以本计划四活节更新，不将稍后结果回填旧09:13时间。root负责提交/推送与CI，子任务不改分支引用。

首组私有产物`private/safe-narrow-18ab609fdc92497199807a092496cfcf`；第二组`private/safe-narrow-43963887e2ea4710a4df4cd964e87a19`，JUnit9310 bytes/SHA256 `e461f5293c59f8daa79e0b0e854d099f843b566515d8403cb4365c4d00b7a3d0`。详细安全计数/摘要及AGENTS§11切片回执在`docs/v4/evidence/P4/2026-10-21-event-notify.md`，不把私有原始文件提交Git。

## Interfaces and Dependencies

新增内部可选 operation_key，现有 send(kind,payload) 调用仍兼容；Schema和wire不增加键。复用 core_operations 而非新表；核心字段按模块 EventColumns/Transaction 约定，模块源码和 EventStore公开接口均不动。通知 channel 仅 mj_run，不混 dispatcher 的 mj_run_queued/mj_run_cancel。

## 修订记录

- 2026-10-21 09:40 +08:00：新树只读盘点后按 root 最小范围创建，明确两个稳定接点及其他普通事件追加/恢复去重未完成；开始前无代码/测试。
- 2026-10-21 09:47 +08:00：记录实际63与41两组窄验证及真实租约重领/通知原子性，保留重叠与P3/P4未完边界，冻结交root。
