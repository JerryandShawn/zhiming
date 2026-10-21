# B1：正式执行入口接入Core venv元数据门

本ExecPlan遵循`.agent/PLANS.md`，所有记录为北京时间。工作树`C:/Users/Administrator/Documents/Codex/zhiming-v4`、分支`v4/p3-agent-runtime`。用户授权本机离线工作，root批准本片apply-only接线；root统一提交推送。不得访问真实Linux/服务器/供应商/飞书或安装依赖。

## Purpose / Big Picture

独立元数据门已有43项纯模型通过；本片让正式候选Core Python的每个实际启动先经过该门，拒绝不受保护的venv。默认校验不新增venv/root扫描，local演练不获得formal身份，PG工具、systemctl与Charts不套用Core专用门。元数据不是wheel字节验证，接线成功也不代表真实Linux演练或stage Go。

## Progress

- [x] (2026-10-21 10:20 +08:00) 读完整相关文件、调用链和旧夹具；先写本计划，划定七个执行接点与受审hash闭包。未改旧源码。
- [x] (2026-10-21 10:23 +08:00) 接线前新组maxfail10停止：10失败/4通过，9项明确缺守卫或固定绑定；1项新fence模型未stub platform.system，Windows版本探测碰禁止Popen，保留原件并仅修模型平台stub，不把这项记业务缺陷。
- [x] (2026-10-21 10:24 +08:00) 完成七处实际执行钩子、B7固定formal绑定及13源generator/helper-controller闭包；旧environment仅单FakePath正例增加stub/调用断言，原assert全保留。
- [x] (2026-10-21 10:25 +08:00) 新接线38 passed/0.72s；随后明确8个相关旧文件189 passed+7 subtests/16.03s，均退出0，无warning/skip。立即归还测试位，不追加测试；未跑目录/全量或新PG环境。
- [x] (2026-10-21 10:27 +08:00) 严格Ruff/format/diff及源码400/60/120静态约束通过；旧environment所有原assert保留，其他原test函数AST完全相同，证据与清单收口。

## Context and Orientation / 复用与保护契约

复用`tools/b1_runtime_trust.py::inspect_core_venv()`：无参数、固定b9 Core路径、非Linux在构造Reader前拒绝；只读metadata与有界pyvenv.cfg，返回`package_content_verified=false`。本片不改这个门或其43项纯模型测试。

复用`ProofRequest.validate/formal_paths`、`ApplicationRequest.validate`、`RestoreRequest.validate`和`verify_candidate`保留固定源码/manifest/ledger校验；不把执行检查插进默认CLI。`core_incremental_binaries.executable`仍保留词法venv身份、系统命令路径白名单与root不可写校验。全部-I/-B/-X、清凭据、关闭追踪、PG身份、撤销/收据与不自动开门保护不变。

## Plan of Work / 拟改文件与函数

`tools/core_incremental_binaries.py::executable`只在固定Core Python分支完成旧校验后调用元数据门，systemctl/pg_dump/pg_restore均零调用；Charts和任意程序仍拒绝。`tools/core_incremental.py::controller_digest`在原core_incremental*.py集合之外显式加helper，使其和consumer/core contracts同属批准controller hash。

`tools/b1_linux_application_drill_process.py::run_worker`在显式验证后、subprocess前formal核门；`tools/b1_linux_application_drill_fence.py::fence`在第二次实际Popen前再核。local模式保留原Windows离线演练且不能签formal Linux。

`tools/b1_restore_proof.py::generate`在platform/validate/dsns后、首个empty_target连接前formal核门；`tools/b1_restore_proof_process.py::run_worker`每次Python启动前再核。`ProofRequest.validate`和默认main无新扫描。generator_hash改为显式受审本地闭包，不增加收据字段。

`tools/b1_restore_replay.py::run_candidate`（额外B7直接Core入口）在formal实际启动前同时核固定candidate_source/python词法路径与Core门，不能给任意解释器借用固定Core的旁证；local及默认validate不变。

新`tests/v4/release/test_b1_runtime_trust_wiring.py`覆盖各接点拒绝零效应、成功调用/重复核验、local/default隔离及源hash闭包。旧`tests/test_core_incremental_environment.py`唯一受信FakePath正例显式stub门并断言Core一次/systemctl零次；保留原返回路径、uid/mode拒绝和任意程序拒绝所有断言，不给其他旧夹具造虚假Linux。

第三方import后置来源检查独立后续，不改critical_imports/App收据ABI。旧Native/App/B3 local夹具与consumer合成formal原断言不动。

## Surprises & Discoveries

B3默认main调用ProofRequest.validate，当前已读输入/manifest，但零PG/子进程；直接塞物理门会新增默认/root扫描，故前检仅放generate与实际worker入口。App fence和B7直接subprocess不经过Native executable；只改四处会漏掉它们。B7正式请求原先只约束绝对路径，必须把固定source/python绑定与门同做。

B3本地控制器import闭包除五份proof外，还包括三份replay模块、Core consumer contracts、新helper及实际使用的本地clock和包初始化三文件；候选动态导入业务代码由固定b9 manifest另行核验，第三方由锁/版本与后续来源审计分开。本片不声称这些hash验证安装wheel字节。

## Decision Log

2026-10-21 10:20 +08:00 / root、Codex：批准apply-only旧接点接线与既有environment正例stub，禁止扩大第三方import检查或ABI。默认不新增venv/root扫描、系统命令不套Core门，local演练明确非formal。既有安全断言原样保留，新的副作用拒绝必须由观察到零subprocess/PG证明。

generator显式列表采用相对项目根路径作hash键，纳入实际控制器依赖，任何helper/consumer/replay/clock变更会改变来源hash。controller保留原glob，再加受审helper。hash只是受保护文件与人工审批绑定，不是JSON的密码签名；实际Linux仍未验证。

2026-10-21 10:25 +08:00 / root、Codex：红组保留了新模型夹具的一个平台探测假红，修法仅补platform.system替身，不改formal拒绝/零副作用断言。旧测试仅批准的FakePath正例增加新门stub，所有旧assert及其他test函数AST保持；实际本机Python契约继续使用local模式，不将其改成合成formal成功。

## Concrete Steps / Validation and Acceptance

root分配单一窄位；运行时剥离模型/飞书/PG能力环境并关追踪。新接线目标先运行，必要时保留修改前固定码不出现的红证据；然后新目标及environment/Native/defaultCLI/B3/App纯契约等明确相关文件串行，禁止全目录/整库。07 R02/F01的隔离、失败即停及原话保护不变量保持。

    python -m pytest tests/v4/release/test_b1_runtime_trust_wiring.py -q

通过标准为formal guard失败时无子进程/连接、每次实际Core启动核门；三个默认CLI和local不新增物理门；PG/systemctl/Charts零Core门；固定source/python与源闭包反例有效。Ruff/format/AST400/60/120及git diff检查通过。真实Linux未运行，不能据此放stage。

## Idempotence and Recovery / Interfaces and Dependencies

无新依赖、迁移、配置、包修改或回执字段；只读门失败保留现状，不修权限/安装/删除/重试。默认行为不变；重复正式启动每次重新核验，不复用过期缓存。测试只用接口替身与现有本地契约，不创建新PG环境。

## Artifacts and Notes

证据写入`docs/v4/evidence/B1/2026-10-21-runtime-trust-wiring.md`；原始目标日志/JUnit/metadata在任务私有`private/b1-runtime-trust-wiring-20261021/`，不含库正文、凭据或DSN。公开文件manifest独立freeze.json，root统一审阅提交。

## Outcomes & Retrospective

本片离线接线已验证：新38项目标与相关旧189项+7 subtests通过，原默认/本地/安全拒绝和缓存保护保留；七处实际执行钩子、B7固定绑定、受审来源hash闭包均有定向反例。元数据本体43项成绩仍属于首片，本片没有追加复跑或借用其成绩称真实Linux通过。第三方import来源、控制器startup信任、wheel内容、stdlib及真实Linux环境未验证；零新增PG环境/模型/飞书/服务器访问，正式B1 No-Go维持。

## 修订记录

- 2026-10-21 10:20 +08:00 创建；列完整实际执行接点、源码hash闭包、旧断言保护和默认/本地边界，开始前先计划。
- 2026-10-21 10:27 +08:00 记录红组9项真实接线缺口+1项模型平台stub修正，完成38新/189旧+7subtests、静态与原assert保护证据；无真实Linux或新PG环境，归还测试位。
