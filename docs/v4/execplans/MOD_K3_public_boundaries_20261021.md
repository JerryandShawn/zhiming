# MOD：K3刷新公开流程九项独立边界

本ExecPlan按`.agent/PLANS.md`维护。只新增独立测试、合成夹具和证据，原K3产品、旧token基线、
原测试和黄金不改。首测后报告并停止；产品修复和扩大兼容都需要root审读后另行授权。
首测9项全过后，root另授权一次两套必要兼容及policy/refresh两产品覆盖，仍不改产品或真值。

## Context and Orientation

工作树`C:/Users/Administrator/Documents/Codex/zhiming-v4-mod`。已完整阅读
`adapters/channels/action_token_refresh_v2.py`、直接caller `action_token_policy_v2.py`、
`action_token_contracts.py`、`action_token_store.py`、`action_tokens.py`及现有策略/独立/旧cards测试。
设计依据为28号K3冻结行、`docs/v4/integration/mod/Q6_p9_v2_20261021.md`。
复用公开`K3TokenService.issue/consume`、`MemoryTokenMetadataLookup.lookup/revoke`、
`MemoryActionTokenStore.snapshot`、`FrozenClock`，不调用产品私有validator/digest/operation helper。
operation预期只观察公开issue结果；坏operation通过公开合法record的dataclasses.replace构造。

K3规定普通卡24小时，删除/应用整理确认15分钟；正确绑定的真实过期只返回刷新意图，不执行旧动作。
owner/subject/open_id/kind/entity/fingerprint、当前metadata、稳定operation和原子消费不变量不能放松。
内存参考不是PG真实性证明；guard退出失败不等于已证明PG回滚，也不等于业务效果完成。

## Purpose / Big Picture

检查当前metadata快照和host guard/Clock异常时是否仍失败关闭，以及多owner合法记录和稳定operation绑定。
本轮不重复已有TTL端点、普通错owner、lookup后取Clock、撤回优先或未知重发规则。
不按82.4176%覆盖数字推导新产品口径，也不执行低优先的R10–R14构造器镜像测试。

## Progress

- [x] (2026-10-21 11:04 +08:00) root批准R01–R09；完整只读审查和相关测试去重已完成。
- [x] (2026-10-21 11:07:12 +08:00) 冻结9行矩阵和12份原相关代码/测试SHA，矩阵SHA为387974c21ef77e8c07748093ca98ec14917cc7938a9936a9d53b76ab873b91c1。
- [x] 新增139行helper/133行test及合成诊断夹具，Ruff/format/尺寸与完整类型检查通过。
- [x] (2026-10-21 11:10:09 +08:00) 单目标首测9/9通过0.07秒；runner.environment清12类key并关tracing，socket/DNS禁用。
- [x] 17份窄范围材料before/after一致；pytest输出先在内存按生成token精确脱敏再落LF，实际替换0次、没有token外泄。
- [x] 保存首测JSON/log并停止；不修产品，不扩大兼容、coverage或性能范围，不Git。
- [x] root另授权p9_v2+p9_official_v3必要兼容，覆盖仅policy_v2/refresh_v2原分母，不新增R10–R14。
- [x] (2026-10-21 11:14:05 +08:00) 单进程1976/1976通过24.34秒；48份窄范围材料集合/字节一致。
- [x] 行126/133、分支29/36、综合155/169=91.71598%；缺行/缺支据实保存，不补测凑100%。
- [x] 更新四活节、新接线补充与§11回执；产品/原测试/黄金不变，冻结后交root统一Git。

## Validation and Acceptance

| ID | 公开输入 | 独立预期 |
| --- | --- | --- |
| R01 | SnapshotTokenStore.snapshot抛合成诊断异常 | 统一ActionTokenError、不泄漏、真实store未消费，不报过期刷新 |
| R02 | snapshot返回合法记录list | 拒绝非不可变快照；真实store未消费、不返回执行许可 |
| R03 | tuple含合法记录和null坏成员 | 整份拒绝、不挑合法项，真实store未消费 |
| R04 | 多owner合法记录，目标不在首位；撤销另一digest | 正确目标仍可首次消费，另一token仍拒绝；旧快照的记录不被原地改变 |
| R05 | lookup.guard进入失败 | 固定无效错误、诊断不泄漏、lookup与consume均未发生 |
| R06 | 本地consume已记录，guard退出失败；随后guard恢复 | 本次不给执行许可；本地used_at保留，后续只有同operation重放、不再次执行 |
| R07 | consume时Clock抛合成诊断异常，随后恢复 | 固定错误、不消费、不误报刷新；恢复后首次消费可执行，再次只重放 |
| R08 | consume时Clock返回naive，随后恢复 | 同R07；不预设内部Clock调用次数 |
| R09 | 合法record携带格式合法但与公开issue不符的operation，且已过期 | 拒绝、不泄漏/不刷新、不消费；不调用私有operation计算器 |

这些是K3公开流程不变量，不把`07_评测场景集.md`里的产品场景标成已通过。
没有构造器绕过、object.__setattr__或伪造typed实例；R02/R03只模拟公开port返回坏容器形状。
合成诊断正文只保存在`tools/eval/fixtures/mod_20261021/k3_public_boundaries_synthetic.json`，异常对外不得带该正文。

## Plan of Work / Concrete Steps

新增`tests/v4/p9_v2/test_token_public_core_mod.py`及独有`token_public_support_core_mod.py`。
真实record通过公开issue/snapshot取得，Clock、snapshot和可选guard用明确本地替身。
所有当前状态只从公开接口观察；不读写产品私有dict/lock，不假装有数据库事务。

    python -m pytest tests/v4/p9_v2/test_token_public_core_mod.py -q -p no:cacheprovider

运行环境先调用`tools.mod_week.completed_regression.environment()`清12类key、关闭tracing、
private TEMP/TMP；禁外连方法/DNS，保留socket类型以免破坏依赖导入，原P9离线fixture保持。
只跑9项，不运行全量、性能、coverage、模型、服务器、PG、飞书或Git。

## Surprises & Discoveries

原测试已覆盖metadata lookup异常，但未直接覆盖MemoryTokenMetadataLookup读取坏snapshot。
guard是可选host事务端口；内存consume后guard退出异常可留下已使用记录，预期必须区分无返回许可与未消费。
首测九项全部通过，没有发现本轮产品实缺。静态检查脚本一次未显式UTF-8而受Windows默认GBK影响，
只修了检查脚本读取编码，未改测试/产品；实际pytest与报告均明确UTF-8。
两套兼容覆盖仍缺policy的构造器坏port分支、refresh的坏构造/结果组合分支；这些不在批准的9项流程内。
覆盖JSON保留工具原始字节（无CR、没有末尾LF），不为排版修改其SHA或把未测路径说成已验证。

## Decision Log

仅实施root批准的九项。R04正向多owner用合法合成身份；不新增重复digest快照政策。
R06不用异常推导PG rollback或实际effect，后续仅观察内存重放。
R07/R08先用合法Clock公开issue，再在consume入口切换坏Clock，恢复后证明token未被烧掉；
不预设Clock/lookup内部调用次数。R09观察公开issue.operation_id后选择另一个合法格式值，独立于私有算法。
before/after只绑定K3五代码、Clock、原测试/黄金/离线fixture及本轮矩阵/新测试/合成夹具，
排除并行legacy bridge代码的无关漂移。runner仅使用environment函数，不调用source_snapshot或Git。
遵守root补充的证据卫生：pytest采用short traceback、清空addopts、不显示locals；输出先留内存，
对本轮全部生成token精确替换后才写日志。公开JSON只有摘要、来源SHA和脱敏状态，不存raw token。
兼容阶段还透明记录secrets.token_urlsafe原返回值，原样返回且try/finally恢复，仅用于精确清理输出；
未改变随机值、产品控制流或测试预期。实际日志替换次数0，无raw token落盘。
root会修改runner显式材料列表，因此不绑定runner整文件，只记录environment函数SHA；
运行before/after绑定K3相关产品/Clock、两套所有Python/JSON测试与夹具、原K3相关测试及新矩阵/诊断夹具。

## Idempotence and Recovery

每项独立内存store/Clock，stable operation由公开issue返回，测试不会运行真实动作。
日志和JSON用新文件独占写入，UTF-8 LF；不覆盖首次失败或旧证据，无迁移、无删除或恢复外部数据。
首测若失败，只记录固定case ID/reason与受控合成断言；不擅自改产品或黄金。

## Outcomes & Retrospective

9项首测全部通过，17份相关材料字节before/after相同；原K3、基线、测试/黄金均未改。
R06证实本地consume已记录而guard退出错误时本次没有返回许可，后续仅同operation重放；
这不证明PG rollback或实际业务效果。R07/R08恢复合法Clock后可首次消费，未预设内部调用次数。
R04合法多owner、非首条查找与另一digest撤销保持隔离；R09公开issue身份不符的过期metadata仍拒绝。
首测阶段没有运行兼容、coverage、全量、性能或外部请求，报告后按当时授权停止。
随后按root新增授权完成一次必要兼容1976/1976，两产品行94.73684%、分支80.55556%、综合91.71598%。
48份材料集合/字节无漂移，原矩阵SHA不变。policy单文件综合97.43590%、refresh86.81319%，缺口未追加镜像测试。
没有产品修复、全项目回归、性能或外部请求；本次测试/覆盖不证明PG、飞书授权或业务效果。

## Artifacts and Notes

新矩阵与首测metadata：`docs/v4/evidence/MOD_2026-10-21/K3_public_*_20261021.json`。
原始log：`private/mod-week/K3_public_first_target.log`。全部源/原测试hash固定在矩阵中，
报告前后仅检查本轮窄相关范围，不把其它并行代码变动归为本轮结果。

## 修订记录

2026-10-21 11:04 +08:00：root批准九项后创建自包含计划；首测后停止，不授权产品修复或兼容扩张。
2026-10-21 11:10 +08:00：记录9/9首测、窄范围17材料无漂移和token日志卫生；不扩测、不修产品。
2026-10-21 11:14 +08:00：按root另授权记录1976兼容、两产品覆盖及48材料快照，补接线/回执并冻结。
