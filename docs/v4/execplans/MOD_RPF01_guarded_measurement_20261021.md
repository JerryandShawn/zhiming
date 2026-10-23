# MOD：RPF01守卫工具版本的离线重观测

本ExecPlan遵循`.agent/PLANS.md`。创建`2026-10-21T11:27:41.431771+08:00`，北京时间。

## Purpose / Big Picture

为已增加普通解释器模式守卫的冻结工具补一份新的同版本观测；这是重观测，不是新优化。
原工具/3实验产品/18反思源/所有fixture和测试不改，不复用旧工具SHA冒充本次来源。
只在一个独立Core子进程运行固定6组，最终成功且语义/来源稳定后才发布公开LF副本。

## Context and Orientation

唯一目录`C:/Users/Administrator/Documents/Codex/zhiming-v4-mod`。
冻结工具`tools/mod_week/benchmark_reflection_projection_RPF01.py` SHA`3878721ba37c645cd48924973c756931ac65232f4036351b77b81fcb71393e2d`。
复用其source_paths、assert_parity、candidate_hook、measured_cases；不替换这些函数或改参数。
performance.measure默认每组1预热、5次perf_counter观测、单独1次tracemalloc，固定oracle再candidate顺序。
source_paths仅读Core Python、工具自身、benchmark_reflection_v3/performance依赖和固定合成reflection_background_synthetic.json。
网络/socket/DNS守卫、parity、finally恢复原4别名与末尾来源集合/字节断言全部保持。
普通`-B`解释器，无-O/PYTHONOPTIMIZE；runner.environment清provider key、trace false、TEMP/TMP在本树private。

## Progress

- [x] 完整读取冻结RPF01工具/performance.py及旧反思workload，预核新输出路径、普通模式和来源。
- [x] (2026-10-21T11:29:36.185421+08:00) 单个普通Core -B子进程开始六组默认工作量；工具/3实验产品/18反思源不改。
- [x] (2026-10-21T11:29:59.211580+08:00) 子进程exit0，全部6组1预热5样本及独立tracemalloc完成；无pytest/full/coverage。
- [x] 成功后核最终experiment、原assert_parity、4alias恢复、288测量来源和239测试Python集合/字节稳定。
- [x] 仅CRLF→LF发布新报告；原始CRLF保留，JSON对象全等且逆变换精确还原raw SHA，lineage完整记录。
- [x] (2026-10-21T11:31:45.557043+08:00) 更新四活段落、§11小回执并冻结；旧perf/hash/产品/测试/fixture均未改。

## Surprises & Discoveries

冻结工具先写中间报告、再补最终字段；本轮只在exit0及所有最终守卫成立后发布。
performance.py“CPU wall time”原文没有被改写，lineage明确实际使用perf_counter墙钟、非CPU采样。
本轮完整100链中位oracle0.614113秒、candidate0.526050秒，比0.8566008210；1000撤源比0.9740682947，差异较小，不能推断显著性。
21份实验/反思产品SHA与旧最终报告一致，语义fingerprint也一致；新数据使用守卫版工具3878721b身份，没有给旧数字换新hash。

## Decision Log

这是新工具版本的重观测，不是新优化；所有6组单位数/顺序/1预热5观测/独立trace与原工具默认相同。
父进程environment移除12类provider key并禁tracing，PYTHONOPTIMIZE移除，子进程正常模式guard未绕过；子进程socket/DNS阻断自检及parity未改。
公开报告只替换实际CRLF为LF，内容/顺序/数字和旧limitations原文全部保留；准确口径在lineage/回执说明。
统计仅固定顺序单机5样本中位及比率，无随机化/置信区间；Python分配峰不是RSS，不把局部400投影当完整链延迟。
测量未接运行入口、仅22类有限精确输入类型；没有真实模型、PG、通知或业务应用结论。

## Outcomes & Retrospective

已完成守卫工具SHA `3878721ba37c645cd48924973c756931ac65232f4036351b77b81fcb71393e2d` 的唯一新观测，真实时间 `2026-10-21T11:29:36.185421+08:00` 至 `2026-10-21T11:29:59.211580+08:00`。
6组全部通过原守卫；288测量来源（284Core及4工具/依赖/固定synthetic）、239测试Python前后稳定。
4alias恢复，semantic SHA `dd83e380ac300e931f0a0cc3aa8ee9ff8fc78488ed42d468865f10b8bac66387`，与旧报告语义一致。
新raw SHA `f8dddbb4c5e654f0848adf80096964e5827bd03987c2233864024b169596f2e9`；LF公开SHA `dfd89ec3216ea6240fc6e46ff37ee34f3783bba115863c25e15b66256b9a9cf6`；旧报告保持原身份 `4d2e89e15144dbe557a6eb07b06fc2d167fca5d65a10e8902ec73c77225d4011`。
新lineage包含精确命令/时刻、逐来源before/after、工具依赖、可逆换行及限制；本任务没有任何产品/测试/fixture变动或Git操作。
不宣称新优化、CPU收益、统计显著、PG质量或上线完成；本轮不再追加测量，冻结交root。

## Plan of Work

用runner.environment启动普通Core Python -B原工具，仅--output指向新private文件。
外层记录真实+08开始结束、原始命令与stdout；前后独立核工具source_paths同形集合/字节。
另外绑定冻结3实验/18反思源及测试Python身份，不读任何私有校准/B正文。
工具成功后对原报告final字段和六组单位/观测次数/parity与别名恢复作发布守卫，然后只规范换行。

## Concrete Steps

工作目录为唯一mod目录，执行原工具：

    C:/Users/Administrator/Documents/Codex/zhiming-v4-p2/.venv-core/Scripts/python.exe -B tools/mod_week/benchmark_reflection_projection_RPF01.py --output private/mod-week/RPF01_guarded_20261021_1127.raw.json

输出公开到`docs/v4/evidence/MOD_2026-10-21/RPF01_guarded_performance_20261021.json`；身份链到`docs/v4/evidence/MOD_2026-10-21/RPF01_guarded_performance_lineage_20261021.json`。
本轮没有pytest或覆盖命令，不运行runner.source_snapshot（其Git不在授权内）。

## Validation and Acceptance

6组名与单位固定为oracle/candidate局部400、完整反思链100、epoch撤源1000；各1预热5样本加单独trace。
原工具assert_parity覆盖来源scope/撤销/无痕/缺permit及退出恢复；保留语义fingerprint不变检查。
无来源集合/字节漂移，无正文外部发送或真实效果；公开LF与私有原件JSON对象相等且字节换行可逆。
F03来源撤回传播、P5b SP06逆操作是沿用背景不变量，有限性能workload不冒称完整系统验收。

## Idempotence and Recovery

所有输出新增，任一路径已存在则停止，原报告与private原件不删不覆盖。
失败保留raw中间件和日志，发布只在最终成功后；重新运行须新路径与root另行授权。
无DB迁移、实际apply、服务、网络、部署或数据删除。

## Artifacts and Notes

原工具SHA见上；固定fixture SHA`185bfa68eb306ae4a2a8dda73df8c14cf0bca93a72076b04eb20720379768b88`。
旧最终身份时区性能保留`RESERVE_RPF01_projection_performance_final_identity_timezone.json`及原工具3ea3b1fa版本身份。
本轮原始SHA、公开SHA、源before/after和真实时刻只在成功后写入新lineage，不猜测数据。

## Interfaces and Dependencies

无新接口、依赖、schema、测试或产品修改。候选只在独立进程替换四个反思dataclass_json别名，finally还原；不接Q2/U4或生产。
perf_counter测量含guard/assert等原workload，排除导入、fixture初读、hash/parity证明和证据写入，非CPU采样。

## 修订记录

- 2026-10-21T11:27:41.431771+08:00：冻结计划及新private输出路径，尚未启动测量。

- 2026-10-21T11:31:45.557043+08:00：六组唯一重观测成功；原件CRLF与公开LF可逆、内容全等，来源/测试稳定；四活段落及回执完成后冻结。
