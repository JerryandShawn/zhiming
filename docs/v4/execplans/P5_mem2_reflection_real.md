# ExecPlan · A：空闲反思接真实模型并更新统一记忆（`v4/mem2-reflection-real`）

依据：大脑交付 50 号第三节（方案与隐私门槛）、第六节（用户 11-08 拍板：(b) 自动写入非敏感明确事实；单独预算每人每天 ≤20 次）。基点：已上线 `bf6e0bbc`。负责：模块线。

## Purpose

线程空闲 10 分钟后，用与对话同一会员模型读取"上次整理以来的新原话 + 已确认画像摘要"，把用户明确说过的非敏感事实直接写进长期记忆（可撤销），敏感、第三人、推断和事件进"待确认"。开关 `MEMORY_REFLECTION_MODEL=scripted|real`，默认 `scripted`（现有本地脚本反思，行为不变）。

## 设计

- 开关：`memory2_reflection_input.reflection_mode`，只接受 `scripted`/`real`，其他值启动即报错。`MemoryMaintenanceSchedule` 在 `real` 时装 `RealMemoryReflection`，模型为 `ModelRegistry().port("background", stop_on_quota=True)` 包成 `ModelReflection`（`config/models.yaml` 的 background 角色就是 kimi-code-main）。
- 触发：沿用脚本版 `_ready`（只限 `life:` 线程、非无痕、空闲 ≥10 分钟、无在途运行）；"已开记忆" = owner 设置 `auto_save_low_sensitivity` 不为 False；线程级会话咨询锁保证同一线程只有一个反思。
- 预算：`runtime_step` 实体 `memory2-reflect-budget:<owner 本地日期>`，每次调用模型前在 owner 事务里 +1，满 20 次返回 `budget_exhausted`；按 owner 时区换日。同一输入（截止点 + 线程活动时间）已经尝试过就不再调用，失败不会每分钟重试耗尽预算。
- 输入最小化：只取本线程 `at_ms` 大于游标的活跃用户原话（≤40 条）；无痕、不允许持久、明确不要记、含凭据、有被撤销区间的消息不送；整条消息命中敏感类别（健康、财务、身份、法律、第三人）只送 `{"id","needs_ask":true}`。画像摘要只取已确认且来源仍有效的条目（≤30 条、每条 ≤200 字）。游标单独存，不带来源 id，撤销原话不会让它回退重送。
- 输出：一次强制工具调用 `submit_memories`，条目必须引用本次送出的消息 id、`quote` 必须逐字且唯一出现在当前原话里；结构不对整轮作废。
- 写入（用户拍板 b）：`explicit` + 类型 ∈ {preference, constraint, background, goal} + `sensitivity()=normal` + 本人 → 走 `V4FactMemory.save_fact`（与对话内 `memory_write` 同一套 v4 默认保存规则，不另造授权），事实带 `origin=memory2_reflection`、`auto_written=true`；其余（推断、事件、敏感、第三人、`save_fact` 不放行的）→ `proposal`（形状同 `memory_write` 的敏感提案，`origin`、`inferred`、单一 `source_refs`）。凭据、出生资料、假设句跳过。
- 血缘与撤销：事实 `source_refs`、提案 `source_ids/source_refs` 都指向原消息；`delete_source` 已有的级联会退休事实、写撤销账、并通过隐私闭包删除提案。运行记录只存 id 与计数，不存正文。
- 额度通道：模型调用包在 `CallScope(lane="background")` 里，走中央守卫的后台份额。

## Progress

- [x] 2026-11-09 读 50 号、现有脚本反思、`save_fact`/提案/撤销闭包、模型端口与中央守卫。
- [x] 2026-11-09 实现开关、输入、模型端口（提示词 `agent/prompts/memory_reflection.md` v1.0.0，单独 sha256 锁定，不改现有提示词清单）、主服务、调度接线。
- [x] 2026-11-09 PG 回归 10 项 + 端口单元 9 项（本机隔离 PG15 55483）。
- [x] 2026-11-09 现有记忆 2.0 回归（见日报）。
- [ ] 推断/普通类待确认提案的用户确认入口（见 Surprises 3）。
- [ ] real 模式的 stage 实测（需要授权与真实模型，本线不做）。

## Surprises & Discoveries

1. **"不计入 80 次/5 小时"在守卫层做不到。**中央守卫按会员账号记 5 小时窗口（`QuotaPolicy.max_calls=80`），所有会员模型调用都会计入；后台通道只是不占交互预留（`interactive_share=0.60`）。本实现：后台通道 + 每人每天 ≤20 次本地预算。要真正不计入，只能换非会员模型或由主线改守卫——需要大脑裁定。
2. 没有单独的"记忆开关"设置；用 `auto_save_low_sensitivity` 作为"已开记忆"。
3. 现有 `MemoryProposalService.accept` 只接受 `sensitivity ∈ SENSITIVITIES` 的提案；反思产生的**非敏感推断项和事件**提案（`sensitivity=normal`）目前没有确认入口，只能看到、不能一键确认。需要主线/前端定入口。
4. 运行记录 `runtime_step` 不在隐私闭包收集的实体类型里（`closure_rows` 只收派生类、消息、episode、interpretive_claim），撤销原话后记录仍在，但只含不透明 id 和计数；脚本版反思记录同样如此。
5. v4 `V4FactMemory._authorized` 已对"当前用户原话、非敏感"默认放行（不只偏好/约束），所以 (b) 不需要额外授权记录。

## Decision Log

- 2026-11-09：不新增迁移，全部用 `core_entities`（runtime_step/fact/proposal）。理由：R31 惯例、避免占迁移号。
- 2026-11-09：反思提示词单独文件 + 模块内 sha256 锁，不加入 `prompts/manifest.json`。理由：清单的文件集合和哈希被 `load_prompts()` 与 release 资产锁定。
- 2026-11-09：任务 id 绑定（截止点, 线程活动时间），同一输入不重试。理由：失败后每分钟重试会在 20 分钟内耗尽每日预算。
- 2026-11-09：整条消息敏感就只送标记；模型输出若引用标记消息，整轮作废。理由：50 号第三节第 3 条"不送或只送需要先问的标记"。

## Outcomes & Retrospective

开关默认 scripted 时行为与上线版相同（调度测试仍断言脚本模型）。real 模式在本机脚本模型下满足第三、六节的触发、预算、最小化、(b) 分流、血缘与撤销要求；真实模型效果未评测。
