# P3 · Agent 运行时、工具集与人生线程

> 前置：P1、P2 已合并到 `v4/main`。这是 v4 的心脏。

---

你是「知命明镜台 v4」的开发者（Codex）。先读 `AGENTS.md`，再**完整**读 `docs/v4/02_v4架构蓝图.md` §0、§3、§4、§5、§10、§11、§16 与 `docs/v4/06_明镜台系统提示词.md`（P1 system、P9 工具描述规范）。按 `.agent/PLANS.md` 写 `docs/v4/execplans/P3_agent_runtime.md`，分支 `v4/p3-agent-runtime`。

## 背景（为什么做）

v3 不是 Agent：`runtime/graph.py:15,47-52` 把十个阶段线性串起来；每次模型调用是一条 JSON 消息 + 一个 `submit` 工具；模型不能查记忆、不能算另一个日期、不能停下来问用户；计划阶段还会用正则改写模型的计划（`consultation.py:408-439`）。我们要的是：**模型自己决定调用哪些工具、看结果再决定下一步，直到给出回答**，同时保留 v3 在持久化、幂等、可恢复上的全部优点。

LangGraph 不再作为主循环（理由见蓝图 §3.1：v3 checkpoint 只存 ID 的不变量 + `ask_user` 用"结束本轮"实现，不需要 interrupt）。新运行时挂在现有 `RuntimePort`（`domain/consultation.py:85-86`）之后。

## 目标

1. `AgentLoopRuntime`：`prepare_context → model ⇄ tools → finalize`，步骤日志持久化、崩溃可续跑、可取消、有安全上限（蓝图 §3）。
2. `AgentDispatcher`：两条通道、全局并发、同线程串行、NOTIFY 唤醒（§3.4）；网页与飞书都通过它执行。
3. `ContextEngine`：分层装配（§5.1 顺序）、引用别名（§5.4）。
4. 工具集第一批（§11）：`time_context`、`calendar_lookup`、`memory_search`、`memory_write`、`memory_update`、`memory_forget`、`note_write`、`profile_get`、`profile_update_request`、`chart_compute`、`tarot_start`、`tarot_read`、`case_list`、`case_update`、`case_add_event`、`ask_user`、`present_options`、`schedule_followup`、`set_reminder`。（`chart_skill` 在 P8；`consult_specialist` 在本阶段末尾或 P8，视进度；后台工具在 P5。）
5. 人生线程与无痕线程（§4）。
6. 提交闸门重做与 `core4.0` 结果信封（§3.5），所有读取端兼容 `core3.0`。
7. 按 owner 设置 `runtime: v3|v4` 路由，便于灰度与回滚。

## 设计要求

### 文件
`mingjing_core/agent/{loop.py, journal.py, dispatcher.py, context.py, toolkit.py, envelope.py}`、`mingjing_core/agent/tools/*.py`、`mingjing_core/agent/prompts/{system.md, onboarding.md, crisis.md}`（内容逐字来自 06 的 P1、P2、P8，带版本注释）、`tests/v4/agent/*`。

### 循环（`loop.py`）
- 伪代码见蓝图 §3.2；安全上限见 §3.2 表格，从 `config/runtime.yaml` 读取。
- 模型调用通过 P1 的 `ModelPort.stream`；本阶段先把流式事件**收集**起来（P4 再推给前端），但 `emit` 接口现在就定义好（`emit(type, data)`，默认 no-op）。
- 每次模型步骤保存规范化助手消息（含 `reasoning` 字段，按能力矩阵决定是否回传）。
- 工具调用并行：同一次模型回复里的多个工具调用，互不依赖的用线程池并行执行（只读工具），写工具顺序执行。
- `ask_user` 返回 `ends_turn=true`：本轮以"提问"结束，信封里 `asked={question, options, allow_free_text, why}`；用户的下一条消息作为新一轮，ContextEngine 会把上一轮的提问放在线程里，模型自然接续。**不要实现 interrupt/resume 机制。**
- 危机检测：在 `prepare_context` 用一个轻量规则 + 模型首轮判断（system 提示词里已有安全段）；规则命中（自伤/自杀/暴力关键词与句式，正反例测试各 ≥15）时，本轮叠加 `crisis.md`、不暴露命理与塔罗工具。热线号码来自 `config/crisis.yaml`（默认 12356）。
- 最终文本为空时兜底（§8.2 第 4 条），绝不返回空回答。

### 步骤日志（`journal.py`）
- 使用 P2 建好的 `core_run_steps`。`next_or_replay(run, kind, name)`：已完成直接返回结果；未完成重做。工具副作用的 `operation_id = f"run:{run_id}:e{epoch}:s{seq}"`，通过 `_operation` / `core_mutation_requests` 去重（`postgres.py:177-185, 379-404`）。
- 测试：在第 k 步后模拟进程崩溃（抛异常+重新 claim），续跑后数据库里的事实、跟进、outbox 行**没有重复**（覆盖 k = 每一种工具）。

### 调度（`dispatcher.py`）
- 取代 `adapters/web.py:126-135 worker()` 的 2 秒轮询单并发；在 FastAPI lifespan 中启动。
- 通道 `interactive`/`background`，全局并发默认 3（`CORE_RUN_CONCURRENCY`）；同线程 `pg_advisory_xact_lock(hashtext('thread:'||thread_id))` 串行。
- `LISTEN mj_run_queued` 唤醒 + 2 秒轮询兜底；入队时 `NOTIFY`。
- 取消：`POST /api/runs/{id}/cancel` 写 `cancel_requested_at` 并 `NOTIFY mj_run_cancel`；运行中检查（每步之间、每个流式分片）→ 关闭模型流（P1 的 `cancel_event`）→ 已生成文本存为 `status=interrupted` 的助手消息 → run 状态 `cancelled`。目标：2 秒内停止。
- 租约 150 秒，每步与流式期间每 20 秒续租（`renew_run`，`postgres.py:458`）。
- 飞书：`feishu_gateway.py:111` 不再直接 `consult`；改为入站写消息+入队（`operation_id = feishu:message:<message_id>`），2.5 秒内同一用户的连续消息合并为一轮（在入队前做合并窗口）；运行完成后由现有 outbox 投递最终文本（P9 再做卡片与流式）。

### 上下文（`context.py`）
- 严格按 §5.1 顺序装配；各层预算可配；超预算时：L5 旧消息先合并进线程摘要（P5 前若没有摘要，就截取最近 N 条并在块头注明"更早的对话见检索"），L4 降 K。**约束类事实永远保留**。
- L2 画像：P5 之前用"有效事实按类别分组"的临时实现（带别名与来源日期）。
- L3：未结事项（标题、目标、最近 3 条事件——v3 从未把这些给过模型）、待跟进、知识缺口（P7 前可为空）。
- L4：`memory_search` 同一实现（P2 的 FTS；P5 再加向量）；查询 = 本轮消息 + 最近 2 轮 + 指代展开（参考 `hermes/context_builder.py:88-91`）。
- L1：P2 的 `render_now_block`；`距上次对话` 用线程里上一条用户消息时间；`未来7天安排` 用带 `event_at` 的事实与跟进。
- 别名：`〔f12〕`（事实）`〔n3〕`（笔记）`〔e5〕`（情景）`〔c7〕`（盘面声明）`〔m9〕`（消息）；在 run 内维护别名→ID 映射；finalize 把回答中出现的别名映射为 `used_fact_ids/used_claim_ids`，未知别名移除并记录（§8.2 第 1 条，本阶段实现）。

### 工具（`toolkit.py` + `tools/`）
- 每个工具：`name`、`description`（按 06 P9 规范写中文）、参数 Pydantic 模型 → 经 P1 `schema_flatten` 输出、`visible(ctx) -> bool`、`execute(args, ctx) -> ToolResult{ok, data, receipt?, ends_turn?, summary}`。`summary` 是给事件流与日志用的安全摘要（不含私人正文）。
- 复用：
  - `chart_compute`：`ConsultationService.authorized_archive`（`consultation.py:441-449`）与 `_phase_calculation` 主体（`:451-479`）、`ChartAdapter.calculate`（`adapters/charts/adapter.py:147`）、`KnowledgeRegistry.claims_for/revalidate_claims`（`knowledge/registry.py:599, 701`）、错误与缺口的公开投影（`consultation.py:956-1001`）。把它们抽成 `application/charts_service.py`，v3 与 v4 共用，不复制粘贴。
  - `tarot_*`：`TarotService.create_draw / get_for_reading / begin_reading / finish_reading`（`application/tarot.py:112, 239, 245, 288`）；**牌面固定的全部不变量保留**。`tarot_start` 返回需要用户点选/揭牌的 draw（前端/飞书渲染），模型在用户揭牌后的下一轮用 `tarot_read` 读取。
  - `case_*`：`MemoryService.create_case`、`resolve_cases`（`memory.py:341, 352`），事件写入复用 `web.py:271-281` 的逻辑（抽到应用层）。
  - `memory_write`：调用 P2 修复后的 `save_fact` 路径 + 蓝图 §6.2 的新敏感分类（`memory/policy.py`）；本阶段 proposal 可以先只写实体并通过回执返回 `pending_confirmation`（确认 UI 在 P5/P10/P9）。**原话区间校验**必须在代码中完成。
  - `memory_forget`：复用 `retire_fact`（`memory.py:298-325`）。
  - `profile_update_request`：只生成"资料确认请求"实体与回执，真正写入仍走 `/api/subjects/self/profile/confirm`（`web.py:293-328`）。
  - `schedule_followup` / `set_reminder`：只写 `followup` / `reminder` 实体（`due_at`、`topic`、`reason`、`source_fact_id`、`status=active`），发送逻辑在 P7。
- 按情境暴露（每轮 ≤15）：无已确认出生资料时不暴露 `chart_compute`；无已揭示 draw 时不暴露 `tarot_read`；无痕线程不暴露写记忆类工具；危机模式只暴露 `time_context`、`memory_search`。

### 人生线程与无痕
- 线程 ID 规则见 §4；无痕：用户在消息中明确说"开个无痕/这段别记"或前端开关（P10）→ 新建 `incognito:<uuid>` 线程，后续消息在该线程中直到用户说"结束无痕"或 24 小时无活动；无痕线程不写记忆、不进主线程上下文、不被反思处理。
- `POST /api/chat` 新增可选字段 `thread_id`（默认主线程）与 `incognito: bool`；旧字段 `session_id` 映射为 `topic_id` 标签。

### 提交闸门与信封
- `commit_run`（`postgres.py:526-535` 一带）新增 v4 分支：排除 `operation_id` 以 `run:{id}:` 开头的写入造成的版本变化；若本轮引用/注入的事实在运行期间被撤销 → 触发一次重新生成迭代（最多一次），再提交。
- `core4.0` 信封见 §3.5；修改所有读取端兼容两种 schema：`channels/hermes.py:150-164 validated_payload`、`adapters/delivery.py:45-56 _fresh`、`application/tarot.py:297-303 finish_reading`、`/api/chat/{id}`、`/api/runs/{id}`、`/api/history`（旧前端仍需正常显示 v4 回答：把 `text` 映射到旧字段 `answer`）。
- 预算：v4 运行不再受 `CALL_LIMITS` 限制（`postgres.py:23`、`charge_run :464-502` 对 `runtime='v4'` 跳过上限，只记账）。

### 路由与灰度
- `ConsultationService.submit` 按 `core_owners.settings.runtime`（默认 `v3`）选择运行时；新增管理命令 `python -m mingjing_core.tools.set_runtime --owner <id> --runtime v4`（只在本机/stage 用）。

## 测试

- 单元：每个工具（参数校验、可见性、回执、幂等）；ContextEngine（层顺序、预算、别名映射、无痕隔离）；循环（上限、熔断、空回答兜底、ask_user 结束本轮）；危机规则正反例。
- 集成（真实隔离 PG + `ScriptedProvider`）：P0 评测框架加入 `--target v4`；以下场景脚本模式 100% 通过：T01–T14、M01–M04、M09–M11、M13、R01–R09、Q01–Q07、TA01–TA03、D01、S01、X03–X05、L01。
- 实测（真实模型 primary，可再加一个降级模型）：T、R、Q 类得分 ≥ 80%，S 类 100%，与基线对比表入库。
- 崩溃续跑与取消：X03、X04 的自动化测试（`kill` 用模拟：在指定步骤抛 `SystemExit` 后重新 claim）。

## 不在本阶段做

前端流式与 SSE v2（P4）；评审员与 legacy lint（P6；本阶段 v4 运行**不调用** v3 的 `_validate`，只做 §8.2 的别名检查与空回答兜底）；反思、画像、向量（P5）；跟进发送（P7）；命理技能包（P8）；飞书卡片（P9）；新前端（P10）。

## 验收标准

1. 上述脚本模式场景 100%；实测 T/R/Q ≥ 80%、S = 100%；报告入库并与基线对比。
2. 崩溃续跑无重复副作用；取消 2 秒内生效（给出测量）。
3. 同一线程并发两条消息时严格串行；不同通道互不阻塞（测试证明）。
4. 旧前端在 `runtime=v4` 下仍能完成一次完整对话并显示回答（DOM 测试或手动截图）。
5. 飞书网关改为入队模式，合并窗口测试（X07）通过；不发送真实飞书消息。
6. `runtime` 开关可在 v3/v4 间来回切换，切回 v3 后旧行为不变。
7. stage 计划 `docs/v4/release/P3_stage_plan.md`（含把主 owner 切到 v4 的步骤与回滚）；执行需用户授权。
8. ExecPlan 与阶段回执。

## 何时停下来问用户

- 实测发现主模型在工具调用上明显不可靠（例如 L01 失败、频繁格式错误），需要调整主模型或降级链时；
- 需要 stage 部署授权时。
