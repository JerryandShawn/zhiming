# B2 Charts单节点：静态副作用复核与最小运行机制

记录时点：北京时间2026-10-21 01:39。此文是只读审阅和候选方案，不是执行回执或许可：

```json
{"execution_approved":false,"coverage_collected":false,"charts_runs":0,"trace_runs":0,"test_runs":0,"network_requests":0}
```

本次选择已发布完整提交 **ed5182001df2c98893159f2dca023e5920e562e7** 作为固定仓库来源，
未使用浮动HEAD；不声称本次实审对应后续新增实现。
安装包另用只读文件和原始字节SHA核查，不能声称这些外部文件受上述Git提交保护。
没有启动Core/Charts解释器、目标测试、trace、网络、数据库或任何部署操作；Git只读命令属于审阅元数据。

## 唯一候选及真实生命周期

唯一候选：

    tests/test_p8_daily_transit_native.py::NativeDailyTransit::test_daily_day_pillars_advance_one_sexagenary_step

已完整读取固定提交的目标模块、daily_transit三体系模块/准备器、sample_natal助手、offline_runtime，
以及加载的hermes八字/紫微模块；对通用时基/规则/导入入口按实际调用阅读。
安装包侧核查py_iztro Astro入口、horoscope转换函数、PythonMonkey初始化/require及XHR桥。
没有声称已逐行审完全部第三方Python、压缩JS或原生DLL。

| 阶段 | 固定来源和行为 | 范围含义 |
| --- | --- | --- |
| 模块导入 | 目标模块1–33行：标准库、sys.path加入本仓库、导入样例和计算助手 | 不是只有一个方法的代码；模块和间接import须先受约束 |
| setUpClass | 目标38–44行：sample_natal；prepare_natal；2026-10-21至27七次daily_transit_prepared | 实际准备八字/紫微/西占，不能把此节点描述为只比较7个字符串的轻量任务 |
| 单个方法 | 目标94–105行：读七个真实日柱，验证相邻天干地支均前进一步 | 只证明六个相邻步进不变量；不等于十四测试或全部专业计算验收 |
| setUp/tearDown | 该类没有自定义setUp、tearDown、tearDownClass或addClassCleanup；继承unittest默认生命周期 | 应由真实unittest suite调用，不能手工直接调方法绕过setUpClass |
| 脚本主入口 | 目标233行起：platform.system、offline_runtime、loadTestsFromTestCase | 会运行整个14测试类；不得直接运行该脚本或以__main__加载来冒充单节点 |

`sample_natal()`仅deepcopy handoff_build.BIRTH，给出明确合成人物scope、固定出生资料和operation。
导入handoff_build还带入P8适配器/worker/Schema等定义；本节点不调用build_preview、generate或CLI main。
这些函数能写样例或启动worker，不应因与BIRTH同文件就被宽泛授权。

## 间接运行与副作用

1. **八字与时基**：prepare_natal使用显式日期、IANA数据与真太阳坐标；load_engine以spec_from_file_location
   执行本仓库hermes/bazi.py、hermes/ziwei.py的模块定义，不是subprocess。
   八字calendar_layers、具名表、U12条件和交互表执行Python计算，并读取knowledge下的本地JSON。
   此链未见模型、SQL或仓库应用服务调用；不因“没有SQL字面量”就推论所有外部包均已安全。
2. **紫微**：hermes/ziwei导入py_iztro；Astro构造从安装包资源读iztro-2.5.0.min.js，pm.require交给
   PythonMonkey的JS引擎。每日明确horoscope(day,6)，不会使用该方法缺参时的当前日期/时辰默认值。
   version/iztro_provenance读取distribution元数据和JS文件做摘要，涉及本地读盘，不是网络版本检查。
3. **西占**：Ephemeris显式swisseph Moshier/SPEED、UTC→TT/UT1及十天体计算，设置进程级历表状态。
   不能与另一采样共享同一长期Charts进程。原生C计算不产生可由Python行trace解释的C内部覆盖。
   未发现下载调用；仍需约束原生库可见文件/环境，不能仅以Moshier名称证明绝无本地辅助读取。
4. **PythonMonkey能力面**：安装的__init__默认require console/base64/timers/url/**XMLHttpRequest**。
   require.py提供本地readFileSync，并把Python eval/exec、getenv、sys.path、stdout/stderr桥给JS。
   本机XHR内部桥实际导入aiohttp，存在可调用的aiohttp.request协程；本次目标bySolar/horoscope路径
   没有发现调用它，但“入口未传URL”不等于运行时根本没有联网能力。
5. **文件与状态**：正常目标值只保存在类内存中；样例generate/main的mkdir/write_text不在候选路径。
   CPython导入默认可写__pycache__，stdout/stderr及JS console可能输出正文，PythonMonkey还会重配编码。
   采样bootstrap必须禁字节码、丢弃输出，并只允许全新私有目录中的获批文件写入。
6. **子进程**：实际计算链是当前Charts解释器里的动态模块/JS/C调用；但现有offline_runtime故意允许
   worker.py/p8_worker.py两个子进程，不能直接拿它证明B2单进程。平台探测也可能触发Windows辅助进程；
   不能在guard外悄悄预热后报告整个运行child_processes=0。

依赖锁requirements-charts.lock自身标注的是旧Linux闭包、非wheel完整校验；
其中含pythonmonkey网络依赖，不证明本机Windows全部二进制与锁完全相同。
本次只读目录显示lunar-python1.4.8、py-iztro0.1.5、pythonmonkey1.1.0、pyswisseph2.10.3.2、
pydantic2.10.6、tzdata2026.5；这些是目录/元数据观察，不是本轮解释器import版本实测。

## 建议的最小机制（仍未批准实现或执行）

### 1. 外层只负责固定元数据与启动

root先对一个完整commit生成A完整own清单与Charts静态计划，记录inventory_sha256、唯一节点和bootstrap自身hash。
对同一清单，核完整Git blob/LF hash、pytest.ini、测试源、所读JSON知识表、依赖锁、解释器及DLL/JS等指纹。
Git元数据读核在采样阶段外顺序进行，不能为读Git给被测过程放开任意subprocess。
未提交工具须另列instrumentation；不得借旧f23有限清单冒称完整own覆盖，也不得自动升级commit。

仅在取得B2具体批准后，启动**真正锁定的Charts解释器**的新进程，唯一任务是该节点。
建议隔离用户site/PYTHONPATH启动注入、禁字节码，显式UTF-8、固定TZPATH及合成数据；
不安装依赖、不访问npm、pip或网络，也不改worker/hermes/v3。
外层启动Charts这一事实必须记入总进程拓扑，不能一边启动子进程一边宣称整项任务子进程0。

### 2. 在首次目标和第三方import前安装强守卫

bootstrap先清凭据、DSN及追踪环境，拒绝已有sys.gettrace；仅允许固定解释器、cwd、完整SHA和单节点。
读取源/依赖可限已核路径；所有写操作限全新私有临时目录和唯一新证据，拒绝越界、链接跳转、删除/重命名。
网络须同时封锁socket连接/DNS、urllib及HTTP路径，DB连接入口和任意进程启动均拒绝；
不能只禁subprocess.run，必须包括Popen、os.system/spawn/exec等，并在审计事件中记录拒绝尝试。
设置严格时间与资源上限，未知库导入/副作用或子进程需求失败关闭，不临时放行或回退到Core。

PythonMonkey可通过Python桥间接执行Python代码，原生DLL也未必受所有Python monkeypatch约束。
故Python级guard属于可测试防线，不能冒称等同操作系统沙箱；若要给全进程绝对网络/写入隔离保证，
必须另有获批、实际验证的OS隔离机制。本报告不授权修改防火墙或系统设置。
没有该机制时，报告只能准确限定“已审路径、已拦截的Python接口与审计可见事件”，不能夸大未观测的C/JS行为。

若第三方初始化确实需要platform探测子进程，应先作为阻塞单独复核；不以“平台预热”暗中扩大许可。
stdlib元数据优先用sys.platform/version_info与固定文件读取，避免不必要platform.system探测。

### 3. 保留真实unittest生命周期，只装配一个case

在guard内以普通模块名导入目标（绝不__main__），显式构造
`unittest.TestSuite([NativeDailyTransit("test_daily_day_pillars_advance_one_sexagenary_step")])`。
使用真实runner触发class/module生命周期，禁止调用loadTestsFromTestCase或整个文件discover。
run结果必须testsRun=1、errors/failures/skips/expectedFailures/unexpectedSuccesses均为0；
setUpClass失败时即使testsRun=0也必须留下失败回执，而不是当空运行成功。

baseline与trace各一个新Charts进程，参数、guard、依赖、节点和生命周期相同；先小baseline，
通过且预算允许后才做trace。禁止用baseline结果补trace失败、自动扩大节点或重复直到成功后删去失败。
把stdout/stderr（含JS console）定向到真正丢弃流；不保留断言正文、异常repr或盘面输出。
原生C/DLL输出可能绕过Python redirect，故还须在启动层将OS标准句柄丢弃；摘要只写获批的独占JSON，
不能把任意stderr混进机器回执或保留为普通日志。
只写受限枚举阶段、退出码、计数、耗时及必要指纹。未预期输出尝试可计数，不保存其内容。

### 4. 真实Charts摘要与同清单合并

`sys.settrace`只覆盖安装它的当前解释器/相应线程；Core的trace**不会**跨到Charts进程。
必须在Charts内部安装collector，并在候选import、setUpClass、目标方法及清理的声明区间内采样，
最后finally卸载，记录trace前后状态及异常。其他线程和原生C/JS明确不采集，不把它们填成已证实覆盖。

从同一完整A inventory逐文件、逐executable_line构造计数表：未观察到的Python行填0，
文件没导入也保留；0行文件保留空表。baseline的coverage_collected=false、覆盖摘要为null，
不能把它的零计数当trace观测。分母是CPython3.11固定compile/dis方法，不是coverage.py或分支覆盖。

实际Charts摘要至少含runtime=charts、真实解释器/版本/二进制hash、同一完整commit/inventory_sha256、
精确节点、生命周期、mode、testsRun和全部失败/跳过计数、exit/status、源/知识表/依赖前后hash、
当前线程范围、所有清单文件的行计数、未采集范围、guard尝试计数和新回执hash。
guard拒绝、hash漂移、版本变化、已有trace或进程超时都必须记失败，保留文件清单和失败阶段；
部分counts最多标partial，不纳入成功union。不回显私密参数。

Core/Charts只合并相同完整commit、inventory摘要、路径、LF hash、行号全集及分母方法的成功trace回执。
类型严格检查bool/float不能充行号/计数；拒绝重复回执、遗漏文件、改分母、负数、baseline和失败/跳过。
保留每个runtime的原摘要及union来源hash；总体覆盖是“任一成功观测count>0”的并集，
不能把执行次数相加当独立覆盖率，也不能删掉未导入文件后提高分数。
新A清单须有匹配的新聚合逻辑；旧v1 merge只处理旧有限选区，不能改个版本号就冒充支持A完整清单。
回执hash只绑定内容，不是签名或独立证明进程确实运行；保留真实启动/退出元数据与父子关系。

## 本机依赖只读指纹

下面是本次Get-FileHash直接读取安装文件的**原始字节SHA256**，不是Git LF hash，也没有执行这些文件：

| 相对Charts site-packages路径 | SHA256 |
| --- | --- |
| py_iztro/core/astro.py | d5288f3350bc5f0cbbfb9a58f466a87302bd47a81160ae357f3e7c043f09b1cf |
| py_iztro/core/models.py | bb9d52077c299aa3444c3862a3b78e729d5d962b3c32a6fb5c2b37612ce98ebb |
| py_iztro/res/iztro-2.5.0.min.js | 09333d6a2da7fff7bd338134c8d17de0d589259c16a70ece1db1d64e17217ea0 |
| pythonmonkey/__init__.py | f10dba7cd7209c11d5f5f87b8caa3490926c4937ef0ea9bcbfe46bc1609d98a0 |
| pythonmonkey/require.py | bf2bdae209015cd1ae4cc4da9aafff1ee1c609e9020ccd8b010e33c2e6f43ae0 |
| pythonmonkey/builtin_modules/XMLHttpRequest-internal.py | e9e7745449c331e855539543e621ac0be4eef81993b3c2bd03ca231090acf406 |
| swisseph.cp311-win_amd64.pyd | b2b3277b7fb4b96b2ada7207b1362becbc9a4653903ba92878999558cce23b9e |

实际执行还应补PythonMonkey的pythonmonkey.pyd/mozjs DLL、lunar、tzdata、完整相关包和解释器指纹；
本次表不是全部依赖闭包验收，也不代替未来运行前后读核。

## 当前结论

候选可以设计成一个真实Charts单节点，但它的准备阶段覆盖三体系和七日实际计算；
现有Core-only runner及允许worker的offline helper都不能直接证明这种新范围安全或已覆盖。
本轮仅交审阅与机制要求，execution_approved仍false；没有实现bootstrap/collector/merge或执行baseline/trace。
测试0、Charts0、trace0、模型/服务器/DB请求0；没有修改任何A冻结资产、worker或旧v3。
