# MOD：晨报当前来源清单独立复核

## Purpose / Scope

独立复核新增current_manifest隐私门禁，限定8个真实PUBLIC compose场景。
最初只读准备；Core/root冻九源并放行后，本轮8项独立PUBLIC首测已通过。没有追加兼容、覆盖或性能运行。
不改9晨报源、原30真值/辅助、旧测试或黄金，不访问网络、模型、PG，不执行Git。

来源当前性是host提供的可信投影，本模块只检查一致性，不能把指纹或类型当作真实数据库授权。
同一source_id不能同时以active与revoked或不同revision/hash称为“当前”；无效P8材料也不能反过来阻断正常历法。

## Context and Orientation

已经完整阅读briefing_v2九源：__init__、authorization、calendar、compose、contracts、current_manifest、
evidence、items、transit；并完整读原30测试、brief_public_support_core_mod.py及其冻结矩阵。
本次不重写原30项；只补订阅/P8跨入口清单、早退和新门禁拒绝顺序的独立约定。

未来仅从公开compose_briefing与BasisRef/BriefSourceState/BriefItem等类型构造输入。
公开calendar_snapshot只用于取得有效P2历法输入；预期不由它决定。
订阅指纹使用独立标准JSON/UTF-8 SHA256计算，不调用subscription_basis来生成期望。
合法P8使用既有显式合成daily_transit_synthetic_20261021.json原文，不调用产品validate_transit、
current_manifest或产品私有helper来重签或判定真值；不运行真实排盘。

## Progress

- [x] 完整阅读九源和原30独立辅助/矩阵，核对PUBLIC输入的正常组装与错误出口。
- [x] 固定下表8个独立期望，原计划SHA在首次执行前记录，未据产品输出调整真值。
- [x] Core/root明确冻源后新增唯一独立helper/test，先复核九源、原30材料和两份合成fixture。
- [x] (2026-10-21 10:15 +08:00) 单目标首轮8/8通过0.63秒；17执行快照前后相同，无产品失败或改动。
- [x] 保存LF证据、Ruff/AST检查和§11短回执；不追加兼容、覆盖或性能，交root审查发布。

## Frozen expectations：8个案例

所有输入先满足scope、当前历法、订阅、候选到期时间和公开类型要求，避免用无关的alias/cap/occurrence错误替代门禁。
items使用独立occurrence和不冲突的m别名；正常正文只取显式合成fixture。

| ID | PUBLIC compose输入 | 独立预期 |
| --- | --- | --- |
| BM01 | 正常当前订阅为active，item声称同一订阅source/revision/hash已revoked | 整次固定BriefingError拒绝，不先省略坏item后继续泄露同源内容 |
| BM02 | 合法且owner/day/profile/doc/hash完全绑定的P8 state为revoked，同源item state为active | 同样拒绝；撤回P8状态不能因不可渲染而先从当前清单消失 |
| BM03 | 两组正例同时存在：subscription/item状态完全相同，合法P8/item状态也完全相同 | 正确允许，历法与合法内容仍可见；重复同值不等于冲突，effects全0 |
| BM04 | P8原文limits改为空而失效，P8 state与同源item呈矛盾 | 坏P8不成为当前权威；省略P8并警告，正常历法与有效item不被阻断 |
| BM05 | P8原文合法，但P8 state的revision与当前profile不匹配，同源item为正确状态 | 错绑定P8仍省略，不用其矛盾投影阻断正常历法/item |
| BM06 | disabled订阅配正确当前订阅状态，items存在彼此矛盾的当前状态 | 保持关闭订阅早退：无正文、无外部effects，不深入item/P8清单 |
| BM07 | 同source同revision/hash的active item排前、revoked item排后 | 固定拒绝，不能挑首个局部有效状态 |
| BM08 | 与BM07同一批交换items顺序 | 同样固定拒绝，不挑最后一项；原因/安全错误与BM07一致 |

拒绝场景核reason及不回显合成正文，不捕获任意异常当通过。BM04/05不能接受抛BriefingError充当省略成功。
BM03/04/05需明确看到正常calendar段；BM06是无内容的安全早退，不意味着可跳过所有输入的scope/历法验证。
BM07/08只改变公开items顺序；原30允许整批拒绝或整批省略的真值不修改，本轮专门核新门禁拒绝约定。

## Surprises & Discoveries

已读实现将跨入口清单核对放在投递关闭早退之后、内容渲染之前。
P8只有在完整文档及scope/day/profile/doc/hash绑定合法时才进入清单；合法且revoked/inactive/incognito的
当前状态仍应参与冲突检查。本轮PUBLIC8项实测全部通过；坏/错绑定P8省略而保留正常历法也分别通过。
没有发现新产品反例，也没有将有限通过外推为PG授权或穷尽证明。

## Decision Log

只读原30辅助以了解公开输入形状；不直接导入其helper或产品validator造预期。
保留“有效且绑定的P8”与“坏/失配P8”两种不同资格，不能为加强门禁而使坏外部材料冻结正常历法。
不调用私有current_manifest入口，不绕过dataclass构造器，不伪造内部冻结状态，不改变原30矩阵。
时间固定2026-10-21北京时间07:00，使用显式FrozenClock与Asia/Shanghai，不依赖Tokyo主机时区。

首测前计划SHA256为`d4fc2aa32662c9625567fc5f385d7529e0af93cdf7201fbbfbc970463d0e75b1`。
本次仅更新活文档状态，原8行真值表保持逐字不变；表SHA256为
`4380db3f91dee5b9b32049b6f8e2d6f2a89a6f4de619929de839e8f213f3d5ed`。

## Outcomes & Retrospective

独立PUBLIC8/8首轮通过0.63秒，无产品/旧测试/黄金修改。新增test_manifest_calendar_mod.py和
manifest_calendar_support_mod.py均位于tests/v4/briefing_v2；完整9产品、原30材料与合成输入前后摘要一致。
含原冻结计划共17快照；计划状态后续更新，运行代码/测试/材料16份单独保留，避免把活文档维护误称源漂移。
证据：[BRIEF_manifest_calendar_verification_20261021.json](../evidence/MOD_2026-10-21/BRIEF_manifest_calendar_verification_20261021.json)，
SHA256 `f9506e59447f8313112415fe909fdfb7b062ca07c4b35c51b9943b9aff95ccc1`。
没有新增兼容/覆盖/性能或真实投递结论。产物全部在mod，新公开JSON显式UTF-8 LF；root负责提交及blob字节核对。

## 原只读检查点与首测核对

current_manifest.py读取时SHA256：`a5d05a982c6ed384c1a56541ac520869601db6e854fc50c62d25bd3b536a23af`。
compose.py：`b38745b7a5ac59affd487f0922d6f9cc986c879d61ce0f9902a2184c6ae5fbde`。
contracts.py：`0e48a65b417120c8bc5268c275a6bd97308f6df8702e03959c88ba6b1bb41a3c`。
这些是原始文件SHA256，不是提交号或真实来源证明；root放行后已重新核对九源，上述三个值未变。

## 修订记录

- 2026-10-21：按root指派完整读九源与原30辅助，冻结8项公开期望，只新增计划，等待Core/root冻源和放行。
- 2026-10-21 10:15 +08:00：获明确放行后首测8全过，保存LF证据与源稳定快照；更新四活段落，不追加兼容或覆盖。
