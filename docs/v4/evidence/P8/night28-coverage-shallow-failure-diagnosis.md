# 真实本机浅检出失败：诊断、参数修复与深路径回归

记录时间：2026-10-21T02:07:10+08:00，北京时间，工具UTC换算。
失败源码提交：`33a9865a32227c67cfce0dfbf3e5e3227682c7ab`。
本轮先只读失败日志和真实Git stderr，向root报告具体原因并获批准后修改；不改历史范围、
删除台账、origin政策、拒绝逻辑、CI或真实历史产物，不以删断言/skip来迁就浅检出。

## 第一次真实浅检出：失败事实保留

根代理的 `private/p8-validation/verify_shallow_portability.py` 通过本机file://创建depth1独占副本，
实际确认只有1个可达commit，7fa/f23/ef5三个历史commit均不存在；没有网络访问。
2026-10-21T02:00:53+08:00至02:01:12，原91项结果为**28失败、63通过，17.56秒**。
收据 `docs/v4/evidence/P8/night28-coverage-shallow-portability.json` 和原日志保留，
没有覆盖成成功；该收据tests=null、exit_code=1、输入SHA前后相等。

这说明此前原工作树91通过不足以证明真实浅副本可移植。
第一阶段修复的旧历史对象依赖没有重新出现；新失败分成一个测试前提问题及27个深路径Git失败。

## 只读复现：真正的stderr与相同参数对照

在失败副本已有的own-inventory-fixtures仓库中，只读执行实际Git命令：

- 合成仓库根绝对路径185字符；git rev-list HEAD可读到4个commit，commit_id/merge-base已成功。
- 完整起点SHA、两个点、终点SHA组成82字符参数；根路径加分隔符及该参数共268字符。
- 原命令 `git rev-list --ancestry-path <base>..<observed>` 真实stderr为：

      fatal: failed to stat '<base>..<observed>': Filename too long

- 对同一仓库、同一范围，加末尾 `--`，退出码0并返回3个后代commit。
- 只对该只读命令临时加 `-c core.longpaths=true` 也退出0，返回完全相同的3个commit。

没有修改失败副本配置或数据。观察到Git在没有路径分隔符时尝试对范围参数做文件路径歧义检查，
Windows路径长度限制导致失败；不是浅库遗漏合成commit，也不是删除台账逻辑应当忽略某些文件。
没有凭顶层coverage_git_read_failed猜错为对象缺失，具体stderr从真实Git取得。

## Decision：精确修复，不配置掩盖

root批准后仅改 `mingjing_core/adapters/charts/benchmarks/line_coverage_own_sources.py:deleted_paths`：

    git_bytes(root, "rev-list", "--ancestry-path", base + ".." + commit, "--")

这是明确“只有版本范围、没有路径”的参数边界修复。base、observed、祖先路径范围、
后续diff-tree、删除台账、全blob验证和所有拒绝规则均保留。
没有给主仓库设置core.longpaths，没有用测试配置隐藏原命令问题，没有遇错返回空删除列表。
Ruff仅把该增加参数的调用排成三行，没有其它源逻辑改动。

新增 `tests/v4/test_p8_git_range_portability.py`，使用独立的真实四commit小Git：

| 新回归 | 实际验证 |
| --- | --- |
| 深路径无路径歧义 | private/tmp内约185字符根，两个40字符SHA范围的候选路径超过260字符；仓库明确core.longpaths=false；真实deleted_paths返回已删路径；透传spy继续调用实际Git，并核rev-list末尾确有-- |
| 深路径净零删除 | 起点后增加、随后删除的文件不出现在净diff，但live inventory仍保留其删除台账；重签清空台账后实际validator重建拒绝pinned_source_mismatch |

业务Python夹具名含synthetic、正文为SYNTHETIC_*，legacy.py正文也明确合成；不使用真实出生/题库资料。
Git只在该新夹具设置longpaths=false、假身份、禁GPG、空hooksPath与fsmonitor=false。
测试没有mock Git输出或手填删除结果；spy只记录参数并透传真实命令。
即使其它平台没有Windows路径长度限制，参数末尾--和实际台账行为仍有明确回归断言。

## v1的38项测试：一处前置安排修复

第一次真实浅副本还暴露
`test_existing_trace_and_non_core_execution_are_refused` 预期existing_trace_refused，
却先收到coverage_core_interpreter_required。
runner.CORE_PYTHON仍是按原固定工作树相邻运行时定义的批准路径；浅副本的ROOT位置变化后，
不能假设实际正在运行的Core解释器已经与它相等。

root只批准该测试开头安排被测前提：

    monkeypatch.setattr(runner, "CORE_PYTHON", Path(runner.sys.executable).resolve())

随后原有gettrace异常断言与错误sys.executable拒绝断言原样保留。
没有放宽runner本身、改变检查顺序或允许任意解释器执行实际采样。
这也是对第一阶段“v1文件不改”的后续明确增量：第一阶段确实未改v1；
真实浅检出才揭示此一个测试前提，不能反写旧证据称它一直已修。
这不宣称v1固定Windows采样入口已改造成通用Linux执行器。

## 原工作树最终定向回归

清API凭据、禁LangSmith/LangChain/OTel追踪、禁pytest插件/conftest，最多1个Core与顺序Git子进程。
原3份覆盖率测试加新深路径文件，合计93项：

    <Core Python> -m pytest --noconftest tests/v4/test_p8_line_coverage.py \
      tests/v4/test_p8_line_coverage_own.py tests/v4/test_p8_own_inventory_independent.py \
      tests/v4/test_p8_git_range_portability.py -q

**93/93通过，0skip，29.63秒**；
Junit `private/p8-validation/coverage-range-portability-final.xml`。
扩展E/F/I/B/UP/SIM、120字符规则与默认88格式通过。

| 最终文件 | 行数 / 最长行 / 最长函数 | LF SHA256 |
| --- | --- | --- |
| line_coverage_own_sources.py | 144 / 87 / 25 | 09d89cfca3b234d9a4cdb35243a2bdf29dab5174192eb98ed8c79a76cf5f357a |
| test_p8_line_coverage.py | 387 / 99 / 25 | 7370f688281b1ddb899527dc20c1d38dddaeb0f8e52f7933b3422d9293549213 |
| test_p8_git_range_portability.py（新增） | 128 / 88 / 30 | 3c85fe99027f0f255df0c87040a20f56d7556e2165a85e3e12f38c56fc762817 |

这个93通过是原工作树的定向结果，不能改写第一次浅检出的28失败，也还不是第二次浅检出成功。
root将提交这份明确源版本后，用另一个exclusive本机浅副本重测；新收据须另存，不能覆盖首次失败。
CI的Linux真实运行仍需推送后另核，不把本机Windows通过直接当GitHub成功。

本轮源/测试已冻结，Core/Git进程已结束；随后仅新增本文。
真实模型0、Charts0、业务覆盖采样0、DB0、网络0、服务器0；
没有删除其它数据或改其它工作树，未自行提交、推送或合并。
