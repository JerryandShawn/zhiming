# 旧消息桥：严格标量证据与独立边界核验补充

记录时间：`2026-10-21T11:14:40.145984+08:00`。这是模块线离线候选的接线补充，不表示主线已接线、DB 已授权或真实用户操作已验收。
旧 [DAY 接线指南](DAY_supplement_20261021.md) 保持原样；本文件只补本次已观察行为及限制。

## 公开入口与不变量

`to_legacy_changeset(snapshot, plan, document, *, scope, approval) -> ChangeSet` 位于
`mingjing_core/organize/supplement_v2/legacy_bridge.py`。
先用公开 EntityRecord/MemorySource/SourceAnchor 和审阅 API 建立合法当前计划，旧桥每次仍重核原有来源与获批内容。
宿主必须继续从当前权威读取 owner/subject、source revision/活性/撤回/无痕、敏感同意和真实审阅收据。
本函数只生成仅标签变更集，不应用 DB，不验证真实登录，不把模型或客户端自称的 approval 当用户授权。

完整消息专用桥要求消息 ID 与唯一来源 ID、全文、角色、时间、源及实体修订、原标签一致。
部分或多源 anchor 可以是合法通用实体映射；本旧桥拒绝它们只表示主线需其他实体适配器，不能删改来源补成单消息。
话题归档计划也不能借 messages 适配器执行。缺失标签与显式 null 仍分别绑定，不能吞掉后续并发变化。

## 本次严格标量修复

原先 raw 字典等值比较会让 True 等同整数 1。独立 LB08 首测保存了 Message 拒绝、旧桥却返回 ChangeSet 的真实结果。
另一组 IB01/IB03/IB04 独立首测也保存了等值 float revision/at_ms 和 bool at_ms 的接受反例。
root 仅在新 legacy_bridge 的 _message_matches 增加通用类型门禁：

- raw revision 缺失时仍按默认 1 比对；存在或缺省值必须为真正整数且 ≥1。
- raw at_ms 必须为真正整数；不将 bool/float 转换成 int，不补写原字段，也不新增正时间限制。
- 无效标量固定拒绝 legacy_message_evidence_changed，原 owner/来源/审阅门禁保持。

原 15 与独立 5 的原断言均未改。LB15 缺失 revision 仍成功且保持键缺失，IB02 匹配 revision=2 仍成功，
IB05 整数 epoch 0 仍成功。没有额外运行负整数时间测试，不声称这轮穷尽时间整数域。

修前旧桥原始 SHA256 为 `e6b5a98bf95241d29470d2236b899a05bfd86615b130c13445a5529e85451c9b`；修后为 `78ec7567a947388968d3d85d8565495aa904bdd8696ca63969ab30a74c3fc793`。
这些是源码字节摘要，不是 Git commit、用户身份或实际 DB 事务证明。

## 实测证据与范围

| 观察 | 结果 | 证据 |
| --- | --- | --- |
| 原 15 首轮 | 1 failed / 14 passed，0.23s；LB08 返回变更集 | [first](../../evidence/MOD_2026-10-21/LEGACY_BRIDGE_independent_first_20261021.json) |
| 原 15 修后 | 15 passed，0.14s；LB08 固定拒绝，LB15 兼容保留 | [postfix](../../evidence/MOD_2026-10-21/LEGACY_BRIDGE_independent_postfix_20261021.json) |
| 两套整理兼容、同次插桩 | 529 passed，2.11s；实际收集 IB01-IB05 | [限定覆盖](../../evidence/MOD_2026-10-21/LEGACY_BRIDGE_compatibility_coverage_20261021.json) |

first SHA `6bb2395267b4462f8657fae8a49f0d59490ca18cf0baa6a09af75674f3661adc`。
postfix SHA `ec7ccd38ba153e6d0b0cd63b7bf0eb56406ac57634284fa6fca73c29e7844e7e`。
限定覆盖 SHA `49419da399476a6cc28ee9f12360014aa24d2754400744034a24880eb672abda`。

修后 32 快照与兼容 33 快照均无漂移，涵盖相关产品、两套全部 5 Python、2 合成 fixture、2 冻结矩阵和历史证据。
runner 可能按 root 的其他工作追加材料，活计划也会维护状态，二者未绑定为本次域源。
首失败与旧源码 hash 保留，没有用通过结果覆盖历史。新公开 JSON 为 UTF-8 LF；发布的 Git blob 一致性由 root 核对。

## 覆盖残余与待接线

分母仅 supplement_v2 九个产品文件：行 554/603=91.8740%，分支 151/200=75.5000%，综合 705/803=87.7958%。
legacy_bridge 单文件行 46/46、分支 26/26、综合 72/72 全覆盖；不能据此把全九文件或整个 PR 宣称 ≥90%。
逐文件执行/缺失行及分支在报告中完整保留。contracts、lifecycle、projection 等仍有未执行拒绝路径，未为数字追加案例。
2.11s 是 coverage 插桩测试时间，不是新性能测量，不与旧 benchmark 比较。

主线仍需事务内重新载入旧文档和当前来源、校验真实审阅及敏感同意、保存 operation/revision/逆操作账本，
并在真正 apply/undo 前再次校验来源撤回与并发状态。本次没有 PG、API、UI 点击、真实整理应用/撤销、外部投递或部署验证。
没有改旧指南、矩阵、测试或 Q5 分类产品；没有真实模型、网络、Git 操作。本轮到此冻结，由 root 管理提交与后续范围。
