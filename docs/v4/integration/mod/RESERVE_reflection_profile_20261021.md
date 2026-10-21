# 反思纯模块的 cProfile 热点观测与优化候选

本轮只新增 `tools/mod_week/profile_reflection_v3.py` 和本说明/JSON证据；没有改冻结18个反思源、旧Q2/U4、基准或测试。没有执行产品优化，也没有预报收益。

最终证据是 `docs/v4/evidence/MOD_2026-10-21/RESERVE_reflection_cprofile_final.json`，实际记录北京时间2026-10-21 08:34:43，运行环境CPython 3.11.16。初版 `RESERVE_reflection_cprofile.json` 保留为08:32:45观测；最终版补齐旧 `memory/policy.py` 的来源hash、运行时版本及pstats总调用数/时间核对，不用初版工具hash充最终结果。

## 如何复现

在 `C:/Users/Administrator/Documents/Codex/zhiming-v4-mod`，使用现有Core解释器、关闭tracing、模型Key置空、TEMP/TMP固定工作树private目录后，指定一个未存在的新JSON文件：

    python tools/mod_week/profile_reflection_v3.py --output docs/v4/evidence/MOD_2026-10-21/<new-name>.json

只读取显式 `synthetic=true` 的 `reflection_background_synthetic.json`，复用原 `benchmark_reflection_v3` 的100次完整链与1000次失效链，未导入测试helper。每条路径预热1次、非profile对照3次、cProfile instrumentation完整执行1次；最多一个性能进程。输入构造、来源和敏感/当前性校验、真实纯函数及原基准断言全部包含。导入、fixture字节读取、源hash和输出写入排除。

运行前后核对反思18源、冻结memory2、timeparse、旧memory policy/slots、调度wall helpers、Clock、原基准、fixture及本工具hash；不一致就拒绝写成功证据。最终记录 `source_hashes_unchanged=true`。没有模型、网络、数据库、队列或真实通知。

## 观测结果

| 路径（每样本工作量） | 非profile三次中位 | cProfile单次wall | 观测比值 | 总调用 / primitive调用 | 函数项 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 完整M1→M2→八节画像（100次） | 0.706174秒 | 2.193717秒 | 3.106倍 | 6,463,203 / 6,137,803 | 381 |
| 撤源epoch→仅失效候选（1000次） | 0.445347秒 | 1.263832秒 | 2.838倍 | 3,661,003 / 3,616,003 | 144 |

cProfile是确定性函数调用插桩，不是统计采样。对大量很短的校验/递归调用，插桩会明显改变相对开销。这里的比值只是同进程1次instrumented与3次非profile观测的比较，不是可外推的因果开销估计，更不是生产延迟。主机调度、其他本地工作、缓存和运行时都会影响数字。

JSON给出所有函数的文件/行/名称、total与primitive calls、self与cumulative秒数、caller归因、两种top20以及按类别汇总的exclusive self。没有函数参数、局部变量、原话或用户正文。生成的dataclass代码可能统一显示为`<string>`，不能仅凭该名称把它归给某一个实体。

完整链的主要热点：

| 函数 | 总调用 | self秒 | cumulative秒 | 含义 |
| --- | ---: | ---: | ---: | --- |
| `reflection_v3.fact_policy.select_facts` | 300 | 0.011073 | 0.733577 | 每100链中work、画像检查和renderer多次选择当前授权事实 |
| `reflection_v3.validation.dataclass_json` | 107,000 | 0.067313 | 0.611809 | summary/intent/work指纹的递归结构投影 |
| 冻结 `memory2.guards.authorize_fact` | 8,200 | 0.024621 | 0.559663 | 与策略/画像等调用树重叠的来源校验 |
| 标准库 `dataclasses._asdict_inner` | 100,800 | 0.134537 | 0.473430 | 递归asdict及复制 |
| 冻结 `memory.policy.mask_quoted` | 22,700 | 0.133159 | 0.463493 | 来源拒记/引语授权使用相同引号遮罩 |
| 标准库 `copy.deepcopy` | 122,200 | 0.115722 | 0.225109 | 主要由asdict调用 |

这些cumulative行互相嵌套，**不能相加成可节省时间**。例如authorize包含anchor校验，mask_quoted又处于该调用树内；dataclass_json包含asdict/deepcopy。exclusive self只是在本次插桩下的函数自身时间，不是去掉函数后的真实收益。

失效路径中，原基准 `arguments` 1000次累计0.700679秒，`pair` 14,000次累计0.408830秒；原基准每轮重新构造14条来源/事实和画像。它们嵌套于1.263832秒总观测，说明这里有大量合成输入准备成本，不能把这些数全部说成“失效引擎慢”，也不能通过移出准备来伪造同一指标变快。

## 尚未实施的可验证候选

### RPF01：专用只读结构投影，先验证指纹完全一致

证据是dataclass_json/asdict/deepcopy的调用量和caller树，特别是`work._sealed`与`summaries._summary`。可在root授权的新版本或独立适配候选中研究直接遍历受支持不可变字段，减少先asdict递归复制再转换的重复工作。本轮没有写该替代器。

验收必须先对支持的所有typed输入验证：UTF8文字、tuple/list、aware时刻UTC、嵌套候选、空集合、bool/int与有限数值保持同一规范化结果、同一指纹，且不改输入；包含至少1000组生成式对照。异常/非法值必须仍失败，不能把原本拒绝的自认证对象变成可用输入。再跑完整240项及root要求的回归，最后用相同100链、相同计时边界的非profile五样本和tracemalloc比较。没有这些测量前收益为“未知”。

### RPF02：六种引号模式预编译，交旧策略所属主线

源码只读核对表明 `mask_quoted` 每次循环构造六组固定模式，反复调用re.escape/re.sub；本次完整链中re.escape总调用408,600。模式编译缓存已有帮助，但构造与escape仍发生。这是冻结旧 `memory/policy.py` 的热点，模块线不代改、不monkeypatch、不全局缓存用户正文。

主线若实施，必须逐字保留原引号类型、Unicode、换行边界、替换为空格的长度和顺序；覆盖嵌套/不完整引号、拒记命令位于引号内外、原话切片边界、假设与双重否定，证明不把转述变成同意。微基准只能解释模式构造，收益判定仍要同一完整链非profile测量。当前没有收益数字。

### RPF03：同一权威快照内共享已计算选择结果，安全成本最高

完整100链触发300次select_facts和8200次authorize_fact，caller显示work与两处current_profile_items重复处理相同投影。可以研究一个只在同一不可变输入/同一时刻内存在的、由可信计算产生的结果对象；当前API没有该适配，不是可直接插入的优化。

必须完整绑定scope/thread、snapshot revision、source epoch、所有使用的事实/原话revision和内容、当前源flags、Clock时刻、settings及confirmation。不能接受调用者传一个`valid=True`，不能跨请求/跨时刻缓存，不能因为epoch没变就忽略原文、role、时间或撤销变化。实际写入/发送前仍单独权威重查；共享结果不是PG权限证明。

验证至少覆盖旧源全文/role/at变化但漏epoch、撤销/incognito/optout、出生专用确认、过期边界、scope交叉、单槽双当前、pinned/手改和空manifest仅失效。先保持所有原断言，再测真实完整链。不能为了减少调用数直接删掉安全校验；此候选需要主线审阅，未实施且收益未知。

### RPF04：把输入准备与引擎本体分开观测，保留原指标

失效基准的主要构造成本属于合成host投影。可新增一个明确标注“已准备不可变输入”的辅助观测，与原完整1000链并列；不得覆盖或重命名旧完整指标，也不能移出授权重查。目的是回答成本位于哪里，不是宣称产品已经优化。`MemoryFact.__post_init__`等严格类型/来源校验不能因合成输入构造昂贵而放松。

## 交接与当前限制

为08:45已完成模块全量回归保留冻结，本轮没有任何产品优化。所有候选等root决定是否安排新版本/适配实验；旧Q2/主线文件保持只读。当前新工具已实际执行两条完整路径及内置断言，pstats调用数与self总量核对通过；源hash一致。没有新增pytest、没有重跑全量、没有Git操作，也不读取整理盲评B或75材料。
