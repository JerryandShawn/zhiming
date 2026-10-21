# Detached transport 静态设计备忘：尚未实现或授权采样

记录日期：2026-10-21，北京时间。本文只审阅当前源码和已有原生证据，不修改启动器、collector、守卫或运行时身份；没有运行解释器、测试、Git、格式器或新探针。本文不是新的执行批准，真实 supervisor、collector、baseline、trace 仍未由这些证据证明。

## 1. 已有证据的准确边界

- [09:40 原创建标志诊断](week-oct21-0940-job-observation-refused.json)：本次实际捕获第二个同 Job 成员，映像为系统 conhost，父 PID 快照指向 A。内层 total2/active0，因此原 total1 门槛仍拒绝；不回填09:08未知 PID 的身份。
- [09:41 detached A](week-oct21-0941-detached-identity.json)：只用 `DETACHED_PROCESS | CREATE_SUSPENDED`，0xC，不叠加 CREATE_NO_WINDOW。直接物理 base、原生 launcher 绑定 Core；内层 total1/active0，外层 total2/active1。A 保存原生 Python/OS 身份；`-I -S` 下 prefix 是物理 base。子程序固定停留0.75秒，项目/pytest未导入，未启 trace/profile。
- [09:42 detached B](week-oct21-0942-detached-bootstrap-help.json)：独立执行固定 bootstrap 的 `--help`，内层 total1/active0，外层 total2/active1，原始文件摘要与清理证据通过。B 没有再次输出全部 Python 内部身份，不能把 A/B 合成一次观测。
- 私有程序与归档的绑定见 [源码摘要索引](week-oct21-launch-artifact-binding.json)；事实分层见 [原生诊断复核](week-oct21-detached-launch-review.md)。旧拒绝不因后来的具名候选通过而变绿。

B 经过 bootstrap 的 `invalid_launch`、手工 Core site 路径及导入，但 argparse 帮助在解析处退出，未进入 `collect_core`。依据：[bootstrap:46](C:/Users/Administrator/Documents/Codex/zhiming-v4-p8/mingjing_core/adapters/charts/benchmarks/line_coverage_core_bootstrap.py:46)、[bootstrap:69](C:/Users/Administrator/Documents/Codex/zhiming-v4-p8/mingjing_core/adapters/charts/benchmarks/line_coverage_core_bootstrap.py:69)、[run:299](C:/Users/Administrator/Documents/Codex/zhiming-v4-p8/mingjing_core/adapters/charts/benchmarks/line_coverage_core_run.py:299)。`bootstrap_guard()` 位于 `collect_core` 内，见 [run:198](C:/Users/Administrator/Documents/Codex/zhiming-v4-p8/mingjing_core/adapters/charts/benchmarks/line_coverage_core_run.py:198)。B 没有调用它，没有运行 pytest、baseline、trace 或实际 `supervise`；导入 trace 模块不等于启用追踪。

## 2. 当前协议不能直接改名验收

| 当前源码事实 | 新协议最小要求；本文均未实现 |
| --- | --- |
| [bootstrap:12](C:/Users/Administrator/Documents/Codex/zhiming-v4-p8/mingjing_core/adapters/charts/benchmarks/line_coverage_core_bootstrap.py:12) 要求原生 `sys.executable == 固定 Core`；[bootstrap:30](C:/Users/Administrator/Documents/Codex/zhiming-v4-p8/mingjing_core/adapters/charts/benchmarks/line_coverage_core_bootstrap.py:30) 固定选项和 bootstrap，但没有验证 orig_argv[0] | 保留现有全部拒绝条件；新增具名 transport 的 orig_argv[0]/物理 image 双重绑定，不能把 sys.executable 改成允许 base，也不赋值或改写任何 sys 身份。 |
| [fingerprint:74](C:/Users/Administrator/Documents/Codex/zhiming-v4-p8/mingjing_core/adapters/charts/benchmarks/line_coverage_core_fingerprint.py:74) 校验 argv[1:7]；[fingerprint:94](C:/Users/Administrator/Documents/Codex/zhiming-v4-p8/mingjing_core/adapters/charts/benchmarks/line_coverage_core_fingerprint.py:94) 另拒绝错误实现、旧 trace/profile、错误 cwd/缓存 | 保留；不能让 A/B 或 `--help` 代替实际采样前这道完整守卫。 |
| [fingerprint:210](C:/Users/Administrator/Documents/Codex/zhiming-v4-p8/mingjing_core/adapters/charts/benchmarks/line_coverage_core_fingerprint.py:210) 指纹包括库、Core、base executable 和依赖；[fingerprint:239](C:/Users/Administrator/Documents/Codex/zhiming-v4-p8/mingjing_core/adapters/charts/benchmarks/line_coverage_core_fingerprint.py:239) 的 executable 写的是固定 Core 常量 | 增补原生实际值、物理 image、pyvenv.cfg、prefix 与 transport 创建标志，并进入稳定 runtime 摘要；不能只记录一个常量路径。 |
| [supervisor:102](C:/Users/Administrator/Documents/Codex/zhiming-v4-p8/mingjing_core/adapters/charts/benchmarks/line_coverage_core_supervisor.py:102) 仍从 Core wrapper 启动；[supervisor:295](C:/Users/Administrator/Documents/Codex/zhiming-v4-p8/mingjing_core/adapters/charts/benchmarks/line_coverage_core_supervisor.py:295) 仍为0x08000004 | 新 transport 必须显式选择物理 base、固定受控 launcher 环境和0xC，版本/名称与旧协议分开；未知 transport 一律拒绝，不能静默替换默认命令或旧回执。 |
| [supervisor:174](C:/Users/Administrator/Documents/Codex/zhiming-v4-p8/mingjing_core/adapters/charts/benchmarks/line_coverage_core_supervisor.py:174) 只以 launcher 已退出、Job active0 判定退出，不检查累计 total | 活跃清零不能证明没有短命 relay。A/B 的 total1 闸门保持；实际采样的阶段账本另审，不能借当前 `_wait` 直接验收新 transport。 |

建议名称仅为设计占位：`core-physical-base-native-launcher-detached-v1`。尚未在代码注册、未成为可选参数，也未取得采样批准。旧协议的缺失新字段、原 flags、未知 orig_argv[0]、不符映像/配置均不能被此名称自动豁免。

## 3. 精确新增身份字段

这些字段需在父协议与实际 collector 内核对并交叉绑定，而不是只抄 A 的历史 JSON。

| 位置 | 建议字段及校验 |
| --- | --- |
| 稳定 transport 身份 | `transport_id`、`transport_schema_version`、`creation_flags=12`、固定 cwd、固定 bootstrap 路径/原始 SHA；显式固定代码 full SHA、inventory/plan SHA，不自动升级。 |
| 原生解释器 | `observed_sys_executable`、`orig_argv0`、`observed_base_executable`；Core launcher 与物理 base 的固定路径/原始 SHA；保留实际 CPython三段版本、实现、架构/cache tag。必须与 A 清单使用的解释器版本一致。 |
| OS/配置 | 挂起时与子程序实际 process image 的路径/原始 SHA；`pyvenv.cfg` 路径/原始 SHA/声明 home；实际 python311/python3 DLL 路径/SHA。区分 uv 逻辑路径与 MSIX LocalCache 物理路径，不能仅凭 `Path.resolve()` 假定二者是同一文件或任意同 hash 文件均获准。 |
| 路径语义 | 实际 `prefix/exec_prefix/base_prefix/base_exec_prefix`、stdlib/Core site 路径、已加载模块来源。`-S` 的真实 base prefix 不改写成正常 venv prefix；Core site 仍只由现有固定入口追加，不调用 site.main 或放开 .pth/user site。 |
| 环境角色 | `launcher_injection=exact_fixed_core`、子程序原生 `launcher_consumed` 状态；当前 flags 和唯一 xoption。只允许在这次原生 Python CreateProcess 的新环境中放入固定 launcher；不继承未知值，不用 PYTHONHOME/PYTHONPATH 强造身份。 |
| 单次观测 | Popen PID、句柄查询 PID、子程序 PID、创建 FILETIME、完整原始 argv、这次缓存/输出路径、时间戳；必须彼此匹配。这些随运行变化的值不进入跨 baseline/trace 必须相同的稳定 runtime 摘要。 |
| 生命周期 | 外层 cap4、内层 cap3、无 breakaway、assign/resume 顺序、每阶段 total/active、异常/超时/清理结果；实际 collector 输出路径与内容 SHA 绑定到这次 supervisor 回执，不接受残留旧输出。 |

稳定身份需前后完全一致并进入 `runtime_sha256`；单次观测保留原始证据且逐项校验，不能为了摘要相同删掉 PID/真实 argv。缓存选项可沿用现有“fresh-private-cache”归一值，但仍须校验每次真实路径与命令相符。新增身份缺失或未观测不能用历史 A 补成当前事实。

## 4. 环境隔离与 Git 继承

[safe_environment:98](C:/Users/Administrator/Documents/Codex/zhiming-v4-p8/mingjing_core/adapters/charts/benchmarks/line_coverage_core_git.py:98) 会清凭据、provider、Git/pytest 与追踪项，但没有排除 `__PYVENV_LAUNCHER__`、PYTHONHOME、PYTHONEXECUTABLE、PYTHONPATH、VIRTUAL_ENV。A 中 CPython 原生消费 launcher 是本次事实，不是以后所有子进程环境都干净的证明。

最小职责分开：先从父环境移除全部这些继承项；只为已命名的 Python 子进程放回固定 Core launcher。MetadataGit 和 taskkill 等非 Python 角色不得收到它；读取前只记录固定键“存在/已清除/匹配”事实，不倾倒任意环境值。当前 [MetadataGit:137](C:/Users/Administrator/Documents/Codex/zhiming-v4-p8/mingjing_core/adapters/charts/benchmarks/line_coverage_core_git.py:137) 保存环境快照，[MetadataGit:196](C:/Users/Administrator/Documents/Codex/zhiming-v4-p8/mingjing_core/adapters/charts/benchmarks/line_coverage_core_git.py:196) 直接传给 Git，因此需要独立实现与反例保护，不能只在 supervisor 环境中清一次。

保留 MetadataGit 的固定二进制、配置原始摘要、ROOT与只读精确参数白名单、fsmonitor禁用和目标执行内禁子进程，见 [MetadataGit:171](C:/Users/Administrator/Documents/Codex/zhiming-v4-p8/mingjing_core/adapters/charts/benchmarks/line_coverage_core_git.py:171)。其 [creationflags:197](C:/Users/Administrator/Documents/Codex/zhiming-v4-p8/mingjing_core/adapters/charts/benchmarks/line_coverage_core_git.py:197) 仍是 CREATE_NO_WINDOW；本次 detached A/B 没有验证 Git 的实际 helper/conhost 链，不能顺手改它或假定无额外成员。

## 5. 数量门槛和超时预算

- A/B launch-only 阶段没有获准的辅助任务，内层累计 total1 门槛保持；未知新增成员仍拒绝。完成端口与 PID 列表只是身份诊断，不能代替 accounting，也不能按名字放行进程。
- 真正 collector 的目标执行外会串行调用 MetadataGit；成功运行会包含这些辅助进程，不能要求全程累计 total 为1。后续需要单独审定各元数据调用的实际映像、父子及创建时间账本；pytest目标阶段新增进程仍为0。不能把 launch-only 的 total1 原样当成整段采样门槛，也不能以“Git必需”为由直接删除累计数量审计。
- 外层一个协调器加内层最多三个进程已满 cap4，额外启动 taskkill 可能需要第五个名额。当前 [supervisor:148](C:/Users/Administrator/Documents/Codex/zhiming-v4-p8/mingjing_core/adapters/charts/benchmarks/line_coverage_core_supervisor.py:148) 会启动它；启动失败后 [supervisor:183](C:/Users/Administrator/Documents/Codex/zhiming-v4-p8/mingjing_core/adapters/charts/benchmarks/line_coverage_core_supervisor.py:183) 才走 Job 终止。不能承诺满额时 taskkill 一定执行，也不提高 cap4。
- A/B 私有小试已获准直接用已拥有的 Job 句柄超时清理；这不等于修改了实际 supervisor 的超时协议。后续必须明确选择有预算的终止协议：保留 taskkill 尝试及失败回执/Job兜底，或另审具名的 job-handle-only 策略；本文没有替 root 决定。禁止按已退出/回收 PID 另杀进程。
- 仍需分别验证：detached 睡眠超时、父进程先退出但后代仍活、元数据 helper 卡住、全额预算时失败路径、assign/query/resume/close失败。此前原 flags 的成功清理不能自动覆盖这些新 transport 分支。

## 6. 后续最低验收顺序；尚未执行，采样待 root 技术复核

1. 固定新协议、进程角色及超时策略，新增身份/环境字段与反例测试；不放宽旧拒绝，不把当前私有脚本直接改名为生产实现。
2. 提交含新实现的完整 SHA，再从既定历史起点重建包含自身工具/测试的完整分母和三个确切节点的静态计划。`execution_approved=false` 仍不是运行令牌。
3. 在独占 cap4 下分别验证新的完整身份守卫、依赖指纹、元数据 Git 链、detached 超时/孤儿及清理失败。保留每次拒绝和不完整收据，不重试到绿后覆盖历史。
4. 只有 root 另行批准确切节点后，才考虑各自全新解释器的 baseline/trace；本文不启动或批准它们。现有固定源/运行时前后检查、完整分母/冷文件0、精确生命周期、空业务数据读许可、禁网络及目标内禁子进程继续保持。
5. supervisor 的“子进程退出且 Job 空”与 collector 的成功收据是两张不同证据。需核同一次调用的路径/SHA、exit0、无超时/清理失败、新 transport 身份与 runtime 摘要，再使用既有严格 merger。跨不同 transport、不同稳定 runtime 或旧缺字段回执不混并；完整源码校验不能省略。

本备忘交付的是静态缺口与验收顺序，不是新覆盖率、性能结果、专业正确性、部署或上线证据。
用户已授权离线续作；这里的逐节点复核由本聊天 root 完成，不要求睡眠中的用户再次批准正常本地开发。
