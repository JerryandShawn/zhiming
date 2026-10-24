# 核心首发生产切换草案

2026-10-24 11:56，北京时间。**No-Go / 草案：尚无可执行的首发生产切换与原生恢复入口。** 新显式本机源写main的默认/坏材料与prefix7完整链首次两目标通过，范围及唯一证据只在[增量ExecPlan](../execplans/first_release_incremental_20261024.md)登记；本机方法级main通过不是Linux应用或生产恢复验收。原正式`f6fb9f1`的push/PR M1会话失败仍保留，旧额外PID身份未知，当前工具头/测试archive均非最终发布包；observer/admission须新捕获并审核10控pin，不能补写旧输入。正式目标仍只有文件契约/可选只读ACL；Linux应用、原中央保全、全局writer、切换及开门均未放行。无服务器、真实模型或飞书动作。

旧B1不再单独上线，旧B/D授权失效。**只有用户对本次最终候选、生产对象、维护窗口、修改、渠道恢复及止损范围重新授权，才可进入生产步骤。** 大脑审核stage及本单是必要输入，不替代用户授权。旧30/31文件、旧工作日窗口或旧一次模型冒烟不能自动成为本次许可。

## 1. 发布身份与前置门

当前草案为P1/P1b/P2/P3的`core-only-1-8-v1`：八项迁移checksum、规范Git blob manifest、artifact、Core/Charts/K3三锁和模型配置须绑定最终审核候选。若P5/0009并入，先新增受审profile、关系/例程清单、恢复链与stage证据，再重写本单；不能临时跳过现门。

| 前置门 | 当前状态 | 必须具备 |
| --- | --- | --- |
| 最终候选与质量 | 最终候选未冻结，不能引用工具提交替代 | 同源脚本/集成及必要真实质量门；实际主模型由受信等价结果/明确fallback决定 |
| stage B0–B8 | 首发stage未验收 | [stage草案](first_release_stage_runbook.md)全部必要步骤完成，并由大脑审核 |
| Linux运行时 | Core/Charts/K3整链未证明 | 实际Linux Python3.11双环境、锁依赖/导入来源/权限、官方K3本地文件、实际网络与跨exec锁 |
| 原生新库恢复 | 只有validate/可选只读ACL，没有apply | 精确备份→新库恢复→合法前缀/1–8→最新撤销及送达收据双重放→幂等/权限/checkpoint证明 |
| 增量/切换/回滚 | 本机Forward及同call源重放/回填闭环已有实证；正式CLI、受保护重绑定与开门前回退链仍缺失 | 分步可审的完整实现、同源Linux演练、失败不放开writer，R1门落实 |
| 新授权与当前环境 | 没有本次生产新授权/盘点 | 明确SHA、窗口、库/角色/unit/env/wrapper/入口、owner范围、正常业务恢复及止损权限 |

任一门缺失就是No-Go。现有Windows逻辑测试、实际Linux PG容器可启动、单个HTTP200或JSON布尔值均不能解除这些门。所有估时是计划值，尚未测得正式RTO。

## 2. 当前能运行的校验，以及不能运行的命令

以下接口已存在，**本次未运行**；所有路径先由审核输入绑定。敏感环境只由受保护loader注入，禁止source任意env、打印口令/完整DSN或把它们放argv。

```bash
cd "$FR_CONTROL_DIR"
"$FR_CONTROL_PYTHON" -m tools.first_release_restore \
  --pin "$FR_PIN" --contract "$FR_CONTRACT"
```

默认文件校验、0PG连接、0修改。正式候选路径固定`/root/zhiming-core-releases/<最终SHA>`。外部审核pin为受信输入；工具校验其字节绑定，不认证审核人、pin文件保护模式、真实Git tree归属或新鲜度。venv/artifacts仍有独立运行时门。

本机隔离范围或用户新授权明确允许**已独立建立的恢复库**后，才可增加只读ACL：

```bash
"$FR_CONTROL_PYTHON" -m tools.first_release_restore \
  --pin "$FR_PIN" --contract "$FR_CONTRACT" --check-acl
```

正式只允许`zhiming_core_first_restore`和同名`_owner`/`_writer`，不接受`zhiming_core_live`、原stage或旧B1恢复库；不创建目标。`FIRST_RELEASE_OWNER_DSN`与`FIRST_RELEASE_WRITER_DSN`不得误指运行库；两次只读事务固定并核验pg_catalog路径，按当前八项迁移和精确最小权限核验，绝不自动修权限。无apply/pg_restore/切换/回滚参数，输出不构成恢复证明。

如果同机stage已占用该固定恢复目标，生产不能覆盖、清空或删除它。独立生产恢复目标及其空库/操作身份约束须先新增受审契约和apply实现；当前单一目标校验不能解决这一缺口。

**禁止套用旧入口：** `core_incremental`、B1 restore proof/replay、`b1_publication`均保留其原b9/scope契约；不改常量来接受最终候选，不用手填proof解除Native拒绝。`deploy_core freeze/install/publish`包含既有全量迁移、旧入口或真实渠道副作用，不能用于已有Core PG增量。`restore-withdrawals`硬live目标也不用于本次新库恢复。本单不提供尚不存在的首发apply命令。

新增`tools.first_release_local_restore`只接受local_drill=true、本机55480/55481及本次随机新库/角色，默认仅校验，显式--apply-local才实际恢复原prefix1–7；创建前拒绝任一既有对象及含中央额度表的archive。同次再显式--upgrade-local可从原持锁新目标前向至8、checkpoint setup、最小授权与精确ACL，0008仅验空表，不构成合法账本保全/重绑定；失败保留阶段，不接管旧库或修复重试。它没有formal/stage/production入口，不支持0008账本恢复、重绑定、unit或开门；默认及upgrade-only路径不重放最新旁账，不能代替D3。实际Windows PG15定向证据见原ExecPlan；Linux容器NAT身份不匹配仍硬拒，未把Windows结果改称Linux通过。

该本机入口另有显式`--replay-preflight-local --preflight-pin --preflight-ledger --candidate-python`组合，完整本机命令及受审pin字段见[stage草案的本机入口](first_release_stage_runbook.md#本机新入口不能替代b3b7)。它必须仍在同call新库恢复/升级的creator锁内，额外启动实际候选Python3.11 venv进程核源码来源、活动依赖与只读目标状态；正常总连接8。名称含replay的预检参数不执行撤销/收据重放，所有正式恢复、运行时、Linux与发布完成位保持false。不能将这一预检移到生产已有库，或拿其回执解除D3；源prefix8的中央身份和历史保全仍未实现。

本机显式`--replay-withdrawals-local`另用独立replay pin与helper hash，只接受新目标原prefix4/7→8，真实候选原生撤销/收据双重放后严格比较完整状态，正常总连接9；完整可用命令与独立擦除未覆盖项同见stage草案。其成功不标记正式native、中央身份、Linux或publication；源prefix8、生产已有库接管及实际Linux切换仍未实现，不能把本机重放结果改称D3通过。

本机已有合成库M1备份现已接显式“关闭准入→旧进程自然退出→采用原标记采集”，命令及精确限制统一见[stage草案的本机备份入口](first_release_stage_runbook.md#本机已有合成库备份m1不能替代stage停写)。新`--close-admission-local`与备份互斥，`--use-admission`只配`--backup-local`，不接管已有失败备份，不覆盖/清除标记，不支持任何生产对象；M1控制hash现为10项，旧pin必须重新审核而非自动升级。限定首链4/4及真实故障保留只证明本机组件接通，旧实际入口尚未共同纳管，Linux、正式中央身份及切换仍未解除，D1/D2不能据此执行。

本机M2已能将新UTC捕获与同call新恢复目标的实际原始内容绑定，命令统一见[stage草案的M2入口](first_release_stage_runbook.md#本机捕获与原始恢复绑定m2)。单独绑定模式在升级之前检查完整表/逻辑列/序列语义；同节另给同时提供capture和replay独立pin的组合命令，已有真实prefix7捕获→原始比较→升级8→原生双重放的1/1定向证据及两次fixture错误记录。它不证明当前源库未再变化，也不提供生产恢复或现库升级授权；D2/D3仍需完整新证据及新授权。

TargetProof、源guard/postcheck、Forward内部组合及后续源重放/回填组件的分轮结果与失败统一只指[原增量ExecPlan](../execplans/first_release_incremental_20261024.md)，组件范围与剩余门见[stage组件表](first_release_stage_runbook.md#本机目标证明与源升级组件正式源写入口未就绪)。本机Forward已组合目标证明/运行时、源升级及prefix7源隐私重放→回填完整闭环；新显式main已完成限定本机验收，固定15参数、默认零副作用与唯一执行旗标统一见[本机源写入口](first_release_stage_runbook.md#本机完整源写命令仅本机合成库)。没有可执行的正式源升级/原生恢复/回填CLI。Linux运行镜像、正式中央身份保全/重绑定、完整切换与开门门仍No-Go；本单不增加未验证生产命令。

同进程固定服务入口 `tools.first_release_service` 的实际参数、受限 writer/SID 绑定、已有 workspace 双栅栏及持锁退出方式统一见[stage 草案的服务入口](first_release_stage_runbook.md#固定服务入口与进程寿命栅栏组件不放行停写门)，证据只登记其服务栅栏 ExecPlan。默认静态校验，显式 `--run` 才启动；当前没有生产运行授权，也未替换任何 unit 或 Hermes wrapper。硬退出能防止后台线程活着时先解锁，但不能证明在途外部投递取消、业务排空或完整停写；不得据此解除 D1/D5–D7、移除维护标记或自动补发。

## 3. 停写、备份、增量、切换、开门顺序

获准后仍一次一阶段核验，不以shell循环串过审核门。以下修改动作当前均因缺失首发入口而阻塞；表中是实现和演练后的操作要求。

| 阶段 | 动作与当前入口状态 | 继续条件 | 停止条件 | 预计耗时 |
| --- | --- | --- | --- | --- |
| D0 | 完整核新授权/stage回执/候选；只读盘点当前主机、PG、schema、磁盘、队列、unit/env/wrapper安全摘要 | 在批准窗口内，所有输入与当前实际状态一致，恢复余量充分 | 任何授权/版本/身份/容量漂移；不能沿用历史容量值 | 10–20分 |
| D1 | 设置生产维护门；停Web、飞书、报告service和timer；排空并持有共同排他writer锁；首发控制器缺失 | 所有入口停写，queued/running/有效lease及未知客户端0，锁覆盖后台线程及完整进程寿命 | writer未停、外部CLI绕过门、未核drop-in或守护进程 | 5–15分 |
| D2 | 一致PG custom dump、最新无正文撤销/墓碑/sent/uncertain旁账及配置/unit/技能备份；首发入口缺失 | 文件/目录保护模式、hash、原schema与业务安全摘要绑定同一停写点 | 备份/旁账失败，源前缀兼容缺口，中央账本可能回退 | 15–40分 |
| D3 | 先恢复D2精确备份到新allowlist库，双重放与幂等/ACL/旧包兼容审查；现工具仅校验 | 实际新库恢复证明及开门前回退路径均合格，中央账本位置/历史保全 | 只有validate输出、旧B1空样本或Windows结果；任何replay差异 | 30–60分起 |
| D4 | 合法已有库前缀前向至8、最小授权；受审owner dry-run→apply→repeat；首发增量/回填入口缺失 | 八checksum/最小ACL精确；repeat的message_metadata/search_tokens/assistant_created均0，其他只读计数可非0；原文、owner隔离、牌面、撤销与收据保持 | 错库/错角色/历史改写、未知owner、重复写变化、误给额度表DELETE | 15–45分 |
| D5 | 同一维护窗更新三service+timer、Core/Charts路径、受审环境、Hermes Core wrapper/manifest；原子步骤入口缺失 | 所有文件与实际进程同最终SHA；原启停状态已保存；没有部分切换 | 部分更新、旧解释器或wrapper残留、环境覆写、未知drop-in | 10–20分 |
| D6 | 门内仅启动受审Web，核Agent实际启用、真实实例/队列/旧网页读兼容；保持渠道/报告停 | 无待恢复真实任务；readiness检查不触发模型或外发；准确核Web自身PG会话 | 关闭Agent混作成功、后台任务抢跑、非预期调用或数据变化 | 10–20分 |
| D7 | 最终Go/No-Go；经新授权的开门控制器记录开门点并恢复获准后台状态；入口缺失 | 同源全部门、窗口、维护/fence、配置和新库恢复证据再次核准，非原子顺序被明确接受 | 任一缺项、窗口不足、只有手删flag方案；不开门 | 3–10分 |
| D8 | 仅当本次新授权明确允许时做精确限定冒烟；本单默认0模型/0飞书 | 指定场景/模型/物理次数与失败规则被授权；结果独立记录 | 未授权、额度/权限错误；不重试、不换key/模型绕过 | 0–5分 |
| D9 | 观察30–60分安全计数、错误和业务状态，交回执 | 无严重故障；正常后台恢复与观察数据一致 | 任一严重异常：按§5关门止损，绝不恢复旧备份覆盖新写入 | 30–60分 |

建议先为主动维护预留2–4小时并按stage实测调整，观察时间另计；缺失实现、审核、安装和等待不计入可承诺维护窗口。避开实际报告准备/投递时段（现有06:45/07:00及其他日程），不为发布擅改日程或补报。

## 4. D5必须一起处理的对象

| 对象 | 受审更新与核验要求 | 当前缺口 |
| --- | --- | --- |
| Web `mingjingtai.service` | WorkingDirectory、固定Core解释器、有效ExecStart、env、单Uvicorn worker及实际PID；Agent dispatcher随Web进程，不凭空加独立worker unit | 最终unit与Linux门内装配/停启未演练 |
| 飞书 `zhiming-core-feishu.service` | 同SHA/解释器/env；既有文字入口，精确恢复维护前获准状态；验收不发测试消息 | 新运行时正常恢复可产生真实业务，须新授权明确包含 |
| 报告 `zhiming-core-reports.service`及`.timer` | 同SHA/解释器/env，保存active/enabled状态，核Persistent和已到期任务，不能启动即补发 | 最终恢复策略及无重复送达证据待审 |
| Charts | `CHART_PYTHON`与独立Charts环境共同固定最终release；不把Core/Charts依赖合并，不仅看文本变量 | Linux解释器、锁依赖、实际子进程来源/缓存与权限未验 |
| K3/模型/中央守卫 | 已验本地官方K3目录与锁、registry模型锁/高思考、已有account/identity/实际location；Agent开关明确true、运行容量至少3 | Linux装配及中央ledger保全/重绑定门未完成；不provision来放行 |
| Hermes知命Core wrapper | 只更新固定release入口及受审manifest，环境加载顺序明确；退役stub/原备份保留，manifest最后原子写 | 旧/新wrapper共享维护门与完整Core进程锁的同源Linux演练待补；不整体重启Hermes |
| 维护门与writer锁 | Web反代/应用门及共同workspace内稳定数据库身份锁覆盖全部Core入口；旧Hermes单独的core-skill锁不能代替；持EX期间核实际无writer | 不能只凭flag存在或源码常量相同声称跨进程成立；全入口替换和排空仍待 |

首发三 service、Hermes wrapper 及共同 CHART/K3/Agent 配置现有本机审核资产生成接口，精确字段、默认零副作用和新目录命令统一见[stage 草案的审核资产](first_release_stage_runbook.md#首发服务审核资产只在本机生成尚未安装)。只生成供审文件，尚未安装；原 timer 不生成、不恢复，真实状态未知。资产不能代替 D5 的原文件备份、有效 drop-in/环境审查、部分失败关门、Linux 联演或授权；D1/D5–D7 仍不能执行。

生产配置只能在受保护文件中做已批准的精确更新，不打印Environment、token、完整DSN、原始reasoning或私人正文。有效unit需核FragmentPath、DropInPaths、NeedDaemonReload、KillMode/SendSIGKILL及实际进程；磁盘文件hash不等于进程已切换。不要触碰无关Hermes技能或服务。

门内Web启动可能恢复队列/反思/提醒任务，HTTP maintenance不自动约束dispatcher和后台writer。必须证明队列为空、无有效租约、无未知PG客户端、渠道及报告仍停；不能把自身“0请求”当作后台流量为0。若采用先Web开门再恢复后台的非原子顺序，新授权须明确接受，中途失败只关门止损。

## 5. R1：只在开门前回滚；开门后保留现场

开门点指首次对外移除维护限制或恢复任何正常业务writer中较早发生的时刻，不能等所有服务成功后才记时。

**开门前：** 保持维护与全部writer停止，只有已演练、授权涵盖的回退路径可执行。若业务库尚未改变，可在兼容审查后回到原配置；若迁移或回填已提交，不能只把unit换回旧包。需要把精确备份恢复到另一个新目标、重放最新撤销/收据、核旧schema/旧代码兼容与权限，再审核DB重绑定。当前首发校验契约只覆盖新候选1–8，不提供旧schema恢复或原生重绑定；旧包兼容链缺失时继续关门，不声称可以回滚。恢复到8并继续新候选是向前恢复，不是旧包回滚。

**v12/R2的新库对调规则：** 禁止向已升级业务库执行`pg_restore --clean --if-exists --single-transaction`，0005的父run外键会阻挡删除旧主键。应把维护前精确dump恢复到另一个新库，保留对象属主和ACL，不能用`--no-owner`或`--no-acl`；现有本机local-only入口使用这两个旗标的合成两角色映射，不是此正式恢复路径，不改其限制冒充合格。对调前记录原库OID、owner、完整CONNECT授权（含PUBLIC/授权选项）及库级和角色库级`ALTER DATABASE/ROLE ... SET`设置，持续维护/停writer并确认两库连接均0，才将原库改名为受审`live_failed_<时间>`、新库改为原名，按原快照恢复库级身份/权限/设置并逐项核验。任一步异常保留两库与现场，禁止强制断连、覆盖、删除或自行重试；旧库保留，未审核前不开放连接。当前工具尚未实现这条正式对调链，D3及回退门继续No-Go；不再投入Docker拉镜像，本机PG只补必要行为验证，应用Linux留到新授权stage。

**开门后：** 不论距开门几分钟，都不自动恢复维护前dump、不降schema、不切旧代码去写不兼容库。严重异常先保持/重设维护门，停止获准Web/飞书/报告+timer写入口，取得Hermes Core writer栅栏，保存最新状态、撤销/送达收据和故障信息，保留新写入，等受审向前修复。旧B1“开门后60分钟恢复旧备份”的规则不适用于本次，不能沿用其接受丢失新消息的旧许可。

0008额度账本绝不随业务备份回退。禁止清空usage/attempt、重建账户、重置stop或自动provision；既有account/ledger identity/location不符时停留关门。正常回填/恢复也不能重发sent/uncertain、复活已撤销内容或丢失恢复后墓碑。提交后checkpoint清除或回执落盘失败均保留现场，不自动重放整批。

已有中央继续保留原位置、仅切新业务DSN的实际配置接缝与本机限定验证统一见[stage中央策略](first_release_stage_runbook.md#原中央与新业务库的配置接缝不放行正式门)。本机路由成立不解除D阶段中央门：实际中央基线/角色、原库保留和旧业务writer处置、受保护env、同候选Linux及各入口仍须逐项审核；不得把“保留原中央”解释成许可继续运行旧业务入口或自动迁移账本。

不在本单中删除原库、旧release、备份、卷、媒体或技能原备份；保留时长和后续清理另批。任何操作异常停止并记录安全错误码，不自行改PG认证/权限后重试。

## 6. 最终回执与来源

一份生产回执应包含新授权引用及窗口、候选/工具/manifest/artifact/三锁、stage验收来源、实际主机/PG/迁移安全投影、备份与最新旁账hash、迁移/回填/双重放计数、三服务+timer/CHART/wrapper前后状态、开门与停写实际北京时间、授权范围内请求/消息计数、观察结果、异常和未验证项。不能由本单生成“通过”布尔值或推断已部署；只引用受保护证据，不新增重复证据副本。

源码：[校验CLI](../../../tools/first_release_restore.py)、[契约](../../../tools/first_release_contracts.py)、[只读ACL](../../../tools/first_release_acl.py)、[Agent装配](../../../mingjing_core/application/production_agent.py)。状态与证据索引见[恢复ExecPlan](../execplans/first_release_recovery_20261023.md)。[旧B1生产单](B1_prod_runbook.md)保留历史事实，其固定b9、旧授权和开门后回滚不得复制进本次执行。
