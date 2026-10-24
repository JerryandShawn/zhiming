# 核心首发包：增量升级与恢复

首发为P1/P1b/P2/P3，已采用指令板v14；真实评测及stage交大脑，模块暂停，本代理只写必要代码并做隔离本机验证。这里的本机证据不授予服务器访问或发布权限；旧B/D均已取消。遵循`.agent/PLANS.md`，所有时间为北京时间。

## Context and Orientation

复用`tools/deploy_core.py:387`的export_withdrawals和`:405`的apply_withdrawals、仓库mutation_request的持久幂等、TarotService的真实删除与现有LangGraph checkpoint清除。旧b9包及其固定恢复工具/测试保留历史事实，不改hash或重签来掩盖已知非空往返限制。最终候选还未冻结，不填写虚构发布SHA。

## Progress

- [x] (2026-10-24 14:41 +08:00) 两份交接单改为现有接口的逐步精确命令：F包/公开artifact上传→新copy/prepare→空增量备份/原生对调→新runtime资产/admit/8788及维护/实际cgroup核验；本机接入4物理/core30自动小批/已知5h新题头run/安全汇总。14个Bash、7个PowerShell块及内嵌Python只做语法解析，未执行服务器/请求；最终候选仍占位硬拒，不标就绪。另静态核现有CI配置发现native fixture误取主CORE5432而忽略已配置的独立restore55480；本机新目标先真实复现早拒1失败（3b2e210fcf534176895b67b09c19bd34），最小fixture修复后新路由与旧完整FK/新库对调两目标2/2（1.78s，bc219b74809b4e649ddcdf44f7ce45bc），根读metadata/XML/log。未放宽正式端口/身份，不声称远端CI已失败或已修绿。

- [x] (2026-10-24 14:19 +08:00) F必要B7/运行资产接线：新副本关门0连接→只读检查精确prefix8/checkpoint→新empty-delta备份→既有R2新库restore/seal/exchange，保留两库、完整Core/checkpoint/sequence相等，旧prefix和在途会话拒绝且保留。初新B7两节点2/2（2.47s，8dc9e5789a974f7586e19c470f57be25）；补prefix8门后必要正反2/2（2.67s，2889fc7d81fb429a977461832d4f86a2）。新stage_app真实DML PG+公开K3+Agent装配，拒模型端口和所有非健康/状态/历史GET、实际writer锁及503维护门1/1（2.33s，70ab1019521643768ff10e21620e857f）；初夹具漏dict_row的setup error保留115a4e70c0f34af5abaf9607736a781a。新runtime工具只新建SCRAM writer/私有配置/unit资产，显式admit仍不安装/启动unit，配置hash拒绝和默认0连接两节点2/2（2.42s，1dabb38720474cd296565e63b66b6009），含新版本身份门的实际配置→健康链。根均已读metadata/XML/log；各轮不相加冒称一次全链，服务器/真实模型/外发0。

- [x] (2026-10-24 14:06 +08:00) 新F副本一次性prepare入口：核copy原件与实际source/target OID、目标关门0连接，在同workspace排他writer锁内记started后，仅新副本显式开连接→精确1–8 checksum迁移→checkpoint→primary dry/apply/repeat零变化→副本撤销/收据双重放及完整Core/checkpoint/sequence幂等→关门0连接；源stage不变，不重试已开始操作。真实PG节点最终1/1（2.22s，private/safe-narrow-d09904b2930e45858b937e134680ad63），默认0连接节点此前单独通过；根已核原件。初轮夹具缺run_id及误把protected_receipts更新数当总数的两次失败原件dff64ed8c4e547aca2c790a6e065a6ee/00e5fc433dea4094b6b6d275c39d6320保留；没有改业务重放/断言迁就故障，也不合称一次2/2。模型/服务器/外发0。

- [x] (2026-10-24 14:00 +08:00) F首发独立包/副本入口第一片：只用canonical Git tracked blobs打包、O_EXCL新产物；独立stdlib unpack可在真实Python -I下执行，先核artifact/manifest/Git blob，拒复用release与路径穿越，失败保留。另加固定原stage只读pg_dump→全新fr_stage恢复，保owner/ACL/库与角色库级设置，最终关闭新副本准入；原stage不改，不接受既有目标。必要新目标分别2/2（.84s，独立-I）和真实PG15 2/2（1.57s），唯一原件private/safe-narrow-7f9adaaa2e2843d1979d5fe387f75077与80c29bb6edf34021ac6ce6ac03e9d739，根已读metadata/XML/log。两轮不拼作同次全链；真实模型/服务器/外发0。

- [x] (2026-10-24 12:55 +08:00) v12新库原生恢复与关门对调的stage限定入口完成必要本机证据。真实PG15首3/3（4.70秒）实际复现旧clean被新增FK阻挡→新库保对象owner/ACL→原库DB设置/CONNECT及授权选项/角色库级设置精确保留→两库0连接对调、旧库/数据保留。公开main首1/1、保护文件门新+受影响CLI2/2、增seal后受影响1/1、最终真实独立-I四步及在途会话保留2/2（4.35秒）；根核各原件，五个不同目标有通过，不冒称一次全5/5。无服务器/真实模型/外发，R11固定c74未改。
- [ ] 完整stage执行单仍未就绪；包/复制/迁移/回填/双重放、B7、无模型运行资产已有必要本机片；最终同源候选、Linux依赖/8788 unit的执行顺序和出站检查命令待完成。R11旧b008已13:09提醒用户；新K31及stage代码须最终普通集成再绑定，不套旧门。正式生产对调不在此stage限定入口。

- [x] (2026-10-24 10:48 +08:00) 新中央routing唯一节点首次1/1通过，0失败/error/skip/warning，XML5.443秒；10:47:49.444198–10:47:55.896752。根独立核metadata、全部XML和log；唯一原件 `private/safe-narrow-83cfec6bf1c9492c9772777ea33d5e65/`。真实prefix7 native restore→8前后原非空中央四表/sequence精确保持，当前宿主真实from_base/require_agent/Registry使用新业务writer+原四MEMBER。原eval历史实际guard reserve/finish及finish_batch，stop账号在基线前设好；受限role运行期禁止provision/clear、真实网络，只用非Mock外壳桥接Mock使真实from-env中央门生效。唯一合法primary POST仅往原中央追加1个http UUID，旧usage全行/batches/auth/account身份location/stop不变、当前账号last_clock_at单调；错库/UUID/location/Access四类共0新POST，中央完整后态不变，新业务四表空/sequence未用保持。官方K3从既有公开artifact真实装配，未patch计量；slot已释放，真实供应商/服务器/外发0。仅当前宿主装配的一次port.complete，不是fresh候选进程或完整Agent业务run，formal_central_rebinding_verified仍false。

- [x] (2026-10-24 10:47 +08:00) 新central_routing专属测试273行/最大函数41已静态冻结，根全文核原restore/production/Registry/guard及fixture，R3独立审无实质阻塞，Ruff E/F/I/B/UP/SIM与120列format通过。仅授slot1唯一新node首次验证，沿真实os.environ四MEMBER及受限role；用BaseTransport桥接Mock避免裸MockTransport免guard，provision/clear和真实网络在运行期禁止。范围是原native restore夹具+当前宿主真实装配的一次port.complete，不是fresh候选app或完整业务run，不证明正式central_binding。尚无测试结果，不扩矩阵。

- [x] (2026-10-24 10:42 +08:00) 前片源写CLI的唯一两节点已根核并推 `045d705` 至自己的 `v4/p3-wire-source-cli-20261024`；未推进formal/feed。当前切独立 `v4/p3-wire-central-routing-20261024`，只保本计划与下一专属测试WIP，归档源将是已提交045；两条源CLI测试已结束，旧控件及新CLI/test冻结。中央组合仍只静态准备，无PG/pytest/真实POST，根审前不给测试槽。

- [ ] (2026-10-24 10:37 +08:00) 在源CLI首验间隙准备下一独立实际恢复/启动组合：不新增proof层、不修改P1b或自动迁移账本，新增专属本机真实PG测试，保留原已配置的非空中央库，恢复另一业务库后仅改业务DSN，沿真实production装配/Registry/MockTransport验证原中央历史不回退、允许调用只追加原中央UUID，新业务库额度表保持空；错库/UUID/location及原停止状态在POST前拒且不自建。先静态审，源CLI片提交推送后再切独立分支并授必要测试，不碰在途控件或已验矩阵。尚未编码或运行。

- [x] (2026-10-24 04:14 +08:00) 根只读核实冻结工具提交7e2c870的Core CI成功（584旧Core、v4 4133通过/75跳过）；正式集成1891975的独立Core CI也成功（584旧Core、v4 4107通过/56跳过）。两者不是同一源码，未合计测试数或当作本机Linux恢复放行；不重复宽验。

- [x] (2026-10-24 03:04 +08:00) 单个prefix7组合目标在两次新fixture错误修正后第三次1/1通过（53.69秒）：固定已提交206f43f实际候选，原生receive/save/correct且满足owner全集/零active和lease，M1真实捕获→另一新目标同call M2原始全状态比较→7至8→原生双重放。只新增capture_replay_chain测试与本计划，工具/effects599/旧测试/R7计划未改；令牌释放，无宽验。
- [x] (2026-10-24 02:38 +08:00) 根审发现的嵌套field_source_refs字符串漏检已修；只复用已验证候选SourceRef严格校验source_refs与field_source_refs，并核source_ids/fact_ids等列表的非空字符串元素。新增真实坏结构残留节点首次1/1通过（35.61秒），first apply前受控拒绝、note保留、完整状态未改；原3路径、业务不变、旧2项未复跑。
- [x] (2026-10-24 02:19 +08:00) 合法缺源span的marker-only观察分支首次新链2/2通过（68.05秒）：真实备份后receive/save/correct正例只保marker且零擦除计数；固定候选原生孤立note反例在first apply前拒绝、完整状态不变。pure/组合未复跑。
- [x] (2026-10-24 02:06 +08:00) 根审组合误拒修正后只跑新whole fact+span目标首次1/1通过（33.42秒）：同owner whole删除目标不列非重叠preserved，仍保raw/context/FTS与whole删空断言；原pure1/1未复跑、不混为pure证据。
- [x] (2026-10-24 02:01 +08:00) pure source_span真实固定938链首次1/1通过（31.44秒）：原生correct_fact只生成superseded span及真实note墓碑，无fact/message/legacy墓碑；raw、context、实际FTS、非重叠fact/另一owner、run/Outbox/全epoch checkpoint及第二遍全状态均独立验证。
- [x] (2026-10-24 01:52 +08:00) legacy独立只读擦除后验与真实不可变候选链首次2/2通过（58.70秒）：固定938正确删空目标/直接派生/embedding并保持第二遍全状态相等；固定144实际残留被REPLAY_ERASURE_FAILED拒绝，不借控制树业务，不改旧失败metadata。
- [x] (2026-10-24 01:44 +08:00) 经主线批准最小legacy_memory目标解析修复，控制树新PG窄链首次8/8通过（2.69秒）：真实mapper的legacy/verified fact、无目标/None、歧义/来源/跨owner边界；真实候选打包与独立擦除后验仍待下一片。
- [x] (2026-10-24 01:39 +08:00) 单一原生legacy迁移/旧备份/最新inactive/候选双apply复现执行完毕，正确擦除断言真实失败1/1（30.95秒）；已确认144b81e业务缺口，未修业务或effects，详见下文安全证据。
- [x] (2026-10-24 01:26 +08:00) 显式同call本机新目标候选双重放首链7/7：真实90a27fb非空及prefix4空正例、真实7e3d098旧候选第二遍状态变化拒绝、类型/同call、helper hash、stale ledger及跨owner整批回滚。独立摘要覆盖全部字段/checkpoint/sequence，正常总9连接；仍非正式恢复证明。
- [x] (2026-10-24 01:28 +08:00) 仅追加共享_process默认路由的原正常预检兼容节点1/1，仍只读且不执行撤销。新增replay限制原始prefix4/7，不扩大既有默认恢复1–7；未宽测。
- [x] (2026-10-24 01:11 +08:00) 同call持锁新目标可选候选fresh-process只读预检9/9：完整Git候选包、实际Python3.11 venv与活动Core锁闭包、真实PG15迁移/owner/运行状态/中央空表；预载控制包、源码漂移及四种目标异常均拒绝并保留新目标，完整状态未变。未调用撤销重放，正式完成位仍false。
- [x] (2026-10-24 01:16 +08:00) 交叉审阅修正owner排序的locale边界：实际PG owner行以Python sorted归一化，与输入保持精确集合相等；仅正常预检和owner缺额两个受影响目标2/2，未复跑其余7项。
- [x] (2026-10-24 00:48 +08:00) 非空消息/事实撤销双重放实证发现并最小修复run/Outbox重复updated_at：完整Core、sequence、checkpoint及原始关联行新回归1/1，必要既有纠错/重新生成2/2；不清state_version、不跳过revoked，不改native提交后purge。
- [x] (2026-10-24 00:36 +08:00) 显式同次新库restore→upgrade阶段以真实PG15验证prefix4/7→8、原文/checkpoint保持、四张空额度表及精确ACL；10个新行为和1个默认兼容节点单链11/11通过。失败保持实际阶段，不提供既有库采用入口。
- [x] (2026-10-24 00:20 +08:00) 新增显式local-only原生恢复基础：真实PG15 pg_dump/pg_restore保持prefix4/7，新库/两角色、不可接管及失败保留边界共18个不同定向行为有通过证据；无前向迁移、重放或正式发布放行。
- [x] (2026-10-24 00:26 +08:00) 两角色密码在客户端生成SCRAM verifier后才进入DDL；实际会话DDL日志边界及受影响prefix4恢复2/2通过。补齐PG15客户端/独立测试库的跨平台发现，未重复18项绿节点。

- [x] (2026-10-23 23:10 +08:00) 最终代码已补owner+draw稳定、无正文的恢复标记；导出去重排序，同一全体owner事务内写入，重复不再增加标记。
- [x] (2026-10-23 23:10 +08:00) 7个新PG行为及3个既有兼容行为均有通过证据（8+1+1定向复测）。真实pg_dump→pg_restore→重放→再导出满足原单调校验，第二次所有表状态不变；跨owner及篡改整批回滚。
- [x] (2026-10-23 23:38 +08:00) 隔离发布准备树新增只校验的首发契约与实际PG15精确ACL核验；45个行为以15+29+1定向记录通过。默认零连接，无apply命令，不构成恢复或发布证明。
- [x] (2026-10-23 23:46 +08:00) 审阅补正视图/SECURITY DEFINER与实际进程PGOPTIONS绕过；新增5个反例及1个受影响合法ACL节点定向6/6通过，未重复旧45项。
- [x] (2026-10-23 23:53 +08:00) 两个ACL事务在identity前固定pg_catalog并核实际路径；目录伪装反例与双角色自定义路径正例2/2通过。
- [ ] 冻结最终首发候选，核实增量升级适用迁移、owner/writer、回填与实际解释器。
- [ ] 本机Docker Linux PG15全链、最终候选原生新库恢复、维护门与writer栅栏演练。
- [x] (2026-10-24 00:03 +08:00) 两份首发stage/prod草案已提交ef3d2e2，明确No-Go、现有校验命令与缺失入口；本片只补本机原始prefix恢复命令。
- [ ] 完成可执行的增量/恢复/停写切换与Linux证据，再复核两份首发操作单；stage/生产等待用户另行授权。

## Surprises & Discoveries

2026-10-24 14:41 +08:00：CI已有单独的FIRST_RELEASE_LOCAL_TEST_ADMIN_DSN/55480，不应把native fixture的端口校验放宽到主CORE5432。新本机片将CORE显式设为不同的合成5432端点，证明修前在连接前拒绝、修后实际连接独立55480/55481；原库和身份门不改。交接单原始报告的主/外评物理小批与题目分组分开，原Markdown可能带回答预览，不能直接拷到公开docs。

2026-10-24 14:19 +08:00：F不能给configured_agent伪造key/中央账户，也不能省掉Agent冒称装配成功；stage专用端口无条件抛ModelUnavailable，注入真实Agent+公开本地计量，实际业务Web子app挂载在只读路由门内，故不启动子app原队列/维护/dispatcher生命周期。该模式只验证健康装配，不证明常驻队列、模型效果或Linux/cgroup出站规则。B7操作同一正式fr_stage；本机另建独立frx新库测试，不误用CopyScope的原source。

2026-10-24 14:06 +08:00：copy继承原库自定义search_path，迁移及checkpoint入口必须显式按保留owner、public/pg_catalog会话路径执行；库/角色原设置不改。合法sent回执重放不做更新，因此protected_receipts为0，不能把它当已导出回执总数；测试保留实际sent/receipt并核全状态，而非期待重复写。无run_id的旧收据仍按既有安全契约拒绝，未放宽历史数据门。

2026-10-24 14:00 +08:00：服务器尚无候选源码时不能先调用包内模块解包；新增stdlib standalone引导脚本，可单独随包传输并先核其审核hash，再由系统Python -I执行，不依赖预装Core。原stage只读复制需要保留库级元数据，不能只使用pg_restore对象owner/ACL；copy完成仍关门，后续迁移/新unit入口必须另作显式编排。

2026-10-24 12:55 +08:00：用真实新合成库备份后再加parent FK，pg_restore clean确实因core_runs_pkey依赖失败且单事务保留新行；因此不能在原升级库上覆盖恢复。新的恢复必须完整保留archive owner/ACL，库级ACL和ALTER DATABASE/ROLE SET不能靠pg_restore自动补齐。metadata语义比较保全部ACL（含PUBLIC/授权选项）和库级/角色库级设置，实际OID/系统身份逐次重核；有任何会话时seal保持关门并拒绝，不强制终止，exchange同事务保持两个旧OID对应对象且不开放连接。

10:37 只读核实：CentralLocation.from_environment只读取MEMBER_CENTRAL_DSN / MEMBER_CENTRAL_SCHEMA / MEMBER_ACCOUNT_ID / MEMBER_LEDGER_IDENTITY，完全不回退ZHIMING_DATABASE_URL；真实configured_agent和每次HTTP guard可继续核原account UUID与实际DB/server/schema位置，runtime不provision。现有0008契约已允许中央与业务分库，无需搬迁或重签。启动guard成功不等于旧usage/batches/authorizations/sequence未回退；自定义启动environment mapping也不能替代真实HTTP最终读取的进程env，组合测试必须同时核这两层。旧库/中央角色保留、正式切换与隐私处置仍需本次发布裁定，不因本机通过开放正式门。

上述两个GitHub CI job均成功，但测试集合不同。7e2工具树包含新恢复测试，正式集成1891975包含评测生命周期接线；不能用其中一个job替代另一个源码的验证，也不能把CI里的48题替身子集当作原81题首发门。

本轮组合链时序经根澄清：真实correct_fact在M1捕获之前，故备份内旧fact仍为superseded且保正文，新更正fact已经存在。裸MemoryService(repo)没有on_revoke回调，recomputable=True将run/Outbox置stale，保留原run.request、清result/JSON checkpoint/lease与Outbox payload，但不物理purge public checkpoint。M2必须先完整恢复这些实际行，再让原生旁账把旧重叠fact删空、run转revoked/清request、Outbox转cancelled并在native提交后物理purge三张checkpoint表；新更正fact保持完整原行。不能混称旧pure链“备份后纠错、新fact不在dump也不重建”的不同情境。

首跑`private/safe-narrow-2d83926f9d5344e8b10f8509f25748c2/metadata.json`在新fixture组合断言失败，1 error/0目标通过，16.36秒；尚未到M1。断言把纠错后的状态误写成revoked/request空/public checkpoint已空，与源码recomputable契约不符。根复核后批准只修新fixture，保留正确的分阶段保护：记录并核stale/STALE_INPUT、原request精确匹配及hash、Outbox stale/空payload、三物理表实际[1,1,1]；native重放后仍严格要求revoked/request空/cancelled/[0,0,0]。没有改候选业务或把红结果隐藏为完整通过。

第二次`private/safe-narrow-932aa60788824876be577648a9384852/metadata.json`仍在M1前出现1个fixture error（13.93秒）；安全诊断`private/capture-replay-chain-b07213d772434405a21880958e527707/metadata.json`实测stale/STALE_INPUT、request保留且精确匹配、结果/lease和Outbox payload清空均正确，三物理表却是[1,0,1]。已安装PostgresSaver.put源码明确primitive str内联于checkpoint，非primitive才进入blob；此前“种子自动每表1”假设错误，不是产品实现故障。保留两轮红，未把缺blob当作通过。根批准只在新测试用真实已安装Saver将同run:e0、同checkpoint的channel换为明确合成dict对象并推进该channel version，实际写blob且在同目标内先核精确[1,1,1]；candidate的receive/save/correct仍原生，旧NATIVE字符串/旧测试/工具/候选均不改。

第三次实际观察确认：显式合成SDK checkpoint扩充在原生correct之前，M1捕获前core run/Outbox均stale、JSON输出/lease已清，三物理表精确[1,1,1]且raw/旧superseded fact正文仍在；M2在升级前核24张表完整原始列和字段，实际7至8再原生replay后run变revoked/原request为空、Outbox变cancelled、三物理表为[0,0,0]。新更正fact整行hash、非重叠fact整行hash与embedding、raw/hash、context常量/实际PG FTS、Bob及真实源全状态均保持，完整第二遍状态/export严格相等。没有声称纠错本身产生复杂blob或已经物理purge，也没有把未知sequence覆盖升级为证明（本合法profile无sequence）。

2026-10-24 02:36 +08:00根审发现真实拒绝接缝：旧递归只确认field_source_refs顶层为dict，其值若是缺源message ID字符串，会因未知field键被当作普通正文而忽略；原生closure同样不处理此损坏形状，不能据此认定零血缘。原生agent_case_changes/privacy_cases的正常值为dict[str,list[SourceRef]]，source_refs为list[SourceRef]；仅校验顶层dict/list不够，source_ids/fact_ids等也不能接受非字符串或空标识元素。

2026-10-24 02:38 +08:00新增实际反例已拒绝：固定938候选在恢复目标原生repo.put写入note，field_source_refs={'field': 实际缺源message ID字符串}；原生旁账未改。observer在first apply之前以REPLAY_ERASURE_FAILED停止，原note仍在、source/fact/run仍缺席，全部Core/checkpoint/sequence前后摘要不变。该节点证明损坏引用结构不能冒充零血缘，没有把拒绝当作擦除成功或修改其他owner行。

缺源span只读确认：原生apply_privacy会保存source_span旁账，即使旧库没有该message；没有匹配fact/run时闭包为空，refresh_source_indexes捕获缺源ScopeError并跳过，原生export仍保留该marker。当前误拒来自effects.span_identity要求message必存在，不是业务apply缺口。合法例子是owner已在备份中，但receive/save/correct全部发生在备份之后；旧备份原本没有原话或两条fact，不能要求重建原文、FTS或新更正正文。owner本身若不在备份，现有完整owner集合门仍拒绝，不能借本分支扩张owner集合。

2026-10-24 02:19 +08:00marker-only实证：first apply前没有同owner source及其已知fact/private/run/Outbox/embedding残留时，原生apply只保存旁账，第二遍全状态相等；raw/source/fact/run检查计数保持0，单列marker-only=1。反例由固定938候选原生repo.put写实际孤立note，source_ids指向备份后真实新source ID；只读扫描在first apply前发现并拒绝，note保留、全部PG表/checkpoint/sequence摘要不变，不能用“message缺席”跳过可归属正文。所有SQL只用当前owner，不查询或借用Bob的同ID行；不按正文相似性/时间/次数猜溯源。

2026-10-24主线批准的单一复现范围：`tests/v4/release/test_first_release_legacy_tombstone_pg.py::test_native_legacy_tombstone_erases_mapped_body_after_candidate_replay`。只新增测试并维护本计划，不修改业务、effects、记忆服务/工具/上下文。当前`legacy_memory`不是实体kind；无原话旧memory经原生migration_core迁移后，`core_legacy_map.kind='fact'`且status为legacy_unverified，但result_id实际指向kind=legacy。原生apply_privacy仅登记legacy_memory，未解析该map；这是待真实PG确认的业务缺口，不能让擦除观察器代删或把旁账存在当作正文已擦除。复现固定真实已提交候选archive/manifest/pin和独立venv/process：原生迁移active→旧PG备份→原SQLite改inactive后原生迁移/export→候选原生恢复/双重放，最后按正确隐私期望直接读取PG status/data。允许测试真实失败留证，只留本机private的映射kind、实际实体kind/status、正文存在布尔值；不回传DSN/正文，不重复宽测。source_span保留raw原话而mask上下文/FTS是既有契约，本复现不改变该语义。

2026-10-24 01:44 +08:00控制树修复确认：真实mapper不论映射kind都为fact，必须以同owner的实际core_entities.kind解引用。新增helper只在原apply事务内FOR SHARE读取精确map、FOR UPDATE读取实际fact/legacy，legacy仍有内容时核source=memories与legacy_id；不增加另一写事务或自行删除。返回ID后复用原fact/legacy删除、闭包和embedding触发器，verified fact与无原话legacy两类均可清空。对无map、excluded/None与实际行缺席，不虚构实体或修改map；歧义/来源冲突固定安全EvidenceError，外部owner没有被回退查询或删除。尚未将修复装入真实新候选，不据控制树8/8宣布候选通过。

2026-10-24 01:52 +08:00独立后验实证：先读取真实map.result_id和目标的实际kind/id，再只记录现存受支持直接source_ids/fact_ids/used_fact_ids派生引用的kind/id；apply后原引用字段已经被清空，不能届时才扫描而产生空检查。两遍都直接查PG status/data={}和embedding为空，并核map不变；只读观察器没有删除或修补业务行。固定938的非空场景实际核1个marker、1个legacy目标、1个直接派生note、2个embedding作用域。固定144的正文和note/embedding仍在，因此即使旧候选返回apply成功，也在first apply之后停止，不进入第二遍。观察范围明确为实际映射目标与受支持直接派生引用，不把这两个节点外推为所有间接/异构隐私血缘全覆盖。

2026-10-24 02:01 +08:00片段契约实证：原始消息保持active及原文hash，context精确变为撤销占位符加完整徒步片段，实际PG生成tsvector对夜班不命中而徒步命中；两个独立常量断言不能由同源投影函数互证替代。旧重叠fact无fact墓碑仍deleted/data={}，同消息非重叠fact完整行hash及其embedding保留。note已有correct_fact原生墓碑，单列whole_revocations_checked=1，不把note删除归为纯span因果。实际血缘另外核runtime_step、run、pending/attempts0合成未发送Outbox和真正Saver的e0三类checkpoint清空；不宣称发生过模型生成或外部发送。更正新fact不在旧备份，恢复后确实缺席，不能把旁账重放冒充正文恢复。

2026-10-24 02:06 +08:00根审发现合法累积旁账的误拒：非重叠fact可以同时被whole fact墓碑撤销，原span保留断言会与whole已删空相冲突。现仅排除同owner明确whole fact ID的preserved要求，重叠fact和逐条whole后验不跳过。独立新组合场景以固定938的原生repo.delete生成徒步fact墓碑，再原生export真实span+fact+note；删除fact本身未撤销徒步原话范围，所以raw原文、context徒步可见和FTS徒步命中仍必须保持，不能通过删消息凑绿。

活动锁解析必须先按子进程真实PEP508环境筛选，再以canonical name去重并传播extras。Core锁的两个numpy版本分别用于Python<3.12与>=3.12；Windows实际platform_machine=AMD64时hf-xet的纯小写marker不激活，不能用最后一条覆盖或忽略marker误报依赖缺失。新预检在实际venv内核已安装版本、活动Requires-Dist闭包及关键模块site来源，不将锁文本本身当成已安装证明。

交叉审阅发现PG的ORDER BY id使用数据库locale，父进程Python sorted使用Unicode顺序；大小写或中文owner合法时两种顺序可能不同。预检改为对实际读到的owner ID用同一Python sorted，不放宽缺额、额外owner或重复owner契约。

新增真实PG回归先以原生MemoryService保存消息/事实和关联run，带sent/uncertain Outbox及两个epoch的非空checkpoint，实际prefix7备份→新目标升级8，再导入最新非空撤销。新摘要夹具首跑因PG15 sequence不能整行to_jsonb而失败，改为显式last_value/log_cnt/is_called摘要；随后真实业务反例仅core_runs及delivery_outbox全状态变化，关联run和两条Outbox唯一变列均为updated_at。撤销、不可复活/重发、checkpoint清空、第二export稳定、另一owner及四张空额度表/sequence均已在该失败前验证。

原因是保留的state_version仍能正确命中已撤销run，原两条UPDATE无实际差异条件，故每次重复设置updated_at。修复只增加目标字段逐项IS DISTINCT FROM/IS NOT NULL条件，NULL也被识别；含残留正文或未清租约的已revoked行仍会更新，不按status整段跳过，原retry路径的stale/request保留语义不变。现有Core文件仅此两条SQL变化，未整体格式化。

现有Core迁移器从自身模块目录扫描SQL，与外部已审candidate_source不是同一边界；新升级阶段不调用其自动扫描路径，复用validate_history并执行再次校验hash后的候选SQL，所有前向SQL与ledger记录共用一个owner事务。真实PostgresSaver.setup包含CREATE INDEX CONCURRENTLY，故在Core提交后用同一owner连接的独立autocommit阶段显式执行。Core SQL失败回到原prefix；checkpoint失败时Core8已经提交；最终ACL失败时保留已提交授权，三者均固定阶段错误码停止，不自动修正或重试。

审阅指出服务端password_encryption不能防止log_statement=ddl/all记录CREATE ROLE中的原口令。实际安装psycopg3.3.6的PGconn.encrypt_password(passwd,user,algorithm=None)返回bytes；现显式使用客户端scram-sha-256，只把verifier交给SQL。新反例在发送前核DDL没有原口令，再将实际admin会话log_statement设为ddl；pg_authid双key与随机密码相符，两个角色实际密码连接成功，回执不含原密码或verifier。未改本机pg_hba，不把现有认证下的成功连接宣称为已实证SCRAM协商。

既有CI隔离库实际5432/core_test，不符合本片实际55480/55481的身份门；不能降级skip或放宽工具。测试优先显式FIRST_RELEASE_LOCAL_TEST_ADMIN_DSN，只有原CORE_TEST_DSN本身符合严格控制库/端口时才兼容使用；客户端优先FIRST_RELEASE_TEST_PG_BIN，Windows已核路径、Linux PATH发现均须实际--version=PG15，缺失即失败。主线另持CI修改，建立独立实际55480/core_test_main服务并选择PG15客户端；本机定向通过不能代替CI/Linux通过。

本机恢复首链16项中13通过、3失败：新owner的NOINHERIT不继承PG15默认public目录的pg_database_owner权限，实际pg_restore创建checkpoint表被拒。私有诊断单节点只输出已知错误类别布尔值，没有SQL/正文/凭据；未修改角色继承、pg_hba或旧库。经主线确认，仅在本工具刚创建且身份匹配的新库、public为空且原owner精确为pg_database_owner时，由新增一次admin连接把public归属设为本次新owner；后验同时核schema owner。实际成功路径4个连接（admin控制库、admin新库初始化、pg_restore新owner、owner只读后验）。writer没有CREATE，NOINHERIT保留。

2026-10-23 23:53 +08:00：本机Docker PG15仍已启动，但Linux Python依赖镜像准备失败。仅尝试拉取官方`python:3.11-slim-bookworm`一次，Docker Hub解析到本机网络的198.18地址后连接超时；未更改Docker代理、ACL、WSL或任何既有服务，未重试/换源。记录`private/linux-runtime-preparation-41f56c4646f14f88bbd5e60e552a65ba/metadata.json`及同目录日志位于主线集成工作树。本片未因此执行迁移、restore或应用服务，Linux应用轨继续阻塞；不将已就绪的Linux PG存储升级成完整演练证明。

旧恢复只删除draw，没有留下下一次export可见的原生删除旁账，故原verify_monotone会拒绝STALE_WITHDRAWALS。最终代码新增`tools/deploy_core_withdrawals.py`，保留原export格式及校验，不删除旧断言。已有draw和既有异owner tombstone均阻止换owner重绑定；所有标记冲突导致全体事务回滚。外部checkpoint清除仍是既有提交后边界，须纳入后续Linux全链失败演练。

首链8通过/2失败/1清理错误：新测试的pg_restore缺少显式dbname模式参数；既有兼容节点先缺PG15 PATH，后因安全runner未传USERPROFILE而在Path.home失败。只修新夹具；私有runner为原旧节点补PG15 PATH与指向新临时目录的USERPROFILE，其余凭据清理不变，不修改旧测试、用户环境或公共runner，不提交重复wrapper。

Docker Linux Engine本轮实际可读（29.5.2），此前环境失败记录不能当作当前故障；PG15镜像下载尚在进行，不代表Linux恢复或应用演练成功。

旧B1权限证明要求普通Core表具备完整DML，但0008额度表刻意只授予其必要权限；最终核验不能补DELETE来迁就旧证明。新检查逐表、列、序列核验有效权限及grant option，检测PUBLIC来源和角色继承，两个迁移账本只读、checkpoint三表DML、禁止DDL/TEMP/owner权限。真实PG15的正确最小授权已通过，越权及缺权均拒绝。

新链首跑15个PG行为通过，30个合成源码夹具因Windows MAX_PATH失败；缩短新测试临时目录后29通过，剩余symlink夹具缺少Windows创建符号链接权限。未提升权限，改用真实NTFS directory junction覆盖同一reparse-point拒绝契约，单节点通过；Linux仍使用实际symlink。记录保留全部失败，未重复PG绿项。

审阅发现只核验base table不能阻止owner视图透出权限，SECURITY DEFINER入口也能绕过底层DML限制。当前core-only profile改为精确24张Core表、4张checkpoint表及0008单个sequence，拒绝额外public/Core视图、外表、关系或rewrite rule；唯一合法routine为0007的clear_retired_embeddings()，核验固定函数体SHA、invoker、trigger返回类型、语言及search_path等签名，拒绝可执行的用户SECURITY DEFINER函数/过程。实际进程PG*与显式environment均检查，传入clean mapping不能掩盖libpq继承PGOPTIONS。

后续只读复核发现角色默认search_path可把pg_class指向owner视图，过滤真实后门目录行。两个只读事务现于任何identity查询前SET LOCAL search_path=pg_catalog，并核对实际配置及实际schema数组。真实反例证实伪目录隐藏public.quota_bypass，view的空谓词DELETE/UPDATE可成功而base DELETE被拒；固定目录后的检查仍发现并拒绝后门。正常owner/writer自定义默认路径不影响合法核验，测试只改本测试角色默认设置并恢复，没有改业务行。

## Decision Log

2026-10-24 14:41 +08:00：最终候选尚未冻结，因此两份单保留不可执行的PENDING占位与No-Go，但所有参数/模块均来自实际CLI，没有虚构flags或中央凭据文件。只做语法核验，不借文档中的SSH/真实评测命令扩大Codex权限。native测试夹具仅优先既有显式restore管理员环境，沿用55480/55481与隔离库名门；这是CI环境接线修复，不改迁移、重放或正式运行源码。

2026-10-24 14:19 +08:00：先把空增量B7放在新writer开门之前，保留新旧两副本；runtime只消费显式exchanged_closed原件/OID，SCRAM在客户端生成，SQL/单位文件不含原口令。unit固定新名、127.0.0.1:8788、Restart=no、cgroup拒外网仅保留回环PG/健康；新运行配置只留DB/网站口令和本地路径，不带模型/中央/代理/追踪配置。显式admit不启动unit，失败不删/修/重试。

2026-10-24 14:06 +08:00：prepare只消费全新copy的固定OID原件；started门置于实际排他锁内避免并发检查竞态。复用真实repository迁移、backfill、withdrawals业务及现有全状态观察，不改memory独占实现、不借替身或原stage迁移。当前只导出副本旁账用于副本重放演练，不称为冻结生产后的最新撤销旁账或B7全链。

2026-10-24 14:00 +08:00：F只允许新副本，故新增CopyScope正式源/目标固定zhiming_core_stage→zhiming_core_fr_stage，不扩大旧local-only Forward工具到服务器。复用已验证的PG15控制身份、新库原生restore与metadata语义保留；所有产物/目标都须全新，失败无删除/采用/重试。此片仅复制与包引导，不能声称B0–B8可执行或stage已就绪。

2026-10-24 12:55 +08:00 / 按v12/v14新增独立native_exchange及metadata工具，只支持新fr_stage副本和随机本机frx演练，不放宽既有本机restore或B1/b9常量，不提供live/prod/原stage目标。capture→restore→seal→exchange是四个显式动作，各写新私有收据，默认无自动清理/重试/开门。正式CLI必须POSIX私有管理员文件，复用已验字面env读取，不打印DSN；本机测试单独local_drill。libc locale及单owner grantor以外保守停止，不修改ACL绕过。输出admission_opened=false表示没有重新开准入，不冒称pg_restore没有建立过连接。

10:37 决定下一片用一个实际恢复上下文验证既有中央路由，避免另建无调用的证明工具或修改共享记忆。测试只可显式provision本次隔离合成中央setup，运行路径不得provision/clear stop/更新旧location；模型只MockTransport，不伪造TTY或人工开始。与当前源CLI两节点互不修改或追加测试，根维护本计划/Git；新测试先留WIP，待前片推送后独立分支授槽。正式中央保全/权限/env切换门继续false。

2026-10-24 04:14 +08:00：按指令板v8以现有绿色CI作为对应源码的回归证据，不在本机重跑同一全量。新增SourceForward尚未测试，88f1d27/5b8397d的CI仍在运行；本次只更新原计划，不追加第二套CI日志。实际Docker应用运行时、正式恢复/切换和新的服务器授权继续关闭。

根批准只新增`tests/v4/release/test_first_release_capture_replay_chain_pg.py`与维护本恢复计划。候选显式固定已提交206f43f0dd05b1c2c87f12b0bf7d27fce703208e实际Git archive，不把并行R7控制树WIP打包。复用现有真实源/捕获fixture和source_span测试的native脚本（脚本本身按payload实际candidate核来源），新包装不沿用其外层938常量断言；不改工具或旧测试。源fixture的额外合成sequence仅在捕获前删除以形成真实合法迁移profile，实际alice/bob/synthetic owner全集锁进SourcePin，零active/lease、原生source_scope与原完整ACL门照常执行；无patch伪造任一门。只读Bob前后观察可复用，native业务执行不替换。

根批准首链fixture契约修正后只重跑该唯一失败链一次，旧工具/ACL/pin依赖在链期间冻结，R7只新增其M3模块/计划。新增私有body-free诊断在阶段断言前写实际状态布尔、规范状态码、原request hash及checkpoint计数，防止后续fixture失败只剩含糊组合断言；不输出原request正文。保留首16.36秒失败证据，不调整whole/span擦除、新fact/原文/另一owner/源不变及第二遍完整状态标准。

第二轮fixture错误后根另准一次同目标复测，修复仅为新文件的显式合成SDK checkpoint种子，先读实际Saver签名/typedump源码；不通过替换旧脚本字符串或注入pipeline伪业务结果来制造blob，也不把此合成对象称作真实Agent输出。新文件306行/函数≤51，静态通过；仍只有一个真实PG测试进程，无额外probe。

组合链通过后只交新测试与本计划供根审，不继续重复稳定性或宽验。主线runbook的同call参数由根另行维护，只引用本恢复计划及唯一证据，不复制新证据文档。此片不改原始候选、M1/M2工具与严格门、任何业务/记忆服务；源库实际升级、回填、Linux及正式发布由各自后续授权/证据决定。

唯一恢复调用同时传capture_binding、upgrade_local和withdrawals_replay，使M1实际dump/ledger/UTC列与全字段状态绑定先在同次新目标核对，随后实际7至8及独立候选原生双重放。断言source全快照保持、新更正fact完整行hash不变、raw/context/实际PG FTS与非重叠fact保持、Bob完整状态不变，以及重放第二遍全Core/checkpoint/sequence与export严格相等；回执连接预算为原9加M2只读1，共10。原有正式门仍false，不将局部组合验证作为源库升级、Linux或正式发布证明。

2026-10-24 02:36 +08:00根批准本轮只修observer：不手写重复五字段契约，使用已验证候选domain.SourceRef及第三方TypeAdapter(strict=True)校验两种嵌套引用，补message_id非空及start<end，source_ids/fact_ids/used_*等标识列表元素必须非空str；任何未知形状统一REPLAY_ERASURE_FAILED，不按全文字符串猜来源。预演新helper方案603行，按根裁定弃用，最终正常Ruff排版599行、所有函数≤60，沿既有软例外且未触600硬限；没有新增动态支持文件/worker或pin字段。原两参数节点保持原断言与真实候选路径，只新增bad-field-source-refs参数节点；该反例用固定938原生repo.put制造实际坏结构note，并保完整拒绝前后状态相等，预期仍为受控拒绝而非擦除。

缺源span下一片最小安全方案（根审已批准限定实现）：沿用实际候选/pin/whole事务与双重放，不改repository、MemoryService或缺源时原生apply。仅当同owner message实际缺席时考虑marker-only；message已deleted但仍有行或身份不明均不进入该分支。根审纠正：Bob拥有相同ID是合法owner隔离，不为Alice marker查询、借用或删除Bob行，也不当全局冲突。先校验明确owner、非空message_id、int且非bool的0<=start<end、SourceMessage长度硬界；源已缺席无法重算原长度，不能声称验证了引文内容，仍以受信完整原生export为前提。marker-only要求原生span_id与候选fingerprint([message_id,start,end])一致、operation为已知native操作、metadata只含已知标识/范围字段；未知形状继续拒绝，不因目标缺席跳校验。

marker-only必须在first apply前和两遍apply后独立只读核零残留：同owner没有原message、metadata.fact_ids目标或任何实际fact source_refs/field_source_refs/source_ids引用；request/state_version（含entity:message等规范化键）、私密runtime/entity/effect/run-step/event字段、Outbox dependencies/payload/run血缘均没有该source或已知fact ID引用，相关embedding作用域为空。使用精确标识/结构关系，不按正文相似性或时间/次数猜身份；遇损坏/未知血缘结构、没有同owner权威run可归属的私密/Outbox等无法解释残留时保守拒绝，不把查询不到一条message当作“全无正文”。checkpoint无owner，只能按同owner权威run/epoch核其实际thread_id，不借用或扫描Bob线程来替Alice证明，不将全局未知线程声称为Alice已擦除。本分支只观察，不补源、不擦残留、不清额度；若现有只读扫描无法在600行内清楚表达，先报告受pin拆分方案，不引入未pin支持模块。

marker-only后验还须逐条直接读取owner+source_span实体ID的operation/metadata，与原生最新旁账精确一致；两次native export仍经过原单调校验并严格相等，全部Core/checkpoint字段与sequence第二遍严格比较保持。回执单列span_marker_only_checked，不把marker-only算作raw/context/FTS已检查，不虚构被擦除数量。正式发布、中央身份及Linux等完成位仍false。其信任边界仍是原已审候选与完整旁账pin；仅凭body-free旁账无法密码学证明缺席原话的原始长度或作者，不能新增自填“身份已证”清单替代既有门。

2026-10-24 02:19 +08:00实际实现仍只effects/既有source_span测试/本计划：owner/source与范围先严格校验，missing分支再核native marker指纹、有限操作及标识字段，前后只读检查同owner core_entities/core_runs/steps/events/Outbox/embedding/Tarot等已知结构化标识和依赖键；没有权威同owner run的私密行/Outbox继续保守拒绝。schema损坏或未知引用结构不作为空，既有raw/context/FTS观察抽为同文件函数保持原语义。effects583行、所有函数≤60；保受审单文件hash、无新增未pin导入，仍在已准软例外及600硬限内，新测试393行。没有修改业务、候选、owner集合门或root R7增量文件。

拟定仅两个真实固定938目标：正例先native ensure_owner并备份，再native receive/save/correct生成真实span旁账，旧备份同call恢复后source/old fact/new fact都缺席、marker存在、两次export及第二遍全状态相等；不生成假span、不重建新fact。反例沿同一真实时间顺序，在测试专用candidate_replay seam、first apply前，由固定候选native repo.put一个明确合成note引用真实新source ID，形成实际孤立私密残留；观察器应first apply前受控拒绝且完整状态不变，不删除该note、不改旁账。故障注入是显式测试种子，不能冒称原业务天然产生该孤立行。拟仍仅effects、独立source_span测试和本计划三路径；本轮未编码/测试，不占令牌。

2026-10-24主线组合审阅裁定：同消息非重叠fact若同时有明确同owner whole fact墓碑，就应由whole后验核删空，不能又被span观察器要求完整行保留。只在span capture的非重叠preserved分支排除同owner明确fact撤销ID；overlap后验和逐条whole擦除均不跳过，不按operation推断或过滤旁账。新增独立combined目标，由固定938候选原生repo.delete徒步fact后export真实source_span+fact+note组合，raw/context/FTS仍保徒步原话可见，因为fact级删除不等于撤销原话范围。只跑新combined一个目标，原pure无fact/message/legacy断言及1/1证据保持，不复跑、不改业务；仍只effects/独立span测试/本计划三路径。

2026-10-24 pure source_span片范围：固定938候选原生接收含夜班与独立徒步的原话、保存两fact并真实备份，再以新原话correct_fact生成superseded片段旁账；必须证明无fact/message/legacy_memory墓碑，不过滤原生导出。根审允许原生note等派生墓碑，因为correct_fact本身会删除note；note只作为whole后验，不冒称其独立由span删除。新`test_first_release_source_span_pg.py`只跑一条真实恢复/双重放正链，effects只读capture旧重叠fact、非重叠完整行hash、raw原文hash、实际run/runtime_step/outbox和checkpoint血缘。后验区分保raw与context/FTS遮挡，另以独立常量和实际PG FTS证明夜班不命中/徒步命中，保同原话非重叠fact和另一owner；新更正fact不在旧备份，不声称被旁账重建。只改effects、新测试和本计划；若首链失败保正确断言/安全metadata停报，不修业务凑绿。根准许effects暂超400软目标但低于600硬限以保现有单文件hash信任边界，每函数≤60；不新增未pin helper或改worker/pin接口。

2026-10-24 02:01 +08:00该片effects实际455行，新测试229行、全部函数≤60。保留单个已受审hash的effects文件是根审明确软例外，不拆入未pin支持模块、不改候选或worker接口，也不为压400隐藏读取逻辑。source_span随整条message墓碑出现时仍由whole后验负责；无对应原话或其已deleted但旁账只有span时，新观察器目前保守失败关闭，未据本正例放宽。当前只验证superseded span；所有跨度/歧义、跨消息和更多间接派生仍需单独证明，不扩大此片验收范围。

2026-10-24主线已本地提交业务修复`93886bbbadc5048e8269c0537e278dc0c12886e9`，批准下一有界片仅改`tools/first_release_replay_effects.py`、原生legacy候选回归与本计划。effects在first apply前独立只读capture真实map、实际fact/legacy目标及受支持直接派生引用ID（无正文），两遍apply后读取实际status/data与embedding，要求目标和直接派生均已删空、map不变；观察器不擦除、不补map、不替代候选业务。固定938不可变候选为正确已删空正例，固定144不可变候选为实际残留导致REPLAY_ERASURE_FAILED的受控负例，保留原144失败metadata。增加候选原生repo写入的明确合成note/embedding夹具以验证新后验不是空检查；source_span保raw契约及全状态第二遍比较不变。一个令牌、仅两目标，不全量，不提交推送。

2026-10-24主线裁定legacy_memory为既有撤销契约遗漏，批准最小共享repository修复：新增`repositories/privacy_legacy.py`，在apply_privacy的legacy_memory分支解析同owner、source=memories、legacy_id、map.kind=fact的真实result_id，再查同owner的实际fact/legacy实体kind；不按ID前缀或旁账metadata推断。双kind同ID或仍有效legacy的source/legacy_id不符时固定EvidenceError，由原事务整批回滚。无map、None或实际实体缺席只保留防导入marker；返回事实ID或legacy目标交原删除、闭包与embedding路径，不另开写事务、不改map、state_version、迁移或source_span保raw契约。先新增`tests/v4/release/test_legacy_memory_apply_pg.py`不超过8个真实PG目标证明实际mapper、verified fact、无目标和歧义/来源/跨owner边界；根提交后才验证真实新候选和独立effects后验。原144复现继续保持正确断言及失败证据，不改金标/xfail。

2026-10-24 legacy复现保留正确隐私期望为普通失败回归，不改成xfail或接受pending，不用直接put/map/revoke构造目标，也不修改旁账来补缺少的legacy撤销。active与inactive阶段均由独立受pin候选的migration_core.migrate实际执行，核manifest、worker、Python/活动Core锁与77个候选业务模块来源；仅测试编排与只读观察来自新测试。根审决定共享业务修复前，暂停该目标复测，不允许effects代替候选删除正文。

双重放新增独立CandidateReplay及first-release-local-replay-pin-v1，绑定受审effects helper实际hash，不能拿旧预检pin或bool启用写阶段；只接受原始prefix4/7。旧preflight pin/schema、只读回执和默认路由保留。fresh worker以固定绝对路径runpy加载hash已审辅助编排，不把该支持代码放进候选tools namespace；实际apply/export、纯verify_monotone与receipt_key均导入自受pin候选，核真实co_filename及前后所有业务模块来源。只复用候选B1模块的纯单调函数，绝不构造旧ProofRequest或使用其固定SHA/迁移/importer。

Native apply严格不外套事务，第一遍成功后原生提交后checkpoint purge已经执行，才核擦除、导出和独立摘要；任一步失败即结束，不自动第二遍或重试。若native第一遍在提交后purge失败，错误码REPLAY_FIRST_APPLY_FAILED不表示整批未提交，现场必须保留；本片没有恢复/采用既有失败目标的入口。第二遍原生counts中的owners/tarot_tombstones/protected_receipts是处理计数，不能当作变化数归零，实际零变化由完整状态和导出相等证明。

独立erased核验原先只明确覆盖whole revocation、draw、revoked run正文/租约及其全部epoch checkpoint；01:52片已补真实map解析的legacy目标/受支持直接派生/embedding只读后验与938正例、144拒绝实证，02:01片追加superseded source_span的raw/投影/FTS及实际重叠/非重叠血缘证明。更多span形态和所有间接legacy血缘仍未覆盖，不宣称全部隐私形态已覆盖。完整状态摘要不删除时间戳或sequence字段，中央四张表必须始终空且中央sequence不变，不清表来满足门。

经主线明确批准，本片触及共享路径mingjing_core/repositories/postgres.py的invalidate_derived两条SQL，是首发恢复完整幂等硬门的必要修复；P5集成时应保留此差异条件。没有改变历史b9或迁移、撤销范围、closure计算、原生apply全owner事务及提交后checkpoint清理，也没有用全表摘要排除时间戳来放宽断言。新回归严格比较全部字段，另核关联原始行逐列相等。

本机原生恢复是独立`tools.first_release_local_restore`入口；旧`first_release_restore`仍只有validate/可选只读ACL。新入口默认零连接/零进程，只有显式--apply-local且local_drill=true才能操作随机新目标；formal及现有对象始终硬拒。源prefix只允许1–7，实际--list预检在任何DDL前拒绝中央额度表/sequence等归档项，故不复制0008账户或usage。任何失败保留角色/库；再次调用拒绝接管，工具无DROP/覆盖/自动恢复重试。测试夹具结束后仅清理其自行创建的精确随机对象，不是工具的失败清理行为。

新增可选--upgrade-local必须与--apply-local同用；内部函数要求同次创建者连接仍持有按本次新库绑定的实际64位advisory锁，且restore及原prefix核验已经在该调用内完成。不能只传现成DSN或普通admin会话来采用目标。现权限服务负责Core最小权，现checkpoint授权函数负责公共表和只读迁移账本，最后两角色只读精确ACL；不增加DELETE来满足旧B1证明。四张0008表实际查询全空，遇非空保留原行并拒绝，不清表、不provision，不形成中央身份迁移或重绑定证明。

凭据边界同时覆盖子进程和SQL：PGPASSWORD仅为显式内存子环境，角色DDL仅含libpq客户端生成的SCRAM verifier，不保留服务端明文加密路径。原CLI负例的参数清单等价压缩为字段映射，保护的PGOPTIONS先拒绝、秘密不回显断言不变，用于保持新测试文件≤400行。

恢复标记仅含owner、draw_id和固定版本的指纹，以及deleted/deleted_ids/kind回执；不保存牌面/问题/正文，不造原HTTP幂等键。复用已有core_mutation_requests，无新表或迁移。0009保留P5，不改变历史1–8。旧b9继续保留独立反例，当前修复只随最终候选发布；首发开门前可以回退，开门后只按另审止损与前向修复方案。

新增`core-only-1-8-v1`只接受外部审核的不可变candidate/manifest/迁移1–8和Core、Charts、K3三锁pin，不把调用者布尔值当作可信证明。P5就绪后若0009纳入候选，必须新增明确审核的profile，不能静默跳过此门。新恢复库仅允许`zhiming_core_first_restore`，本地仅本次operation随机库；原live/stage及旧B1目标均拒绝。新入口没有apply、pg_restore、unit或开门动作，不解除旧B1 Native硬门。

目录路径固定只作用于本次两个核验事务，不永久改变运行角色search_path，也不放宽关系、routine或0008最小权限门。

## Concrete Steps / Plan of Work

2026-10-24下一片显式本机双重放：新增独立不可变replay pin绑定受审effects helper实际hash，默认preflight pin与只读路径保持不变。仅同call显式apply+upgrade、原creator锁仍在的新prefix4/7→8目标可进入；以当前已提交90a27fb完整真候选及真实Python执行候选原生apply/export和已核来源的纯monotone函数，绝不注入控制树业务修复。先核既有导出不比latest更新；再第一遍原生apply（无外套事务）→导出/擦除与checkpoint核验→完整Core/checkpoint/sequence摘要→第二遍原生apply→导出及完整摘要严格相等。四张中央空表及sequence始终只读核不变；任一异常即停止保留，不自动补第二遍、重试或清理新目标。

范围仅新增first_release_replay_effects、一份新PG测试，加candidate_process/replay_worker/local_restore小接线与本计划；若新增共享测试helper须先报路径。首链≤8必要组，实际完整90a27fb正例及7e3d098旧候选幂等失败负例，不伪造包。回执仍明确local-only，native_restore_completed/runtime_verified/linux_attestation/central_binding_verified/publication为false。源prefix8与中央身份保全、既有库采用、Linux/formal/stage/prod仍未实现；源码/依赖元数据核验不构成供应链认证。

2026-10-24下一基础片只做显式local replay preflight，必须同call apply+upgrade且原新目标creator锁仍在；不调用apply_withdrawals，不宣称双重放已接。新增不可变输入绑定candidate/manifest/dump/latest ledger/实际Python及受审控制worker。纯stdlib bootstrap在任何业务导入前固定候选tools namespace与mingjing_core包，拒绝预载控制树业务；前后校验全部候选模块真实路径与manifest字节，控制worker自身不进入tools命名空间。

子进程核实际Python3.11、venv与活动Core锁闭包，须以真实PEP508 marker环境筛选后canonical去重并传播extras，不能覆盖条件重复pin。既有.venv-k3实际Python3.11/AMD64的68活动pin及113活动依赖边已只读盘点满足，可用于本机正例；此盘点不是预检/PG测试，更不是wheel/.pth/Linux供应链认证。目标只读核迁移1–8、完整owner集合、无active run/lease、四张中央空表；任何异常保留新目标，正式完成位仍false。两新tool与一份完整候选/真实Python/PG目标测试，加既有入口最小接线；默认零连接行为不变，不提供现成库adoption。真实重放worker与备份8/中央身份保全继续下一片。

主线自有CI接线将原Core+test锁安装移入RUNNER_TEMP下的真实专用venv（--copies、--require-hashes），导出其bin与FIRST_RELEASE_CANDIDATE_TEST_PYTHON，Charts环境照旧，没有另装第二套Core闭包。这只是待实际CI验证的运行时路径调整；YAML/Bash解析不构成Linux、运行时供应链或正式发布门通过。

2026-10-24重放幂等实证后的最小共享路径修复：仅调整mingjing_core/repositories/postgres.py中invalidate_derived的core_runs及delivery_outbox两条UPDATE，目标字段含NULL以IS DISTINCT FROM比较，仅实际需要清理/改变时更新updated_at。不跳过已revoked记录，不清空state_version，不改变closure、retry/stale语义或native apply事务提交后checkpoint purge边界。原因是实际非空消息/事实撤销双重放已证明第二遍仅重复改动run和Outbox的updated_at；共享repo路径须由主线在P5集成时说明此边界。先复跑唯一新PG回归，再仅两个必要既有纠错/重新生成节点，不宽测、不改旧b9。

2026-10-24下一小片增加显式--upgrade-local，必须同时--apply-local，仅在同一次调用已创建新目标、仍持有原操作锁且真实restore/原prefix核验后执行。默认保留原prefix恢复；不新增采用既有库的命令。只执行同一外部审核候选的迁移SQL，复用validate_history校验历史，保持全部前向迁移和版本记录在一个owner事务内。PostgresRepository.initialize固定扫描其包目录，不能冒充外部候选SQL执行器，故本片只复用其历史契约而不调用其自动迁移路径。

升级后复用真实PostgresSaver.setup的显式checkpoint迁移（包含CONCURRENTLY索引，不能嵌入Core迁移事务），随后复用权限服务和checkpoint授权，再以两角色只读精确ACL核验。0008仅建空的四张表和sequence，不provision/复制/清理账户，不把空表当作中央身份保全或重绑定证明。任何失败保留新库/角色及已提交阶段，不修权限重试、不删除或回退；最新撤销/送达收据双重放另片，formal/native/Linux证明始终false。本片最多两个新tool/一个新PG测试文件，加现有入口小接线；定向验证prefix4/7→8、原文/checkpoint保持、精确权限及阶段失败，不全量。

2026-10-24下一片限定为本机新库原生恢复基础：仅显式local_drill=true、严格operation随机库/角色、loopback 55480/55481；同一外部审核输入绑定候选/manifest、custom dump和PG15 pg_restore原始hash及源迁移前缀。默认零连接校验，显式本机apply才创建本次非特权角色与全新库并由新owner恢复；发现任一既有库/角色即拒绝，失败保留新对象且不自动删除或重跑。最多新增三个tool与一个定向PG测试文件，不改旧B1或正式目标边界。

实际pg_restore限定no-owner/no-acl/exit-on-error/single-transaction/no-password，无shell；仅通过有限子环境传递显式内存凭据，不把凭据放argv、输出或文件，不继承PG隐式环境。首片源prefix只允许连续1–7，实测4或7；审核pin声明8或archive目录出现中央额度关系均在创建任何库/角色前拒绝，避免在未保全时复制额度身份。恢复后只读核原prefix与对象owner，不迁至8、不重放撤销/收据、不重绑定或provision中央账户、不接正式stage/生产、unit或开门。真实本机PG与pg_dump/restore测试完成前本片未验证；Windows证据不解除Linux/生产门。角色生命周期或认证不能满足此边界时保留现场、报告具体阻塞，不修改既有认证/角色权限。

相关验证使用清凭据的私有安全runner和本机隔离PG15。代码审阅、定向验证、提交推送之后才进入Linux演练；最终候选增量入口不得复用freeze/install/publish去覆盖既有Core库。Native入口须恢复到全新明确allowlist数据库，验证备份、最新撤销/发送收据、同源解释器、角色权限与重复无变化；旧Native入口仍主动拒绝缺失的生产恢复证明，不能用JSON布尔值解除。

本片`python -m tools.first_release_restore --pin <绝对审核pin路径> --contract <绝对契约路径>`只校验输入，默认不连接PG；显式`--check-acl`才使用`FIRST_RELEASE_OWNER_DSN`及`FIRST_RELEASE_WRITER_DSN`各开一次只读事务。不继承PG隐式环境、不接受远端host、services、options、改址、默认passfile或不匹配角色。外部运行目录venv/artifacts仍须后片独立真实性核验，本片永不声明runtime_verified或linux_attestation。

本片将外部审核pin视为可信输入，只验证字节与其一致；不认证审核人、pin文件的保护权限、真实Git tree归属或审核新鲜度。这些与最终运行时审计、维护门、writer栅栏均是未来apply的前置门，不能从当前validation JSON推导批准或原生恢复已完成。

## Validation and Acceptance

场景F01–F04与X03的“不复活、不重复”约束同样适用于恢复。非空备份恢复后实际删除目标、其他owner牌与正文不变、重导出保留所有删除、第二次全表摘要及旁账行均不变；坏指纹/收据/owner须在整体事务内失败。Windows PG证据只解除该代码分支验证项；Linux、正式候选、Web/飞书/报告三个unit、CHART_PYTHON、Hermes wrapper和checkpoint权限仍需各自真实离线演练。

## Idempotence and Recovery

标记key由owner+draw+版本确定，重放返回draw_tombstones_added=0。输入冲突时整个SQL事务回滚；不删除用户数据库或Docker卷，不自动清理失败演练。部署任何异常保持维护门/栅栏并记录，服务器操作须等新授权。

## Artifacts and Notes

`private/safe-narrow-d0bd8d2a6c774c838bf5c6921470fab4/metadata.json`为本片首链7/7（132.58秒，2026-10-24 01:24–01:26 +08:00）。完整真实90a27fb候选非空恢复→升级8→原生撤销/收据双重放、删除墓碑可再导出、sent/uncertain不可重发、checkpoint清除、另一owner全状态保持及第二遍全部Core/checkpoint/sequence不变均通过；prefix4空路径亦通过。完整真实7e3d098旧包按预期因第二遍状态变化拒绝，证实没有借控制树e8修复代替候选业务。类型/同call、helper hash、stale最新旁账及owner碰撞整批回滚均通过，异常新目标保持存在。使用实际Windows PG15、真实pg_dump/restore、实际Python3.11 venv及清凭据/关追踪安全runner，测试时区Tokyo，模型/外发/服务器0；无全量或Linux证明。

`private/safe-narrow-0a345fdb97814566b24e3a66014ddfe7/metadata.json`为唯一必要旧预检兼容节点1/1（23.44秒，01:27–01:28 +08:00），确认共享_process和worker新增路由后，默认preflight仍保持只读、零重放和原schema。没有重跑其余7个新增目标。

`private/safe-narrow-645cf96374aa41ca876ec8c6c25e00e0/metadata.json`记录本片唯一链9/9（170.50秒，2026-10-24 01:08–01:11 +08:00）。夹具仅一次打包当前真实Git候选完整源码，各目标独立受pin副本；actual Python为本机既有`.venv-k3`的Python3.11，真实Windows PG15与实际dump/restore。正常只读预检、两个控制树namespace预载、升级后源码漂移、缺同call gate及owner/active/lease/central四个目标拒绝全部通过；Core全部字段、checkpoint及sequence独立摘要均不变。安全runner清凭据/关追踪、测试时区Tokyo，模型/外发/服务器0；没有重跑旧幂等业务、全量或Linux证明。

`private/safe-narrow-d39d12338be94844967a4df709ac6387/metadata.json`为owner排序修正后的仅2目标复测2/2（44.33秒，01:15–01:16 +08:00）；保留原9目标链记录，没有重复其余7项或扩大为全量。

本次复现与修复证据依次为`private/safe-narrow-c866375ca5154a3f9223fca318ddabfd/metadata.json`（1个新摘要夹具失败）、`private/safe-narrow-4c7135726460421aa6181feafda1b03a/metadata.json`（真实第二遍updated_at回归失败，2.66秒）、`private/safe-narrow-f90c8f6a23ea415689ef1374e6ee009b/metadata.json`（同一目标修复后1/1，2.80秒）、`private/safe-narrow-83409a83e1534dc3a70ad77181938112/metadata.json`（仅两个必要既有纠错/干净epoch节点2/2，1.94秒）。新目标没有给native apply包外层事务；实际Windows PG15/真实备份恢复、有限测试环境、Tokyo测试时区，真实模型/外发/服务器0。没有全量、候选child或Linux证明。

`private/safe-narrow-b8fce224277a4a02bf3e302eb5468163/metadata.json`为本片唯一窄链11/11（16.27秒）：10个新行为加1个受影响默认prefix4兼容节点。两个正常节点实际pg_dump/restore后由4或7升级至8，三张checkpoint数据表及其ledger和原文不变；其余覆盖无apply/无原锁、候选SQL或历史漂移、Core事务与checkpoint故障、额外额度DELETE、非空额度表停止保留。清凭据/关闭追踪，测试时区Tokyo；真实Windows PG15，模型/外部发送/服务器0。无额外全量或旧19项复跑。

本片首链`private/safe-narrow-1fd4430d834d44dda2f2ca74a5547ec2/metadata.json`为13通过/3失败（13.68秒）；私有分类诊断`private/safe-narrow-83d2cbf6f31b484c85c0c33bfe216e6b/metadata.json`为单节点仍失败，确认schema CREATE权限断点。最小新public初始化后，仅3个失败目标复测`private/safe-narrow-d648e09347d44f9f8fd43ad8f0523ae5/metadata.json`为3/3（4.50秒）。必要的public占用/归属漂移负例2项及受影响真实restore失败保留节点1项，在`private/safe-narrow-c6438c08376542d2bdbc361d150a5bdd/metadata.json`为3/3（4.66秒）；合计18个不同节点有通过证据，非一次完整全绿。清凭据/关闭追踪、安全runner测试时区Tokyo，真实模型/消息/服务器均0；测试用实际Windows PG15与实际dump/restore，不作Linux证明。

`private/safe-narrow-dcae469240fa4641b6902ea918d2c263/metadata.json`记录客户端SCRAM/实际DDL日志边界新节点与跨平台发现后的必要prefix4节点2/2（3.58秒）。新增行为合计19个不同节点有通过记录，未声称一次19项全链绿；有限环境、实际Windows PG15及真实dump/restore，不改既有认证/角色权限。

私有metadata位于`private/safe-narrow-e24b119d52034f6b964941d0ff2223f3/`（首链）、`private/safe-narrow-d63fc6d3c64b491287fe0c7c2be93f2e/`（真实恢复复测1通过）、`private/safe-narrow-633554d7fb314b37b3d8efe25f0c1a0a/`（原旧节点1通过）。另一次临时wrapper定位错误未执行业务，记录保留在`private/safe-narrow-6d10d0df18d544708bb4fb6ace80978e/`，wrapper已完全移除。并非一次全链全绿；无模型、飞书或服务器调用。

新发布准备树`private/safe-narrow-f984c1a674c0418287303db71219f5d1/metadata.json`记录15通过/30夹具失败；`private/safe-narrow-3598b8b0a07a4bb08034feeaee499b86/metadata.json`记录短路径复测29通过/1链接夹具失败；`private/safe-narrow-eeb111b1d7074ae7b39143bcf6abf632/metadata.json`记录NTFS junction节点1通过。安全runner测试时区Asia/Tokyo，记录北京时间，真实模型/消息/服务器均0；只使用本测试新建并清理的随机PG15库和两角色，未改变既有角色权限。

`private/safe-narrow-b5e7270f799c4c57855f263c2dc08b73/metadata.json`记录审阅修正后6/6（4.08秒）：两个schema的可更新view反例、SECURITY DEFINER函数与过程反例、实际PGOPTIONS在connect前被拒，以及正常checkpoint/0008最小ACL保留通过。反例只新建本测试对象和授权，不执行破坏性业务DML，结束清理测试库。

`private/safe-narrow-8bb25014e4394185a06bda249989bb50/metadata.json`记录目录伪装负例及双角色默认路径正例2/2（2.11秒）；只运行这两个新增目标，真实模型/消息/服务器均0。

## Interfaces and Dependencies

新增受独立hash审核的first_release_replay_effects，只编排实际候选业务并以只读SQL核状态。显式`--apply-local --upgrade-local --replay-withdrawals-local --replay-pin <审核pin> --replay-ledger <本operation目录latest-withdrawals.json> --candidate-python <真实venv解释器>`才进入；与原--replay-preflight-local参数互斥，不提供单独目标DSN采用命令。正常总连接9（原升级7、候选预检只读1、候选原生pool最大1），不是把native apply包在第十个外层事务。local_candidate_replay_completed和latest_withdrawals_replayed只表示本机新目标实测，central_binding_verified/runtime_verified/native_restore_completed/linux_attestation/publication始终false，中央不provision。

新增两个tools：first_release_candidate_process绑定不可变候选/manifest/dump/latest ledger/实际Python/受审worker，first_release_replay_worker为纯stdlib bootstrap之后的独立候选只读核验器。现有local_restore显式`--apply-local --upgrade-local --replay-preflight-local`并提供`--preflight-pin --preflight-ledger --candidate-python`，才在原creator锁内新建/恢复/升级后的目标加1个owner只读连接，正常总连接8；默认原始/升级路径仍4/7。子进程不继承用户PG或模型环境，不输出原stderr/DSN。真实候选tools namespace与mingjing_core导入前后核路径及manifest字节；这里只确认候选导入与已安装活动依赖元数据，不认证wheel、.pth、审核人或解释器完整供应链。

新增三个tool：first_release_local_inputs（同源审核dump/program/prefix绑定、严格本机输入）、first_release_local_pg（目标缺席检查、创建/持锁/新public初始化/原prefix及owner后验）、first_release_local_restore（默认校验及显式本机原生restore）。`FIRST_RELEASE_ADMIN_DSN`只允许同一实际loopback 55480/55481的postgres或core_test_main控制库；owner/writer继续使用原显式变量。实际进程与显式环境PG*均拒绝，子进程不继承用户PG配置；仅允许显式内存密码注入子PGPASSWORD，固定空passfile，不进argv/输出/文件。外部审核pin及实际可执行/DLL运行环境仍是受信前提，不声称认证审核人或完整解释器供应链。

可选本机升级新增一个内部tool first_release_local_upgrade；只从同次新库上下文调用_upgrade_new_target(inputs,dsns,creator)。正常路径沿用原4连接，增加1个owner升级连接及2个只读ACL连接，共7；PostgresSaver在该owner连接复用，不另开pool。成功回执区分original_prefix与upgraded_migrations，并保持central_binding_verified、central_provisioned、runtime_verified、native_restore_completed、linux_attestation、publication为false；runtime_acl_verified仅表示当前两角色精确权限已核，不代表运行时或发布已验证。

export保持core3-withdrawals-v2格式，deleted_draws规范化为唯一(owner,draw_id)排序列表。apply新增只读计数draw_tombstones_added；所有旧计数及撤销/收据保护保留。新增helper不引依赖，真实PG15测试用已有本机客户端。

## Outcomes & Retrospective

2026-10-24 14:41 +08:00：必要运行源码保持feea；F与核心评测命令已具体化，唯一新测试环境缺口有本机红→绿与必要兼容证据。b008的实际push CI40064916028已只读确认success，feea CI40069757961仍in_progress，不能合并未知CI或用旧门发请求。下一等必要分支CI结果、普通集成后一次最终同源门/里程碑回归，再补最终SHA及就绪提醒。

2026-10-24 14:19 +08:00：必要B7、实际只读Web/Agent装配、拒模型、writer栅栏及维护门、新writer和单位资产各有定向证据；仍未正式Linux启动/验证cgroup，未冻结同源发布候选，执行单不标就绪。下一只整合最终候选并补可审精确命令，不扩重构或新功能。

2026-10-24 14:06 +08:00：副本从prefix4到8、primary消息metadata/搜索回填与第二遍0、sent收据保持、双重放完整幂等、源库prefix4/正文不变及新对象属主均有同一真实PG节点证据。仍缺新运行角色/无模型8788装配、维护门与B7空增量备份串联；最终候选和执行单继续No-Go，不发就绪提醒。

2026-10-24 14:00 +08:00：新copy/pack/unpack必要行为已验证；最终执行单、F副本迁移/回填/收据撤销重放及8788新unit仍待必要接线。无服务器操作，无Docker投入，不发stage就绪提醒；生产继续No-Go。

2026-10-24 12:55 +08:00 R2片：工具新增124/348行，测试约350行、函数≤60。唯一原件都在release-prep/private：首链safe-narrow-6de81d03c3f04e1ea2f9ef1f22cbb05f；公开CLI初版94aa2c4694914a7a8bc3715b14799939；保护env门/必要CLI90760023039c47f3b961bb706a9ac149；seal接线071d53fb4f0f4ec2954e18390537b4f1；最终独立-I四步+在途客户端保留8ffacf96515348629bea32d9e746b5aa。根已读每次metadata/XML/log，没有重复稳定性或宽回归。正式stage需要的四步精确命令及每步继续/停止条件写入既有stage runbook，保原No-Go，不另建证据副本。Windows本机PG、受审管理员文件的早拒和stage限定接口不等同Linux已验、生产可用、完整执行单或授权；交大脑执行的全链及新模型交接尚待补齐，本代理真实请求/服务器0。

10:48 本机实际恢复库与原非空中央的生产装配/Registry路由组合成立，新增273行专属测试，生产/P1b/旧测试无改动；只跑该唯一新node，不重复旧已验矩阵。配置接缝是仅切业务ZHIMING_DATABASE_URL、保原MEMBER中央四项；旧账本不复制、不重签、不清stop，错误绑定拒绝且runtime不开新账户。源restore fixture是明确的合成原生本机样本，app来自当前宿主已提交045代码，不声称是fresh候选archive。两份首发草案补可复用的配置策略，但正式权限、受保护env、真实中央基线、同候选Linux及三unit/wrapper切换均未验收，central_binding/publication继续false。

10:37 原中央继续承载账本的现有配置能力已只读核实；新恢复库实际启动及ModelPort路由组合尚未验证。现阶段不宣称central_binding_verified，下一限定测试不能替代Linux应用、三unit/wrapper、全局writer或用户新授权。

冻结工具[7e2c870 CI](https://github.com/JerryandShawn/zhiming/actions/runs/40009060893)于03:53 +08:00完成：Core584、v4 4133 passed/75 skipped/2 warnings，独立ModelPort949通过（与v4有重叠，不相加）。正式集成[1891975 CI](https://github.com/JerryandShawn/zhiming/actions/runs/40012851772)于04:07 +08:00完成：Core584、v4 4107 passed/56 skipped/2 warnings，ModelPort970通过（同样不相加）。保留跳过与警告，未重跑绿色集合；以上是GitHub Linux CI，未验证本机Docker首发应用恢复或解除全81题脚本/中央身份/正式上线门。

2026-10-24 03:04 +08:00组合链第三次1/1通过（53.69秒，`private/safe-narrow-69ff1a619b7a41fdaa2d14d3992c0837/metadata.json`）；安全组合观察`private/capture-replay-chain-c2df0da3fb6a469da5161fdb70a4e715/metadata.json`。实际固定206f43f原生receive/save/correct、M1捕获及不同新目标同call M2→8→原生双replay完成；M2核24表、sequence=0，连接10，span source/overlap/preserved/run/Outbox各1、checkpoint范围3。源old fact superseded且有正文、run/Outbox stale、public checkpoint[1,1,1]；目标重放后old fact deleted/data={}、run revoked/空request、Outbox cancelled、checkpoint[0,0,0]。新更正fact完整行hash、另一owner、源全部原始状态、raw/context/FTS/非重叠fact均保持，第二遍完整状态与export一致。保留首次16.36秒和第二次13.93秒fixture错误，不能称首次或一次三项全绿；复杂blob是捕获前明确合成SDK seed，非correct_fact或真实Agent输出。新文件306行/最大函数51，Ruff/格式/AST/diff通过，测试令牌已释放，真实模型/服务器/消息0。没有改工具/effects/旧tests，Linux、正式恢复、全局停写、中央身份与发布门仍未放行。

2026-10-24 02:38 +08:00审阅修正的唯一新节点首次1/1通过（35.61秒，`private/safe-narrow-deb14c0902014f8ab032bcef11807a6a/metadata.json`），安全布尔证据`private/source-span-missing-0387e0df665246399f45c9586a138e5d/metadata.json`记录REPLAY_ERASURE_FAILED、orphan_present=true、original_entities_absent=true、runtime_scopes_empty=true及完整状态未改。沿用实际Windows PG15、固定938候选native入口、安全runner清凭据/关追踪/Tokyo测试时区；真实模型/服务器/消息0，测试令牌已释放。effects正常Ruff排版599行、新测试399行，全函数≤60，Ruff/格式/AST/diff检查通过；没有新增helper、worker或pin面，没有复跑旧marker-only/孤立note两项、pure/组合或宽验。此前2/2证据保留，未虚称当前一次全链3/3或正式发布已放行。

2026-10-24 02:19 +08:00marker-only限定片首次2/2通过（68.05秒，`private/safe-narrow-e188bcaa51bc4348a494d5cd45aedaf2/metadata.json`）。固定938真实owner先备份、其后原生receive/save/correct，旧备份恢复后原话、旧两fact、新更正fact、note/runtime/run/Outbox/embedding都缺席；marker精确读回、两export及第二遍全状态严格相等，marker-only=1而raw/source/fact/run擦除计数0，安全证据`private/source-span-missing-5fe8c479177348fe812f4390a2d225eb/metadata.json`。实际孤立note反例在first apply前REPLAY_ERASURE_FAILED拒绝，note仍存在、全状态不变，安全证据`private/source-span-missing-ca12e180a1384dbca33619ed6c2460ea/metadata.json`。没有把受控反例称为已擦除，没有查询/借用/删除Bob同ID行，另一owner保持。Ruff/120列格式/语法/尺寸/diff通过，effects583行软例外、新测试393行、全函数≤60；测试令牌已释放，真实模型/服务器/飞书0。没有复跑pure/组合，源长度/作者仍依受信原生旁账pin，其他缺源/损坏形态与Linux/正式发布未因此放行。

此前只读设计确认原生业务允许缺源marker、观察器存在误拒；随后仅按根审限定门实现并取得上述两项证据。更多未知血缘和无法验证原长度的保守边界未被自动放宽；未修改R7增量路径或任何业务。

2026-10-24 02:06 +08:00组合兼容独立目标首次1/1通过（33.42秒，`private/safe-narrow-fb8cf5172950430c818841bd902b5139/metadata.json`），安全观察`private/source-span-combined-80caf0a207aa48c8a6eda5c989b104c7/metadata.json`。真实固定938旁账含source_span(superseded)+whole fact+whole note，检查span overlap=1/preserved=0、whole=2、private=2/run=1/Outbox=1/checkpoint=3；两fact及embedding均清空，raw仍active/hash不变，context徒步可见，实际PG FTS夜班false/徒步true，另一owner和第二遍全状态严格相等。原pure无fact/message/legacy断言及已过1/1保持、未复跑；本目标只证明whole+span观察器组合兼容，不冒称pure。effects现464行（根审软例外、低于600硬限）、新测试290行，全函数≤60，静态通过；令牌释放、真实模型/服务器/飞书0，同三路径冻结供根审。

2026-10-24 02:01 +08:00pure span片首次唯一真实链1/1通过（31.44秒，`private/safe-narrow-0b81061b92b8408684f39ffcfaa4b8b1/metadata.json`）；安全布尔观察与回执`private/source-span-native-f4c86f2644c74e30b1ce3375702fb178/metadata.json`。固定938原生接收/保存两fact/真实备份/new source correct_fact，旧fact先实证superseded且导出仅source_span+原生note墓碑，未手插或过滤旁账。恢复双apply后独立检查source=1、重叠fact=1、保留fact=1、private=2、run=1、Outbox=1、checkpoint范围=3、whole note=1；raw hash、非重叠完整行hash、bob全状态与第二遍完整Core/checkpoint/sequence严格保持。实际PG FTS夜班false/徒步true，context精确常量正确，旧fact/runtime/run/Outbox/checkpoint失效且只剩非重叠fact的embedding；新更正fact缺席符合旧备份。两文件Ruff/120列格式/语法/尺寸及diff通过，455行effects软例外按根裁定记录；测试令牌释放，真实模型/服务器/飞书0。未重复B或宽测，更多span缺失源/歧义与间接血缘、Linux、正式发布仍未验证。

2026-10-24 01:52 +08:00真实不可变候选证据：唯一新链2/2通过（58.70秒，`private/safe-narrow-43496d4dd96642bda3bdef712f70acdd/metadata.json`）。固定938候选的真实原生迁移→旧备份→latest inactive旁账→原生双重放后，legacy目标deleted/data={}、派生note deleted/无正文、embedding=0，map不变，独立后验检查1/1/1/2且全部Core/checkpoint字段与sequence第二遍相等；安全观察`private/legacy-native-replay-41a06438183348b19c1dc2aecaa05809/metadata.json`。固定144未被控制树新业务替换，真实body_present=true、note active/正文存在、embedding=1，effects只读核验在first apply之后以REPLAY_ERASURE_FAILED拒绝；安全观察`private/legacy-native-replay-56cef1e89d6d4769957f8aa03efcc6af/metadata.json`。原01:39红回归和metadata保留，当前正确删除断言移到固定938正例；144改为要求实际残留的受控负例，没有xfail或降预期。两个Python文件Ruff/120列格式/语法/尺寸、diff通过，真实模型/服务器/飞书0，测试令牌已释放。source_span专门片、其他隐私血缘、Linux与正式恢复仍待，不据这两个Windows本机节点放行发布。

2026-10-24 01:44 +08:00最小共享repository修复的控制树证据：`tests/v4/release/test_legacy_memory_apply_pg.py`共3组/8参数首次8/8通过（2.69秒，`private/safe-narrow-a7affe005d0043b3b1649b9f3644c0a5/metadata.json`）。实际迁移生成legacy_unverified legacy及verified fact，最新仅legacy_memory的原生导出经apply均清空目标正文，原embedding清理及派生note闭包生效，map不变、第二遍全部本schema表字段hash不变；缺map/None/实体、双kind同ID、archive来源与跨owner错映射均按保守规则处理。helper42行/函数28行，新测试188行/最大函数37行，Ruff/120列格式/语法/diff通过；postgres仅import与5行分支，没有改变memory服务/工具/上下文、source_span、state_version、原事务或迁移。令牌已释放。根提交新候选后才能验证真实candidate正例、旧候选拒绝和effects独立擦除后验；原144失败证据与正确断言保持，未伪称全链修好。

2026-10-24 01:39 +08:00新增实际失败：候选`144b81eeed3e792221393673bd611637fbaae01f`的原生mapper使无原话memory映射kind=fact、mapping_status=legacy_unverified，实际实体kind=legacy/status=pending。真实dump之后SQLite改为deleted，原生迁移/export只产生legacy_memory旁账；旧备份原生恢复和两遍apply之后，实体仍pending、body_present=true、data_empty=false。两遍全状态hash却严格相等，故只看幂等/旁账无法证明擦除。运行证据`private/safe-narrow-35534b4e32e04af5bcd853f51cdaf6cf/metadata.json`，仅安全布尔值/状态的业务证据`private/legacy-native-replay-d8f8ab8dac6642d6ba1ffb180f9f46ba/metadata.json`；真实模型/服务器/外部发送0，TZ Tokyo。新测试172行/最大函数44行，Ruff、120列格式、语法和diff检查通过。测试令牌已释放；本片只交真实失败与两个文件，业务修复及独立span/legacy擦除观察仍未完成，正式首发保持No-Go。

当前已完成实际受pin候选在同call新本机目标上的原生双重放及第二遍完整幂等基础，legacy实际映射目标及受支持直接派生有固定938/144正反证据，superseded source_span有固定938的raw/投影/FTS及实际血缘证明；真实旧候选负例会停止，不能换用控制树修复将其放行。仍未涵盖源prefix8备份/中央身份保全、所有间接legacy及其他span形态、Linux运行时、供应链认证、既有库增量apply、正式stage/生产或开门。外部审核pin仍是受信前提，测试自产pin和真实Git包不认证审核人；正式首发继续No-Go。

独立只读预检模式已验证真实候选fresh-process、Python3.11 venv活动依赖及新目标状态；该模式仍不执行撤销/收据双重放，回执read_only=true、mutations=0及各正式完成位不变。新增的显式双重放使用另一个pin/schema与9连接，不把只读预检的8连接回执升级成重放证明。外部审核pin仍是受信输入，测试自产pin不构成独立审核；两个模式均不能宣称生产恢复就绪。

早先控制树原生业务的非空隐私/回执幂等回归已延伸到受pin实际候选的独立进程；真实旧候选第二遍仍变化时会失败，不能拼接控制树修复。Windows本机逻辑证据不等同Linux正式恢复或中央身份保全，正式首发仍No-Go。

本机原始prefix恢复、同次新目标前向到8、checkpoint显式setup、最小授权/精确ACL和可选最新旁账双重放均已有定向证据。回填、源prefix8中央账本保全/重绑定、正式Linux/容器端口映射、stage/生产、unit及开门仍未实现或验证，首发全链尚未完成。现有formal硬门不变，Linux容器NAT实际端口与严格身份不匹配时继续拒绝，不能放宽为Linux通过。开门前回退和开门后止损规则不变。

新凭据边界与正常恢复均有定向证据；跨平台CI实际运行和SCRAM认证端点验证由主线CI结果判定，当前不声称已绿。角色verifier也不进入回执，服务端审计日志可能记录verifier，须继续按敏感运行日志保护。

已修最终代码的非空撤销往返，并完成相关Windows PG15实际备份恢复验证。未完成Docker/Linux整链、生产原生恢复入口或可执行的新发布单，首发保持No-Go；不沿用b9的空样本或旧授权放行。

只校验契约与精确ACL基础的45个早期定向行为证据仍保留；此后本机新库恢复、升级、真实候选预检和双重放的证据分别登记，不相加冒称一次全链通过。最终冻结candidate、正式恢复入口、实际Linux运行时、中央账本改址及unit切换仍缺失；JSON输入及本地Windows检查不具有部署授权。

审阅追加5个不同安全反例及1个受影响合法节点通过，合计50个不同定向行为有通过记录；没有把外部审核pin、Windows证据或关系/函数元数据校验升级为可信发布证明。

目录路径补正又有两个不同定向行为通过，累计52个不同通过行为；仍为validate-only，无apply或原生恢复执行。

## 修订记录
- 2026-10-24 12:55 +08:00：采用v14，按v12交R2独立新库/metadata/关门对调与必要本机证据；新增stage限定实际命令，不宣称全单或生产就绪。
- 2026-10-24 10:48 +08:00：中央routing唯一新节点首次1/1、根核原件，明确旧历史/sequence与唯一新增物理UUID、四类早拒及当前宿主装配边界；生产代码不改，正式门继续关闭。
- 2026-10-24 10:37 +08:00：先登记原中央/新业务库真实恢复路由的必要组合设计与现有原生接缝，不新建证明层或擅改位置身份。

- 2026-10-24 04:14 +08:00：根核对应冻结工具与正式集成两个确切SHA的绿色CI，分别记录范围、跳过项与不能放行的门；没有重新测试或复制原始日志。

- 2026-10-24 01:26 +08:00：新增独立replay pin、受审编排helper与7/7真实候选双重放窄验；记录旧包真实失败、原生提交后purge边界、9连接及隐私形态覆盖限制，正式门不变。
- 2026-10-24 01:11 +08:00：新增显式同call候选fresh-process只读预检与9/9真实窄验；记录活动marker、候选namespace/来源、依赖元数据及CI路径边界，未接撤销重放或正式恢复。
- 2026-10-24 00:48 +08:00：记录非空双重放真实失败及共享repo两SQL最小幂等修复，保留全部字段断言和1+2窄验，说明候选worker与正式恢复仍未完成。
- 2026-10-24 00:36 +08:00：新增同次本机新库显式升级阶段和11/11窄验；保留默认原prefix路径、阶段失败现场与中央身份/正式发布硬门。
- 2026-10-24 00:26 +08:00：修复DDL日志中的原口令路径，记录2/2窄验与实际认证证据边界；明确Linux PG15客户端及独立测试库要求。
- 2026-10-24 00:20 +08:00：新增本机local-only原始prefix真实恢复基础与18项定向证据；记录NOINHERIT/public初始化失败及最小修正、失败保留和正式恢复仍阻塞。

- 2026-10-23 23:10 +08:00：记录最终候选删除血缘修复、实际PG定向证据及仍未解除的发布门。
- 2026-10-23 23:38 +08:00：记录独立发布准备树的只校验契约、0008精确ACL、45个定向行为与两次Windows夹具修正；明确未执行任何原生恢复或Linux发布。
- 2026-10-23 23:46 +08:00：修复审阅发现的视图/SECURITY DEFINER与PGOPTIONS绕过，记录6/6定向结果和外部审核pin信任边界。
- 2026-10-23 23:53 +08:00：固定并核验两个ACL事务的pg_catalog路径，记录真实目录伪装反例及双角色自定义路径正例2/2。
