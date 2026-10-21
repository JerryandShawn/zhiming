# P3 M1 Journal 子范围证据（不是完整阶段验收）

- 分支：`v4/p3-agent-runtime`。本轮开始基底：`97f656cd177d573a0eb9c11a668ea0d13a40881d`；证据编写时主线 HEAD 为 `181288473ab63755dfa8450a450040fc157edcbe`。后续提交由 root 统一处理，本执行者未提交、推送或合并。
- ExecPlan：`docs/v4/execplans/P3_agent_runtime.md`，由 root 维护；本文件只记录 M1 中持久步骤日志的离线子范围。
- 工作树：`C:/Users/Administrator/Documents/Codex/zhiming-v4`。日期：2026-10-18，Asia/Taipei。
- 状态：Journal 原语与定向测试已验证；完整 M1 模型工具循环、API 回读及完整 P3 尚未完成，未报告阶段完成或 CI 通过。

## 完成了什么

- 使用既有 `core_run_steps`，不创建平行存储、不修改历史迁移。所有读回和完成写入均校验受信 owner、权威 run、人物范围、当前 epoch、有效 lease、取消标记和执行截止时间；默认 v3 run 拒绝进入 Journal。
- 每个新的执行遍历从 seq=1 开始，以 run/epoch/seq 定位。输入指纹和 kind/name 不符时拒绝复用；完成步骤直接读回，未完成步骤保留稳定的 `run:{run_id}:e{epoch}:s{seq}` 操作号。
- `complete` 首次持久化规范化 JSON 对象及 usage；同一结果可幂等完成，异结果/usage 不得覆盖。JSON 布尔值与数字不因 Python 相等规则被误认为同一回执；未知实际 usage 保留 null。
- 完成记录的正文为空、失效标记存在或完成元数据缺失时明确拒绝恢复；数据库中的 `completed` 状态本身不能证明正文仍有效。测试通过真实 `retire_fact` 验证已登记依赖的来源撤销会清空 output，迟到内存结果不能重新填回。
- 通过真实 MemoryService 和 `mutation_request`，验证执行前、效果成功但日志未完成、日志完成后三个崩溃窗口：重新领取 lease 后只保留一个事实、一个 mutation 回执和一个步骤。外层事务异常时效果、回执与日志一起回滚。
- 覆盖跨连接竞争、同实例线程序号分配、换 lease、同 token 换 epoch、取消、过期、跨 owner、伪造人物/步骤及 UTC 元数据。

## 实际验证与命令

最终定向运行使用 P2 Core Python，工作目录为上述 P3 工作树：

    C:/Users/Administrator/Documents/Codex/zhiming-v4-p2/.venv-core/Scripts/python.exe -m pytest tests/v4/agent/test_journal_pg.py tests/v4/agent/test_journal_recovery_pg.py -q --tb=short

结果：**39 passed in 9.52s，退出0，零跳过**。此前首轮38项通过；增加布尔值/数字回执边界用例并修正静态格式后，以上39项全部重跑通过。

root合并复核时另以同一P2 Core解释器/本机隔离PG执行`-m pytest tests/v4/agent -q --tb=short`：**102 passed in 70.81s，退出0**。这次同时覆盖已提交的63项上下文与39项Journal，没有改动冻结源码；凭据清空、追踪关闭，不使用stage/live，不代表全部v4重跑或完整M1闭环。

测试前在独立进程环境清空 API key / auth token 变量，设置 `LANGSMITH_TRACING=false`、`LANGCHAIN_TRACING_V2=false`。`CORE_TEST_DSN` 仅指向已授权的本机 PostgreSQL15 测试库 `core_test_main`（回环端口55480）；不含 stage/live 数据。涉及 PG 的每个用例复用既有 `p2_repo` fixture，创建独立 `p2_test_<uuid>` schema，结束时只清理该用例自己的 schema。没有停启共享 PostgreSQL、创建新共享库或清理他人 schema。

HTTP 发送在测试 fixture 中显式拒绝。Journal 本身没有模型/渠道传输入口。本轮真实供应商请求、真实模型评审、真实飞书、stage/生产访问均为 **0**。本轮没有运行旧 Core 全套、全部 v4、live runner 或远端 CI；39项结果不替代它们。

静态检查使用主工作树 Core 中的 Ruff，仅检查本次三个 Python 文件：

    C:/Users/Administrator/Documents/Codex/zhiming-v4/.venv-core/Scripts/python.exe -m ruff check mingjing_core/agent/journal.py tests/v4/agent/test_journal_pg.py tests/v4/agent/test_journal_recovery_pg.py --select E,F,I,B,UP,SIM --line-length 120
    C:/Users/Administrator/Documents/Codex/zhiming-v4/.venv-core/Scripts/python.exe -m ruff format --check --line-length 120 mingjing_core/agent/journal.py tests/v4/agent/test_journal_pg.py tests/v4/agent/test_journal_recovery_pg.py
    git diff --check

最终结果：Ruff `All checks passed!`，format `3 files already formatted`，diff check退出0。独立 AST/字节检查确认以下行数、最长函数、单行不超过120字符、UTF-8/LF、无BOM。工具返回的 stdout 为本轮结果依据，未另造不存在的日志文件路径。

## 关键文件与冻结字节

| 文件 | 行数 / 最长函数 | SHA256 |
| --- | --- | --- |
| `mingjing_core/agent/journal.py` | 219 / 33 | `0bbf307db07b0df35cfae3fb2f523aac407b73d87ac545ab4349471b84a0e743` |
| `tests/v4/agent/test_journal_pg.py` | 223 / 21 | `b4750ad26db10e3e7bbf447d00221bbb470222c12deb8f680b89d67985785a44` |
| `tests/v4/agent/test_journal_recovery_pg.py` | 205 / 26 | `1a01f3aea3d14f2c738e7521a454cc9eb549615bf3d23f781091447610fd2e08` |

接口为 `Journal(repo, owner, clock=...)`、`next_or_replay(run, *, kind, input_fp, name='')`、`complete(step, output, usage=None)`。返回 `JournalStep` 提供 `completed`、`operation_id`、output/usage；其 repr 不含正文、reasoning 或 lease token。`input_fingerprint(kind, name, inputs)` 对严格 JSON 输入产生指纹；调用者必须将规范参数及有效来源版本放入 inputs。

## 数据库迁移与恢复边界

新增迁移：**0**。仅使用已合并0005中的步骤表；不修改 repository、迁移、context、loop、ExecPlan或运行配置。关闭/不接入该模块不会改变默认 v3 路由；不删除表或正文来模拟回滚。

恢复时每个执行/重新领取 lease 创建新的 Journal，从 seq=1 重建遍历；旧执行实例不能接着使用旧 token 完成步骤。epoch 变化进入新命名空间，不把旧 epoch 的结果重标为新结果。外层事务回滚后同样新建遍历，不延续已回滚执行的内存游标。

Journal 不负责执行工具或自动恢复运行。工具仍须使用稳定 operation_id 和既有应用服务幂等；完成步骤不执行工具。未完成模型步骤若被后续 loop 重发，必须重新通过真实请求预算与计费；本模块没有发请求或免计费的入口。

## 偏离设计与未验证 / 已知风险

本轮按授权只交 Journal 原语，不把模块存在、39项通过或已有 context 原型冒充完整 Agent。没有改变旧断言、旧 v3 预算、模型配置或架构设计。

尚未接入 loop、Toolkit、ModelPort、API、v4 提交闸门、真实请求计费/共享守卫或调度器；没有验证整轮模型→工具→模型→安全提交→API回读。依赖血缘登记仍由后续 loop/提交闸门完成，本轮仅证明已经登记的依赖被撤销及步骤正文被清空后不可恢复，不能宣称所有尚未接线的来源都自动具备闭包。

事件日志、30天步骤正文清理、24小时事件清理和完整运行取消流不在本子范围内。真实供应商协议/质量、stage/生产、浏览器及飞书端到端均未验证。

## 需要用户或大脑决定的问题 / 建议后续

本子范围无新增产品决策或密钥需求。root 后续接入安全模型工具循环时，须登记实际来源依赖、使用稳定操作号，并证明完成模型步骤重放不发新请求；接入 v4 安全提交和 API 回读后才能推进完整 M1 验收。真实请求仍遵守本聊天逐批开始授权和夜间零真实请求的既定边界。
