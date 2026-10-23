# 主线 CI 窄分组静态证据

记录：2026-10-21 08:18，北京时间 UTC+08。只有两份主树workflow添加concurrency；不改变on/name/jobs/steps/check名字，不手动取消旧run。本片无pytest、提交、推送、真实模型、服务器或飞书操作。

## 只读排队事实

08:08–08:10 GitHub connector GET 完整分页，queued35条、in_progress20条，requested/waiting/pending均0。以下是workflow run数量，不能当成job数量、账户并发额度或当前仍未变化的实时状态：

| 分支 | queued | in_progress |
|---|---:|---:|
| v4/p3-agent-runtime | 23 | 5 |
| v4/integration | 1 | 1 |
| v4/mod-organize | 4 | 5 |
| v4/p10-frontend | 7 | 5 |
| v4/p8-calc | 0 | 4 |

55条中23对/46条是同workflow、branch、head的push/PR双触发。P3的timezone8条均queued；Core15条queued/5条in_progress。cd953874的PR Core [39517671972](https://github.com/JerryandShawn/zhiming/actions/runs/39517671972)、timezone [39517671983](https://github.com/JerryandShawn/zhiming/actions/runs/39517671983)和integration2ca的PR [39518095632](https://github.com/JerryandShawn/zhiming/actions/runs/39518095632)当时排队；同2ca的push [39518064447](https://github.com/JerryandShawn/zhiming/actions/runs/39518064447)实际已进入Core/calculator步骤，不能因PR queued推断CI故障。08:13后续check-run GET另看到cd953874的push39517666865已in_progress，状态变化单独记录。

P1b PR9 API核到准确head ref `v4/p1b-k3-hardening`、SHA `8087d7fa64839dc5a080491fd5db4e358f5814ec`，open/Draft。可见check名为core、Packaged tzdata on ubuntu-latest、Packaged tzdata on windows-latest，原名字全部保留。哪些被设为required没有可读证明：main protection返回403 Resource not accessible by integration，v4/main encoded slash被connector路径校验拒绝400；不能把不可读当作没有保护。

## 最终配置与边界

修改 `.github/workflows/ci.yml` 与 `timezone-data.yml` 的workflow级concurrency，group包含workflow、event和准入branch；仅本仓库的v4/p3-agent-runtime、v4/p3-wire-*、v4/p1b-*、v4/integration可按branch归组。其余一律使用各自run_id，cancel-in-progress=false。PR用head_ref，push/dispatch用ref_name；相同名字的fork PR和标签不进入主线组。

保留event可让push和PR独立，不因取消push旧提交而丢失唯一PR检查；保留workflow避免Core与timezone互相取消。本实现减少同事件内的旧主线提交，并不消除同head的push/PR双份工作。[GitHub官方并发规则](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency)说明同组默认会替换旧pending，因此只将cancel-in-progress设false仍不足以隔离别线；run_id回退避免该副作用。

既有无group旧run不会被此新文件追溯分组或清掉，本片没有调用取消API。仅大小写不同的分支名会受GitHub平台不区分大小写的比较/分组语义影响；现有ref均为核到的小写，不另建大小写别名。

## 实际静态检查

使用已有P2 Core Python与现存PyYAML，`yaml.load(text, Loader=yaml.BaseLoader)`保留on字面键。从实际两份新YAML提取concurrency，移除它后，与`git show HEAD:<path>`解析结果逐字段相等；不新增解析器依赖。实际结果各为：

    .github/workflows/ci.yml: 35/35 scope cases; 35/35 run_id comparisons
    .github/workflows/timezone-data.yml: 35/35 scope cases; 35/35 run_id comparisons
    on_name_jobs_steps_preserved=true
    different_event_isolated=true; different_workflow_isolated=true
    pytest_executed=false; hosted_engine_executed=false

35例组成：以下五个准入branch各测push/PR，共10例：P3精确分支、wire-p6-lint、wire-p1b-20261021、准确P1b分支、integration。以下11个非准入branch各测push/PR，共22例：main、v4/main、模块、前端、P8、P3研究、P3精确名字加后缀、p3-wires-p6-lint相似名、无末尾横杠的p3-wire、无末尾横杠的p1b、integration-new。再加同名fork PR、同名tag两例拒绝和本仓P1b workflow_dispatch一例准入，总35例。每例换run_id再比较：准入组不变、非准入组改变；另外检查push/PR和不同workflow的组互不相同。

受限本地求值将实际表达式的`&&/||`映射为对应短路逻辑，比较和startsWith按GitHub文档的大小写语义处理；只暴露github上下文和startsWith，不开放builtins。这是静态示例验证，不能冒称GitHub表达式引擎或托管CI已运行。初次本地脚本缺多行外括号导致SyntaxError，修脚本后31例通过；主代理扩大wire前缀后重新验证最终35例，没有放宽非准入断言。

`git diff --check`通过，diff只增加concurrency块51行。冻结Git blob：ci.yml `a0ef9262504141dbfdbf7f153d59615f0afed68a`；timezone-data.yml `52df0ad33be38795c78ad9566be5155afeef6136`。尚未推送，新组在GitHub托管引擎中的实际行为待主代理提交后同头CI核验。
