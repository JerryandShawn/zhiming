# RPF01：未接线的等价投影实验

当前只交付独立候选和离线证据，不替换现有反思入口。旧18个反思源、Q2、U4和既有测试没有改动。
候选能否接线需要主线另行评审，JSON/hash等价不证明来源授权、归纳真实性或线上性能。

最终候选已完成独立身份/时区边界审查。修前确有接受面扩大：metaclass equality/hash可冒充
白名单，自定义或不可复制时区在嵌套dataclass中也会越过旧deepcopy拒绝。已经先保存真实失败及
修前SHA，再修新候选；旧三个67a77版本性能报告都保留，不作为本页最终性能。

## 接口和支持范围

新增 `mingjing_core.application.reflection_projection_exp` 导出
`project_json(value) -> JSON值`、`projection_fingerprint(value) -> str`、`ProjectionError` 和
`SUPPORTED_TYPES`。错误继承旧`ReflectionError`，只有固定中文信息和固定reason_code。
字段名静态缓存；用户内容、时刻、来源/授权结果和投影结果没有缓存。

精确白名单22类为MemoryScope、MemoryFact、SourceAnchor、ReflectionProposal、ExtendedEventCandidate、
TimeCandidate、TimeRangeResult、AbsolutizedText、ReflectionEffects、ProcessedSource、ReflectionIntent、
BoundExcerpt、ExtractiveSummary、FactCandidate、DuplicateCandidate、KnowledgeGap、GapPriorityCandidate、
ArchiveCandidate、FollowupCandidate、WorkOmission、InvalidationCandidate和ReflectionWorkPlan。
这是冻结反思投影调用实际嵌套的类型；没有泛化接受任意dataclass或按字段长相认类型。

基础输入为None、精确str/bool/int、有限float、精确date/标准aware datetime，以及plain list/tuple/dict。
所有类型检查使用is；字段表用id整数键，持有强类引用并再次is核对，不调用攻击者类的hash/eq。
datetime时区只支持精确datetime.timezone和可reduce的精确ZoneInfo；自定义tz、时区子类和
不可复制的ZoneInfo.from_file保守拒绝。普通ZoneInfo.no_cache、DST fold0/1保持原oracle语义。
dict键必须是精确str；datetime使用原`instant`转换UTC ISO。每次重建list/dict，重复引用输入DAG
也逐路径生成独立输出，当前路径循环受控拒绝。最大深度64。未知类型、子类、非字符串键和更深
结构比原函数更窄；单独自定义时区datetime旧可能接受、新候选仍拒绝，不能叫通用drop-in替换。
这些限制不能悄悄应用到未经盘点的新调用方。输入须在投影期间不被并发修改。

原`dataclass_json`可能原样返回不能编码的对象；真正可用边界还包括`digest`的JSON/UTF-8编码。
新候选没有把bytes、set、NaN/Infinity、naive时间或循环变成可指纹输入。孤立代理码点字符串在
投影层与原函数一致，但仍被指纹UTF-8编码拒绝。投影本身不能替代Schema或字段语义校验。

## 验证和复现

`tests/v4/reflection_projection_exp/`最终1238项通过1.93秒，其中1200组确定种子的真实typed嵌套
向量逐组核对原JSON、原digest、输入不变、输出之间和重复输入路径之间不共享可变容器。
22类、UTC/六时区/DST瞬间、Unicode、空容器、bool/int、有限浮点、非法值、循环和更窄边界另有
明确断言。合成字符串仅保存在`tools/eval/fixtures/mod_20261021/reflection_projection_vectors_synthetic.json`。

独立peer9项包括原6个metaclass反例和时区复制改变offset/no_cache fold0/1；自有3项补齐
嵌套自定义tz、单独datetime更窄以及精确ZoneInfo.from_file。原6项断言未迁就产品改动。
仅3实验源branch coverage的1238项另过3.63秒：行79/79、分支26/26、综合105/105均100%；
详见coverage_final及coverage_scope_final。没有为覆盖增造对象，行/分支全覆盖不等于条件覆盖、
完整输入证明或授权正确性。

在仓库根目录、隔离Core解释器中运行新目标测试；不是全量、不是模型评测：

    python -B -m pytest tests/v4/reflection_projection_exp -q -p no:cacheprovider

性能复现须使用全新的输出文件名：

    python -B tools/mod_week/benchmark_reflection_projection_RPF01.py --output <仓库内新JSON路径>

工具自行清五个API key环境值、关闭两项tracing，阻断socket和DNS入口并验证阻断。没有传输、
模型、PG或真实消息。独立进程只临时替换反思validation/intent_guard/summaries/work四处投影别名，
`try/finally`恢复并核对对象身份；没有patch旧Q2/U4。原oracle递归会读取模块全局别名，所以等价
比较只在hook之外进行。异常退出的恢复路径也有断言。全Core文件集合和字节前后都核对。

## 实际观测

唯一最终证据是`docs/v4/evidence/MOD_2026-10-21/RESERVE_RPF01_projection_performance_final_identity_timezone.json`，
实际北京时间2026-10-21 09:07:20，进程48708，283个Core源加工具/fixture共287来源全部前后及
当前复核一致。候选aggregate为`707ed17655c261b35407ef26e9826bacd96befd82afb1f4b755b662de49c8005`；
旧反思18源仍为`2eee084f643e38d0e32d918e52ecc93c7ce1564558332419a94ffa3321ef390d`。

| 同一工具的配对路径 | 原实现中位秒 | 候选中位秒 | 原/候选独立Python分配峰（字节） |
| --- | ---: | ---: | ---: |
| 400次局部投影+原digest | 0.1317979 | 0.0438021 | 252098 / 124528 |
| 完整100次M1→M2→八节renderer | 0.6147579 | 0.5142756 | 294721 / 233489 |
| 1000次撤源epoch→仅失效候选 | 0.3821930 | 0.3734919 | 44973 / 43071 |

完整100链本次中位下降约16.35%，不能拿局部约66.77%的下降冒充完整收益。每路径一轮预热、
五个未插桩墙钟样本和独立tracemalloc；完整链包含fixture解码、输入构造、全部当前授权守卫和输出断言。
局部路径预先构造语料，不包含其准备。导入、fixture字节读取、hash、额外等价证明与证据写入不计时。
分配峰是Python分配，不是RSS。样本没有置信区间，配对顺序未随机化，缓存和OS活动可能影响结果。

团队通过消息协调在最终进程期间没有其他测试/性能进程；这不是OS全局空闲证明。前三个报告
`RESERVE_RPF01_projection_performance.json`、`..._final.json`及`..._final_hardened.json`均保留，
全是67a77修前产品；前两个还是工具加固前记录，首个还可能与短pytest重叠。旧文件名含final
也不能当最终采用证据。详细分类在同目录run_manifest中。

## 主线接线和退出条件

本轮不要求改任何既有文件。未来若接线，主线应逐点核实新增调用形状仍在白名单/深度范围，
保留所有当前来源、revision/epoch、scope、许可、时钟、失败和失效重查，再决定四个调用点是否
显式导入候选。不要用通用try/except把未知类型悄悄吞掉；不支持输入应保守失败或显式回原入口，
且回退也须有完整等价/错误行为测试。不能把候选投影当成可授权凭证或自动写入的依据。

任一等价、输入不变、无共享、来源集合/hash或恢复证明失败，立即弃用本候选并保留证据。收益
不稳定或线上调用面不兼容时不接线即可，冻结实现一直保留，没有数据库迁移或回滚操作。
