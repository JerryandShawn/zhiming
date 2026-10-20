# B1 Core 行采样工具：实现与边界验证回执

记录：2026-10-21 02:07（北京时间）。本轮是实现交付候选；真实 baseline/trace 尚未获准，也未启动。不能把下面的单测数量当作行覆盖率或业务质量分数。

## 文件与接口

新增 `mingjing_core/adapters/charts/benchmarks/line_coverage_core_{bootstrap,boundary,fingerprint,git,reports,run}.py`，以及 `tests/v4/test_p8_core_coverage_{guards,receipts}.py`。各文件≤400行、各函数≤60行，默认88格式；指定Ruff规则通过。8文件的原始与归一LF SHA见 `night28-core-b1-author-boundaries.json`。

- 固定入口：Core解释器 `-I -S -B -X pycache_prefix=<新建空private/tmp目录>`，随后是已提交的 `line_coverage_core_bootstrap.py` 绝对路径。bootstrap 与第二道守卫都拒绝 -O/-OO、额外启动开关、非固定入口或复用缓存。
- `collect_core(inventory, plan, *, node, mode, commit)`：只接受完整显式40位SHA、A完整自身代码清单与三确切Core节点的静态计划；单进程只运行一次。每个baseline/trace由外层另起全新Core解释器，collector不启动测试孩子。
- `MetadataGit`：目标执行外固定ROOT/二进制/只读参数；`core.fsmonitor=false`、无系统/全局配置、无可交互凭据，目标执行内禁Git。`rev-list --ancestry-path BASE..COMMIT --`强制末尾分隔符；没有旧无分隔符特许。绑定Git本地配置前后原始SHA，拒绝未复核include。
- `Gate`：事前允许读取的文件只有固定源码/配置、解释器与逐文件指纹化的依赖。项目业务数据allowlist为空。未知native扩展的import filename在执行PyInit前拒绝；拒绝ctypes调用、DLL搜索目录变更、网络、子进程、额外线程、trace/profile篡改及文件写入。pyc只发出FileNotFoundError以回退源码，不读取已有字节码。
- `Witness`：真实pytest收集恰一个批准node；无fixture、无skip/xfail，setup/call/teardown三阶段均成功，真实整数退出码0。禁第三方autoload、conftest、cache/JUnit等无关插件；不预热platform.node/uname。
- `merge_core`：从Git重建完整inventory和固定三节点计划；校验每张成功receipt的完整行表、真实整数计数、空拒绝记录、生命周期、前后源码/依赖及计划SHA。不导入文件仍在分母且保留0。失败和partial receipt不能进入union。

## 本轮实际验证

1. 首轮纯边界79项通过，0跳过，0.36秒。独立只读审阅随后指出原 `__stdout__` / `__stderr__` 缓冲可能在恢复FD后泄出；该轮仅作为修前历史保存。
2. 修后纯边界80项通过，0跳过，0.25秒。保存原流先flush、目标期间原流名称也换成丢弃流、退出在FD仍指向NUL时flush再恢复；合成marker单测保护这一顺序。
3. 测试期间外层拒绝Socket连接、DNS和subprocess.run/Popen；实际Charts进程0、Git进程0、collector调用0、实际trace样本0。trace生命周期测试使用FakeTrace和合成函数，没有调用真实sys.settrace或目标node。
4. 覆盖负例包括 -O/-OO双入口、metadata命令/payload、未知native import、业务JSON读/写/文件描述符、网络/进程/线程/trace、吞掉拒绝仍失败、选错/漏/多node、fixture、缺阶段/skip/xfail、bool/float冒充、缩行表/重复文件、重签失败事实、冷文件0、baseline的null观测，以及mock-Git验证重建顺序和不同文件排序的union。

## 诚实边界与下一步

- 这些是80个真实pytest边界用例，不是80次专业排盘、实际覆盖采样或字段断言累计。真实Core三节点baseline/trace尚未运行；Charts采样继续为0。
- Python audit/patch是已审代码的防意外边界，不是OS沙箱；没有声称能约束恶意native代码。捕获的pytest正文不落日志；receipt只保留机器枚举、路径、SHA、行号/计数和阶段。
- 非忽略的未跟踪Python被拒绝；没有声称扫描全部ignored源码。实际读取/import则受精确指纹allowlist限制，未导入冷文件保持0。
- union还要求当前原始源码与Git配置对应；合法CRLF或本地配置变化后也会拒绝历史重放，应在新的明确观测轮记录，不借归一LF偷偷放宽运行事实。SHA只提供内容完整性，不提供执行身份认证。
- 先提交含collector的新完整SHA，再重建包括collector本身的A清单和Core计划；root明确批准确切节点后才可另开实际小试。不自动升级commit，不修改旧v1/A/历史报告。
- 本轮没有实现外层硬超时监督器。真实小试前由root固定监督命令、截止与强制终止失败回执；未满足时继续不采样。目标异常和前/后置拒绝在工具内以固定phase记账，不保存任意异常正文。

## 07:41 root最终源补充

作者80项及其原始8摘要是02:07历史；随后root仅作导入/格式和等价守卫写法校正。07:29–07:32完整2939/2939、0skip包含作者80与独立5边界，370项最终源摘要见night28-resume-full-validation-20261021.json。独立5未另跑独立收据，不将其冒称02:10已完成。真实collector及Charts覆盖采样仍0，外层硬超时未就绪，未宣称覆盖率或已批准执行。
