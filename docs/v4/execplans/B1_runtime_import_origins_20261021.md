# B1：App第三方import来源的执行后位置诊断

本ExecPlan遵循`.agent/PLANS.md`；工作树`C:/Users/Administrator/Documents/Codex/zhiming-v4`、分支`v4/p3-agent-runtime`，记录为北京时间。root最初只批准只读设计，现已批准新helper/新测试与critical_imports最小接线；只运行已批明确窄目标，不改旧断言，不访问Linux/服务器/PG/供应商/飞书，不安装依赖。

## Purpose / Big Picture

App runtime目前会核Python3.11、固定Core lock、安装版本与Requires-Dist，以及Core模块位于固定候选源码；四个关键第三方模块只要求有__file__。本设计让实际导入后的第三方文件与namespace搜索目录必须位于该解释器的受期望site-packages，外部来源用固定码拒绝。它是执行后位置诊断，不防已执行的.pth，不验证wheel字节、恶意模块伪造__file__/spec或控制器startup，更不能充当Linux证明。

## Progress

- [x] (2026-10-21 10:31 +08:00) 完整读App runtime/process/CLI/contracts、全部旧App纯/PG测试及新执行门测试；核调用与原安全断言。其他代理未跟踪文件只读、不碰。
- [x] (2026-10-21 10:32 +08:00) 仅用Test-Path核本机既有Core测试venv有限六个成员：四个叶子__init__.py存在，langgraph与langgraph/checkpoint的__init__.py不存在；未执行import或读取库内容，不能以目录布局声称已观测运行时spec或Linux。
- [x] (2026-10-21 10:32 +08:00) 完成固定模块/namespace、实际解释器期望根、错误/ABI边界和最小源/测试清单设计，提交root审阅。
- [x] (2026-10-21 10:42 +08:00) root批准新helper/必要support/新纯目标及critical_imports最小接线；runtime_capability/CLI/process/ABI与全部旧断言保持。新增源码已静态Ruff通过，准备先红钩子验证，尚无pytest。
- [x] (2026-10-21 10:42 +08:00) 接线前单例实际失败：Core来源均合法、第三方pydantic在外部目录却未拒绝，1 failed/0.20s，原件保留。
- [x] (2026-10-21 10:43 +08:00) 最小接线后新纯/临时目录组33 passed/0.50s；随后旧App纯契约40 passed/3.99s（含实际本机Python runtime-only/0PG对照），均退出0，无warning/skip。串行单链，结束立即归还测试位，不跑八PG或整库。
- [x] (2026-10-21 10:44 +08:00) 严格Ruff/格式及400/60/120静态通过；dependencies/runtime_capability AST完全未改，旧App纯/PG文件字节保持，原七项名单/ABI不变。证据/六件清单收口，停止新pytest。

## Context and Orientation / 完整调用链与复用

`tools/b1_linux_application_drill.py::main`默认无apply直接plan，不构造request或worker。显式execute→`process.run_worker`先校request/formal元数据门，再固定词法解释器-I/-B/-X启动child；`worker_code`先加载受审controller模块，插入候选源码，然后`runtime.runtime_capability`完成lock/版本/依赖及critical_imports，最后才进入backfill或fence。新检查只在这个已存在的critical_imports执行点，默认plan不加FS/PG/子进程。

复用`tools/b1_linux_application_drill_runtime.py::critical_imports`现有七个返回名称，保留`runtime_capability`的Python3.11、解释器身份、Core lock hash、安装版本完全相等和Requires-Dist全部断言与顺序。Core三个模块仍要求真实文件位于request.candidate_source真实目录，错误码`APPLICATION_IMPORT_ORIGIN_MISSING`/`APPLICATION_IMPORT_OUTSIDE_CANDIDATE`保持。收据`critical_imports`列表不增加namespace名字或新字段，ABI不变。

## 实际模块与namespace策略

固定第三方叶子是`psycopg`、`langgraph.graph`、`langgraph.checkpoint.postgres`、`pydantic`。这些明确叶子在当前本机既有测试venv均有__init__.py，应要求非空绝对__file__、与spec.origin一致且真实文件位于期望根。绝不把缺失/None文件路径当叶子成功，也不扩大为任意已加载模块扫描。

两个有限namespace祖先是`langgraph`、`langgraph.checkpoint`。它们已被导入叶子时加载，应从实际sys.modules取得并核其ModuleSpec与submodule_search_locations；不能凭叶子在根内就忽略父namespace混入外部目录。若__file__为None，仅这两个已知namespace允许：必须spec.origin为None、非空搜索位置、各位置为绝对实际目录且均在期望根内。若未来某个祖先成为有__init__.py的普通包，则按普通包文件和搜索目录双核，不能一概拒绝合法普通包，也不能将namespace的None当成功。

普通包的非空submodule_search_locations也须逐项在同根内，模块__path__与spec搜索目录两种观察须一致，不能只核其中一个而忽略另一个外部位置；普通非包模块的locations可为None。缺失spec、spec.name不符、叶子冒充namespace、namespace空搜索目录、任何外部追加目录、无效/非绝对/循环路径或文件/spec不一致均固定码拒绝。路径用resolve(strict=True)+is_relative_to校真实位置，不用字符串前缀；不读取文件内容，不修权限或复制文件。有限位置逐项最多16项、每项有长度限制，不能先无界list再限量。

Core叶子的原来源检查应在新第三方诊断前保持优先。现旧测试将所有import返回同一个外部__file__，原本保护Core开发源码拒绝；若一开始新增第三方spec检查会抢先改变其错误码。实现可先收集七个实际叶子并执行原Core检查，再执行第三方/namespace位置诊断，保留原assert，不改旧测试去迁就新顺序。

## 期望根来自运行中的解释器

formal唯一根是固定`/root/zhiming-core-releases/b9a89b6f84f7bebb640de080548010859aae630c/venv/core/lib/python3.11/site-packages`，不能由request或CLI传expected_path。可同时核运行中的sys.prefix真实位置等于固定Core venv、sysconfig默认purelib/platlib规范位置与该固定根一致；默认配置若漂到system site应拒绝，lib64正常别名只在resolve后同根时成立。formal仍依赖先前实际启动前元数据门保护，不替代它。

local根由**实际运行child**的sys.prefix及sysconfig默认purelib/platlib生成，沿用既有sys.executable与request.candidate_python真实身份相等检查；不得从request.candidate_source、candidate_python父目录猜Windows/Linux布局，更不新增调用者可传的根参数。即使local第三方来源通过，原local回执schema/admissible_linux=false、stage_acceptance=false不变。新helper内部可用替身建模sys.prefix/sysconfig进行纯反例，不能以这些模型称实际解释器或Linux通过。

## 文件、函数和测试范围

新增`tools/b1_linux_application_drill_origins.py`，提供无expected_path公共参数的`verify_third_party_origins(request, modules)`；内部`package_roots`只从formal常量或实际解释器sys.prefix/sysconfig求期望根，`check_module`/`locations`有界核观察值。它只接收critical_imports本轮实际import结果，namespace祖先从sys.modules读取，不接受CLI提供伪模块或新信任标志。

最小修改`tools/b1_linux_application_drill_runtime.py::critical_imports`收集原七个叶子、保留原Core来源检查后调用新helper，仍返回原七名称。helper在runtime顶层导入，worker在prepend candidate前即绑定controller tools来源。`runtime_capability`及CLI/process/default/formal元数据门/consumer不改，不加收据字段，不改B3显式hash列表；B3没有import这个App路径，App源码清单和新helper须在本片证据给精确hash供root受审。若后续增加独立App controller来源字段，应另行审批ABI，不混本片。

新增`tests/v4/release/test_b1_runtime_import_origins.py`及独立support，合成明确ModuleSpec/namespace位置、局部真实临时目录，不触实际/root或Linux。33项正反例覆盖有文件第三方、两个namespace同根、多位置全同根、普通包祖先、非package普通叶子；反例覆盖叶子None、缺spec/name错误、namespace空/None/外部第二位置、普通包外部__path__、file/spec不一致、路径前缀碰撞/无效路径、位置超限、formal根/运行prefix不符、caller字段不能重定向local根及原Core拒绝优先。异常只固定码，无路径/内容/版本细节外泄。resolve后的真实symlink/链接循环、特殊loader和真实Linux尚无专门实测，不把所写处理分支冒充已覆盖。

旧`test_critical_import_rejects_development_runtime_outside_fixed_candidate`与锁/Requires-Dist/默认/缓存原assert全部保留；`test_actual_local_interpreter_is_not_linux_proof`若批准验证，使用现有真实本机Pythonlocal链证明正常namespace可通过，仍不计Linux。现有App PG八项只读核影响，本轮设计不运行也不改；以后是否复验由root分配，不能新建PG环境凑证明。

## Surprises & Discoveries

本机有限路径观察确认langgraph和checkpoint没有__init__.py，而两个具体叶子有；这支持必须设计namespace处理，但不等于已执行import观测__file__/spec。包版本一致也可能从外部文件导入，因此版本检查与来源诊断必须分开。

worker在位置诊断前已加载controller和第三方导入代码；恶意.pth、模块顶层副作用或伪造元数据可能已执行。该检查不能前移成“未执行恶意代码”的安全保证。这里只核固定关键模块，不声称涵盖所有传递导入、二进制扩展、stdlib、共享库或第三方wheel完整性。

## Decision Log

2026-10-21 10:32 +08:00 / root、Codex：只读设计，未获准代码/pytest。固定叶子四个+namespace祖先两个、Core三个旧检查不变；formal固定根、local实际解释器推导，所有路径诊断仅执行后。无expected_path参数、无新ABI、无默认扫描，现有元数据门及来源hash审批保持。

2026-10-21 10:44 +08:00 / root、Codex：后续已批准最小实现与单一窄位，helper顶层绑定于controller。仅改critical_imports并新增helper/support/目标，旧App纯/PG文件完全不改；dependencies/runtime_capability AST原样，原Core拒绝优先与七项名单/ABI全保留。33新/40旧纯通过后即归还测试位，不扩大PG或目录回归。

新旧诊断顺序必须保留原Core外部来源固定码，不能改旧断言。namespace合法None只在明确ModuleSpec与全部受限目录都成立时接受；没有证明时拒绝，不靠None/空集合默许。局部真实临时目录或POSIX模型仅证明算法，Windowslocal成功不升级formal，真实Linux仍No-Go。

## Validation and Acceptance / Concrete Steps

获root批准并分配单一窄位后，先新增纯目标并保留必要红证据，再最小接线，随后新目标+旧App纯契约串行；剥离模型/PG/能力环境与关闭追踪/飞书。默认plan继续零新扫描/零PG/子进程；07 R02/F01隔离和失败即停不变量不变。

    python -m pytest tests/v4/release/test_b1_runtime_import_origins.py -q
    python -m pytest tests/v4/release/test_b1_linux_application_contracts.py -q

两条命令已获准依次执行，新33/旧40全通过。原七项收据列表不变，外部file/search path及缺证明固定拒绝，实际本机runtime-only对照未被namespace规则误拒；既有Core/锁/缓存断言全部保留。新增源≤400行/函数≤60/120列，严格Ruff/格式与源hash证据通过；不借旧整库/CI成绩为本片背书。

## Idempotence and Recovery / Interfaces and Dependencies

只观察已导入模块，失败不安装/修权限/删cache/重试/写收据；无迁移、配置、依赖、包b9或Charts变化。错误使用ApplicationBlocked固定码，不暴露实际源路径、库文件内容或私密正文。失败停止于backfill/fence前，但不能撤销已经发生的import副作用，必须明确这项局限。

## Artifacts and Notes

证据写入`docs/v4/evidence/B1/2026-10-21-runtime-import-origins.md`，私有原件位于任务`private/b1-runtime-import-origins-20261021/`；root统一审阅代码/manifest并发布，不动其他代理回归证据和日报。新纯模型不导入合成库代码；旧App契约按既有方式实际运行本机Python并导入当前已装依赖，这只是本机对照。

## Outcomes & Retrospective

已完成获准的后置位置诊断与最小接线：先红1项缺漏，后新33/旧App纯40通过、静态检查和旧源码/断言保持证据齐备。检查仅执行后位置/元数据，未防已执行.pth或恶意伪file/spec，未验证wheel字节、所有传递导入、真实symlink/特殊loader或Linux。没有PG、新环境、服务器、模型/飞书/外网请求，B1正式No-Go不变。代码待root统一审阅发布，不能将本机对照当Linuxproof。

## 修订记录

- 2026-10-21 10:32 +08:00 创建只读设计，明确namespace实际布局、固定/实际解释器根、旧断言优先级与执行后诊断局限；未编码测试。
- 2026-10-21 10:44 +08:00 记录后续实施授权、先红缺漏及新33/旧40通过；最小顶层绑定/原AST与ABI保持、测试位归还及未覆盖真实边界，冻结候选。
