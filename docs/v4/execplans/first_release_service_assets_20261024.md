# P3：把共同 writer 栅栏接入首发服务安装资产

本 ExecPlan 遵循 `.agent/PLANS.md`。所有记录为北京时间；仅开发和本机合成验证，无安装、服务控制或服务器授权。

## Purpose / Big Picture

新寿命 launcher 已能在实际 PG 与后台线程存活时保持共同锁，但现有 `deploy_core.units` 和 Hermes wrapper 仍直接走旧入口。本片生成供审核的三份 service、Hermes wrapper 和不含秘密的共同配置，让未来安装步骤有具体资产可审。只向显式新本机目录落盘，不替换现有 unit、wrapper 或任何链接，不运行 systemctl。生成与本机命令接线不能代替 Linux systemd、四个完整应用、排空、正式恢复及发布验收。

## Context and Orientation

复用 `tools/first_release_service.py::_arguments/_run/main` 的固定四角色及完整进程寿命锁、`first_release_service_binding.py::ServiceBinding` 的稳定数据库身份与受限 writer 核验、既有实际 PG/子进程测试支撑。旧 `deploy_core.py::units/skill_wrapper/parse_environment` 只作兼容背景，不调用其 freeze/install/publish 或硬编码 live 路径。README 与 CLOUD_DEVELOPMENT 要求 Core/Charts 两环境、显式环境和合成隔离 PG；不修改共享记忆、暂停线或 web/static/charts/skills/knowledge。

## Progress

- [x] (2026-10-24 11:46 +08:00) 核实旧三 unit/Hermes 尚未调用新 launcher，冻结本片边界。
- [x] (2026-10-24 11:55 +08:00) 三 service 与 Hermes 使用共同 entry builder；配置/环境/manifest 共七文件，默认零写，显式新私有目录独占生成。
- [x] (2026-10-24 11:55 +08:00) 唯一三个新目标首次3/3通过；真实底层 launcher/Memory 提交、错实际OID/维护拒绝、默认零IO/输出独占及入口拒绝边界成立。
- [x] (2026-10-24 11:56 +08:00) 根完整核实现、metadata/JUnit/log，四文件 Ruff/格式通过；独立审修正 consumer 的非-I门。当前测试槽均释放。
- [x] (2026-10-24 11:56 +08:00) 根完成可提交内容与runbook核对；分支推送/CI状态以Git元数据及日报为准，不把本机组件或静态资产当作正式候选/安装验收。

## Surprises & Discoveries

正式 restore 的 creator、端口及同 call 出生证明与 LocalInputs 严格绑定，无法靠改常量接通。本片不改任何恢复限制。旧 timer 的 Persistent=true 和到期任务有外部投递意义，不能在资产工作中擅自决定追赶策略。

Windows 即使执行 chmod(0600)，也不能据此认证 POSIX 私有模式；实际读取器明确以 ENTRY_PRIVATE_PERMISSIONS_UNVERIFIED 拒绝。三 unit 的 Linux entry argv 虽已渲染，不等于正式 entry 已成功加载环境或 systemd 已执行。

## Decision Log

2026-10-24 11:46，根：只生成供审核资产和必要薄入口。三 service、Hermes 共用同一显式配置、Core Python、CHART_PYTHON、候选根、workspace/SID/数据库 OID/writer OID；秘密只来自原受保护环境，不进入配置、argv、manifest 或回执。解释器或路径不得借 shell、systemd %/$ 展开或任意模块绕路。运行时必须继续经过原 launcher 的实际 PG/双锁门。

不生成或安装新 timer，明确保留已审核旧 timer 并保持停止；真实安装需保存/审阅原文件、drop-in、active/enabled 与到期任务。本片不恢复 timer、不强制启用飞书、不移除维护标记、不改变中央四项身份、不自动建账户、不给部署完成位。Linux 资产路径与本机实际命令接缝的验证范围必须分别写明，不能把映射后的 Windows 命令当作原样 systemd 执行。

2026-10-24 11:55，根及独立审：三 unit/wrapper 均先用固定 Core `-I` 执行固定 entry 文件，consumer 在 tools 导入前及正式 run/main 再核隔离标记。共同片段明确 Agent=true/容量3/池4，防旧默认关闭；保留 Web 5秒、飞书10秒重启间隔。wrapper 使用明确的 repr/f-string，避免合法 RELEASE 文件名破坏模板；私有读取核 open 前后完整 inode/大小/时间/权限/uid，拒绝注入 PG/PYTHON 环境。

## Plan of Work / Interfaces

新增 `tools/first_release_service_assets.py`：只接收明确的无秘密配置，校验统一绑定，渲染固定资产；默认只验证，显式本机写旗标才以独占创建和 fsync 写新目录。新增必要的 Hermes 薄入口或共用环境加载器只为统一配置到 launcher，不调用旧部署器、不读默认 env、不执行 shell；缺失/不安全配置用固定错误码拒绝，不泄露异常正文。实际公共字段由实现与根审在下文记录，禁止加入可手填的 Go/admissible 标记。

接口为 `Assets.parse/validate`、`entry_argv`、内部 `launcher_argv`、`render`、`execute(..., write_local=False)`；CLI 为 `--config --output [--write-assets-local]`。schema 精确字段与本机命令只列于 stage runbook，不另造证明格式。Linux候选/Core/Charts路径由40位SHA推导，输入OID/SID在生成时仅作格式校验。`LocalProjection` 仅用于显式程序库测试映射，不进入JSON/CLI，不授权正式身份。薄入口 `tools/first_release_hermes_entry.py` 实际运行才读两个有序受保护环境文件及固定共同片段，然后同进程调原 launcher；环境/来源失败不回退旧入口，也不输出成功JSON。

测试只新增本片目标，复用既有 restore/service fixture，真实 PG、文件锁和进程退出不能替代；native 接缝可采用已有合成 MemoryService 调度。先审实现再授权一条窄链，主线最多两个 pytest。若发现失败，保留原件，只修/复验受影响目标。

## Validation and Acceptance

与 07 场景 X03a/b 的渠道一致性及 X08 的故障保留边界有关，本片不是这些完整考题的通过证据。验收观察为共同配置生成的启动命令真实进入原 launcher；正常受限 writer 可提交合成原话，实际维护标记拒绝所有新入口；错绑定/路径/隐式 PG 或已有输出不覆盖；Hermes 参数和 stdout/退出码不被包装回执污染。生成器默认无 PG/子进程/文件写入，不触发任何真实模型或外发。

## Idempotence and Recovery

输出必须是新的本机审核目录，任一已有目录/文件、链接或漂移直接拒绝。写入中失败保留已写现场；不删除、覆盖、安装或自动重试。不控制 unit、不更新技能 manifest、不切链接，故无需真实部署回滚。旧 marker 与数据库保持原门语义。

## Artifacts and Notes

唯一首链为 `private/safe-narrow-d9868d868dac4db18563d5959a72f169/{metadata.json,pytest.xml,pytest.log}`，北京时间11:55:38.762839–11:55:44.306406，JUnit4.516秒/pytest4.53秒，3通过、0失败/错误/跳过/警告；根独立读三原件。使用唯一安全窄 runner、清凭据/关追踪、TZ=Asia/Tokyo，实际本机PG15、fixture打包父HEAD41cc907业务并仅在本测试新prefix7库/角色上恢复到8；新增控制源码为本片WIP，不冒称冻结候选。

第一node核三service/wrapper确实来自同一 entry builder；显式本机投影的内部launcher argv通过实际受限writer写一条合成Memory，原stdout与真实os._exit保持，native dispatch是唯一业务调度替身，不证明四完整应用。第二node真实错误OID与marker拒绝，完整Core状态/原文件保持。第三node验证默认0PG/子进程/写、新输出独占与已有产物保持、字面参数、原重启间隔、合法RELEASE路径wrapper AST，以及真实非-I冷入口在读缺失config前固定78；Windows私有读取实际拒权限未验，entry.run注入环境实际最早拒绝码为ENTRY_INJECTED_ENVIRONMENT_REJECTED，未假称走到POSIX保护或成功加载。wrapper真实子进程同样固定78/空stdout。没有stat/PG/锁/退出替身，没有重复旧生命周期矩阵或全量回归。

## Outcomes & Retrospective

供审安装资产及限定底层接线已实现、通过首3/3及根/独立静态审核。生产文件352/164行，新测试297/58行，最长函数47行，Ruff E/F/I/B/UP/SIM120与格式通过；未改旧控件、原生业务、共享记忆或暂停线。运行时真实SID/角色仍由原launcher核验，不信静态格式输入。

当前五个首发门仍 No-Go。未验证正式 entry 成功加载受保护环境、Linux systemd/权限/依赖、四完整应用/投递排空或真实安装、有效drop-in与timer状态；正式恢复、原中央及最终候选审核未因本片放行。真实模型、服务器访问、飞书和其他外部发送为零。

## 修订记录

2026-10-24 11:46 +08:00：先建计划，限定审核资产与真实接线，保留 timer/安装/正式恢复门。

2026-10-24 11:56 +08:00：登记实际3/3、原件与静态/独立修正，严格区分Linux渲染、内部本机launcher和正式entry未验。
