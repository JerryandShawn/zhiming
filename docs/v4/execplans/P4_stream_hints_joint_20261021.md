# P4：timer、事件提示与真实HTTP联合候选

遵循`.agent/PLANS.md`，四活节持续更新，记录均为北京时间UTC+08。工作树`C:/Users/Administrator/Documents/Codex/zhiming-v4-p3-wire-p4`，M2b提交`8c35aff322c4c4860eeb2ae5b67e01169589815b`/tree`a92c9843`。仅新增测试/helper/计划/证据，不修改生产或当前游标代理文件。候选默认关，不代表完整P4验收、发布或真实供应商ready。

## Purpose / Context and Orientation

把已分别通过的timer和事件提示候选同时启用，观察真实PG、真实Uvicorn SSE是否及时交付不足40字的静默片段；再用真实HTTP取消，确认旧worker/连接结束且不会晚到final。复用`create_app(event_hints=True)`、`AgentRuntime(streaming_candidate=True)`、实际RuntimeAssembly/RunSignals/dispatcher、原local_app、quiet_server、原SSE frame/decoded工具。生产EventReader/游标/Schema语义不改，首红只报根因。

同进程用assembly.signals.controls，HTTP取消必须穿过实际路由/信号/quiet socket；跨进程父app以agent=None仅作reader，run先由已装agent服务实际submit，child独占execute。跨进程不是父dispatcher门，不能混报。供应商只用127.0.0.1标准库quiet HTTP fixture，OpenAICompat直连transport、重试0、offline合成meter；所有client显式trust_env=False，清代理/供应商/追踪。

## Progress

- [x] (2026-10-21 10:41 +08:00) 完整只读现M3 HTTP helper/真实quiet dispatcher测试、assembly/路由/reader/lifespan；向root交具体3门与新文件清单。
- [x] (2026-10-21 10:43 +08:00) root批准只新增3个测试/helper源与本计划/evidence，单窄槽、11:00前暂停新pytest。
- [x] (2026-10-21 10:46 +08:00) 同进程双开关首次1/1通过；全3门首轮1过2红，跨进程首delta超时，取消人为5秒fallback下终态超时。保留原日志。
- [x] (2026-10-21 10:48 +08:00) root批准取消用例恢复受信默认150ms fallback，保留<2s/状态/资源/无迟到断言并通过；跨进程在quiet.started已到后仍首delta超时，根因未实证。
- [x] (2026-10-21 10:50 +08:00) 只新增冷启动分离/安全phase诊断，跨进程单例1/1通过；最终3/3通过7.22s，0fail/error/skip。但旧间歇超时未被一次绿关闭，不改生产、阈值、xfail或旧断言。
- [x] (2026-10-21 10:50 +08:00) 释放窄槽，不再启动pytest，保留11点窗口；Ruff/format/AST/400-60/diff静态检查通过。
- [ ] root审查小提交；不部署、不合并。

## Surprises & Discoveries

真实create_app lifespan会自动从RuntimeAssembly启动dispatcher；跨进程若父同样有agent会抢run。因此父reader明确agent=None，而child运行真实新Runtime。原quiet HTTP端口首片不足40字、尾由父gate释放；同进程port在真正HTTP连接前等SSE进入等待，避免把已在PG的首次快照当LISTEN唤醒证明。

M3 listener独立连接不是pool借用，资源门分别核本次actor.done/线程对象、pool requests_waiting/available与listener/订阅归零，不停共享PG、不结束他人进程。只延长Subscription.wait回退到5秒证明真实通知唤醒，不能靠150ms轮询凑绿。

10:46首轮人为把取消的fallback也拉到5秒，PG已cancelled但终态HTTP读超时。现cancelled状态转换只通知mj_run_cancel供dispatcher，未主动通知事件mj_run，reader需要默认150ms回读生成终态error；因此5秒注入不是受信实际取消配置。该通知差额仍未实现；经root批准只把取消目标恢复默认150ms，2秒与其余断言不变，生产0改。

跨进程两次首delta读超时分别在10:46与10:48；第二次quiet.started的前置断言已过。后来加安全phase/源码帧诊断及分离-I冷启动后，单例及完整3门都绿，但不能推断两次旧超时已归因冷启动。旧失败没有保留child安全stdout或PG首delta快照，精确缺失观测列于evidence；间歇根因仍待root只读定位。

## Decision Log

2026-10-21 10:43 / root：只新增`test_stream_hints_joint_http_pg.py`、`stream_joint_http_support.py`、`stream_joint_process.py`和计划/最终evidence。真实生产源码0改；系统代理禁用。子进程stdin先核loopback test库/随机schema/固定owner及provider URL，再连接；白名单OS环境、-I/-B/null pycache prefix，stdout仅安全计数，异常不含DSN或正文。

2026-10-21 10:43 / root：本线与其他线全机最多4测试链，本片只有一个窄位。11:00前停止启动pytest，未完则记录断点，不为全绿改游标或其他生产。

2026-10-21 10:48 / root：delta门继续用5秒fallback证明mj_run唤醒；取消按受信默认150ms验证<2秒，而非注入5秒下强求<2。原5秒首红/未主动终态通知差额保留，不修生产凑绿。

2026-10-21 10:51 / root：按真实3/3与未实证历史间歇收口冻结，不再pytest；11点不可变P4候选可以不含这片，不以一次绿关闭缺口，不xfail/skip/删历史。

## Outcomes & Retrospective

联合明确目标最新3/3通过7.22s，验证真实双开关、跨进程原Runtime与重连、默认150ms回读下HTTP取消<2秒/资源归还/无迟到；生产源码0改。首轮1过2红、次轮1过1红保留，跨进程旧超时缺少诊断、根因未实证，不能宣组合稳定或完整P4。证据`docs/v4/evidence/P4/2026-10-21-stream-hints-joint.md`列可用时点与未采集数据。P3 X03、旧DOM、encoder、B1 No-Go及完整P4门保留。

## Plan of Work / Validation and Acceptance

第一门：真实HTTP创建life线程与消息、真实dispatcher执行；Subscription.wait先进入5秒通知等待才放开本地provider连接。SSE收到started/status后看到首个不足40字delta，此时quiet HTTP尾未释放；核实际PG同seq/body与通知计数，随后放尾得到严格core4 final。

第二门：父reader app启用event_hints、无agent；child清环境后实际执行同一run，在quiet provider静默期间经PG NOTIFY唤醒父HTTP。收到delta后断线，携真实Last-Event-ID重连；释放尾后final，前后seq无重复、与PG全集一致，物理请求只有一次。child仅本次进程可终止，stdin不落盘/不回显凭据。

第三门：实际POST /api/runs/{id}/cancel，计时至PGcancelled与SSE结束<2秒；原quiet socket port finally结束、本次actor.done、pool连接归还、0final。随后释放provider尾，确认事件高水位无迟到delta/final；HTTP/应用lifespan退订并关闭listener。对应X04取消、X08断线/游标边界，不修改原场景断言。

第三门使用实际默认150ms fallback，前两门才延长到5秒。子进程启动等待与提交后通知读取分离，但最终通过并未证明旧间歇的原因；不继续拉大读超时或循环重试。

## Concrete Steps / Recovery

root安全runner、既有P2 Python/隔离PG、TZTokyo。明确新文件单目标串行跑，不跑目录全量；11:00前暂停。每个本地server/client/process用有界finally清理，不改数据库服务或生产。全部合成记录在随机schema，原p2_repo清理流程沿用。失败保留原日志，先报告root，不自动修生产。

## Artifacts / Interfaces / Dependencies

拟证据`docs/v4/evidence/P4/2026-10-21-stream-hints-joint.md`。只有测试内部接口，新增依赖/迁移/API/公共Schema0；真实模型/服务器/飞书0。不以mock连接/ASGI TestClient代替真实socket，不声称网络黑洞或任意callback可强制取消。

## 修订记录

- 2026-10-21 10:43 +08:00：root批准联合只新增测试后建计划，固定同/跨进程装配、3门、代理/凭据边界、资源归还与11点暂停规则。
- 2026-10-21 10:51 +08:00：记录首次/次轮失败、默认取消配置的受审修正、最新3/3与历史间歇未归因；冻结前列缺失时点，不继续pytest或修生产。
