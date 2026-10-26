# B1 Core完整自身代码行采样：最小执行方案

记录：2026-10-21T01:44:21+08:00（北京时间）。根代理已批准实现私有草稿和边界测试准备，**未批准真实 baseline/trace**。静态A计划的 `execution_approved=false` 保持不变；此文不是执行许可。本轮仅读源/AST/本机pytest源码，测试、Charts、网络和trace均0。

## 三个精确节点与依赖

首批仅 `tests/v4/test_p8_e2_night28_controls.py` 的以下三项，完整ID不接受前缀、-k、任意文件/脚本或参数变体：

1. `test_matching_is_reproducible_and_independent_of_input_order`：`records(7)` → `BirthMetadata/Question.__post_init__` → `same_source_placebo` 的 `_groups/_donors` → `controls_v2._matching/augment`；再 `rehearse_controls` → `_checks/_pair_audit`、`shuffle_options`、`question_year`、`fingerprint/scoring_fingerprint`。排序/固定random.Random仅作用于合成内存记录。
2. `test_no_chart_only_has_original_question_and_permuted_options`：`records()[0]` → `no_chart_input/shuffle_options`、`rehearse_no_chart`，只构造合成题文和重排选项，不读题库。
3. `test_empty_batch_is_available_without_a_fabricated_score`：空列表的 `same_source_placebo/rehearse_controls`，不评分、不排盘。

三函数无参数、fixture或decorator；模块没有 `pytest_plugins`、autouse、setup/teardown钩子。仍由真实pytest执行 collection/setup/call/teardown，不直接调用函数来代替测试。模块其他参数化函数的decorator会在import时建立，不能把“只选3项”误称“只导入3个函数”；最终收集集合须精确等于本次批准节点，不擅自deselect未知项。

测试模块还导入未被这三函数调用的 `_rehearsal`。它让导入链经 night28_audit→night24_audit/sources/scripted_v2→engine/annual/adapter/skills，静态import闭包含47个项目文件（含包init）。已逐项审模块顶层及实际可达helper模块全文；顶层为常量、regex、Path.resolve、dataclass/Pydantic类和lru_cache装饰。P8Engine、ChartAdapter、SkillLibrary等类型被定义，不在这三节点中实例化/调用。所有 `__main__` CLI分支保持未执行。

**数据守卫：项目数据读取allowlist为空。** loaders/loaders_v2/night24_sources 的专业JSON读取、SkillLibrary构造时catalog/章节读取、rules.registry._loaded的rules_v1.json，以及 elements.table 的知识JSON读取都在未调用函数体内；没有项目JSONSchema模块的顶层读取。仅给固定源Python、pytest.ini及锁配置只读许可，不因import了loader就开放corpus/knowledge/schema/samples/private缓存。任何实际项目JSON/Markdown/题库读取均应拒绝并保留固定错误，不静默扩权限。依赖包自身资源属固定Core安装文件，另作实际内容hash守卫。

## 固定分母与新实现来源

A已批准起点为 `7fa5e10a4dbe0e2878e28c6f6a115f17d013aaa2`；220文件/23,733行仅是89f68e6历史静态事实。新collector和边界测试先测试/提交，再显式固定包含它们的完整40位F提交，重建A完整inventory和Core静态计划。分母必须含新collector、bootstrap、指纹/边界/报告代码及其测试；不固定未来数量，不排除没导入的文件。

每次B1输入显式 `commit=F / inventory_sha / static_plan_sha / exact_node / mode`。static_plan自身仍未批准执行；根代理的本次运行授权通过另一个明确请求表达，代码校验格式与指纹不等于证明人类授权。拒绝源未提交、未知Python、工作树/配置差异、现有trace/profile、目标模块已热导入、非固定Core解释器或不匹配的CPython3.11。

v1报告/合并不接受v2，保留6c历史；B1使用新的receipt/union schema，完整8分组与总表、Core与未来Charts分表，冷文件逐行0。baseline的执行行与比例为null而非伪造0命中；失败或守卫失配可保留partial计数但不进入成功union。

## 最小实现拆分

独立 `line_coverage_core_bootstrap.py`（固定命令入口）、`line_coverage_core_fingerprint.py`（Git/解释器/依赖与工作树前后）、`line_coverage_core_boundary.py`（Python层I/O边界）、`line_coverage_core_run.py`（真实pytest witness/计数/receipt）。必要时纯报告合并另分文件；不修改v1/A、worker、v3、CI或锁/依赖。每文件≤400/函数≤60，先private全文审阅后移入。

建议外层仅启动固定Core命令：`-I -S -B -X pycache_prefix=<本工作树新UUID缓存>` + 固定bootstrap路径和白名单参数。bootstrap只加明确的Core site-packages与本工作树，跳过用户site、.pth/sitecustomize；不安装、不改变venv。baseline和trace分别全新解释器进程、各仅一次pytest会话，禁止在同一解释器先baseline再trace产生热缓存差异。若这些启动约束不能在现机满足，直接拒绝并拆步，不静默换解释器/模式。

固定Core解释器、base executable/DLL、stdlib/DLLs以及pytest/Pydantic实际所需的安装包源/扩展/元数据/资源逐文件hash（不只相信version/RECORD），运行前后表与摘要必须一致。固定requirements-core/test锁及pytest.ini。包路径、已载入模块来源与新载入来源不得越出已hash集合；不预热platform.node/uname或pytest目标。初始化未被追踪的自身行保留0，不能给instrumentation补命中。

## 生命周期、I/O与失败

真实pytest以固定配置、`--noconftest`、禁第三方autoload/外来pytest参数，明确关闭cacheprovider、logging、junitxml、doctest/faulthandler等不需要的输出/探测路径。不写JUnit：平台hostname仅用已有sys.platform等常量，不让platform.node→win32_ver→ver子进程成为隐藏例外。自有固定witness只记录精确收集集合、每项setup/call/teardown和退出/skip状态；任何多/少项、skip/xfail、非0退出或不完整生命周期均不作为成功。

Git读取仅发生在目标执行外：固定Git二进制与ROOT、完整SHA、rev-parse/merge-base/ls-tree/cat-file/rev-list/diff-tree/diff等A重建需要的只读参数，不给任意命令/root/环境或写Git权限。目标执行内一律拒绝Git以及任何其他子进程，计数仅写固定类别；不靠提前偷偷调用来声称child0。

执行中Python层audit/固定patch拦截网络/DNS、子进程、额外线程/trace篡改和文件写操作；只读许可限已固定源/配置、解释器与依赖文件。数据allowlist空。所有缓存/临时目录为本工作树private/tmp下新UUID，字节码不写；执行期无业务写需求，pytest私有basetemp仅作预置边界，不给任意数据写许可。源码/数据路径越界、符号链接、包资源漂移或意外文件访问都失败，不把失败项从分母删掉。

标准输出/错误同时用Python丢弃流及FD级NUL隔离，禁持久化pytest capstdout/caplog/longrepr/异常/locals；真实pytest内部可以暂存异常，但不冒称内存中从未出现题文。原始事件记录仅允许机器生成字段：固定phase/批准node/状态/计数/来源hash/Clock时间，不保存或hash测试正文、出生信息、答案、异常文本。失败回执同样写出固定拒绝原因、阶段/退出/计数是否partial，不能只留下成功报告。进程异常退出缺finish即不完整；外层须有明确超时终止与固定失败记录，不重试到绿。

Python audit/patch是本机已审源的防意外边界，不宣称对恶意native代码提供OS级沙箱。第三方二进制仍需来源内容指纹；若审阅要求更强隔离，拆作后续环境工作，不在本轮假称已实现。

## 可独立验证的最小增量

先只测纯验证器/边界/witness/report：错误SHA/未提交collector、config与包内容漂移、项目JSON读取、越界/链接/写、目标内Git与模型网络、热模块/错解释器/旧trace、同值float/bool计数、未知/额外/缺失node、skip/xfail/setup/teardown失败、私文输出丢弃、失败receipt不进union、冷文件完整0。正例用合成计数/报告和受控副作用探针，**不借单测准备启动真实collector trace**。

根代理读private完整源码→批准移入→专属测试/独立审阅→提交→固定新F/完整分母→再次批准真实3节点。正式首轮可先1节点 baseline+trace，每个新解释器，总目标计时≤5秒的小试后评估开销；不自动扩大到全部v4，不占02:15错峰全量窗口。当前测试并行总≤4；B1自身仅1Core，Charts0、实际业务子进程0。任何守卫拒绝原样记失败，先解决原因再另轮新文件，不覆盖旧事实。
