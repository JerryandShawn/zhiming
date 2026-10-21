# P4：在集成候选上接通冻结 v1 事件流

本 ExecPlan 遵循 `.agent/PLANS.md`。Progress、Surprises & Discoveries、Decision Log、Outcomes & Retrospective 四节持续更新。所有记录使用北京时间（Asia/Shanghai，UTC+08）。**本片只有计划，未实现 P4、未运行测试、未合并或部署。**

## Purpose / Big Picture（目的与全局）

用户应在模型开始后 1 秒内看到状态、3 秒内看到首字；断线后继续看到同一条真实运行，文本不丢失、不重复。网页应能订阅其他进程执行的同 owner 运行，停止按钮仍在真实本机 HTTP 下 2 秒内关闭生成流。完成后保留安全提交的最终消息，按提交时刻清理中间文本；撤销和无痕关闭优先于任何缓存、补发或恢复。

本计划依据大脑交付 `05_Codex提示词/P4_真流式.md`、28 号第三节冻结 v1、33 号一§3；原 P4 提示词要求 P3 已合并与独立 `v4/p4-streaming`，本周用户指定的 33 号改为在 `v4/integration` 或其子分支集成，且禁止合入 `v4/main` / `main`。P3 未验收的 X03、旧 DOM 回执和真实 K3 encoder 不会因创建本计划而消失。

## Context and Orientation（背景与定位）

计划写入工作树 `C:/Users/Administrator/Documents/Codex/zhiming-v4-p3-wire-p1b`，分支 `v4/p3-wire-p1b-20261021`，固定已提交头 `5b691475c41791b4df2166db96dd3db54cc78d2b`。该树正在由 root 从 archive 做完整回归，本片不改代码、不运行测试，也不把未提交的 `docs/v4/evidence/P3_wire/2026-10-21-0900-*` 报告当作通过。后续实现须从 root 审过的集成头另开子分支，建议名称 `v4/p3-wire-p4-20261021`，本片没有创建它。

只读模块来源为本机已有 `origin/v4/mod-organize@ebfa22f8f7c59e486c6632035ae6bc8307f0f438`。已完整核对原四份 Q1 整理、Q2 校验、Q3 主动规则、Q4 卡片接线说明，以及新索引和 `Q3_sse_20261021.md`；没有 fetch、联系其他聊天或修改他线。原四份说明仍区分纯模块、真实 PG 接线和真实送达，P4 不借用其纯测试宣称运行时完成。

复用现有函数与不可改变的行为：

| 位置（本次固定头） | 已有真实边界 / P4 的用途 |
|---|---|
| `agent/events.py::make_event / validate_event / encode_sse / heartbeat` | 冻结 wire 类型与 SSE 编码；公共字段不可由模型覆盖，中文安全错误，心跳为注释 |
| `application/agent_runtime_events.py:56 RuntimeEvents.send` | 当前 lease / epoch 校验、事件先落库后 callback；已提交 final / asked / options 核对与幂等复用 |
| `application/agent_runtime.py:115 _start`、`:128 _finish`，`agent/loop_cycle.py:170 _text_delta` | 实际 started / status、模型分片、工具与修订事件、最终安全提交；接合并器而不新增模型请求 |
| `application/agent_finalization.py:108 finalize` | owner / subject / lease / epoch / 依赖撤销 / 真实回执 / core4 提交闸门；不能为流式弱化 |
| `application/run_event_read.py:29 authority`、`:38 validate_cursor`、`:51 ensure_terminal`、`:107 page` | 按 owner/run 回读、终态缺事件幂等修复、撤销清空正文不重建；升级补发而不并行造另一读端 |
| `adapters/thread_events.py:17 event_response`、`thread_routes.py::event_routes` | 已认证 SSE 入口、Last-Event-ID、响应防缓存/缓冲头；改为订阅加持久补足 |
| `adapters/web.py:179 stream`、`/api/chat`、`:408 tarot readings` | v3 旧 SSE 与 v4 当前桥接、旧页面兼容和固定牌阵读取的接点 |
| `application/dispatcher_cancellation.py::request / finish`，`agent/loop_policy.py::RunControl` | PG 取消标记、关闭静默 HTTP、合法 interrupted 消息与来源撤销；不能由断线隐式取消 |
| `application/privacy_maintenance.py`、`maintenance_schedule.py`、`private_retention.py`、`repositories/privacy_foundation.py` | 现有 30 天步骤清理、无痕/撤销级联；接 P4 增量清理，保持原正文清除边界 |

模块线的 `streaming` 是纯模块：`DeltaBuffer / feed_delta / poll_delta / flush_delta / replace_text`、`PgEventStore`、`EventTransaction / TransactionFactory`、`parse_last_event_id / replay_after_header`、`text_projection.reduce_event`、`heartbeat_tick`、`CommittedRun / plan_delta_cleanup`。`PgEventStore` 不自行连接数据库；`plan_delta_cleanup` 不执行删除；MemoryEventStore 不能替代真实 PG。

## Progress（进度）

- [x] (2026-10-21 09:13 +08:00) 只读固定接线头、P4 原提示词、28 号冻结 v1、33 号主线 §3、蓝图 §3.4/§9/§16、07 号 X/F 场景与模块线四份旧说明/新 SSE 指南。
- [x] (2026-10-21 09:13 +08:00) 核对现有 HTTP/落库/取消/隐私路径，确定缺少 hub、事件 mj_run 监听、合并/清理与旧格式桥等实际差额；主线 Schema 与模块线冻结副本原始 SHA 完全相同。
- [x] (2026-10-21 09:17 +08:00) 仅新增本计划，列出最小接线和未来测试门；文档结构/空白检查通过，未执行计划中的测试命令。此时同树出现其他代理的 native fixture WIP，只读状态记录，不纳入本计划或覆写。
- [ ] M0：root 选择已审集成基底、接收模块源并记录完整回归；分配实现子分支与文件所有权。
- [ ] M1：真实 PG EventTransaction、稳定操作账本、提交后 NOTIFY、终态提交元数据与幂等测试。
- [ ] M2：40 字/150ms 合并、独立超时驱动、generation 保护与进程内有界 hub。
- [ ] M3：单进程一个 LISTEN mj_run、无缝补发/跟随、规范游标、15 秒心跳和断线恢复。
- [ ] M4：新 JSON 入队入口、v3 旧格式兼容投影、塔罗固定牌阵事件接线；与前端线交接类型/DOM。
- [ ] M5：提交后 24 小时增量清理、30 天保留、撤销与无痕清理、游标墓碑和恢复视图。
- [ ] M6：慢流/跨进程/三次随机重连/真实 HTTP 取消、X/F 脚本与完整组合回归；如实保留未通过项。

## Surprises & Discoveries（意外发现）

不能沿用“v4 完全没有 SSE/落库”的旧描述。此头 `RuntimeEvents` 已逐事件写真实 `core_run_events`，`RunEventReader` 会修复提交后 final/提问/选项缺口；`thread_events` 已编码冻结 v1、支持 header 游标和 15 秒心跳。它每 150ms 直接查库，没有进程内 hub，也没有跨进程 `LISTEN mj_run`。dispatcher 的 `mj_run_queued / mj_run_cancel` 是另一用途，不能算 P4 事件监听已接通。

`RuntimeEvents._append` 对每个分片立即落库，没有 40 字/150ms 合并，也没有普通事件的事务内 `pg_notify('mj_run', ...)`；当前 terminal error 修复单独有 notify。因此不能把“有一次 error 通知”说成全部事件已通知。终态 final 幂等不能代替各普通事件跨崩溃的稳定 operation 去重。

当前 cursor 只验证 `0 <= after <= 本 run max(seq)`，不验证非零 cursor 是否在当前 owner/run 真正存在；HTTP 查询参数是 `after_seq`，尚无提示词要求的 `after` 别名，`int()` 也接受非规范文本。未来物理清理会产生空洞，不能继续用 max 判断归属。

`/api/chat` 尚无 `Accept: application/json` 的立即 JSON 分支；v4 直接返回冻结 SSE，旧 `static/app.js:475–494` 却只看 data 内的 `type`，忽略 SSE event 头。该页面可在 EOF 后通过状态接口恢复正文，并不证明旧实时格式已兼容。`:288` 还读取 `memory_receipts`，core4 的持久字段是 `receipts`；现有旧 DOM 严格 xfail 不能被计为通过。不得通过给 core4 信封加未冻结字段来掩盖这个缺口。

`/api/threads/{id}/messages` 已返回 202/run/thread/events_url，但未返回提示词要求的 source `message_id`。既有 tarot readings POST 在 owner=v4 时明确拒绝接线，原牌阵被保留；不能将此拒绝包装成已有 v4 解读流。

`core_run_events` 真实列是 `owner/run_id/seq/kind/payload/created_at`，seq 没有 bigserial 默认或 operation_id 列。现有清理只有无痕/来源撤销清正文和 30 天步骤正文；没有提交后 24 小时 text_delta 清理。`core_runs.updated_at` 不是稳定提交时刻，finalizer 也没有持久 `committed_at / final_seq` 证明，必须在提交处补足，不能由清理任务猜测。

## Decision Log（决策记录）

2026-10-21 09:13 / Codex：以 28 号冻结 v1 为唯一公开字段源，保留 `events_v1.schema.json` / `core4_envelope_v1`，不再建立漂移的第二份 `run-events.schema.json`。若原路径需要兼容，只提供同源生成/引用并用等价测试锁定。公共 owner 永不进 wire；owner 来自服务端 X-Token/既有认证或已绑定渠道，通知和模型不能授予 owner 权限。

2026-10-21 09:13 / Codex：先在集成子分支做离线接线，保留 P3 的权威 PG、原安全闸门和最终事件修复。不把前置“P3 已合并”改写成 P3 已验收；本周 33 号允许依赖未好先做本地候选，发布门仍等待 X03、旧 DOM、encoder 与组合回归。仅普通 merge，所有本周分支保持草稿，不合 `v4/main` / `main`。

2026-10-21 09:13 / Codex：取消沿用冻结 v1 的 `error{code:"RUN_CANCELLED", message, retryable:false}` 和独立 `status=interrupted` 助手记录，不向 final 增加提示词旧例中的 `interrupted:true`。取消、撤销和失效 lease 后禁止最终发布；断开 SSE 只取消订阅，不取消运行。

2026-10-21 09:13 / Codex：优先复用现有操作/usage 存储实现仅含 seq/指纹的事件账本和提交/清理元数据；实施前验证唯一键、当前 epoch/generation、撤销和墓碑是否满足协议。若确需新表，先由 root 在集成路线图分配编号（P1b 0008，P5b B 预留 0009，之后按合入顺序 ≥0010），不改已固定 0005–0008，也不把任何新迁移放入 B1 b9 包。

2026-10-21 09:13 / Codex：主线不改 `web/**` 或他线工作树。TS 类型必须从同一 Schema 生成并交前端线入其拥有路径；尚未入库/未真实 DOM 验证就保持该验收项未完成。新旧数据格式适配只在后端兼容层做，不修改持久 core4 或伪造记忆/送达回执。

## Outcomes & Retrospective（结果与复盘）

本片完成可审计划和当前差额盘点，P4 源码实施、测试、TS/DOM、跨进程监听、清理与性能验收全部尚未进行。仅只读 Git/文件/结构比较，没有 pytest、PG、HTTP、模型、飞书或服务器操作。Schema 原始摘要相同只证明契约一致；原模块纯测试、既有本机取消证据和在途 archive 回归均不等于本片通过。阻塞写入后继续其他已授权工作，用户不在线时不等待答复、不启动真实请求。

## Plan of Work（最小接线与里程碑）

### M0：冻结来源、所有权与组合基底

root 先核当前 `v4/integration`、本 wire 的 P1b / socket / case 恢复候选和模块 PR 的精确头及完整回归结果。接收 `streaming/**` 必须通过正常集成过程保留来源，评审模块线其他同名 validation 目录冲突，不能为 SSE 直接覆盖现有 P6/P3。实现后只回集成分支，不回写模块/前端/命理线。本计划不授权实际 merge。

契约公共字段固定 `{v:1,run_id,seq,ts}`，ts 显式 +08，seq 是该 run 递增正整数，重放保留原 seq/ts。12 类型为 started、status、tool_call、tool_result、text_delta、text_reset、memory_receipt、ask_user、present_options、review、final、error；心跳 `: ping\n\n` 不占 seq。final/message_id、asked/options、receipt、review 语义全部沿用现 Schema，不发 reasoning、工具参数/原始结果、供应商异常或私人评审引句。

### M1：实际 PG 适配与提交原子性

新增主线应用/仓储适配器，填充模块 `EventTransaction / TransactionFactory`；不修改模块端口来掩盖真实 PG 缺项。事务顺序为 owner/run 锁 → 当前 subject/thread/lease/epoch/generation 或已提交终态证明 → 精确 operation 查重 → 分 seq → row+仅元数据 operation 账本 → `pg_notify('mj_run', run_id||':'||seq)` → 提交。读回 callback/hub 只能在提交之后执行。失败回滚，通知只是唤醒提示，不能把通知内容当事件正文或授权。

非终态 operation 由受信 run/epoch、Journal step、generation 与真实分片区间生成，模型不能提供；同 key 异内容拒绝。已有 final/asked/options 单份核对保留。新终态建议在 finalizer 的同一安全提交事务保存可信 `committed_at`、message/revision、final event/seq 与账本，之后 callback；当前 `_finish` 的 send 变成幂等回读。旧版本留下的提交/事件缺口仍用 reader 安全修复，但不能把清理墓碑当崩溃缺口重造正文。

拟新增接点为 `application/run_event_store.py`（名称实施时由 root 冻结）；最小修改 `RuntimeEvents` 与 finalizer，只让其委托统一适配器，禁止第二套 seq 分配器。选择 reuse 或新迁移之前先用真实隔离 PG 证明双连接序号/操作唯一性、事务回滚、旧 worker / 跨 owner 拒绝；不做长期持锁的模型或网络调用。

### M2：文本合并、generation 与有界 hub

`LoopCycle._text_delta → RuntimeEvents` 统一委托主线 EventSink，使用模块 coalescer。40 字或从首字起 150ms 达到阈值即落库；必须有独立于下一个模型 chunk 的受控 timer/tick，静默慢流也按时 flush；结束、提问、错误、取消前刷新或按撤销规则丢弃。timer 与模型线程操作同一 run buffer 时用短锁/CAS；不能在持有 PG owner 事务时等待线程或 socket。

`replace_text` 丢旧 buffer、递增 generation，只提交 `reason=revised/resumed`。重复 completed 模型日志不再追加旧流；真实未完成模型重启在新片段前发一次稳定 resumed reset。旧 epoch/lease/generation 的 tick 必须拒绝，不能晚到覆盖新稿。评审修订最多一次，与当前 P6 wire 协调；流中的工具前导文字与终稿可以不同，客户端 reducer 最终以安全提交 envelope.text 收尾。

hub 以 `(repo schema,owner,run_id)` 隔离，执行线程用 `loop.call_soon_threadsafe` 投递到有界 asyncio.Queue，不等待慢消费者。推荐队列承载已提交 seq 的有界唤醒提示，溢出合并为“该 run 有新高水位”，读端从 PG 按 last_seq 补足；不能丢回执/终态，也不能把临时合并文本编造为旧 seq 的新正文。订阅退出必须移除 queue/loop 引用，无痕关闭或来源撤销清理本地 buffer/缓存。

### M3：单 LISTEN 与无缝 SSE 续传

Web lifespan 管理一个独立 autocommit `LISTEN mj_run` 连接并重连，停服可关闭；不占用每订阅者一个连接，也不复用 dispatcher 的取消监听。解析通知从最后一个冒号切分 seq（run_id 本身允许冒号），只当提示；按当前受信 repo/owner/run 查增量。LISTEN 断开/通知丢失用有界周期 PG 补读兜底，不以模型探针恢复。

`event_response` 先认证并核 run/subject/thread，再注册订阅、读取持久高水位、补发和接收后续提示，所有发送以实际 seq 去重。订阅建立/快照/通知之间的竞争必须有交叉测试；分页超过 256/1000 行仍完整，不因已终态过早关闭。规范解析 Last-Event-ID；增加 `after=<seq>` 别名，保留 `after_seq` 兼容，冲突拒绝。非零游标必须归属当前 run 的真实行或受信清理墓碑；unknown/foreign 统一不可用，不用 max 或其他 owner 记录推断。

仅在持久 final/error 被发送后关闭；终态追赶不能凭内存状态丢最后一帧。15 秒空闲心跳为冻结注释，不落库、不递增 seq。持续保留 Cache-Control:no-cache / X-Accel-Buffering:no；取消路由仍写 PG 标记并发信号，确保慢客户端或关闭订阅不阻塞模型流关闭。

### M4：HTTP 新旧协议、固定塔罗与网页发现

`POST /api/chat` 的新客户端显式 `Accept: application/json`：提交真实入队后立即返回 202 + `{run_id,message_id,thread_id,events_url}`；message_id 是本轮已保存原话 ID。旧请求默认仍返回原 `started/context/status/result/error/[DONE]`，由同一持久流适配，不能再复制执行一次 consultation。`final` 到旧 `result` 的投影与 core3/core4 history 共用已验证 reader，但新增 legacy 展示别名必须在独立兼容对象中，不能给 core4 Schema 添加 memory_receipts 等字段。

`/api/threads/{id}/messages` 的 202 投影补 message_id，`GET /api/runs/{id}/events` 保持冻结 wire。旧 DOM 需要真实浏览器读取同一 FastAPI/PG 三轮 v3→v4→v3，验证正文、可见实际回执、历史、取消与错误，不能只靠 API answer 或恢复后文字出现；不删除严格 xfail，也不把现有正文恢复当流式已兼容。涉及 `web/src/contracts/runEvents.ts` 或静态页面修补时交前端线，主线只提供 Schema/hash/兼容 API 契约。

既有塔罗 readings POST 先保留当前诚实拒绝，另片受审后才接 v4：用原 draw/deck/reading 和 source refs 入队，不重抽、不换牌、不绕过 U7；完成后经现有 TarotService/read_result 更新同一版本。失败/取消保留原牌阵和真实状态，不造 success。相同事件流用于网页与未来 P9 注入消费者，P9 暂不启用真实 CardKit 或 sender。

飞书与网页共用同 owner 的 life thread，跨进程运行用同一事件表。已知 run 的订阅先验收；网页自动发现飞书新 run 还需要受认证线程运行列表/轻量发现通知与前端消费者。若本片只做到“已知 run 能订阅”，明确保持“飞书发起后网页自动出现”未完成，不能用手工复制 run_id 冒充整项目标。

### M5：按安全提交计时的清理与撤销

模块 `CommittedRun` 只从真实提交事务的 message/revision/committed_at/final_seq 构造，不使用请求时间、事件 created_at 或会变化的 updated_at 猜测。独立每小时的 bounded sweep 调用模块 plan，23:59:59.999 不清、恰满 24h 可清；执行短 owner/run 事务，复核提交 revision/当前撤销状态、每个 seq/类型/指纹后删除 text_delta 行，保持最终助手消息和当前其他事件。

物理删除前保存无正文的 owner/run/seq/指纹/清理原因墓碑，避免丢失游标归属或让幂等操作重新发旧正文；重跑为零变化。合法退休游标可用现有持久 final 帧/鉴权 run 状态恢复当前结果，不伪造不存在的 delta 或新 seq，不恢复已撤销内容。其他事件 30 天后的清理同样要与 terminal 修复区分，不能因 ensure_terminal 读不到已清理 final 就重新落一份。

与现 60 秒 PrivacyMaintenanceSchedule 的步骤/无痕任务分开管理 next_due（新事件 sweep 为 3600 秒），不改旧任务口径/服务器 cron。来源或事实撤销、区间撤销、private thread 关闭时立即沿原闭包清事件/步骤正文并停旧生成；并发订阅在取缓存或 yield 前复核当前来源/generation，清队列中的过时提示/正文。30 天步骤无正文元数据、sent/uncertain 不重发和持久原件不变都保留。

失败或取消且没有安全 final 的运行不能伪造 CommittedRun/message_id 来满足模块参数。已有 interrupted 消息与 terminal error 可作为真实终态元数据的输入，但其增量到期口径需在实施时由 root/大脑明确并加反例；未定前把这一覆盖缺口保留，不宣称所有终态的事件保留策略都完成。

## Concrete Steps（未来执行命令；本片未运行）

root 完成 M0 并分配测试槽后，在实现子分支使用现有 P2 Core Python、隔离 loopback PG 的新随机 schema，清供应商/飞书凭据并关闭追踪；CHART_PYTHON 指向独立已锁 Charts 环境。原模块测试目录只有正常接收源后才存在，`streaming_integration` 是拟新增测试路径。

    python -m pytest tests/v4/streaming tests/v4/streaming_integration -q
    python -m pytest tests/v4/agent/test_public_events_contract.py tests/v4/agent/test_run_event_replay_pg.py tests/v4/agent/test_dispatcher_http.py -q
    python -m pytest tests/v4/agent/test_legacy_dom_runtime_pg.py -q
    python tools/eval/runner.py --mode scripted --target v4 --scenario X01,X02,X03,X04,X05,X06,X07,X08 --output private/p4-scripted-X
    python -m unittest discover -s tests -p 'test_core*.py' -v
    python -m pytest tests/v4 -q
    python tools/eval/runner.py --mode scripted --target fake --self-test --output private/p4-framework

宽回归仅在北京时间每小时 00–15 分开始，最多四个测试进程；本片没有占用测试槽。新增代码 Ruff 使用 E/F/I/B/UP/SIM、120 列、≤400 行/函数≤60。完整回归还须按当次 CI 跑 Charts（独立解释器）及 legacy npm/DOM/build；Node 必须记录实际版本，本机 Node24 功能绿不等价 Node22 门。新前端测试/类型生成由前端线按其脚本执行并提供可核结果，不默认根目录 npm 已覆盖新 web。

## Validation and Acceptance（测试闸门）

| 需求与场景 | 必须观察到的实际行为；未来证据 |
|---|---|
| 冻结契约 | 12 种事件同 Schema 校验，id/seq/event/type 一致；+08 时间跨 Tokyo/UTC 不漂移；防额外私有键、NaN、换行注入、双重 data 包装；TS 与同源 Schema 漂移检测 |
| M1 实际持久化 | 两 PG 连接并发 append 唯一递增、同 operation 原 seq/ts、异内容冲突；事务回滚无 row/ledger/notify；旧 lease/epoch/owner/subject/generation 拒绝；NOTIFY 在 commit 后可见 |
| 合并与负载 | 39/40 字、149/150ms、单 chunk/静默/结束 flush、reset 丢旧 buffer、慢订阅队列有界、生产线程不等待客户端；按实际持久事件恢复全文 |
| 首状态 / 首字 | ScriptedProvider 每 50ms 一个字，真实单调时钟测 status<1s、首 delta<3s；PG/HTTP 完整经过应用，不能只量纯函数 |
| X08 重连 | 本机真实 HTTP（不能用缓冲整个响应的替身假装流式），固定种子随机断开三次、当前真实 Last-Event-ID 续接；观察 seq 不重复/不漏，reducer 最终等于 envelope.text；覆盖 >256 条与终态边界 |
| 跨进程 | 独立进程执行、Web LISTEN 接收已提交增量，外进程重启/监听断线后回补；两 owner 同 ID/通知混入不串读，断开订阅不取消 run |
| X04 取消 | 复用本机静默 HTTP 源/真实 socket shutdown，从取消请求到流关闭/PG 终态<2s；停止后无新最终发布，合法部分文字只有一条 interrupted，旧 lease 无权继续 emit |
| X01/X03/X05/X06/X07 | 一次修订 reset、不重复工具副作用、循环熔断仍回答、lint 只告警、飞书合并仅替身入站；X03 旧四断言待脑，不改评分或伪造 Outbox，未裁定不能宣称 X 类全绿 |
| F03/F04、隐私 | 撤销消息/事实/区间与订阅/恢复并发，正文从事件/步骤/缓冲闭包清除，不由 final 缺口修复复活；private close/到期隔离，无痕不写长期记忆 |
| 24h / 30d | 冻结 Clock 验严格边界、提交元数据缺失拒猜、错 revision/指纹/owner 全拒、重复清理0变、退休 cursor 归属正确；最终原件与 Outbox 不动 |
| HTTP/旧页面/塔罗 | JSON 入队及时返回 source message ID；legacy 原事件格式、可见 receipts/错误/历史、v3→v4→v3 实际 DOM；固定牌阵解读/重试/取消不重抽；类型/前端依赖未交则不勾完成 |

指标报告应分开本地纯模块、真实 PG、真实 loopback HTTP、多进程、DOM 与全套 CI，保存候选树 SHA、命令、测试数/skip/警告、真实时间与原始日志摘要；不得把这些叫真实模型质量。原 P4 的“真实主模型五个对话”另列待授权，只在用户在线明确开始、中央额度守卫/encoder 就绪后执行；本周当前真实模型请求为 0 的限制不变。

## Idempotence and Recovery（幂等与恢复）

事件写入、NOTIFY、operation 账本在一个事务，崩溃后按原操作复用原 seq；不重放业务工具来补事件。最终提交后事件缺口从真实 envelope 修复；撤销/清理的缺口不修复。断线/重新订阅只读 PG，不 claim 或重启 run。主动取消才修改 PG 标记，旧 lease / generation 的并行写拒绝。

清理保存无正文墓碑，CAS 失败整片停止/回滚并记录安全 code；不为重试恢复已清内容。回滚实现以功能开关退回原 per-run PG 轮询/旧格式投影，不退数据库历史、不修改冻结 Schema、不重新执行已完成工具。若新增迁移已应用，只可前向修复；本地测试库用新随机 schema 重演，不把 v3 旧源码直接接更高 schema 当回滚。所有 stage/生产操作另走受审执行单，B1 固定 b9 不受此片影响。

## Artifacts and Notes（产物与待决）

未来证据目录为 `docs/v4/evidence/P4/`，包括阶段回执、契约/PG/HTTP/取消/清理/DOM/脚本报告。只记录安全统计/摘要；合成正文测试报告可留明确合成目录，真实正文、token、完整 DSN、出生信息和模型推理不得入日志/Git。

本片当前源码依据：事件 Schema 40498 字节 / SHA256 `fa42065d1baebb5b486283b073f4e141ead00d8b96538254c0a4b3112916a04d`，与模块 `docs/v4/evidence/MOD_2026-10-21/events_v1.origin.schema.json` 原始字节完全相同（其来源 f307231d）。`agent/events.py` SHA `92d3f600f9016a79c5ccb08254b239bf993d6ccbf2258d4a56c49850e983f44b`；`RuntimeEvents` `21049e03897422e1399ebe477072b847a037cc2bd47640465679deaed00b8fae`；`RunEventReader` `01b0015e17d2792b5ef8459c72ff5df4daa1f0707b8bd2d4c0743ed640bf5b56`；`thread_events.py` `e8c5366d7eb62805dd929c88c52b0317b5c0017d92f08892b4e82a55aab61b91`。这些是只读盘点身份，不是测试结果。

待决/剩余依赖集中保留：P3 原 X03 四条发送断言需大脑裁定；旧 DOM 的 core4 receipts 展示尚未验收；真实公开 K3 encoder 受信加载和新增依赖许可未好；P1b/P3 当前组合宽回归仍需 root 核最终结果；模块源尚未在该 wire 接收；TS/新客户端归前端线；事件账本/墓碑若需迁移由 root 分号。没有这些答案时可做离线实现与反例，但不宣称 P3/P4验收或 supplier ready。

## Interfaces and Dependencies（接口与所有权）

实现预计最小主线文件集：新增实际 PG EventTransaction 适配、EventSink/hub/listener/cleanup 服务与 `tests/v4/streaming_integration/`；小改 `agent_runtime_events.py`、`loop_cycle.py` 的输出委托、`agent_finalization.py`、`run_event_read.py`、`thread_events.py`、`thread_routes.py`、`web.py` 的协议选择与 lifespan、`privacy_maintenance.py / maintenance_schedule.py` 的独立事件清理调度。与 P6 wire 共用 review/reset、与 P1b wire 共用唯一模型/取消链，实施前 root 分配排他所有权；不得在其他代理仍编辑时并行修改。

保留 EventColumns 默认映射的 `owner/run_id/seq/kind/payload/created_at` 六个真实列；EventStore 接口 `append(scope,draft,operation_id=...) / replay(scope,after_seq=...,limit=...) / metadata(scope)` 不自行认领 run。新 HTTP 投影与 after 别名不改变冻结公共事件字段。模块和 P4 只用现有锁定依赖（asyncio、psycopg、FastAPI、Pydantic、当前模型端口）；需要新依赖先记待决，不安装、不新增 lock。

## 修订记录

- 2026-10-21 09:13 +08:00：只读当前固定头与模块 ref 后创建；按 33 号集成路线准备 P4，明确全部实施/测试待做，未碰 archive 测试源码或既有文件。
- 2026-10-21 09:17 +08:00：完成只读复核和结构检查，补无 final 终态保留口径的依赖，冻结本计划交 root；无代码/测试运行。
