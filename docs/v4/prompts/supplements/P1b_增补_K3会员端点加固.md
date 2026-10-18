# P1b · 增补：Kimi K3 会员端点加固（错误分类、额度与并发守卫、推理回传、effort 锁定）

> 前置：P1（PR #3，含 14 号 A 节的 403 额度修复）与 P2 已合并到 `v4/main`。
> 分支：从合并后的 `v4/main` 切 `v4/p1b-k3-hardening`。**可与 P3 并行**：本增补只改 `mingjing_core/models/`、`config/models.yaml`、`tools/probe_models.py`、`tools/eval/` 的调用守卫与一个新迁移；P3 改 `mingjing_core/agent/`。两边的接口约定见 §F。
> 研究依据：`docs/v4/17_深度研究_算命Agent架构v2.md` §6（U37–U39、U42、U43）。
> 文件归属（按 `20_并行开发与夜间作业构思.md` 第二节）：修改已有的 `models/*.py`、`config/models.yaml`、迁移、`tools/eval/**` 与全部真实探针调用都归**主线**；新模块 `models/quota_guard.py` 的核心逻辑与单测可以由**模块线**先写（只新增），主线接线。

## 与原提示词的关系

| 原条款 | 处理 |
| --- | --- |
| P1"供应商迁移"第 3 条"识别额度类错误（429、usage limit、quota）→ `ModelQuotaExhausted`" | **替换**为本文 §A 的分类表。会员端点的 429 不再一律视为额度用完 |
| 14 号 A 节（403 + `permission_error` + `usage limit` → `quota_5h` / `quota_weekly`） | **保留并扩展**：新增 `quota_monthly`、`concurrency_limited`、402、429 细分、400 细分 |
| `config/models.yaml` 中 `kimi-code-main`、`kimi-critic` 的 `reasoning_replay: false`、`thinking.budget_tokens: 1024`、`temperature: 1`，以及 `tool_choice` 列表含 `none` | **替换**为 §C、§D 的配置 |
| P1 `tools/probe_models.py` | **新增**探针项（§E） |
| 15 号文件的额度规则（每 5 小时 ≤80 次、批间 20 分钟、遇 `quota_5h` 可自动续一次） | **不变**，由 §B 的守卫在代码层强制执行，不再只靠 runner 自觉 |
| 用户决定：会员端点、主模型 `k3`、评审 `k3-256k`、同模型独立上下文、遇额度错误即停、不改 User-Agent | **全部不变**。§G 的两项（流量分流、主模型改 `k3-256k`）只实现配置开关，**默认值保持用户现有决定**，等用户回答后再切换 |

---

你是「知命明镜台 v4」的开发者（Codex）。先读 `AGENTS.md`、`docs/v4/prompts/P1_模型可移植层.md`、本增补，以及 `docs/v4/17_深度研究_算命Agent架构v2.md` §6。按 `.agent/PLANS.md` 新建 `docs/v4/execplans/P1b_k3_hardening.md`。

## 背景（证据）

以下事实均来自官方文档（2026-10-18 核查，链接见 17 号 §10）或本仓库：

1. **Kimi Code 错误参考**列出 4 种 403，都"不要重试"：
   - 5 小时额度；
   - 周额度（只限老套餐）；
   - **月额度**：账号冻结，与 Kimi 全部会员权益共用；
   - **并发限制**：风控触发，与额度无关。

   其他状态码：
   - 402：会员验证失败，稍后可重试；
   - 429：请求过多或引擎过载（工作日 14:00–17:00 高峰），可退避重试；
   - 400：消息总大小 >2MB、超过 262,144 token、开启思考但工具消息缺 `reasoning_content`、工具重名、内容安全拒绝。
2. **Kimi Code 社区准则**：订阅"仅供个人交互式使用"，"不要把 Kimi Code 用于非交互式自动化"，例子是脚本批量运行；违规的处置是限制并发。
3. **Kimi Code 模型页**：
   - 关闭思考时，K3 请求由 K2.8 Preview（无思考）处理；
   - effort 档位为 low/high/max，K3 默认 high；
   - 切换模型或 effort 会使上下文缓存失效；
   - `k3`（1M）的额度消耗约为 `k3-256k` 的 2 倍。
4. **Kimi 开放平台 K3 文档**：
   - 思考常开；
   - 采样参数固定（不要传 `temperature`、`top_p`）；
   - 多轮与工具调用必须原样回传完整助手消息；
   - **指定函数的 `tool_choice` 与思考不兼容，返回 400**。
5. **本仓库探针**（`docs/v4/model-probe-2026-10-17.md`）：
   - 指定工具失败；
   - `tool_choice=none` 只返回推理、没有正文；
   - 推理回传与不回传各接受一次请求，但没有记录签名是否存在。
6. **本仓库代码**（行号取自 PR #3 分支，合并后以 `v4/main` 实际为准）：
   - `mingjing_core/models/transport.py:54-66` 的 `http_error` 在会员端点上把任何 429 映射为 `ModelQuotaExhausted`，关键字只有 `usage limit/quota/额度`；
   - `:111-116` 的 `stream_error` 同理。
   - `config/models.yaml` 中 `kimi-code-main`、`kimi-critic` 的 `reasoning_replay: false`。

## 目标

1. 会员端点的每一种错误都被正确分类，并执行唯一、明确的动作（§A）。
2. 一个跨进程的**额度账本 + 并发守卫**，让网页对话、评审、后台、评测共用同一套约束，而且评测 runner 无法绕过（§B）。
3. 工具循环内**原样回传推理**；**禁止**关闭 K3 的思考；effort 按角色固定（§C）。
4. `tool_choice` 只使用安全的取值；请求体积在发送前检查（§D）。
5. 探针补测，回答四个尚未有证据的问题（§E）。
6. 为两项待用户决定的改动准备好配置开关，默认不启用（§G）。

## 设计要求

### A. 错误分类（`mingjing_core/models/errors.py`、`transport.py`）

在现有类上增加 `kind` 字段，或增加子类，二选一并写入 Decision Log。分类依据依次为：HTTP 状态码 → 响应体 `error.type` → 提示文字关键字（中英文，大小写不敏感）。关键字以 Kimi Code 官方错误参考页和旧诊断文件（`work/provider-access-diagnostic-*.json`）中的格式为准；**不要凭空编造提示文字**，拿不到原文的类别，用合成夹具并在夹具注释里写"格式推定"。

| 状态 | 判定 | 类型 / kind | 动作 |
| --- | --- | --- | --- |
| 403 | 5 小时额度 | `ModelQuotaExhausted(kind=quota_5h)` | 不重试，不降级到同一会员的其他模型。按 15 号规则：评测停止并写"预计恢复 = 停止时刻 + 5 小时"；交互返回友好提示 |
| 403 | 周额度 | `quota_weekly` | 同上；汇总置顶提醒"线上可能受影响" |
| 403 | 月额度（monthly） | `quota_monthly` | **全部停止**（交互、评审、后台、评测）。置顶通知用户："你的 Kimi 会员月额度已用完，Kimi 网页版、Kimi Code 等都会受影响。"写持久停止标志，需人工解除 |
| 403 | 并发限制（concurrent） | `ModelConcurrencyLimited` | 不重试。守卫把全局在途上限降为 1，停后台与评测 24 小时，置顶通知用户（这是风控信号） |
| 403 | 其他 | `ModelPermissionError` | 不重试 |
| 402 | 会员验证失败 | `ModelMembershipUnverified` | 等 60 秒重试一次；再失败按不可用处理 |
| 429 | 请求过多 / 引擎过载 | `ModelRateLimited(kind=rate_limited｜engine_overloaded)` | 指数退避（沿用 1s/3s/9s + 抖动，最多 3 次）；**不再**映射为额度用完 |
| 400 | 缺 reasoning_content | `ModelBadRequest(kind=reasoning_missing)` | 不重试；记为**代码缺陷**告警（§C 实现后不应出现） |
| 400 | 消息超过 2MB / 超 token 上限 | `kind=payload_too_large｜token_limit` | 不重试，交给上层压缩（P3） |
| 400 | 内容安全拒绝 | `ModelContentFiltered` | 不重试；上层处理（P3 的危机兜底模板） |
| 400 | 工具重名等 | `kind=bad_request` | 不重试 |
| 5xx / 连接错误 | — | `ModelUnavailable` | 沿用现有重试 |

- 流式中途的错误事件（`stream_error`）走同一张分类表。
- 诊断信息只允许包含：状态码、`error.type`、kind、供应商提示的前 240 字（14 号 A.2 已授权）。**不得包含请求或响应正文。**

### B. 额度账本与并发守卫（`mingjing_core/models/quota_guard.py`，新增）

**迁移编号说明**：本阶段是 0005–0007 之后第一个需要新表的阶段，新增 `mingjing_core/repositories/migrations/0008_model_usage.sql`。蓝图 §15 原定的 `0008_memory_proactive` 顺延为 `0009`，`0009_pgvector` 顺延为 `0010`，`0010_retire_langgraph` 顺延为 `0011`。在 Decision Log 记录，并在回执提醒大脑更新蓝图 §15（`18_提示词增补包/P5_增补` 已按新编号写）。如果 `verify_schema` 的已知迁移序列机制不允许这样做，**停下来问大脑**。

**1. 账本表 `core_model_usage`**
- 列：`id bigserial`、`at timestamptz`、`provider`、`model`、`role`（primary/critic/fast/vision/evaluation/background）、`lane`（interactive/background/eval/probe）、`run_id null`、`status`（ok 或错误 kind）、`input_tokens`、`cache_read_tokens`、`cache_write_tokens`、`output_tokens`、`latency_ms`。
- **不含任何正文。**
- 写入点：`ModelRegistry` 每次调用结束时写一行（成功、失败都写）。字段来自流式 `usage` 事件：Anthropic 协议读 `cache_read_input_tokens` / `cache_creation_input_tokens`，OpenAI 协议读 `prompt_tokens_details.cached_tokens` / `cache_write_tokens`；拿不到就记 null。
- 新表要在 `tools/deploy_core.py` 的授权步骤里覆盖（P2 已改造的授权逻辑）。

**2. 滚动窗口预算**（只对 `membership: true` 的提供方生效）
- 计数对象：最近 5 小时的调用次数（含失败），token 只记录不限制，因为官方没有公开 token 口径。
- 上限读 `config/runtime.yaml` 的 `membership_budget`，默认值：

      window_hours: 5
      max_calls_per_window: 80        # 15 号文件
      reserve:                        # 份额（项目口径）
        interactive: 0.60
        critic: 0.20
        background: 0.20
      eval_max_calls_per_window: 80   # 评测单独计数，但与上面共用总上限
      eval_batch_gap_minutes: 20

- 判定顺序：先看总量是否超限，再看本通道的份额。超出份额但总量未满时：交互可以借用其他通道的余量；后台和评测不能借。
- 降级顺序：后台先停；评审改为"只做程序化证据检查"（由 P6 读取 `guard.critic_allowed()`）；交互最后受影响。

**3. 全局在途上限**（跨进程）
- 默认 `max_in_flight: 2`：槽位 1 留给交互，槽位 2 给其他通道。
- 实现：PG 会话级 advisory lock（`pg_try_advisory_lock(<固定命名空间>, slot)`），每次调用期间持有一个专用连接。
- 等待：交互最多等 10 秒，后台和评测排队等待。
- 遇到 `ModelConcurrencyLimited`：上限降为 1，持续 24 小时（记在 owner 设置或运行时状态表里）。

**4. 评测 runner 接入**
- `tools/eval/runner.py` 的目标调用与评审调用都必须经过守卫（`lane=eval`）。
- 每批之间的 20 分钟间隔由守卫强制，不再靠 runner 自觉。
- 遇到 `quota_5h` 的"自动续跑一次"规则（15 号文件）保留在 runner 里，但"何时可以续"由守卫根据账本计算。

**5. 只读接口（P3、P6、P7 会用）**
- `guard.acquire(role, lane, timeout)`：上下文管理器。
- `guard.status()`：返回窗口已用、各通道余量、在途数、是否有停止标志。
- `guard.critic_allowed()`、`guard.background_allowed()`。

### C. 推理回传、思考与 effort（`anthropic_messages.py`、`openai_compat.py`、`registry.py`、`config/models.yaml`）

1. **推理回传**：
   - `kimi-code-main`、`kimi-critic`（以及将来的 `kimi-open`）的 `reasoning_replay` 改为 `true`。
   - 回传范围保持现有的 `tool_cycle` 语义（`port.py:47` 的注释：新的真实用户轮次关闭之前的推理/工具循环），即**只在同一运行的工具循环内回传**，跨轮不回传。
   - Anthropic 协议回传 thinking 块与签名（`anthropic_messages.py:37-41` 现有逻辑）。**若签名缺失**：记录 `reasoning_signature_missing` 计数，探针里要能看到；行为上仍回传 thinking 文本，除非 §E 的探针证明这会导致 400，届时停下来问大脑。
2. **禁止关闭思考**：
   - 加载配置时校验：`provider.settings.membership == true` 且 `model` 以 `k3` 开头，且 `settings.thinking.type` 为 `disabled`（或任何等价写法）→ 抛 `ConfigError` 拒绝启动。
   - 写测试。
   - 理由：官方说明关闭思考会换成 K2.8 Preview，破坏"评审与主模型同一模型"的用户决定。
3. **effort 锁定**：
   - 移除 v3 遗留的 `budget_tokens: 1024`，改为按角色固定 effort（项目口径）：primary=high、critic=high、fast（沉思、晨报、跟进生成）=low。
   - **字段名**：以 Kimi 官方文档（Anthropic 兼容接入）和 Anthropic 官方文档为准，不要猜；文档没写的，用 §E 第 3 项探针确定。
   - 如果确认没有可用的 effort 字段，就不传思考参数，使用服务端默认值（K3 默认 high），fast 角色也用 high，并记入 Decision Log。
   - effort 写进每次调用的 run meta 和评测报告头，视为模型标识的一部分。
4. **采样参数**：K3 模型（`caps.sampling_fixed: true`）不发送 `temperature`、`top_p` 等参数。

### D. `tool_choice` 与请求体积

1. K3 的 `caps.tool_choice` 改为 `[auto, required]`。`none` 移入 `caps.tool_choice_unusable: {none: "returns_reasoning_only", named: "incompatible_with_thinking"}`。
2. 端口层规则：
   - 调用方要"指定某个工具"：适配器抛 `CapabilityError("named_tool_choice")`，**不发请求**。正确做法写进 P3 增补：只暴露这一个工具，再加 `required`。
   - 调用方要"不用工具、只要文字"：适配器**不传 tools 字段**，而不是传 `none`。
3. 请求体积：发送前计算序列化后的字节数；超过 1.8MB（可配置）抛 `ModelPayloadTooLarge`，不发请求，由 P3 做压缩。
4. 工具调用 ID：保留供应商返回的原样 ID；自行生成的 ID 采用 `functions.<name>:<idx>` 格式（K2 Vendor Verifier 的规范；对 K3 是否必要未知，记为预防措施）。

### E. 探针补测（`tools/probe_models.py` 新增 `--suite k3-hardening`）

全部遵守 §B 守卫，合计 ≤40 次调用，可分两个窗口完成。只记元数据，不存提示词与回答全文。

| 编号 | 问题 | 方法 | 调用 |
| --- | --- | --- | --- |
| E1 | 回传推理与不回传，在多步工具场景上有无质量差？ | 5 个合成的多步工具任务（查日期 → 算间隔 → 写记忆），两种配置各跑一次，比较完成率与工具参数正确率 | ≤10 |
| E2 | Anthropic 协议下是否返回 thinking 签名？缺签名回传是否报错？ | 记录签名是否存在；构造无签名回传一次 | ≤4 |
| E3 | effort 字段是否生效？ | 同一题分别用 low/high 两档（加上"不传"），比较推理 token 数 | ≤6 |
| E4 | 会员端点是否返回缓存读写字段？两次同前缀请求是否命中？ | 连续两次相同的长前缀（≥4k token）请求 | ≤4 |
| E5（需用户同意 §G.2） | `k3` 与 `k3-256k` 是否等价？ | T01–T05、R01–R03 的单轮子集，两模型各一次，比较确定性断言通过数 | ≤16 |

报告写入 `docs/v4/model-probe-<date>-k3-hardening.md`（与原报告同格式），并据此更新 `config/models.yaml` 的 caps。

### F. 与 P3 的接口约定（P3 同时在做）

- P3 的 `AgentDispatcher` 每次模型调用都通过 `guard.acquire(role, lane)`。P1b 未合并前，P3 先按现有 `ModelPort` 实现，**把"接入守卫"作为 P3 的独立里程碑，等 P1b 合并后完成**。不要写假守卫冒充。
- P3 的危机兜底（P3 增补 §E）捕获 `ModelContentFiltered`、`ModelQuotaExhausted`、`ModelConcurrencyLimited`、`ModelUnavailable`。
- P3 的上下文压缩捕获 `ModelPayloadTooLarge` 和 `kind=payload_too_large｜token_limit`。

### G. 两项待用户决定的配置开关（只实现，默认不启用）

1. **后台与评测流量分流**（17 号 U42，用户决定 D1）：
   - `config/models.yaml` 新增角色 `background`（沉思、晨报生成、跟进生成）。
   - `evaluation` 角色已存在；两者默认都指向 `kimi-code-main`，即用户现有决定。
   - 用户选 A 时，改指向 `kimi-open`（`provider: moonshot`，`model: kimi-k3`，base URL 以开放平台控制台显示为准：国内 `api.moonshot.cn`，国际 `api.moonshot.ai`）。这需要用户以环境变量 `MOONSHOT_API_KEY` 提供开放平台 Key，**由用户本人设置，绝不让用户把 Key 贴进对话**。
   - 切换前先对 `kimi-open` 跑一遍 P1 原有探针 + §E 第 1、4 项。
   - 报告头把 `kimi-open/kimi-k3` 与 `kimi-code/k3` 视为两个模型标识，分数不跨标识比较。
2. **主模型改 `k3-256k`**（17 号 U43，用户决定 D2）：
   - 只新增模型条目 `kimi-code-main-256k`，`roles.primary` 默认不变。
   - 用户同意后，先跑 §E 第 5 项，确认等价再切换。

## 测试

- `tests/v4/models/`：用 `httpx.MockTransport` 为 §A 表中每一类错误各至少 1 个夹具（含流式中途错误），断言类型、kind、动作（是否重试、守卫状态变化）。
- 守卫（真实隔离 PG）：
  - 两个线程或进程同时 `acquire`，第 3 个调用被阻塞或超时；
  - 交互能借用余量，后台不能；
  - 预算超限后后台被拒绝；
  - `concurrency_limited` 后上限降为 1；
  - `quota_monthly` 写入持久停止标志，重启后仍然生效。
- 配置校验：k3 + thinking disabled 时拒绝启动；`none` 和指定工具被端口拒绝且不发请求（MockTransport 断言请求次数为 0）。
- 推理回传：同一运行内第二次模型请求的消息体包含上一步的 thinking 块或 `reasoning_content`；新用户轮次的请求体不包含。
- 体积守卫：构造 1.9MB 的请求，断言抛 `ModelPayloadTooLarge` 且没有发出请求。
- 评测 runner：模拟 `quota_5h`，runner 停止并写出恢复时间；批间间隔不足时守卫拒绝下一批。

## 验收标准（可观察）

1. 用 MockTransport 回放 §A 每一类错误，回执中附一张"错误 → 类型 → 动作"实测表，全部与 §A 一致；其中会员端点的 429 显示为"退避重试"，不是"额度用完"。
2. 在真实隔离 PG 上，同时发起 3 个会员端点调用，最多 2 个在途（附计时日志）；模拟 `concurrency_limited` 后最多 1 个在途。
3. 模拟 `quota_monthly` 后，网页对话、评审、后台、评测全部停止，汇总置顶出现月额度提醒；重启进程后停止状态仍在，人工解除后恢复。
4. 把 `kimi-code-main` 的 thinking 改成 disabled，服务启动失败，报错信息清楚说明原因。
5. §E 探针报告入库，E1–E4 都有结论（含"无法确定"的如实记录），`config/models.yaml` 的 caps 据此更新；真实调用总数与各窗口用量写进报告。
6. 评测 runner 的所有真实调用都出现在 `core_model_usage` 中，`lane=eval`；没有绕过守卫的调用路径（附 `git grep` 证明 runner 中没有直接构造 HTTP 客户端）。
7. CI 绿；`mingjing_core/models/` 覆盖率不低于 P1 合并时的水平。
8. ExecPlan 与阶段回执（AGENTS.md §11）。

## 不在本增补范围

Agent 循环内的压缩与危机兜底（P3）、评审的降级逻辑（P6）、切换流量分流和主模型（等用户决定）。

## 何时停下来问用户 / 大脑

- 用户选择 §G.1 选项 A 时：需要用户以环境变量提供开放平台 Key，并确认是否付费（问用户）。
- §E 第 2 项发现"缺签名回传会报错"，或第 1 项发现回传推理反而变差（问大脑）。
- 迁移编号顺延与 `verify_schema` 冲突（问大脑）。
- 遇到 `quota_weekly`、`quota_monthly` 或 `concurrency_limited`（立即停止，在汇总置顶，等用户）。
