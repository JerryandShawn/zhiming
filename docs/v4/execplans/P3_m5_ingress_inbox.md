# P3 M5：持久线程入站、运行中补充与飞书合并

本ExecPlan遵循.agent/PLANS.md。工作树C:/Users/Administrator/Documents/Codex/zhiming-v4，分支v4/p3-agent-runtime。root独占ThreadService/Runtime/Loop/context，M7代理独占dispatcher/postgres；本子范围独占新增application/thread_ingress.py、thread_queue.py、thread_inbox*.py、feishu_ingress*.py与adapters/feishu_gateway.py及新测试。真实供应商、服务器、飞书0，不自行提交。

## Purpose / Big Picture

消息先成为不可替换的用户原话和持久队列，再由独立worker处理。运行中补充可以在下一模型迭代被证实采用，不能采用或执行失败时落到下一轮，不能丢失。飞书同一绑定用户/私聊/线程的消息在固定2.5秒窗口内合成一个运行，原话分别保留时间与quote映射；网关不直接consult。

## Progress

- [x] (2026-10-21 00:17 +08:00) 读ThreadService、Runtime、Context边界、真实FeishuGateway与队列/NOTIFY调用方，确认并行文件归属与接口。
- [x] (2026-10-21 00:39 +08:00) 持久inbox/可信owner runtime/原子排队与幂等，原话与入队字段同事务，NOTIFY只在提交后可见。
- [x] (2026-10-21 00:39 +08:00) before_model claim/ack真实请求与最终assistant双重证明、同epoch新lease重领/恢复ack、100来源上限及失败下一轮恢复。
- [x] (2026-10-21 00:39 +08:00) 飞书固定2500ms持久窗口、原话时间/native ID/多源区间、边界另批/重启/去重，网关仅buffer/queue与既有outbox，不consult。
- [x] 真实隔离PG最终35 passed/18.68s，旧飞书8项原保护迁移与静态/证据完成；代码冻结交root，完整阶段/CI另核。

## Surprises & Discoveries

2026-10-21 00:39 +08:00 / 旧网关测试的同步handle立即生成与新设计冲突，明确改成buffer/queued后由测试外部合成worker执行，保留exact正文、一次模型执行、一次outbox、送达不明不重发、原话删除拒重导等全部原保护。导入test_dsn改别名，避免pytest把helper错收成返回str的“测试”，没有删除数据库检查。初轮31通过/1删除重导异常类型失败，root已修ThreadService先核撤销。新v4 E2E初次直接赋service.runtime被新受信assembly正确拒绝，改为constructor显式agent_runtime注入后通过，不绕计量/缺依赖门。

现FeishuGateway.accept立即submit且_process直接consult，不符合新队列分工。原Context强制当前消息为线程最新user，会拒绝正常排队较早轮次；root正在新增受信run_context旧边界。ThreadService原缺外部时间/native source_id与重复不touch，root已按本接口请求补齐。core_runs.status无枚举约束，故inbox_wait可作候选内部待采用态，不加迁移。

## Decision Log

2026-10-21 00:39 +08:00 / root澄清：after_model是“已决定终轮”的cutoff，不是每次模型完成后无条件defer。模型I/O期间补充若当前返回工具且还有正常下一迭代，可在下一before_model采用；已结束正文/ask/进入critic纯文本revision才defer到下一轮。工具事件注入与终轮I/O迟到各有真实ScriptedRuntime测试。

2026-10-21 00:17 +08:00 / root裁定：runtime只从core_owners.settings.runtime=v3|v4取，默认v3，不接受前端runtime布尔，不发明subject映射。新行仍经既有queue_run业务校验/预算/通知，在同owner事务追加runtime/thread/lane/request/incognito；只有提交后NOTIFY可见。重复operation固定旧runtime，不因开关变化偷换。

运行中输入先有inbox_wait fallback。ack只能引用真实completed模型步骤及请求快照，不代表已发布；recover须再核最终提交包含该补充source版本和助手血缘，成功才取消fallback。未采用/失败/取消/旧epoch保留下一轮，重复recover无重复通知。after_model到达仅下一轮，不篡改已发请求。

## Outcomes & Retrospective

组件与真实Runtime/Loop/outbox最终同组35 passed/18.68s，0skip、0warning；证据为docs/v4/evidence/P3/2026-10-21-m5-ingress.md。没有真实外部调用/部署/合并，完整阶段与CI不在本组件结论内。

## Context and Orientation

复用application/threads.py:create/receive/get/history、application/consultation.py:submit、repositories/postgres.py:queue_run/transaction/_leased、repositories/dispatch_hooks.py:notify_run、MemoryService.get_source的撤销投影。复用Journal/RequestLedger实际模型请求快照与AgentFinalizer提交后assistant.source_ids。不能改变owner/subject/thread、原话不可替换、当前lease/epoch、撤销防复活、outbox不重发和固定塔罗。

## Plan of Work

先实现受信Ingress/queue与持久inbox，再实现claim/ack证明与回退，最后飞书合并与网关接线。每片只跑本机真实PG和替身I/O，根代理统一测试/提交/推送。新增文件400行内、函数60行内；需要拆分时按队列、证明、聚合职责拆。

## Concrete Steps

    python -m pytest -q tests/v4/agent/test_thread_inbox_pg.py tests/v4/agent/test_feishu_ingress_pg.py
    python -m pytest -q tests/test_core_feishu_gateway.py
    ruff check --select E,F,I,B,UP,SIM --line-length 120 <owned files>

## Validation and Acceptance

对应X03/X05/X07：真实PG不同owner/subject/thread不能读或claim；重放同消息不新增/改文、不延长无痕TTL；运行中插话在真实模型请求证明+成功提交后才吞并fallback，其他情况下一轮；飞书2500ms前不排队、边界后另batch、重启可flush、不同私聊/作者不合并，所有send仅替身。

## Idempotence and Recovery

入站native ID、inbox ID、batch首事件ID和run operation稳定；不覆盖原话/既有运行时。事务回滚不留下半个run或通知；进程停止后未采用fallback保持inbox_wait并由recover判定。没有迁移/删库/服务器操作；回滚代码不得抹除已收原话，保留候选内部态供人工/恢复入口处理。

## Interfaces and Dependencies

ThreadIngress.receive/submit/queue/history可注入service、Clock。ThreadInbox.claim(run,phase,iteration)、ack(run,claim,model_seq)、defer/run、recover(owner)为受信Runtime接口，不由模型参数授权。多源request含source_message_id最新一条、source_message_ids全部、source_segments逐条message_id/version/start/end；不存拼接伪原话。依赖现有psycopg/httpx/Clock，无新增依赖。

## Artifacts and Notes

证据预定docs/v4/evidence/P3/2026-10-21-m5-ingress.md。未验证项包含完整Runtime接线、生产入口/真实供应商/真实飞书与CI。

## 修订记录

- 2026-10-21 00:17 +08:00 创建，记录实际代码与root/M7边界。

- 2026-10-21 00:39 +08:00 实现持久组件/飞书网关并完成实际PG/ScriptedRuntime/共享outbox窄目标，待最终同组结果及root发布。
