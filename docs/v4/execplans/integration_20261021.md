# 集成：从固定 v4/main 接入 P1b 并核完整本机门

本 ExecPlan 遵循 `.agent/PLANS.md`。所有时间为北京时间 UTC+08。当前08:57口径：主代理已普通合P1b、在固定2ca完成本机功能门，并观察同精确头Node22配置push CI全部success；后续文档续作独立记录。本片不授权服务器、模型或消息操作。

## Purpose / Big Picture

把已独立验证的 P1b 候选接入独立 v4/integration，记录精确版本与完整回归证据，再继续 P3 等后续线路。依据 33 号第一节第 2 项，顺序为 P1b→P3→模块→命理→前端→文档，每合一条都解决实际冲突并跑 Core、v4、Charts 和当前前端。任何本机结果均不代表已经部署、真实供应商就绪或允许合入 v4/main/main。

## Context and Orientation

唯一工作树：`C:/Users/Administrator/Documents/Codex/zhiming-v4-integration`，分支 v4/integration。07:41 只读核到 HEAD `b9a89b6f84f7bebb640de080548010859aae630c`，tree `8ed180539f655124fc76d8981df318a337292ff1`，工作树干净、尚无 merge；根主 P3 树不由本片修改。P1b 固定候选 `8087d7fa64839dc5a080491fd5db4e358f5814ec` 已由主代理 fetch 核同头 CI run 39466971699 success，本片不把这次外部核验冒称自己重跑 CI。

复用 `.github/workflows/ci.yml` 的原命令、`tools/eval/targets/local_db.py:verify_local_postgres/local_dsn`、`tests/v4/conftest.py:p2_repo` 与各 Core unittest 自有 UUID schema。PG 必须是本机 loopback PostgreSQL15 的可丢弃测试库，测试使用全新独立 schema 并沿既有夹具收尾；不碰 stage/live/生产，不复用真实资料。

解释器复用已存在的 `C:/Users/Administrator/Documents/Codex/zhiming-v4-p2/.venv-core/Scripts/python.exe` 与 `C:/Users/Administrator/Documents/Codex/zhiming-v4/.venv-charts/Scripts/python.exe`。Node 模块复用 `C:/Users/Administrator/Documents/Codex/zhiming-v4-p2/node_modules`，只配置 NODE_PATH/PATH，不安装依赖、不创建 junction、不改锁文件。Core 与 Charts 环境不合并。

## Progress

- [x] (2026-10-21 07:41) 核清独立树 b9 精确头、P1b 原 CI 脚本及现有本机依赖路径；本片尚未 merge、提交或启动全量。
- [x] (2026-10-21 07:44) 私有 runner 默认 plan_only 验证成功，tests_executed=false；静态 Ruff/format/AST 检查通过。
- [x] (2026-10-21 07:45) 明确系统 Node24 与 CI Node22 不等价；保留 Node24 可做的本机 DOM/build，另记 node22_parity=false，不安装 Node22。
- [x] (2026-10-21 07:53) 主代理普通 merge P1b 固定候选为 49d40dd，记录双父、tree 与原 1–7 不变的证据；随后文档提交固定为 2ca1378。
- [x] (2026-10-21 08:00–08:19) 主代理从 clean 2ca1378 的 archive 串行完成 Core→v4→Charts→legacy frontend。Core 08:00:37 开始，v4 08:13:38 开始，均在 00–15 分窗口；全部 14 条检查命令退出 0，没有 deferred/skip。
- [x] (2026-10-21 08:26) 逐份完整读取 15 份私有安全日志及汇总，摘录实际数字、警告和原始字节 SHA256，形成 `docs/v4/release/integration/2026-10-21_P1b.md`；本片未重跑测试。
- [x] (2026-10-21 08:28:48 核验，08:57活节补记) 精确2ca1378的push39518064447/core118954903079全部completed/success，包括Models及清理。该workflow配置Node22，作为独立补充；原本机Node24 functional_passed=true、node22_parity=false、gate_passed=false及外层exit1全部保留。08:26两run在途是历史，PR run39518095632终态本次未复查。

## Surprises & Discoveries

08:57补记：Node22是同头Hosted workflow配置与成功步骤的证据，并非本机版本变更。CI成功覆盖精确2ca；f756731/5658d640及本次只有文档更新，没有重新跑全部套件，也不借此声称后续业务树全部绿。

新树没有自己的 venv/node_modules，但可直接用现有绝对解释器与 NODE_PATH，无需创建依赖 junction。当前未包含 web/ 新源码，前端门是根 package.json 的旧原生页面检查，不能写成新前端已验收。

07:44 核系统 Node 为 v24.15.0，Codex 已捆绑 Node 为 v24.19.0；两者均非 CI 明确要求的 22。主代理裁定继续做已有 Node24 的完整 DOM/build，结果只记本机功能证据；Node22 对齐保持未验/No-Go，之后以同集成提交的 CI22 作为独立证据，不能下载新运行时来掩盖此边界。

08:19 的实际报告为 functional_passed=true、gate_passed=false、actual_node_version=v24.15.0；14 条检查自身全为 exit 0，而主代理观察到外层 PowerShell 最终 exit 1。原计划中 parity-only 预期退出 2 没有成为这次外层实测值，必须分别记录，不能将 exit 1 改写为 2，也不能据此谎报有功能套件失败。本片只读证据，不修改 runner 或门判定。

完整 v4 有 1 条 Starlette/AnyIO BlockingPortal 弃用警告，前端 build 有 caniuse-lite 过期提示；两者都没有造成命令失败。现有锁不更新，本片未安装依赖。fake/c21 汇总中的 85 次 model_calls 各自都是脚本模拟调用，不能误称真实 Kimi 请求。

## Decision Log

2026-10-21 08:57 / root：按08:28:48实际保存的GitHub jobs终态关闭固定2ca的Node22配置CI补充门，不重跑已绿功能套件，不改原Node24报告。下一P3等业务普通合并须新固定archive和完整门，未合v4/main/main或部署。

2026-10-21 07:41：只借已有锁定依赖，不安装、不改 lock、不改变 B1 固定 b9 发布包。集成可新增 P1b 0008；0001–0007 原字节/校验和不变，0009 留给分区/话题，不能因新集成把 B1 变成 schema8 包。

2026-10-21 07:44：私有 runner 从明确 expected-head 的 git archive 创建独立 source 快照，在该快照运行，不从持续变化的工作树采集；构建 CSS 也只落入私有快照。全量 Core/v4 只能在北京时间每小时 00–15 分开始。runner 不自行开并行工作，各命令串行，进程位由主代理统一调度。

2026-10-21 07:45：私有 runner 支持显式 --node-executable 指向已存在解释器；记录 actual_node_version/actual_major/node22_parity。Node24 前端测试全过时 functional_passed=true，但 gate_passed=false、退出码2，明确区分功能证据与 Node22 完整门。命令失败为退出码1；不因 parity 缺口略过可做检查。

2026-10-21 07:46：按主代理最新四位调度，新增 --suite all 同一固定快照依序运行完整门。每个 Core/v4 开始时重新检查北京时间；Core 完成后如 v4 已错过 00–15 分，则该阶段标 deferred_next_hour、tests_executed=false，立即继续可做的 Charts/legacy，不能假造 v4 已执行或睡到下小时占住调度。

2026-10-21 08:26：保留 07:53 的历史“尚无回归”记录，另以实际 08:00–08:19 结果更新活文档；候选和证据均固定 2ca1378/tree 665a3b0，不借用后来 P3、P6 或 CI 分组提交成绩。记录原始 result/source/log 字节 hash，合成场景输出与完整日志继续只存 private，tracked 回执只摘录数字。

2026-10-21 08:26：读取实际迁移测试 `test_quota_guard_migration_pg.py`，全 v4 与 models 两次套件均零 skip、零失败，因而包含 7→8 保数据/重复 initialize、旧清单拒新库和降权运行角色禁止 DDL/篡改账本的真实 PG 断言。它不是 B1 Linux 演练或任何远端部署证据；0008 不进入 B1 固定 b9 包。

## Outcomes & Retrospective

截至 2026-10-21 08:26，主代理已完成普通 P1b 合并，并在固定集成 2ca1378/tree 665a3b0 上取得本机全部功能通过：Core 553、v4 1296、models 889（覆盖率 96%）、评测框架 self-test 48、fake 80/80、c21 scripted 80/80、Charts 60+10，以及六条旧页面 DOM/语法/build 命令。所有 manifest 检查 exit 0、skip=false；没有将重叠套件相加成独立测试总数。组合阶段回执及完整 hash 索引见 `docs/v4/release/integration/2026-10-21_P1b.md`。

08:57更新：精确同头push CI的Node22配置门已有全部success；PR触发的另一run终态未复核，不声称两run均绿。本机Node24.15.0 functional_passed=true、gate_passed=false和外层PowerShell exit1仍原样保留。本片仅文档收口，无重复套件或业务修改；主代理已推后续文档，后续业务树另验。真实供应商、B1 Linux、stage、生产、飞书均未验证、没有访问。

## Plan of Work

主代理先核 v4/integration 的当前 HEAD、P1b 固定头和同头 CI；仅普通 merge，不 rebase、强推或合到 v4/main/main。检查迁移 0008 新增且原 1–7 不变，保存 merge 的双父提交和 tree；如果存在未预期冲突先记录再按代码事实解决，不能覆盖运行时/中央额度守卫的真实分工。

在 merge 已提交的新精确头运行私有 runner。它默认只列计划；--execute 需 clean v4/integration、匹配 --expected-head、全新 private 输出目录和现存依赖。环境清供应商凭据、PGSERVICE/隐式 PG 路由、代理与追踪；设置隔离 CORE_TEST_DSN、CHART_PYTHON、NODE_PATH。Python/Charts 子进程只许 loopback socket/DNS；PG 身份另外实际验证15。报告不输出 DSN/密钥，日志只留 private，复制回执前继续脱敏。

## Concrete Steps

以下是原准备时交给主代理的本机命令，本子代理没有运行 merge 或任何 --execute；主代理后来完成的精确版本与实测见 Progress 和阶段回执。先记录：

    git -C C:/Users/Administrator/Documents/Codex/zhiming-v4-integration rev-parse HEAD
    git -C C:/Users/Administrator/Documents/Codex/zhiming-v4-integration merge --no-ff 8087d7fa64839dc5a080491fd5db4e358f5814ec
    git -C C:/Users/Administrator/Documents/Codex/zhiming-v4-integration rev-parse HEAD HEAD^{tree}

将下列 `<merge-sha>` 替换为主代理实际提交。08:00–08:15 首选整体串行入口，它仅占一个顶层检查位；默认去掉 --execute 只打印计划：

    C:/Users/Administrator/Documents/Codex/zhiming-v4-p2/.venv-core/Scripts/python.exe private/integration_20261021_runner.py --suite all --expected-head <merge-sha> --node-executable "C:/Program Files/nodejs/node.exe" --execute

单独阶段入口也保留，每条必须新输出目录。如果整体运行将 v4 记为 deferred_next_hour，下个整点窗口只补该阶段；不重复已完成的其他门：

    C:/Users/Administrator/Documents/Codex/zhiming-v4-p2/.venv-core/Scripts/python.exe private/integration_20261021_runner.py --suite core --expected-head <merge-sha> --execute
    C:/Users/Administrator/Documents/Codex/zhiming-v4-p2/.venv-core/Scripts/python.exe private/integration_20261021_runner.py --suite v4 --expected-head <merge-sha> --execute
    C:/Users/Administrator/Documents/Codex/zhiming-v4-p2/.venv-core/Scripts/python.exe private/integration_20261021_runner.py --suite charts --expected-head <merge-sha> --execute
    C:/Users/Administrator/Documents/Codex/zhiming-v4-p2/.venv-core/Scripts/python.exe private/integration_20261021_runner.py --suite frontend --expected-head <merge-sha> --node-executable "C:/Program Files/nodejs/node.exe" --execute

实际完整命令与 CI 映射如下；所有 python 为上述 Core，除最后一项质量检查明确使用上述 Charts：

    python -m unittest discover -s tests -p test_core*.py -v
    python -m pytest tests/v4 -q
    python -m coverage run --source=mingjing_core.models -m pytest tests/v4/models -q
    python -m coverage report --fail-under=85
    python tools/eval/runner.py --mode scripted --target fake --self-test --output <private>/fake
    python tools/eval/runner_v2.py --mode scripted --stop-file <private>/c21-stop.json --once-file <private>/c21-once.json --output <private>/c21
    python -m unittest tests.test_core_charts tests.test_core_knowledge tests.test_core_calculation_boundaries -v
    <Charts-python> -m unittest tests.test_chart_quality_v5 -v
    npm test
    node tests/dom.test.cjs
    node tests/report-settings.dom.test.cjs
    node tests/method-limits.dom.test.cjs
    node --check static/app.js
    npm run build

npm 在 runner 中以选定 node 执行现有 npm-cli.js，依赖来自 P2；无需 shell 拼接或 npm ci。没有 E1/live/probe 命令，也不会触发真人开始闸门。

## Validation and Acceptance

每一项都要记录该固定 merge head/tree、命令、退出码、耗时、测试数和跳过项。Core 实际 calculator 必须走 CHART_PYTHON 真引擎；Charts quality 在 Charts 环境消除可选库 skip。任何正数 skip 都单列为 gate 未完成，不能记作全部通过。Models coverage 至少85；fake self-test只验证框架，c21 scripted仅脚本证据，不能替代 v4 Runtime 或真实模型分数。

Node24 本机 DOM/build 的实际结果独立记录；同集成头 Node22 CI 成功之前，Node22 门保持未验。P1b新迁移用全新 UUID schema实际初始化，并另外核 prior7→8 增量、重复verify无变化和运行角色无DDL既有目标；尚无这些结果时明确未验证。引用07场景集的脚本属于相应 target，不改冻结 v2.1 基线断言。

## Idempotence and Recovery

每次 runner 使用新 private 目录和固定 archive，coverage/fake/c21 输出互不覆盖。新测试 schema 的创建/清理由真实既有夹具负责；不恢复或导入真实资料。不因失败重试真实供应商，所有脚本模式不带密钥。失败保留源码快照/私有日志，只改候选实现后在允许窗口从新精确提交复验；不 reset 或改写已共享集成历史。需要撤回集成时由主代理审普通 revert，不影响 b9 发布包或任何服务器。

## Artifacts and Notes

可提交产物为本 ExecPlan 与集成阶段回执 `docs/v4/release/integration/2026-10-21_P1b.md`。私有本机入口 `private/integration_20261021_runner.py` 与网络护栏 `private/integration_network_guard/sitecustomize.py` 被现有 private/ ignore，不纳入产品包。实际报告在 `private/integration-checks/20261021-080036-all-ad7ee171/result.json`；tracked 集成回执只摘录脱敏汇总、原始 hash 与对应固定提交，不能把 private 日志或完整 DSN 加入 Git。

## Interfaces and Dependencies

没有新增业务接口、依赖、锁文件或迁移。本片只列并复用各 CI 原检查；P1b 0008 来自候选源分支，由主代理正常 merge。没有新运维授权令牌协议，也不借 B1 授权放行 P3 或生产。

## 修订记录

- 2026-10-21 08:49 root按08:28:48已保存的只读jobs终态补记：精确2ca的push CI39518064447/core118954903079全部success，含Models和cleanup；不继承到仅文档f756或后续业务树，不改本机Node24原门与外层exit1。
- 2026-10-21 07:41 建立 b9→P1b 的版本、迁移与完整本机门计划。
- 2026-10-21 07:44 准备固定 archive 私有 runner，默认只计划，静态检查通过。
- 2026-10-21 07:45 根据实测与主代理裁定保留 Node24 完整功能证据，并将 Node22 parity 单独标未验；未执行套件。
- 2026-10-21 07:46 对齐四位调度为整体串行入口，v4 错过启动窗口则明确推迟，仍继续 Charts/legacy。
- 2026-10-21 08:26 按实际固定候选的完整本机结果更新四活节，记录 Node24 功能通过、外层 exit 1、Node22 CI 在途以及两类警告；没有重跑或更改门。

## 2026-10-21 07:53:24 +08:00 root合并候选与门状态

已从真实b9创建独立v4/integration，计划提交092ec036后，普通--no-ff合并精确P1b8087d7fa为 **49d40dd69d299200d4549f22b70931dbf47ac171**，双父092ec036/8087d7fa，tree **8b0754ef42ab34383894064da236ba840a947cf8**。无文本冲突，无rebase/强推，尚未推送或合入v4/main/main。7份原迁移git blob逐字节不变；唯一新增0008_model_usage.sql SHA256=5eef5d65363baa0ab4dc8ec9763b85136f4ba249688330b9cd8448f0b39ccbcb，0009未创建，B1包仍b9/1–7。此后仅更新本计划，最终固定头以runner expected-head为准。

尚无本次完整回归，不能以P1b源头CI代替集成头。08点准备四位以内执行P3Core/P3v4/M8及本集成串行门。root核runner后补入实际本机PGbin绝对路径并验证pg_dump/pg_restore存在，避免重演01点工具路径失败；测试TZ显式Tokyo，记录/调度仍北京。Node实际24功能证据与Node22CI门分开。全部检查只隔离PG、清凭据/关追踪、Python网络仅loopback，未发真实模型/飞书或访问服务器。
