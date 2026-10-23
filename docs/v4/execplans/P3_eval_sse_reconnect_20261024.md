# P3：离线真实 SSE 中断与续接驱动

本 ExecPlan 遵循 `.agent/PLANS.md`，四个活文档段落持续维护。所有记录为北京时间。

## Purpose / Big Picture

原 X08 在评测动作入口被拒绝，尚未调用已有 P3 的事件 HTTP 接口。本片只补离线评测驱动：真实运行中收到第一个正文片段后关闭回环 HTTP 连接，再以实际数值 Last-Event-ID 续接。运行时、事件契约、前端及延期 P4 均不改；原题、controls、expect 与契约哈希保持。原正式 f18 的 69/81 报告保留，局部证据不代替完整门。

## Context and Orientation

工作树 `C:/Users/Administrator/Documents/Codex/zhiming-v4-eval-resume`，分支 `v4/p3-wire-sse-reconnect-20261024`，起点正式 `d40fcd3`。复用 `mingjing_core/adapters/thread_routes.py:event_routes`、`thread_events.py:event_response`、`application/run_event_read.py:RunEventReader`、`agent_runtime.py:AgentRuntime` 与真实隔离 PG。只允许修改 `tools/eval/targets/`、必要新离线测试和本计划；不写生产文件、gold、场景、旧报告，不启用 P4/P6/P7，不发真实模型、飞书或服务器请求。

## Progress

- [x] (2026-10-24 04:45 +08:00) 只读核对原 X08、正式驱动及 P3 事件链；执行计划先于实现写入。
- [x] (2026-10-24 04:50 +08:00) 静态实现离线分片、真实回环 HTTP 驱动与全帧观察校验；Ruff/AST 通过，交主线审核，尚无 pytest/collect。
- [x] 主线授槽后只执行六节点首链及失败的一节点必要复验；未全量或重复旧五绿。
- [x] (2026-10-24 04:52 +08:00) 唯一首链 5 passed /1 failed /1 warning，1.94 秒；原题真实 HTTP 正例在 uvicorn 平台探测被新夹具子进程护栏拒绝，尚未触达 producer/SSE。旧五绿不重复。
- [x] (2026-10-24 04:54 +08:00) 按主线批准仅在新夹具安装护栏前预热真实标准库平台缓存；唯一失败节点复验 1 passed /1.95 秒，原题真实 running 断开及 HTTP/PG 全帧比较通过。

## Surprises & Discoveries

原 X08 只有一个模型 text 动作，旧 ScriptedModelPort 只产生一个文本片段；不能把持久事件事后拆成两个。现 P3 已提供真实数值 seq 的重读接口；原 gold 使用抽象 event-N、text.delta 与 run.completed，需要受控表示映射而非改变生产契约。原 L02/X02/X06 分别仍缺真实跨模型报告、与单会员首发冲突的跨供应商策略、延期 lint 来源，继续待决，本片不处理。

首链已实际创建/领取隔离 PG 请求并绑定本机随机 socket，但 uvicorn startup 的 platform.system→uname→Windows 版本只读查询触发子进程护栏；producer 尚未启动，因此不能据此判断 chunk 是否合并或重连是否正确。原日志保留在 `private/safe-narrow-56b1dfd5fd7c43cc86690c9255ee30b9/`。

仅失败节点复验于 04:53:53–04:53:56 +08:00 通过，证据保留 `private/safe-narrow-157e80bc50e64783825324fc28c4358f/` 的 metadata、pytest.log、pytest.xml。真实运行时确实分别持久化两个 delta，断开时仍 running；初次与续接所有 HTTP 帧按原生 seq/全帧摘要与 PG 完整序列相等。无须修改生产或启用 P4。

## Decision Log

2026-10-24 04:45 +08:00 / root 已批准普通离线评测表示映射：原生 text_delta→text.delta、final→run.completed；event-N 仅由本次真实相关 seq 顺序映射。全部原生 HTTP/PG ID 另保留无正文证明，校验所有帧的顺序、游标、完整性与唯一性，不能隐藏额外同类事件。仅离线模型输出可将原文本分为两块，由真实运行时产生两个持久 delta；若运行时合并，记录阻塞而不改产品或造事件。模型 barrier 只控制离线 producer 时间，不预写事件。

2026-10-24 04:53 +08:00 / root 批准只修新夹具：在安装 subprocess 拒绝护栏前调用真实 platform.uname 预热标准库缓存，保留实际平台值，不 monkeypatch 平台、不放行任意子进程/HTTP。只复验一红，五项旧绿不重复。

2026-10-24 04:54 +08:00 / 原题评分、controls、expect、contract hash 和旧报告均未改。六项行为的通过证据是首轮五绿加单独一红复验一绿，不能描述为同次 6/6 或完整 81 题门通过。此片只证明离线 P3 SSE 驱动，生产/P4能力与真实模型质量不扩大。

## Plan of Work

新增独立 SSE helper，借实际 P3 路由在随机回环端口运行；不启动后台 dispatcher，由单个受控运行线程执行已领取的真实请求。ScriptedModelPort 仅在明确的离线 text_chunks 输出中逐块发出，旧动作不变；新驱动内部 overlay 只从原 text 生成，不能读取 expect 或脚本 db/event。第一片持久并被 HTTP 客户端收到时 producer 停在 barrier，关闭连接后核真实 running 状态与第一片序列，再释放 producer 并用真实 Last-Event-ID 重连。最终逐帧比较 HTTP 与 PG 全量持久序列后才生成抽象观察。

## Validation and Acceptance

对应 `docs/v4/07_评测场景集.md` X08。拟不超过六项必要行为：原题契约不变且真实断线续接通过；旧模型 text/tool 行为及严格 chunk 输出边界；重复帧拒绝；缺帧或游标漂移拒绝；额外同类事件全部保留而非隐藏；错 owner/run 的真实观察拒绝。只用隔离 PG、真实回环 HTTP 与 ScriptedProvider，测试时区 Tokyo。先静态审阅再由主线授槽，无全量复跑。

## Idempotence and Recovery

每次评测沿 V4Target 新建随机 schema，HTTP 只绑定 127.0.0.1 随机端口。异常释放 producer barrier 并停止自有 HTTP 线程，不重试模型、不改既有生产状态。失败保留测试原输出，不能修补旧报告或从 gold 构造通过状态。

## Interfaces and Dependencies

复用已锁 FastAPI、uvicorn、httpx、psycopg，无依赖或锁文件变化。新 helper 仅接实际 target 和不含 expect 的 turn；返回 TurnResult 及无正文 stream proof，供 inspect_db/case_evidence 读取。公开产品 API 和 DB schema 不变。text_chunks 仅是离线 ScriptedProvider 内部输出，可验证与同动作 text 完整拼接一致，禁止混入 DB/event/receipt/proof。

## Concrete Steps

在上述工作树先执行指定新增/修改路径的 Ruff 和 AST 静态检查。经主线审核授槽后，使用既有 safe-narrow runner 与真实 Core/K3 环境运行明确节点，记录同份 JUnit 数字，不新增第二套证据或宽回归。

## Outcomes & Retrospective

六项必要行为按“首链五通过、一夹具失败；仅失败节点复验一通过”完成。原 X08 契约现经真实隔离 PG、运行中的回环 HTTP 中断/续接及真实数值 Last-Event-ID 验证；全部原生帧比较通过，额外同类帧不被隐藏。无正文 stream proof 由 inspect_db/case_evidence 提供，未复制额外报告。新增 helper 分别 80/70/142 行，最长函数 36 行；Ruff/format/AST 通过。没有跑完整 81 题或改写旧正式报告，真实模型请求、外发、服务器操作均为零。冻结八路径交主线提交。

## 修订记录

2026-10-24 04:45 +08:00 创建：按已批准的离线 P3 SSE 接缝限定实现和证据边界。
2026-10-24 04:50 +08:00 静态实现冻结：保留全量原生帧的 ID/种类/摘要及实际切断时 running 状态；六节点先交审，不启动测试。
2026-10-24 04:53 +08:00 如实记录首链五绿一红与未触达边界；按主线批准仅修新夹具平台缓存，禁止重跑旧绿或修改原模型/HTTP实现。
2026-10-24 04:54 +08:00 记录一红复验一绿与实际 HTTP/PG 边界；六行为分轮有据，不冒称同次全绿、生产或全题库放行。
