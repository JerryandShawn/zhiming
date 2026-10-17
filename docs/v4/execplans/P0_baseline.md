# P0：建立可重复的 v3 基线与评测框架

本 ExecPlan 是活文档。遵循 `.agent/PLANS.md`，四个活文档段落随工作更新。所有时间为 UTC+08:00。

## Purpose / Big Picture（目的与全局）

把现有线上等价 v3 代码保留为比较起点，让时间、记忆与主动能力能按同一组合成场景重复评分。用户可以查看 80 个 YAML 场景的校验结果、框架自测及真实模型基线分类成绩。可冻结时钟让日期测试不依赖执行当天。P0 不部署、不改既有业务策略、不实现 v4 Agent。

## Context and Orientation（背景与定位）

仓库为 `C:\Users\Administrator\Documents\Codex\zhiming-v4`，从 origin/main `b996f42` 建立 `v4/main` 与 `v4/p0-baseline`。设计来源为 `docs/v4/02_v4架构蓝图.md` §0、§3、§5、§15、§16；场景定义为 `docs/v4/07_评测场景集.md`。

复用 `mingjing_core/application/consultation.py:42 today`（保持上海日期语义）、`:86 submit`、`:112 consult`、`:124 execute`（完整真实流水线）；复用 `mingjing_core/adapters/model.py:10 ConfiguredModel`（现有 Kimi 协议），`MemoryService` 与 `PostgresRepository` 负责合成种子和隔离状态。修改前阅读这些文件相关部分及调用方。Target 是评测对被测系统的统一入口；断言是确定性的状态/文本检查；rubric 是固定版本的评审标准。

不可改变 owner 隔离、用户原话溯源、拒绝保存优先、撤销账本无正文、固定塔罗、送达不明不重发。绝不连接 stage/live；真实模型仅在用户明确同意并由进程环境提供密钥后调用。评测历史必须保留角色、时间、渠道，助手历史不能转为事实。报告只含合成回答至多 200 字，不含密钥、完整请求或回答。

## Progress（进度）

- [x] (2026-10-17) 读取 P0、AGENTS、PLANS、场景集及蓝图关键章节；克隆基线、建立两个分支并复制允许的设计文件。
- [x] (2026-10-17) 比较旧 AGENTS，将有效遗漏补到新 §5，并保留旧规则证据。
- [ ] 环境：Python 3.11 Core/Charts、Node 22、隔离 PG15；记录旧测试。
- [ ] Clock 接口和 today 冻结测试。
- [ ] 80 个 YAML、严格 schema、确定性断言、ScriptedProvider、fake 自测、真实 v3 Target、固定评审与报告。
- [ ] 真实 Kimi 基线（等待用户明确同意及环境密钥）。
- [ ] 更新 CI、提交/PR、核对绿灯；更新计划和 §11 回执。

## Surprises & Discoveries（意外发现）

旧 AGENTS 尚有配置预读、唯一权威库、用户正文表达、日程、行为覆盖索引与样式生成一致性的约束，新文件未全部明确，已逐条保留于 §5。旧工作区已有 postgres、pg-data 与启动日志，优先只读定位，另建 P0 库，不复用任何线上连接配置。origin/main 的交接文档说明运行时代码与线上等价树相同，后续差异仅为测试与文档；本阶段不访问线上核对。

## Decision Log（决策记录）

决定：评测 fake 仅验证框架回放和判分，不代表 v4 业务已实现。v3 基线必须完整通过 ConsultationService，模型不替换成假实现。理由：避免把场景预期回放当作业务通过。日期/作者：2026-10-17 / Codex；无需大脑确认。

决定：用户授权前完成所有独立工作，真实调用保持待运行。理由：阶段提示词明确要求；已发出不索取密钥正文的环境配置问题。日期/作者：2026-10-17 / Codex。

## Outcomes & Retrospective（结果与复盘）

进行中。真实基线与 PR CI 尚未验证；不得宣称阶段完成。阶段结束在此记录实际通过数、未完成项与下一阶段建议。

## Plan of Work（工作计划）

里程碑一：重建两套 Python 3.11 环境，安装锁文件；确认 Node 22；使用只绑定回环地址的 PG15 新隔离库。原始测试运行日志放本机忽略目录，公开证据仅摘要、计数及安全错误原因。代码原因旧失败只记录；大面积失败即停问。

里程碑二：新增 `mingjing_core/timekit/clock.py` 的 Clock、SystemClock、FrozenClock 与模块访问函数。只把 consultation.today 的取时接到 Clock；测试 UTC 归一化、时区边界和 advance。其余业务取时保留到 P2。

里程碑三：在 tools/eval 实现 schema、目标协议、断言、回放、报告及固定 rubric。逐条转写 80 场景，补齐合成 seed/turns/expect/scripted。v4 专有的动作与工具断言标为 v4，并在 v3 报告中明确 n/a。fake 回放不根据 expect 动态制造结果；自测证明断言确实会失败。

里程碑四：用户同意后用现有 Kimi 配置和隔离 PG 跑 v3，可恢复、记录真实调用数、耗时及错误。固定评审配置与 rubric 哈希写报告，分数为确定性通过乘以 0–1 评审分。输出日期命名报告和 baseline-v3.json，不美化失败。

里程碑五：CI 加 pytest 和 fake self-test，完成本地验证、分阶段提交并发 PR 回 v4/main，核对 CI 结果。最终逐条阶段回执。

## Concrete Steps（具体步骤）

在仓库根运行（Python 指向新 Core venv，CHART_PYTHON 指向新 Charts venv，CORE_TEST_DSN 必须是本地隔离库）：

    python -m unittest discover -s tests -p 'test_core*.py'
    npm test
    node tests/dom.test.cjs
    node tests/report-settings.dom.test.cjs
    node tests/method-limits.dom.test.cjs
    python -m pytest tests/v4 -q
    python tools/eval/runner.py --mode scripted --target fake --self-test
    python tools/eval/runner.py --mode live --target v3 --model kimi

最后一条仅在授权和配置就绪后执行。安装、启动和校验步骤将在发现实际可用解释器与 PG 路径后补充。

## Validation and Acceptance（验证与验收）

分支与文档用 git branch、git ls-files 证明；旧测试计数写 `docs/v4/evidence/P0/v3-tests.md`。冻结到 T01 的时间，today 必须返回 2026-10-17，UTC 跨日边界仍按上海日期。所有 T01–T14、M01–M13、R01–R09、F01–F04、Q01–Q07、P01–P07、C01–C07、TA01–TA03、D01–D02、S01–S04、X01–X08、L01–L02 共 80 个 YAML 必须校验通过。文本、工具、回执、DB 与事件断言都须有正反例，重复回放结果相同。实测报告有分类成绩、调用数、耗时、rubric 版本/哈希、评审模型及 n/a 清单；三个典型失败只列 ID、断言、一句原因。CI 必须在 PR 上实测绿灯，未跑即未验证。

## Idempotence and Recovery（幂等与恢复）

仅创建新的隔离测试 schema/owner，删除范围严格限定为本次生成的测试对象。复跑场景先重置自己的命名空间，不清空任何共享用户。无生产数据库迁移；Clock 改动可通过回退提交恢复。真实调用的中间进度仅记录合成数据与元数据，可按场景恢复，不能把未运行场景记为通过。不要把 .env、PG 数据或原始日志加入 Git。

## Artifacts and Notes（产物与备注）

证据目录为 `docs/v4/evidence/P0/`；评测为 `docs/v4/eval/`；本地环境/日志位于忽略的 `.venv*` 或 `private/`。`00_先读我_使用说明书.md` 与 `10_验收清单_给Claude复核用.md` 不复制。

## Interfaces and Dependencies（接口与依赖）

Clock.now() 返回带时区 UTC datetime，FrozenClock.advance(timedelta) 更新冻结时间；get_clock()/set_clock() 管理默认 SystemClock。Target.reset(seed)、send(turn) -> TurnResult、inspect_db() 是后续 v4 Target 的接入点。P0 保持 v3 模型适配器及数据库 schema 不变。schema 用现有 Pydantic v2 与 PyYAML，pytest 来自现有 Core 锁文件。新增代码 ruff E,F,I,B,UP,SIM，单文件不超过 400 行（硬限600）、函数不超过60行、行长120。

## P2 待统一的直接取时位置

`mingjing_core/domain/report_schedules.py:108`；`application/report_schedules.py:99,169`；`application/memory.py:88,329`；`domain/contracts.py:43`；`adapters/tarot.py:32`；`adapters/delivery.py:62,93,131,143`；`adapters/core_report_worker.py:52`。P0 只改 consultation.today，保留其余行为。

## 修订记录

2026-10-17：创建自包含执行计划；记录旧约束差异、真实调用授权门槛、复用接口和 P2 取时清单。
