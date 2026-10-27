# MOD：v2.3素材CLI公开文件边界（独立8项）

本ExecPlan按`.agent/PLANS.md`维护。readiness是“素材与检查器就绪状态”，并非产品场景验收。
本轮只新增独立测试、helper和证据；`tools/eval_material_v23`、既有112测试及全部素材原字节不可改。

## Context and Orientation

工作树为`C:/Users/Administrator/Documents/Codex/zhiming-v4-mod`。
已完整读`tools/eval_material_v23/__main__.py`、`loader.py`、`report.py`、`observe.py`、README与现有全部112测试。
复用`__main__.main`（构造参数、验证新workspace路径、写JSON和输出计数）、`loader.load_materials`
（SHA与严格59项契约）、`report.build_readiness`（注入Clock、按上海时间显示）、`FrozenClock`。
CLI不执行产品；19号52项与P5b SP01–SP07是59条候选素材。D4相关PR02/PR06和时辰倒推仍阻塞，
J01/J02仍record_only，E2仍2025；不改历史v2.1/v2.2或任何黄金。

## Purpose / Big Picture

让CLI使用者看到固定时钟下的59候选、189断言和零产品通过，并确认文件不会覆盖旧报告或写出workspace。
这补充纯函数测试未经过的真实命令入口，但只处理本地合成素材与文件。
不据语句/分支0覆盖强造私有态，也不把本次文件检查等同于运行59产品场景。

## Progress

- [x] (2026-10-21 10:17 +08:00) 完整阅读入口、依赖、现有112测试和时钟实现，列出8项独立可观察真值。
- [x] (2026-10-21 10:18:54 +08:00) 冻结8项矩阵及16份原来源/素材/既有测试/计划，矩阵SHA为44be447faaa1107705ce6a4a05ffea1f11a5400b8b1fcb767bc2a6f525015a60。
- [x] (2026-10-21 10:20:41 +08:00) 初次启动exit4，尚未收集用例：隔离harness替换socket类型导致依赖导入失败；原LF/source/test/hash保留并报root。
- [x] (2026-10-21 10:21:26 +08:00) 只修新helper/harness隔离方式，保留8项真值；8/8通过0.45秒，原产品/材料均未改。
- [x] (2026-10-21 10:22:17 +08:00) 单模块120/120通过1.45秒，19材料集合/字节before/after一致；CLI单文件覆盖综合92%。
- [x] 更新回执、区分测试harness启动错误与产品结果；不运行全量/性能/业务接口，不Git，冻结新测试。
- [x] (2026-10-21 10:26:12 +08:00) root核对CI默认无basetemp，保存不写文件的helper反例；确认为新测试夹具前提差额，非真实CI或CLI失败。
- [x] 仅新test模块新增显式private临时目录fixture；保留原8函数体/断言，并可重建原文件SHA证明。
- [x] (2026-10-21 10:27:15 +08:00) 不传basetemp，修正后8/8通过0.43秒，6个唯一目录均在private，不删除。
- [x] (2026-10-21 10:27:55 +08:00) 必要120兼容全部通过1.36秒，19材料无漂移，另存最新CLI单文件覆盖92%。

## Validation and Acceptance

| ID | 输入 | 冻结可观察预期 |
| --- | --- | --- |
| CLI01 | main两次，固定同一UTC瞬间但Clock分别返回UTC/Tokyo表示，新private路径 | 两份报告对象相同、generated_at为上海+08、59候选/189断言、51未验证/1决定阻塞/7依赖阻塞/0通过；stdout仅对应计数 |
| CLI02 | private中已有文件 | 固定MaterialError、原字节逐字节不变，不执行报告生成 |
| CLI03 | 绝对workspace外新路径 | 固定MaterialError，不创建外部文件，不执行报告生成 |
| CLI04 | private作为cwd，../相对路径resolve后逃逸workspace | 同上，仅验证拒绝，不向外写入 |
| CLI05 | private中新文件但父目录不存在 | 固定MaterialError，不创建父目录/文件，不执行报告生成 |
| CLI06 | 无--output | argparse退出2，stderr说明必需参数，无报告/生成调用 |
| CLI07 | --help | argparse退出0，stdout有usage/--output，无报告/生成调用 |
| CLI08 | 干净离线子进程用模块入口和固定Clock，新private路径 | exit0、上海+08、59候选/189断言/0通过、stdout计数；不依赖主机Tokyo |

CLI01/08涉及DC01–DC04等19号素材和SP01–SP07的完整材料清单，仅检查readiness；
不以`07_评测场景集.md`中任何产品ID标为已通过。素材覆盖与原产品场景结果明确分开。

## Plan of Work / Concrete Steps

新增`tests/v4/eval_material_v23/cli_public_support_core_mod.py`与`test_cli_public_core_mod.py`。
固定时钟通过主机依赖注入（替换SystemClock构造器），不替换load_materials/build_readiness的正常路径。
拒绝路径用报告函数sentinel证明未生成；不注入私有CLI状态，也不改loader黄金。
先冻结metadata矩阵，再运行：

    python -m pytest tests/v4/eval_material_v23/test_cli_public_core_mod.py -q -p no:cacheprovider

只有必要的单套兼容与CLI单文件覆盖；同一时刻最多1个pytest，所有tmp/basetemp均在mod/private。
网络/DNS禁止、keys空、tracing关闭、禁止pycache与pytest缓存，不运行模型/PG/产品或全量。

## Surprises & Discoveries

公开入口先`resolve`，再同时拒绝workspace外、已存在目标或缺父目录，写时使用`x`模式。
现有readiness测试已核零pass与时区不变量，但尚未经过argparse、文件独占写入及模块入口。
没有发现CLI产品实缺，不依据0%覆盖预设产品错误。
第一次测试启动时，过早把socket.socket类替换为函数，使上层conftest导入psycopg/ssl失败，8项尚未收集。
保持socket类型，仅禁connect/connect_ex/sendto/DNS后，依赖正常导入；没有修改任何预期或产品。
原首次exit4证据保留，不能把它说成CLI用例失败或产品缺陷。
root随后发现本轮helper只接受private路径，而`.github/workflows/ci.yml`的pytest命令不传basetemp，
`tests/v4/conftest.py`也未覆盖tmp_path。只读代码差额与无写helper调用确证此夹具可移植性问题，
并没有实际运行CI或向OS默认临时目录写文件。原120通过仅证明当时显式private basetemp下成立。

## Decision Log

只采用8条有限真值，不追加相似对象或私有构造覆盖。workspace外负例只构造路径并验证未创建，
不会先在外面建立文件再测试。CLI01的跨时区报告可以合在同一真值下作同瞬间不变量。
模块入口用干净子进程固定Clock，既隔离模块导入状态又实际覆盖`__main__`；该进程不运行性能。
失败不授权自行修复，需root审读；所有首次输出/快照另存不覆盖。
本轮没有产品修复。干净子进程实际走模块main guard真分支，但parent coverage不采子进程，
因此如实保留29行及28→29分支未覆盖，不为100%追加私有入口或改测试结构。
按root要求只在新test模块增加同名tmp_path fixture：`tempfile.mkdtemp(dir=ROOT/private/mod-week/tmp)`，
不依赖调用方basetemp或主机OS临时目录，唯一目录不自动删除。不改CI、共用conftest、原112或CLI。
仅移除新tempfile import和新fixture即可重建原test SHA，证明8函数体/断言未变。

## Idempotence and Recovery

每次测试使用private下独立pytest临时目录与新输出文件；不删除/覆盖已有证据或workspace外数据。
拒绝覆盖测试只写其自身合成哨兵并核原字节；无数据库迁移、运行时接线或业务副作用。
root独占Git，本子任务不提交/推送。

## Outcomes & Retrospective

最终新fixture下独立8/8在不传basetemp时通过；连同原112项单模块120/120通过，19材料集合/字节一致。
10:22的120/coverage与旧test SHA保留为历史；10:27新的目标、兼容和coverage另存，源/旧新test SHA分列。
CLI文件行20/21=95.23810%，分支3/4=75%，综合23/25=92%；单文件分母与此前静态384源范围分开。
固定UTC/Tokyo表示的Clock均生成上海07:30报告；59候选/189断言保持51未验证、1决定阻塞、7依赖阻塞、0通过。
拒覆盖保原CRLF哨兵字节；外路径负例只验证拒绝，未创建workspace外文件。
没有执行59产品场景、全项目回归、性能、PG/服务器/模型/平台；没有改CLI、素材、既有112测试或源清单。
计划作为活文档在测试后更新，冻结矩阵内的计划SHA属于测试前版本；不回写原冻结证据。

## Artifacts and Notes

矩阵及首测/兼容/CLI单文件覆盖JSON放`docs/v4/evidence/MOD_2026-10-21/CLI_material_*`；
原始LF日志及临时报告放`private/mod-week/`。来源快照单独绑定`tools/eval_material_v23`全部原文件、
其Clock依赖与现有测试，不把此前384源的静态范围充作本轮绑定。

## 修订记录

2026-10-21 10:17 +08:00：完整阅读后新增独立8项CLI计划；源与矩阵待立即冻结，未运行测试。
2026-10-21 10:22 +08:00：保留首次harness导入失败及修正隔离方式，补8目标/120兼容和CLI单文件真实覆盖结果。
2026-10-21 10:27 +08:00：更正新测试对basetemp的隐藏前提，保留无写反例；自给private fixture及无basetemp8/必要120重验均通过。
