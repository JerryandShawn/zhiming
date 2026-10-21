# B1：从实际恢复流程生成隔离恢复证明

本 ExecPlan 是活文档，遵循 `.agent/PLANS.md`。所有时间显式使用北京时间（UTC+08:00）。恢复证明是控制器在迁移原 stage 库前核验备份可恢复的证据，不是新的部署授权。

## Purpose / Big Picture

提供默认只校验、显式 apply 才写隔离目标的恢复证明生成入口。入口必须自己执行受审 pg_restore、比对 B2 精确备份内容、调用固定 b9 的前向迁移和撤销/收据重放、验证第二次无变化以及运行角色权限，不能读取手填 true 来签发证明。Windows 本机只输出不同 schema 的本地演练回执，现有控制器必须拒绝它。正式放行仍要求真实 Linux PG15；指令板 v2 与 30 号 No-Go 保持有效。

## Context and Orientation

工作树 `C:/Users/Administrator/Documents/Codex/zhiming-v4`。复用 `tools/core_incremental_contracts.py` 的固定 TARGET/MIGRATIONS、Request、digest/validate_backup/validate_restore；复用 `tools/b1_restore_replay_contracts.py` 的候选逐 blob 核验、raw ledger 校验与新输出保护；业务重放仅调用固定 b9 中 `tools.deploy_core.apply_withdrawals`，不导入当前 P3 业务代码。`tools/core_incremental_pg.py` 的全表摘要算法是精确恢复前后比较基准。B1 只含 0001–0007，0008 不能混入。其他代理拥有 B6/runbook、case proof 与主线生产文件，本任务仅新增 b1_restore_proof 前缀文件和本计划/独立证据。

## Progress

- [x] (2026-10-21 08:36 +08:00) 完整读指令板 v2、30 号、现有 restore/replay/PG port/执行单；确认 Docker 两次恢复均失败，停止修复，不建立 SSH。
- [x] (2026-10-21 08:36 +08:00) 定义本地与正式证明分离：本地 schema `b1-local-restore-drill-v1`，`admissible=false`；不能由参数升级平台身份。
- [x] (2026-10-21 08:57 +08:00) 五模块入口实现：默认 0PG，显式 apply 真实恢复/摘要/固定 b9 迁7/两次重放/权限流程，私有输出独占创建。
- [x] (2026-10-21 08:57 +08:00) 候选48 passed /45.58秒（39纯契约+9真实Windows PG15），0失败/错误/跳过/警告；严格 Ruff/format 与尺寸通过。
- [x] (2026-10-21 09:02 +08:00) 补连接前owner/writer同实例交叉核、formal返回前消费者ABI自校验。最终51 passed /77.38秒（42纯契约+9真实Windows PG15），0失败/错误/跳过/警告；原始JUnit/本地回执hash见独立证据。
- [x] (2026-10-21 09:07 +08:00) 空目标门补非默认namespace、public用户类型/域和非默认extension；enum/空schema真实反例在restore前拒绝且保留对象。最终53 passed /106.43秒（42纯契约+11真实Windows PG15），0失败/错误/跳过/警告；先前51为历史候选，最终源码/raw hash已更新。
- [x] (2026-10-21 09:12 +08:00) root实际证明-B仍读污染pyc；唯一候选Python子进程固定-X pycache_prefix=绝对系统null，新增真实缓存/argv反例。最终55 passed /109.72秒（44纯/实际本机Python契约+11真实Windows PG15）；两cache node格式后2passed/0.21秒不重复计数。新源码/raw hash更新，旧53保留历史。
- [ ] Linux 正式演练与正式 proof —— 环境阻塞，不以 Windows 替代。
- [x] (2026-10-21 09:16 +08:00) root已原子提交producer+consumer：本机f8e7f760d4be28447c5bf04be08285397be906d7→远端9c3966b2fc9e321c8358e8def15008738eeece44；本任务没有git add/commit/push。
- [x] (2026-10-21 09:28 +08:00) 第二窄片完成：support/B3纯contracts/App纯contracts/本计划/新portable证据五件。最终无.git、PATH空、无PG工具/管理DSN归档联合88 passed /13.90秒（B3 48+App 40），含两条POSIX0600修正；真实Windows PG11 passed /66.11秒独立复验。5生产工具/consumer/CI不改，未运行Linux。

## Surprises & Discoveries

现有 `validate_restore` 只校 schema、绑定 hash 与四个 true，没有运行平台或生成器出处检查。因此本地演练绝不能输出正式 schema；正式签发逻辑必须由实际 Linux/PG 查询、实际命令结果决定。现有 replay CLI 的固定数据库身份不适合每例唯一的新本地数据库；生成器会在独立候选进程内复用底层重放，并自己核固定正式目标或严格本地前缀，不放宽旧 CLI。

只读安全复核补出了三个实际边界：libpq 默认环境可在 identity 检查前改路由；源码逐 blob 相等不足以证明来自固定受保护发布目录/venv；PostgreSQL 默认 PUBLIC TEMP 仍属于 DDL。已分别前置拒绝隐式 PG 环境并规范 hostaddr/port、固定正式路径并核 root 所有权不可组他写、对精确恢复库撤 PUBLIC/writer 数据库权限后只授 CONNECT，最终加入真实临时表拒绝探针。另显式系统 null passfile 禁默认用户 home 回落；所有反例保留，不把历史30/33/46/47成绩当最终48。

第二片确认两套纯夹具都依赖本地Git b9历史：B3在修复后，App仍直接materialize，不能仅把B3归档绿当联合可移植完成。获root追加授权后让App复用同一强核候选helper，未删改旧断言。两处纯夹具文件补0600，避免Linux上默认umask与正式private regular校验冲突；本机是Windows，改后通过本机归档不能冒称已执行POSIX权限验证。

## Decision Log

2026-10-21 08:36 +08:00 / Codex：不改固定 b9 和既有 validator。正式目标仅 stage 的 `zhiming_core_b1_restore`，本地目标仅专用随机命名数据库；均须独立 owner/writer 且目标为空，不使用 clean、drop、replace。源 DSN 不进入 argv/证据；失败保持已恢复状态，不自动删除或重试。

2026-10-21 08:36 +08:00 / Codex：正式 proof 不接受 `--platform`、预制阶段回执或 true 汇总。应用流程自己观察 PG15 身份/系统、pg_restore 退出状态、schema4 内容摘要、七条 checksum、两次真实重放状态及 writer 权限。需要扩旧 validator 时先向 root 提案，不能静默改控制器契约。

2026-10-21 08:57 +08:00 / Codex：修复上述复核发现并保留新反例；父任务另授 B6 代理加强 consumer 和 Native 前置门，本任务不改其文件。空库只能证明 empty，回执明确 database_creation_observed=false。原 SQL drill 已消耗恢复库的流程不能顺序套 B3，交应用代理的显式 storage-preparation 轨保留空目标；B3 不放宽门、不清库兼容旧轨。

2026-10-21 09:02 +08:00 / Codex：producer每次连接前交叉核owner/writer的规范hostaddr/port/database；formal receipt返回前调用增强consumer自校验，避免生成admissible=true却ABI拒绝的误导回执。local仍不走formal签发。只加最小连接/自校验反例，不运行Linux探测；与consumer同原子提交由root处理，自己不git add/commit/push。

2026-10-21 09:07 +08:00 / Codex：空库不能仅无relations/functions，补user enum/domain、非默认namespace/extension有效检查和真实反例，不删除未知对象。当前测试支撑固定Windows工具路径且依赖完整b9历史，默认CI的11个PG用例会skip、纯夹具在Linux/浅克隆还可能失败；明确不继承wire固定回归。root批准提交后下一窄片再做可移植入口，不重排consumer、CI或正式目标护栏。

2026-10-21 09:12 +08:00 / Codex：匹配mtime/size的污染pyc能绕过只核源码且-B的入口，固定-X null-prefix在读前屏蔽旧cache，实际合成对照保留缓存字节不变，不触固定包。Windows真实试验不能当Linuxcache隔离放行；只改本任务唯一spawn，旧replay/Native其它spawn由root另片处理。

2026-10-21 09:28 +08:00 / Codex：纯测试不再借真实Windows pg_restore文件模拟默认校验，改为临时regular文件+实际hash，仅用于零apply契约；真实PG仍先核显式工具实际版本15与候选，再创建自己随机库。配置候选必须绝对路径且完整verify_candidate，不提供自动fetch或错误回退。App仅替换夹具候选来源，保留40个既有断言；新增4个B3反例保护显式pin、坏pin、版本15和缺工具零执行。不借测试路径放松正式目标/平台/端口/权限。

## Plan of Work

先实现只校输入与受保护输出的契约，再实现候选隔离进程及 PG 观察器，最后接显式 apply CLI。目标数据库/角色由独立获准准备步骤创建，生成器拒绝已有业务对象，不创建或修改别的库。候选进程只加载固定 b9，migration/grant/replay 结果结合实际 PG 查询验证，公开证据仅 hash/计数/身份元数据。

第二窄片只修测试前提：`B1_PROOF_TEST_CANDIDATE_SOURCE`优先且每次verify_candidate固定b9，未配置才用本地Git已有历史，不fetch。真实PG仅显式ADMIN_DSN opt-in，工具由绝对`B1_PROOF_TEST_PG_BIN`或现存Windows兼容路径提供并实际核15；pure fixture显式合成regular工具文件/hash，不把它拿去apply。最终验收包含B3与App两套纯contracts的真实无.git归档子进程：外部已核候选仍须完整blob核验，PATH为空且无管理DSN/PG工具；再独立真实WindowsPG复验，保留Linux未通过。默认浅Git CI仍须由root配置固定b9历史/候选，不借测试夹具放松正式入口。

## Concrete Steps

在主树使用已锁定 Core Python，清除模型/渠道凭据并关闭追踪后：

    python -m tools.b1_restore_proof --help
    python -m pytest tests/v4/release/test_b1_restore_proof_contracts.py -q
    python -m pytest tests/v4/release/test_b1_restore_proof_pg.py -q

完整 apply 参数见 `python -m tools.b1_restore_proof --help` 和独立证据中的实际接口。正式 DSN 仅用 B1_PROOF_OWNER_DSN/WRITER_DSN，私有文件仅通过 B1_PROOF_PGPASSFILE；普通非空 PG 路由/凭据环境会在连接前拒绝。本轮不运行 Linux、服务器或任何模型请求。

## Validation and Acceptance

对应 B1 B3/B7 和评测集 R 类的撤销/重放不变量：默认输入校验不建连接；live/业务库、非空目标、角色/端口/版本/候选/hash不符在写前拒绝；真实 schema4 dump 恢复摘要一致，迁7、最新撤销与 sent/uncertain 保护、第二次重放 changed=false，writer 无 DDL、两账本只读、业务 CRUD。篡改 dump/ledger、过期撤销、输出已存在与权限异常不得签 proof。Windows 本地回执必须被原 validate_restore 拒绝；真实 Linux 尚未执行必须明确未验。

## Idempotence and Recovery

校验可重复；apply 不是自动重试。目标已有对象或输出存在即停，命令失败保留新恢复库供审阅，不覆盖源库、不清空目标、不删数据。所有私有输入/输出路径拒绝 symlink，正式 POSIX 目录 0700、文件 0600，输出独占创建并 fsync；输出失败可能在 PG 提交后，必须保留状态停审。

## Artifacts and Notes

公开证据 `docs/v4/evidence/B1/2026-10-21-restore-proof-generator.md`，第二片见 `docs/v4/evidence/B1/2026-10-21-restore-proof-portability.md`；私有 dump/ledger 不入 Git。父任务独占日报与汇总，本任务提供状态由 root 记录。

## Interfaces and Dependencies

新增 `tools.b1_restore_proof*` 与 `tests/v4/release/test_b1_restore_proof*`，仅依赖锁定 psycopg、stdlib 与既有测试环境。不新增迁移或运行时依赖，不改固定包或旧 replay 行为。

## Outcomes & Retrospective

生成器本地实现与55项目标验证已由root提交；第二片完成88项目标归档联合验证与独立11项真实Windows PG复验，修复无Git/纯夹具误依赖真实工具与POSIX模式前提。所有PG结果仍来自Windows，输出只为不可放行的local schema。正式Linux环境两次非破坏恢复仍失败，正式证明与stage放行继续阻塞；真实模型/飞书/服务器调用均为0。Linux执行、固定头GitHub CI、默认浅克隆的固定b9候选准备仍未验证/未接，交root后续配置。五件冻结交root审查提交；未继承任何旧CI或宣称全阶段验收。

## 修订记录

- 2026-10-21 08:36 +08:00 创建；按指令板 v2 优先补 B3，并明确 Windows 回执不能解锁正式控制器。
- 2026-10-21 08:57 +08:00 完成本地生成器与48目标验证，补复核发现/路径/权限/null passfile/正式平台边界，记录独立证据；Linux与正式放行仍未完成。
- 2026-10-21 09:02 +08:00 补两DSN同实例前置门、正式consumer ABI自校验及51项目标验证，更新最终原始hash和历史口径；root统一stage/原子提交，本任务冻结后只读。
- 2026-10-21 09:07 +08:00 强化empty catalog并完成53项真实本地目标，更新最终hash，明确Windows路径/Git历史/CI前提缺口；待root提交后再另片做测试可移植性。
- 2026-10-21 09:12 +08:00 隔离匹配timestamp/size的旧pyc并完成55目标/2子集复验，保留实际body-free本地回执与raw hash，正式Linux及其它旧spawn不冒称通过。
- 2026-10-21 09:16 +08:00 root提交55里程碑后释放第二片，登记4件独占范围与无Git/合成纯fixture/显式真实PG15验证方案；不改运行工具、consumer或CI。
- 2026-10-21 09:28 +08:00 获批追加App夹具同源接点；完成最终无Git/PATH空/无PG工具与管理DSN的88项目标及独立11项Windows PG复验，补两处0600并明确尚无Linux验证，冻结五件和独立原始hash。
