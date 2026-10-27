# P8流日与晨报契约只读对照

本机证据读取截至北京时间2026-10-21 11:26:06。本轮只读契约、Schema、明确synthetic样例与晨报消费代码，
只新增本文。没有修改对方工作树、原pending文档、产品、测试或黄金；未运行验证器、产品、测试、探针、coverage、
网络、fetch、模型、PG或平台接口。

## 本机版本与样例身份

命理线工作树：`C:/Users/Administrator/Documents/Codex/zhiming-v4-p8`。
两次只读HEAD均为`c471d4ac89444bcb004e102a8ab026c738c2788c`。
限定到本轮所读5个P8文件的`git --no-optional-locks status --porcelain=v1`输出为空，表示这些路径在观察时无dirty项。
不代表全树clean、远端同步或已部署。

先读`contracts/samples/daily_transit/README.md`与manifest，确认七份样例为完全合成人物、本机引擎计算，
随后只读取10月21日样例的字段结构。没有读取真实出生/盘面数据，也不在本文复制合成出生资料或盘面正文。
P8该样例与本线`daily_transit_synthetic_20261021.json`逐字节相同，SHA均为
`0b0984e1a6cf9c48f060071e861da1438d9ee2122a7635095d7f71933a589205`。
其40个rule hit、64个c别名和40个r别名的字段形状与本线当前样例一致。这是样例同源证据，不是本轮运行验收。

## 已对齐的字段与语义

| 字段 | P8依据 | 晨报依据 / 结论 |
| --- | --- | --- |
| version / 顶层键 | `daily_transit.schema.json:6`、`:10` | `evidence.py:15`、`:76`：同为`p8-daily-transit-v1`及9个顶层键 |
| scope身份/版本 | Schema `:37`–`:45`，md输入/输出 | `evidence.py:78`–`:88`：`owner_user_id`映射host owner，subject相等；scope.revision与外部`profile_revision`相等，均为非负整数 |
| `profile_revision`名称 | P8 wire使用`scope.revision`，没有同名顶层字段 | 它是晨报host的当前权威投影参数，不要求P8额外增加wire字段。仅值一致不能证明当前授权 |
| 日期/时刻 | md `:7`；Schema `:64`–`:68` | `evidence.py:92`起：显式目标日、北京时间正午12:00、同瞬间04:00 UTC；不能外推全天或跨周期 |
| document_id | Schema `:14`；md `:81`：绑定版本/scope/完整data/命中/来源 | `evidence.py:16`、`:47`：按这5根重新计算`tool-<sha256>`。当前样例完全一致；md/schema没有单独写出完整canonical JSON序列化规范，不能据一个样例推导未来所有实现 |
| c别名 | Schema `:149`；md `:79` | 两边为`alias,path,value_sha256,claim_id`；data Pointer去重排序后编号，当前样例字段集合一致 |
| r别名 | Schema `:160`；md `:79` | 两边增加`rule_id,evidence_aliases`；按rule_hits顺序编号并关联c。claim和文档绑定，短别名不跨人/跨日全局复用 |
| 当前来源 | P8明示只读、无持久依据/撤回账本 | `authorization.py:56`、`current_manifest.py:35`：晨报另需当前source state，其source_id为完整document_id，hash为其摘要，revision与host版本一致。这是额外host责任，不是P8已认证PG |

只读样例中的日层标识：

| system/kind | 10月21日合成样例 | 当前晨报消费 |
| --- | --- | --- |
| bazi / ten_god | 3项，`context.layer`为yearly/monthly/daily字符串 | 只取`layer == "daily"`，`transit.py:74` |
| ziwei / mutagen | 12项，`context.layer`为yearly/monthly/daily字符串 | 只取daily且落点唯一resolved，`:87`起 |
| bazi / relation | 15项，`context.target_layers`全部为list；出现`["daily"]`、`["monthly"]`、`["yearly"]`、`["yearly","monthly"]` | `:79`检查daily成员；下节所述类型未由上游Schema冻结 |
| astro / aspect | 10项，无`layer`或`target_layers`字段 | 由整份显式日期/正午快照表明流日；不能擅自新增layer必填要求 |

## 仍存在的契约差额

**target_layers待决不能关闭。** 上游md `:70`只列该字段为稳定字段；Schema `$defs.hit.context`
（`:146`）仅要求system/kind并定义system枚举，没有定义target_layers、layer或每种kind的字段类型。
样例足以证明当前生产者样例采用list，不能证明字符串已被正式契约禁止。
本线`transit.py:79`的`"daily" in context.get("target_layers", [])`在字符串上具有子串语义，
因此消费端没有独立保证“完整日层成员”的类型。这里只记录静态类型差额，未构造输入或运行验证/渲染，
不把它写成已复现故障，不更改此前冻结真值或pending文档。

**hit的允许扩展范围不同。** 上游Schema `$defs.hit`未写`additionalProperties:false`，
`source`仅要求object；本线`evidence.py:124`要求恰好6个hit键，`:126`要求source非空。
因此上游Schema可表达的集合比晨报实际接受集合更宽。当前合成样例没有这个差额，
此前BE04/BE05已保护晨报拒绝额外hit字段/空source，不能为“向前兼容”自行放宽。
应由主线/大脑决定收紧上游Schema还是显式保留消费端子集，不把未知扩展默认为事实。

**内容绑定不等于真实性。** 两边doc/alias/claim形状一致，不证明P8数值已被独立天文核验、
scope.revision确为当前资料版本或该source未撤回。本轮未执行canonical hash重算/Schema校验，
只比对文档说明、代码、字段形状及文件字节，不能据此报告端到端验收或发布同步。

## 建议的未来工作（本轮均未运行）

先在上游契约中明确relation的target_layers是否为非空字符串数组、合法层枚举及未知层/重复项处理，
再冻结消费者边界测试。若裁定为数组，应覆盖完整`daily`成员与非日层；字符串（含daily子串）、null、
对象和混合成员按批准口径受控拒绝或省略，不能先把这些变成新的黄金。

针对hit扩展范围与source完整性，先对齐声明，再复用已有BE04/BE05，不重复新增同义测试。
未来若新增跨线契约检查，应显式选取已标明synthetic的固定样例、版本/SHA，并区分Schema可接受与
晨报支持的日层子集；现有owner/profile/撤回/alias防线保持，不新增无依据的astro.layer要求。
这些建议没有授权改P8树、晨报代码或冻结材料。

## 来源SHA（本机读取快照）

P8根目录相对于`C:/Users/Administrator/Documents/Codex/zhiming-v4-p8`：

| 文件 | SHA256 |
| --- | --- |
| docs/v4/contracts/daily_transit.md | aaee393c9e8c934afbbdb768975a8a7880e4c10b26389429a829c9a114729557 |
| docs/v4/contracts/daily_transit.schema.json | ac389257dade5198ca42573e137591a51b27dd0a34ef443a49cb4d1d7a9861aa |
| docs/v4/contracts/samples/daily_transit/README.md | 83b8b17e498bf115fa6d846148586be7fa634bdfd87539bfdc14df7d03e4926c |
| docs/v4/contracts/samples/daily_transit/manifest.json | 3bc9081cd0e61bfcb3d0f1aec55a0c1c93d3a3f6d9cfbcb84bb98aa8393103f0 |
| docs/v4/contracts/samples/daily_transit/ayuan_2026-10-21.json | 0b0984e1a6cf9c48f060071e861da1438d9ee2122a7635095d7f71933a589205 |

本线根目录相对于`C:/Users/Administrator/Documents/Codex/zhiming-v4-mod`：

| 文件 | SHA256 |
| --- | --- |
| mingjing_core/application/briefing_v2/evidence.py | fe0fd74df3ac39502b0a192e76413e3cae58d9250a7fb048b9834130c2c3e7d6 |
| mingjing_core/application/briefing_v2/transit.py | bdd019a0febb45831f23cf476429da61c9ceec7dd05fc867b3e20672ed12ffad |
| mingjing_core/application/briefing_v2/contracts.py | 0e48a65b417120c8bc5268c275a6bd97308f6df8702e03959c88ba6b1bb41a3c |
| mingjing_core/application/briefing_v2/current_manifest.py | a5d05a982c6ed384c1a56541ac520869601db6e854fc50c62d25bd3b536a23af |
| mingjing_core/application/briefing_v2/authorization.py | dfc208bc9c5b45b00cf256a36d27a448af250c12db89558404712eb79193a742 |
| mingjing_core/application/briefing_v2/compose.py | b38745b7a5ac59affd487f0922d6f9cc986c879d61ce0f9902a2184c6ae5fbde |
| tests/v4/briefing_v2/fixtures/daily_transit_synthetic_20261021.json | 0b0984e1a6cf9c48f060071e861da1438d9ee2122a7635095d7f71933a589205 |

hash仅绑定这些已读取文件的本机字节，不代表远端、部署、未来HEAD或其它未读数据。
