# B1：固定 Core venv 的只读元数据保护门（独立原型）

本 ExecPlan 遵循 `.agent/PLANS.md`，记录使用北京时间。工作树 `C:/Users/Administrator/Documents/Codex/zhiming-v4`。本片只新增helper、纯元数据测试及本计划；不接旧入口、不改旧夹具、不读取库内容或执行包代码。root统一提交发布。

## Purpose / Big Picture

现有App/B3检查固定源码、解释器及祖先权限，却不覆盖venv包文件及pyvenv.cfg。元数据门要在未来任何候选Python启动前拒绝非root所有者、组/其他可写文件、危险链接和系统site-packages，避免只核版本metadata就误当受保护运行环境。本门不证明wheel字节、锁安装来源、第三方import位置或实际Linux演练；这些边界必须明确分开。

## Progress

- [x] (2026-10-21 10:03 +08:00) 获root批准新helper/纯测试/独立计划；完整读binaries/App/B3/Native及相关现有夹具，已发送影响清单，未改旧代码/断言。
- [x] (2026-10-21 10:08 +08:00) 新增独立helper与合成Posix元数据正反例源码，完整Core树/祖先/叶子/有限链接/有界cfg/变更复核和非Linux零读边界；无旧文件diff，无包内容读取、.pth执行或Linux环境访问。
- [x] (2026-10-21 10:08 +08:00) 新三源严格Ruff/120格式通过，AST静态400/60/120检查；未启动pytest，合成正例和真实Linux均尚未验证。
- [x] (2026-10-21 10:11 +08:00) 按root只读审阅收紧目录扫描：物理scandir逐项计数，在第MAX_ENTRIES+1项拒绝；受控Reader返回集合在生成pending前核长度/总待扫上限。finish除二次lstat外重新readlink比对原目标；新增对应纯元数据反例，仍未运行pytest。
- [x] (2026-10-21 10:15 +08:00) 四宽在途时未启动pytest；获root 10:14:27释放第4位后，仅跑本片纯目标43 passed/0.13s，退出0。原始stdout/JUnit/清理环境的metadata保留，结束已立即归还测试位；未追加测试。
- [ ] 旧入口接线、第三方import来源后置检查及真实Linux元数据验证 —— 未批准/未执行，后续单独审。

## Surprises & Discoveries

Linux venv通常有0777模式的python符号链接和lib64→lib。链接模式本身不作为可写文件处理，必须核root链接所有者、不可写父目录、有限允许位置及所有真实目标链；笼统拒绝0777会误拒合法venv。仅包metadata版本/Requires-Dist不验证wheel字节；只核解释器inode和父目录也不足以保护包叶子文件。

当前元数据范围仅固定Core venv及解释器目标/祖先。系统stdlib、共享库、root主动篡改、安装来源及第三方import真实来源不由此单门证明；不扫描Charts，不把正例替身写成真实Linux通过。

## Decision Log

2026-10-21 10:03 +08:00 / root、Codex：本片独占新 `tools/b1_runtime_trust.py`、新纯元数据测试/支持和本计划。公共物理入口无参数，只看固定b9 Core venv，非Linux先拒且不访问路径；内部纯检查器使用PosixPath语义和受控Reader协议，测试构造元数据模型。只读lstat/scandir/readlink及有界pyvenv.cfg读取，不读包内容、导入依赖、启动子进程、联网、安装或修权限。

有限链接策略为Core bin下python/python3/python3.11及顶层lib64→lib；解释器目标链有限跳数、root所有者和所有祖先保护，其他包/目录链接拒绝。pyvenv.cfg必须唯一include-system-site-packages=false。完整Core树每项核root/无组他写，边界数量/路径/文件类型与二次元数据稳定核验防止不完整扫描，输出仅hash/计数/固定码。

2026-10-21 10:11 +08:00 / root、Codex：目录数限制必须发生在物理扫描过程中，不能先无界收集再拒绝；Reader模型也先核长度和pending上限，再做去重与扩展。有限readlink目标在finish再次实际读取比对，不能仅凭lstat稳定声称字符串已复核。整树元数据、链接值复核仍不构成文件内容或系统stdlib完整性证明。

只接受标准Core根配置，额外bin/pyvenv.cfg作为非标准歧义配置直接拒绝且不读内容；不声称已经在真实Linux验证配置解析行为。门检查的是启动目标及Core包树，不能反向保护调用检查器的Python已发生的startup/site初始化，正式B0仍须保证控制器自身先受信。

## Context and Orientation / 旧接线影响清单

复用固定TARGET/RELEASE_ROOT常量；旧四接点暂不改：App ApplicationRequest.validate、B3 ProofRequest.validate、Core executable分支以及App runtime关键import后置报告。

`tests/test_core_incremental_environment.py::test_reviewed_command_resolves_without_path_and_keeps_venv_identity`仅FakePath uid/mode/parents，不含配置和包树；未来接线必须显式提供新guard的合成成功响应并新增调用断言，保留固定词法venv、不走PATH、危险程序先拒。systemctl/PG工具不得误套Core venv门。

`tests/test_core_incremental_native.py::NativeAdapterTests._release`是tmp HostFiles的部分manifest，无真实venv；FakeCommands绕LocalCommands，因此只接binaries时原控制流夹具可不变，不能据此报Linux。`tests/test_core_incremental_cli.py`默认仅校请求，不能因接线提前选择Native或探实际/root。

App application_request和真实本机PG全部local_drill=True，使用Windows解释器；正式门不能升级本地证据。默认plan、bad phase、scope、外部import拒绝、污染pyc/argv、清凭据与关追踪保护继续。B3 inputs/proof_db同为local模式，formal_paths测试仅核固定词法路径，不能顺便变真实/root扫描。consumer合成JSON没有执行门，不应改字段或放松既有判断。

`test_b1_existing_candidate_bytecode.py`的LocalRunner显式替换可用本机Python，只证明-I/-B/-X缓存边界，不能被新guard误当真实Linux正例；保留全部缓存和来源断言。未来接线还须核generator/controller源hash闭包是否纳入新helper；本片不改正式ABI或旧fixture。

## Plan of Work / Concrete Steps

先定义不可变元数据项、只读Reader和固定路径检查器。真实wrapper在Linux保护前不构造Reader；有界读取仅pyvenv.cfg，库源码/metadata文件只stat。纯测试覆盖合法根树、所有祖先、包叶子、.pth、cfg、有限链接/外部目标链、逃逸/循环/缺失/特殊文件、边界数与扫描中变化。测试正例只来自合成模型，无真实Posix运行证据。

    python -m pytest tests/v4/release/test_b1_runtime_trust.py -q

此命令仅在root释放单一测试位后执行一次；10:15已完成43项纯目标。静态Ruff/format与400/60/120约束可独立检查，不启动第二轮pytest或旧接线测试。

### 下一片接线提案（只读结论，尚未获准实施）

实际的默认边界须精确定义：App无apply时直接返回plan，Native默认仅读请求及controller代码hash；B3默认已有输入文件/候选manifest读取，但零PG、零子进程。本片之后的接线不得给这些默认路径新增Core venv、系统/root或第三方包树扫描。故不能直接把物理门塞入B3 `ProofRequest.validate`：该方法由默认CLI和worker共用。

1. `tools/core_incremental_binaries.py::executable`：只在 `name == candidate_python` 的固定Core词法分支、完成既有可执行文件保护后调用物理门，再返回原venv路径。PG工具与systemctl候选的解析/权限保护不变，不调用Core门；Charts不在该候选表中，仍拒绝。Native `PostgresPort.candidate`→`LocalCommands.run`通过此唯一分支复核，不改构造器或默认CLI。
2. `tools/b1_linux_application_drill_process.py::run_worker`：显式执行、`request.validate()`完成后而subprocess前，formal模式调用固定门，local模式跳过且保持 `admissible_linux=false`。`ApplicationRequest.validate/trusted_files`继续只做现有源/路径保护，默认plan不走此入口。child里的runtime重新验证不代替控制器启动前门；fence的第二次候选Popen亦须在其实际启动前复核，不能仅依赖较早一次结果。
3. `tools/b1_restore_proof.py::generate`：`platform/validate/dsns`通过后、第一次 `empty_target`连接前加formal运行时前检；`tools/b1_restore_proof_process.py::run_worker`在每次候选Python启动前再核，避免只在restore已发生后才拒绝。`ProofRequest.validate/formal_paths`不新增物理树读取，默认validate继续零连接/零子进程，local回执schema不变、不能走formal Linux门。
4. `tools/b1_linux_application_drill_runtime.py::critical_imports`：只在现有 `import_module`后核第三方psycopg/langgraph/pydantic各 `__file__` 的真实位置位于该模式解释器的受期望site-packages中，Core模块仍严格位于固定候选源码。formal期望为固定Core `lib/python3.11/site-packages`；local期望由其实际venv构造而不能填成Linux位置。此检查是导入后来源报告，不能声称阻止恶意.pth启动或验证wheel内容。是否把名称/计数或仅hash加入App运行收据须另审，不输出实际库路径/内容。

另一个未包含于原四接点的物理Core入口为 `tools/b1_restore_replay.py::run_candidate`（B7）：它直接subprocess启动候选解释器，不能借Native的executable门继承保护。若批准下一片，应在该实际formal启动前独立调用固定门；local/默认validate不改。其原请求仅核绝对路径，需同时复用formal固定source/python语义，不能让任意解释器获得一个“固定树已核”的旁证。

源闭包：`core_incremental.controller_digest()`当前只glob `core_incremental*.py`，已覆盖consumer `core_incremental_contracts.py`但不含新helper；下一片须显式纳入新helper。`b1_restore_proof.generator_hash()`当前只glob五份B3文件，亦不含新helper及实际consumer/replay依赖；应采用显式受审列表（B3五源、helper、consumer contracts和实际三份replay源），而非任意全tools扫描。这样新helper和consumer的变更都会改变已审generator/controller hash。App目前无controller hash字段；若新增来源闭包收据，需独立列出App实际七模块及共享依赖，先审ABI。hash仅为受保护文件/人工审批绑定，不能把无签名JSON当密码签名。

拟新增接线反例为：每个formal实际启动在门拒绝时零subprocess/零PG；默认三CLI门构造即禁用且仍可默认校验；local既有Windows真PG/纯组不调用物理门、不能获得formal位；systemctl/PG/Charts不调用Core门；外部第三方来源固定码拒绝；helper内容hash变化令generator/controller闭包变化；返回词法venv与-I/-B/-X/取消清凭据保护保持。

旧夹具只拟最小扩展：environment.py的受信Core FakePath正例显式stub新guard并断言一次调用，systemctl正例断言零调用，原uid/mode和任意程序拒绝断言不变；Native `_release`/FakeCommands不必造真实venv或改旧断言，新增实际LocalCommands分支目标覆盖即可。App `application_request`、B3 `inputs/proof_db`均保持local模式和现有锁/PG实测；formal_paths原四断言不改。App现有外部Core import反例保持，新加第三方外部/受信模型反例。consumer合成formal shape与原Windows拒绝反例不更改平台来源或既有ABI；若root选择增加收据字段或固定hash消费门，必须另外列consumer/upgrade fixture变更，未批准前不动。

## Validation and Acceptance

07 R02/F01的受保护发布与失败即停不变量不变：不受信条目必拒、无副作用、错误只固定码，正常符号链接不破坏词法venv身份。元数据通过不等于Linux、包字节准确、安装来源可信或stage Go。

## Idempotence and Recovery / Interfaces and Dependencies

公共inspect入口只读、无参数、固定Linux Core venv；内部元数据Reader仅供Python测试建模，不在CLI暴露路径/信任标志。失败不chmod/chown/删除/写盘/重试。无新依赖、迁移、服务、正式schema字段或Charts变化。

## Artifacts and Notes

本片尚未创建任何Linux/PG证明；测试结果待独立证据 `docs/v4/evidence/B1/2026-10-21-runtime-trust.md`记录。公开记录不含文件内容、完整环境、凭据或正文。父任务独占日报与发布。

## Outcomes & Retrospective

已完成影响审查、独立元数据原型、纯测试及静态检查；10:15唯一纯目标43 passed/0.13s，涵盖有限符号链接、系统site=false、整树保护、目录有界与扫描稳定性。没有接四旧入口、默认CLI或B7，也没有验证真实Linux、wheel字节、stdlib或第三方import来源。四宽仍占满时无pytest，root明确释放后才运行本片一次，结束立即归还测试位；本片无Linux环境访问、PG、模型、飞书或外部调用。现五门和No-Go不改变。

## 修订记录

- 2026-10-21 10:03 +08:00 创建；明确仅新helper/纯元数据测试、有限链接策略、旧夹具影响与真实Linux/包字节证明边界。
- 2026-10-21 10:08 +08:00 完成独立源码与静态检查，增加标准配置/文件读取范围和启动前置限制说明；未运行测试或接旧入口，4宽链配额保持。
- 2026-10-21 10:11 +08:00 按审阅增加物理目录扫描/模型待扫队列上限及readlink原目标二次复核；新增纯反例未运行，保持package_content_verified=false与系统stdlib未覆盖边界。
- 2026-10-21 10:16 +08:00 记录唯一纯目标43 passed/0.13s与立即归还测试位；准确列下一片apply-only接线、B7额外入口和源闭包提案，均未实施。正式Linux仍No-Go。
