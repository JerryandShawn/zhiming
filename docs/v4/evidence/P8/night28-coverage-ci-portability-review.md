# 覆盖率静态测试：浅检出可移植性与保护迁移

完成时间：2026-10-21T01:57:54+08:00，北京时间，工具UTC换算。
审阅基线：`6292199d8fdb167d03fe54b07f74060cec59e101`；仅本工作树 `v4/p8-calc`。
初轮完整读取3份覆盖率测试、相关builder/source/plan/manifest和CI；先把迁移diff交root审阅，
获批准后才执行。没有改CI、builder、默认origin/cutover、v1工具、真实旧产物或其它工作树。

## 定位：四个节点，而非三文件全部有历史依赖

`.github/workflows/ci.yml:18` 使用actions/checkout@v4，没有fetch-depth配置，
`:69` 执行整个tests/v4。按此次预检的默认浅检出前提，若新检出只有当前提交及其树/blob，
不含7fa/f23/ef5旧commit对象，下面路径必定不能重新读取它们；这不是一个可由JSON重签修复的输入问题。
本轮没有运行真实GitHub CI、下载checkout action或联网fetch，不把静态推导写成已观察到的Actions失败。

| 原节点/位置 | 对旧对象的依赖 | 仅有当前浅提交时的行为 |
| --- | --- | --- |
| own.py原145：real_fixed_history | build_own_inventory(ROOT, origin7fa, ef5) | _pinned先commit_id→git rev-parse --verify；缺旧对象报coverage_git_read_failed |
| own.py原334：cutover_f23拒绝 | build_own_inventory(ROOT, base=f23, commit=ef5) | commit_id先于origin比较；缺对象时不能得到本来预期的approved_origin_required |
| independent.py原125：初版10路径 | real_inventory fixture原117先重建7fa→ef5，测试中又做两段真实diff | fixture先因缺旧对象失败，尚未进入路径断言 |
| independent.py原166：重签错误起点 | 同一real_inventory fixture | 同上；不能把fixture失败当成成功验证错误起点拒绝 |

其中own.py指 `tests/v4/test_p8_line_coverage_own.py`，independent.py指
`tests/v4/test_p8_own_inventory_independent.py`。构建顺序依据
`mingjing_core/adapters/charts/benchmarks/line_coverage_own_inventory.py:_pinned` 与
`line_coverage_manifest.py:commit_id/git_bytes`。

完整审阅后的两个重要排除项：

- `test_p8_line_coverage.py` 的build_manifest均显式传入private小Git的动态base/head；
  测试没有直接使用manifest模块的f23/6c默认值。本轮此文件完全不改。
- own.py的CPython版本保护仍保留ROOT/HISTORICAL字面值，但先将sys.version_info设为3.12，
  builder在safe_root/commit_id之前即拒绝；该节点不需要旧Git对象，没有删除或skip。
  同理，独立坏blob测试把git_bytes明确故障注入，ROOT参数本身不导致读历史。

上述判断针对已读调用路径；不能保证任意未来测试都没有历史依赖，未来新增默认builder调用仍需复查。

## 迁移Decision Log：原保护逐项保留

| 原保护 | 现在如何保留 | CI可证明的边界 |
| --- | --- | --- |
| 真实ef5的214文件/22741行、carry10、research51/native13/helper3/tool1 | own的固定真实artifact快照测试逐条保留原assert；新增helper核canonical inventory摘要与明确7fa/f23/ef5 | 证明提交产物未变，不称CI从真实Git重新推导214/22741 |
| 完整性true、coverage_collected精确false、每文件无line_counts | 原断言保留；合成live新增节点也逐项核同语义 | 仍是静态分母，不能由此声称已采样或达到90% |
| 原始默认origin/cutover不能静默换成其它值 | own快照节点额外比较产品source.ORIGIN/CUTOVER与冻结真实artifact元数据 | 合成patch不能掩盖默认历史政策常量漂移 |
| 初版10是完整路径、属于files及全部静态guard，非恰好数量10 | 固定真实artifact核实际10路径集合；另建合成3commit、10条同名路径、假内容，独立通过真实Git两段diff计算集合并和live inventory/guards比较 | 真实路径事实来自本机预检及固定产物；当前算法的结转行为由可移植的真实小Git验证 |
| f23/cutover不得取代初版之前origin | 作者原拒绝节点改用现有合成repository，临时patch ORIGIN/CUTOVER后传入确实存在的cutover与observed | 真的走commit_id及_pinned，不能以缺对象或摘要错误冒充approved_origin_required |
| 重签错误base仍拒绝 | 独立节点先用新合成历史live build，改history_base为该cutover、重签，再在相同policy下validate_own_inventory | 仍由实际builder重建/起点门禁拒绝，不是只信已存JSON |
| 各类自身源码归属/初版代码不漏 | 新增合成节点覆盖8分组；15个完整文件/15个可执行行，初版10未改均结转 | 数字只描述假源夹具，不能冒称真实P8当前分母 |
| 重签漏项/重复、坏hash/行号、bool/float类型、净零增删台账 | 原测试全部保留，继续用原private Git及真实重建验证 | 没有用固定快照替换这些算法与安全断言 |
| 任意Python链接/非正规blob、假Git头/截断内容、路径/未知归属 | 原测试全部保留，真实Git模式或明确坏响应故障注入 | 不导入目标源码，不以同长度/同数值假相等放行 |
| 静态计划不得变执行许可、精确AST/配置/节点/fixture/lifecycle | 原测试全部保留 | AST安全边界不升级成动态执行许可，未启动Charts或业务覆盖采样 |
| v1冷文件/归一换行/合并计数/重签/丢弃私密输出/独占输出 | 原v1文件38项不改 | 不为修新A测试牺牲既有v1保护 |

没有加“缺对象就skip”、xfail、网络fetch、可选绕过、放宽origin或信任任意自报hash。
算法guard继续调用真实builder/validator，不把它们替换成固定JSON结构检查。

## 假源夹具与真实产物严格区分

新增 `tests/v4/p8_coverage_history_context.py`：

- `historical_snapshot`只读root新生成的exclusive真实ef5清单，不调用依赖旧对象的
  validate_own_inventory(ROOT, artifact)；用canonical摘要绑定整个固定对象，同时核真实10路径/guards。
- `synthetic_history_repository`在本工作树private/tmp/coverage-portable-history/唯一目录创建独立Git，
  origin→cutover→observed三个动态完整SHA；README标SYNTHETIC，所有Python正文仅SYNTHETIC_*常量。
- 10条路径沿用真实初版文件名是为了测试归属分类及完整路径结转，内容与commit身份均是假源，
  不是拷贝旧业务源码或“重建出相同历史SHA”。后续5文件补齐8类归属，真实legacy.py作为未改排除项。
- ORIGIN/CUTOVER只在对应Python临时context内patch；Git实际对象、祖先关系、diff/tree/blob均真实计算。
  不更改builder常量、主仓库Git配置或当前分支。
- Git显式SHA1、假作者、禁GPG、空hooksPath及core.fsmonitor=false；只操作新建合成仓库。
  没有安装依赖、网络clone/fetch、递归删除或真实项目Git提交。

### 真实历史证据没有消失

根代理在2026-10-21T01:52:21+08:00用完整本机Git及当前A代码重新build/validate，
独占新建 `docs/v4/evidence/P8/night28-own-inventory-ef5fed9-static.json`，
canonical inventory SHA为
`6b4d2c868ce430bc04498ea8c56734a919a578b04b1d263452fe3043142d2d57`。
这里引用root已执行结果，不冒称本子任务再次全量重建或CI拥有旧对象。
原ed/89产物没有覆盖；ef5点仍是214/22741、carry10、guards417、excluded202、deleted0。

本轮只读Git cat-file确认本机7fa/f23/ef5三个commit对象确实存在。
真实重新推导仍只能在已核对象、祖先和编译环境的本机预检中执行；快照与合成单测均不能替代这一证据层。
本文未复制全仓历史、未执行真实浅克隆；缺对象结论是上述明确对象集合下的静态必然路径，
不宣称已在所有GitHub事件/缓存/runner上重现。

## 最终定向结果与样式

root先完整审阅迁移diff/helper并批准再运行。进程清API凭据、禁LangSmith/LangChain/OTel追踪、
禁pytest外部插件和conftest；指定原有解释器/tzdata，最多一个Core及其顺序Git子进程。

    <Core Python> -m pytest --noconftest tests/v4/test_p8_line_coverage.py \
      tests/v4/test_p8_line_coverage_own.py tests/v4/test_p8_own_inventory_independent.py -q

首次聚合91/91、0skip、24.18秒（v1 38 + 作者42 + 独立11）。
随后扩展仓库E/F/I/B/UP/SIM检查发现新增两条常量在左的SIM300；
只交换字符串相等断言两端，值/保护含义不变，再跑同一集合：
**最终91/91、0skip、26.74秒**，Junit `private/p8-validation/coverage-ci-portable-sim-final.xml`。
扩展Ruff120规则与默认88格式最终全部通过，diff无空白错误。
本轮不借旧2728或其它全量结果，也不把重复91项累加成182项。

| 文件 | 行数 / 最长行 / 最长函数 | 最终LF SHA256 |
| --- | --- | --- |
| p8_coverage_history_context.py（新增） | 113 / 88 / 28 | 7458c44ef2e2dd6cc7548a855132da81763b29ef51d5fab7e2a3956090ff48f1 |
| test_p8_line_coverage_own.py | 394 / 89 / 36 | 3053fc7a01d6f9676c3b7b8ef9d9d6e1a5c506354d6a8cf06bfb8db8554b7adb |
| test_p8_own_inventory_independent.py | 303 / 88 / 41 | 63f1cebb90a493cc010c162623308a9103282095e593252a707135da1957583b |
| test_p8_line_coverage.py（未改） | 原v1保护 | f23c431fc984890300c58ce3e3f6c4284b001c123cf885ffa77fa748ab065a70 |

所有测试/Git进程已结束、源码及测试冻结，之后只写本文。真实模型0、Charts0、业务目标覆盖率采样0、
DB0、网络0、服务器0；v1故障隔离测试内部的trace不作为已批准的业务覆盖观测。
未访问其它工作树、未提交/推送/合并。实际GitHub CI状态由root推送后独立确认。
