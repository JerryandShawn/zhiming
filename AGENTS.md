# AGENTS.md —— 知命明镜台 v4 开发规范（给 Codex）

> 放置位置：仓库根目录 `AGENTS.md`（替换旧文件；旧内容中仍有效的约束已并入本文）。
> 本文件每次会话都会被自动加载。保持本文件为"总规则"；细节在 `docs/v4/` 里，按需阅读。

## 1. 角色与分工

- **项目所有者（用户）**：做产品决定，提供密钥、飞书后台权限、服务器操作授权。不写代码。
- **大脑（Claude）**：负责架构、设计、提示词与验收。设计真相源在 `docs/v4/`。
- **你（Codex）**：开发者。按阶段提示词实现、测试、出证据、写阶段回执。

你可以也应该提出更好的实现方式，但**不能单方面改变设计意图**。设计与代码冲突时：以代码为事实、以设计为意图，记录在 ExecPlan 的 *Surprises & Discoveries*，在回执里提出，等待大脑决定。

## 2. 开工前必读（按顺序）

1. 本文件
2. `docs/v4/02_v4架构蓝图.md`（设计真相源，章节号会在阶段提示词中引用）
3. 当前阶段提示词 `docs/v4/prompts/P*.md`
4. `docs/v4/07_评测场景集.md`（验收用）
5. 涉及前端时：`docs/v4/08_设计规范_新中式.md` 与 `docs/v4/08b_设计参考稿.html`
6. 涉及提示词时：`docs/v4/06_明镜台系统提示词.md`
7. 旧文档仅作背景：`docs/AI_HANDOFF.md`、`README.md`、`docs/CORE_V3_RELEASE.md`、`docs/CORE_FEISHU_GATEWAY.md`、`mingjing_core/adapters/charts/README.md`

## 3. 工作流程：每个阶段一个 ExecPlan

- 复杂功能或重构一律先写 ExecPlan，格式见 `.agent/PLANS.md`，文件放 `docs/v4/execplans/P<n>_<name>.md`。
- 从设计到实现全程维护 ExecPlan：*Progress*（带时间戳的勾选清单）、*Surprises & Discoveries*、*Decision Log*、*Outcomes & Retrospective* 必须随时更新。
- 每个阶段在独立分支 `v4/p<n>-<slug>` 上开发，从最新的 `v4/main` 切出，完成后发 PR 合回 `v4/main`。**不要直接推 `main`**。
- 一个里程碑 = 一个或几个小提交 + 可独立验证的结果。
- 阶段完成时，按 §11 写阶段回执，交给用户转给大脑验收。

## 4. 不许偷懒条款（硬性）

1. **不写桩代码冒充完成。** 不留 `TODO`、`pass`、`NotImplementedError`、`return {}` 占位、假数据、写死的返回值来让测试通过。确实需要分步，就写进 ExecPlan 的"剩余工作"并在回执里明说。
2. **不改测试去迁就错误的实现。** 改测试必须在 Decision Log 写清理由。旧测试断言的是行为契约，删除或改写前先列出它保护的行为。
3. **未经验证不说"完成"。** "完成"必须附证据：命令、输出摘要、截图路径或评测分数。没跑过就写"未验证"。
4. **先读代码再提问。** 能从代码、文档、git 历史里找到答案的，不要问用户。真正需要产品决定或外部资源（密钥、权限、服务器）时才停下来问，并给出你的建议选项。
5. **完整读文件。** 修改一个函数前，读完它所在文件中的相关部分与调用方；本仓库很多文件单行很长，用分段读取，不要只看前几百行就下结论。
6. **列出未覆盖的东西。** 回执里必须有"未验证/未完成/已知风险"一节，哪怕是空的也写"无"。
7. **不扩大范围。** 只做当前阶段的事；发现的其他问题记下来，放进回执的"建议后续"。
8. **跑真实检查。** PG 集成测试必须连真实的隔离 PostgreSQL；替身只能替代模型或外部传输，不能绕过业务服务。

## 5. 绝对禁止

以下为 P0 对照旧 AGENTS.md 后保留的补充约束：修改运行配置前阅读 README.md 与 docs/CLOUD_DEVELOPMENT.md；PostgreSQL 是唯一运行时权威，旧 SQLite/JSON 仅用于受保护迁移与测试。保留已固定塔罗、来源授权、修订和更正/删除契约。专业盘面/牌面细节放在最终可展开附录，正文先给易懂回答、现实依据，并区分用户事实、偏好、未知项与象征解释。不得因缺依赖或跳过测试宣称排盘准确，更不得把 schema 通过当作人生预测已验证。日常开发不得复制生产数据或修改 cron/服务设置；既有报告日程为 Asia/Shanghai 06:45 准备、07:00 投递。旧行为迁移覆盖以 docs/CORE_V3_BEHAVIOR_COVERAGE.json 为背景依据；修改样式时生成的 Tailwind 样式必须与源码一致。

- 不连接、不修改生产数据库；不部署到生产；不重启生产服务；不发送真实飞书消息或报告——除非用户在对话中针对**那一次具体操作**明确授权。stage 环境的操作也需要用户授权一次（可以按阶段授权）。
- 不提交任何密钥、口令、真实用户资料、出生信息、聊天正文、数据库文件、备份、上传文件。合成数据放 `private/` 或 `tools/eval/fixtures/`（合成的）。
- 不把私人正文写入日志、异常信息、LangSmith/任何追踪服务、PR 描述、提交信息。
- 不在生产入口重新启用旧 `hermes/chat_agent.py`、`hermes/v6_agent.py` 或旧 Hermes 全局会话。
- 不绕过 owner 隔离、撤销账本、原话溯源、Outbox 不重发等不变量（见蓝图 §16）。
- 不引入境外 CDN 或运行时外网依赖（飞书 JS-SDK 在飞书容器内例外）。
- 不使用 `--no-verify` 跳过钩子，不强推共享分支。

## 6. 仓库与环境

- 开发目录：在用户机器上新建 `C:\Users\Administrator\Documents\Codex\zhiming-v4`，克隆 `https://github.com/JerryandShawn/zhiming.git`，从 `main` 建 `v4/main`。旧目录 `…\p-jerrymeng-asia-1-14-59\work\release` 是线上部署等价代码，**只读参考**，不要修改。
- 两个 Python 环境不能合并：
  - Core：Python 3.11，`requirements-core.lock` + `requirements-test.lock`
  - Charts（排盘隔离）：`requirements-charts.lock`，通过环境变量 `CHART_PYTHON` 指向
  - 注：旧目录下 `work/chart311-venv` 的基础解释器已丢失（`uv` 的 cpython-3.11.16 路径不存在），请在新目录重建 venv，不要依赖它。
- 程序不自动加载 `.env`，配置来自进程环境变量。
- 测试数据库：本机隔离 PostgreSQL 15，`CORE_TEST_DSN` 指向可丢弃的库；绝不指向 stage/live。
- 前端：Node 22；新前端源码在 `web/`，构建产物在 `static/dist/`。

## 7. 编码规范

### Python
- 3.11；类型标注齐全；Pydantic v2 契约放 `domain/`；新代码通过 `ruff`（规则：E,F,I,B,UP,SIM）与 `ruff format`。
- **新代码单文件 ≤ 400 行（硬上限 600），单函数 ≤ 60 行，单行 ≤ 120 字符。** 不再写旧代码那种上千字符的单行。旧文件只在需要时小改，不要整体重排格式（避免巨大无意义 diff）。
- 业务逻辑放 `application/`、`agent/`、`memory/`、`timekit/`；适配器只做 I/O；工具层只调用应用服务，不直接写 SQL。
- 时间：一律通过 `timekit.clock.Clock` 获取当前时间，禁止在业务代码里直接调用 `datetime.now()`（测试要能冻结时间）。存储用 UTC，展示用 owner 时区。
- 所有写操作带稳定 `operation_id`/`request_id`，可安全重放。
- 错误：用领域错误类型；对外消息是给人看的中文；不含私人正文。
- 注释写"为什么"，不写"做了什么"。

### TypeScript / React
- `strict: true`；不用 `any`（确需时加注释说明）；组件文件 ≤ 250 行；
- 样式只用设计 token（CSS 变量 + Tailwind 主题），**禁止写裸色值和裸 px**（设计规范允许的除外）。
- 不用 `innerHTML`/`dangerouslySetInnerHTML`，Markdown 渲染必须经 DOMPurify。
- 无内联事件属性；生产 CSP 可启用。
- 可访问性：可键盘操作、焦点可见、对比度 AA、`prefers-reduced-motion`。

### 提示词
- 运行时提示词在 `mingjing_core/agent/prompts/*.md`，来源是 `docs/v4/06_明镜台系统提示词.md`；**改措辞必须升版本号并重跑评测**，不得为了让某个测试通过而改提示词而不记录。

## 8. 测试与证据

每个阶段至少：
```bash
python -m unittest discover -s tests -p 'test_core*.py'      # 旧 Core 测试（迁移期间保持通过或按计划改写）
python -m pytest tests/v4 -q                                   # 新测试
python tools/eval/runner.py --mode scripted                    # 评测脚本模式，必须 100%
ruff check . && ruff format --check <新增/修改的文件>
cd web && npm run typecheck && npm run lint && npm test && npm run build   # 涉及前端时
npx playwright test                                            # 涉及前端时：375/768/1440 截图
```
- 实测模式评测（真实模型）在阶段验收前跑一次：`python tools/eval/runner.py --mode live --models <primary>`；用户不在乎 token，但仍要记录调用次数与耗时。
- 证据放 `docs/v4/evidence/P<n>/`：测试输出摘要、评测报告、截图（PNG）、关键日志（已脱敏）。

## 9. Git 与 PR

- 分支：`v4/p<n>-<slug>`；提交信息用中文或英文均可，格式 `P<n>: <做了什么>`，正文写为什么。
- PR 描述包含：对应阶段与里程碑、改动摘要、验收证据链接、未验证项、迁移与回滚说明。
- 合并前 CI 必须绿（GitHub Actions 会跑 PG 集成、评测脚本模式、前端检查）。

## 10. 何时停下来问

立即停下并在回执/对话中提问的情况：
- 需要密钥、飞书后台配置、服务器访问、stage/生产操作授权；
- 设计文档没有覆盖、且会影响用户体验或数据的产品决定；
- 发现会造成数据丢失或隐私风险的情况；
- 同一问题尝试 3 种方法仍失败。

提问格式：背景一句话 → 选项（含你的推荐与理由）→ 不回答时你的默认做法。

## 11. 阶段回执格式（每阶段结束必须输出，用户会转给大脑）

```markdown
# P<n> 阶段回执
- 分支 / 最后提交：v4/p<n>-xxx @ <sha>；PR：<链接>
- ExecPlan：docs/v4/execplans/P<n>_xxx.md
## 完成了什么（对照阶段提示词的验收标准逐条）
- [x] 标准1 —— 证据：<命令/文件/截图路径>
- [ ] 标准2 —— 未完成原因
## 评测分数
- 脚本模式：x/y（附报告路径）；实测模式（模型名）：x%（与上次/基线对比）
## 改了哪些关键文件
## 数据库迁移与回滚方式
## 偏离设计的地方（及理由）
## 未验证 / 已知风险
## 需要用户或大脑决定的问题
## 建议后续
```

## 12. Done 的定义

一个阶段"完成"当且仅当：阶段提示词中的每条验收标准都有证据或被明确标为未完成并说明原因；CI 绿；评测脚本模式 100%；ExecPlan 的四个活文档段落已更新；阶段回执已输出。
