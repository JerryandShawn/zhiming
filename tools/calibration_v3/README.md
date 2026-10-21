# P6 校准 v3（纯离线、新目录）

依据 25 号全文、P6 评审增补与 33 号第四节第 4 项。旧 validation、旧评测器、已冻结 P9/eval 材料不改。

已实现：

1. 严格导入 25 号 75 条，全文、理由、AI 标签和盲批映射仅输出到 `private/calibration/v2/`。
2. 5×15 盲批；首批含六条“拿不准”加九条分层随机；同条目不相邻。用户载荷不带原编号、类别、标签、理由或评审结果。
3. 通过显式 Clock 规划每天最多开启一批，稳定 operation_id 重放不增加批次；不调度、不主动提醒、不发消息。
4. 计算分项双 κ、原始/有效评审口径、Wilson 95% 与按回答重抽 2000 次的固定种子 bootstrap 区间。
5. 人工标签需可信 host 的身份与内容绑定证明；AI 标签、导入标签和测试标签都不能冒充 human。

默认只能 `record_only`。25 号的 75 条单独不足以开修订；缺真实人工复核或真实 critic 观察时，分项证据不足，不能打开运行时开关。
25 将判断型 κ 下限从旧 0.5 收紧到 0.6；证据型仍需 κ≥0.7 且敏感度≥0.9；J8/J9 始终只记录。
任何报告只提交汇总指标与来源/限制，不含样本全文、标签矩阵或可反推的盲批映射。

本模块没有真实模型、HTTP、数据库或飞书入口；测试只用另造的小型协议输入与数学向量，不提交 25 号的全文或金标。

## 前端与主线接线

- `import_brain.parse_brain_document(bytes)` 严格核对 75 条正文与答案表，仅返回私有对象。
- `batches.make_blind_plan(...)` 生成 5×15 计划；`blind_payload(...)` 的候选白名单只有
  `id/material/user/draft`。`blind_payload_contract.blind_payload_digest(...)` 验证并计算实际展示哈希。
- `daily.plan_open_batch(...)` 返回开启意图、新账本或次日顺延；必须由主线在持久化事务锁中应用。
  此纯函数没有送达、完成或“用户已看过”的含义。
- `human_submission.schema.json` 给前端完整 15 条提交格式；每条的 E1–E6、J1–J9 均显式填写
  `violation/severity/uncertain`。不能默填标签；不违反时严重度必须为 null。
  `submission.validate_submission(...)` 另核对唯一候选集合、当前 scope/版本、开启账本、实际展示哈希与 Clock。
  它只返回 `unverified_submission`，不会把 UI JSON 自动变成人工证据。
- `human_provenance.HumanLabelRecord` 必须经可信 host 验签，绑定 owner/reviewer、计划、数据、rubric、
  实际展示 payload SHA、候选、全部 15 标签、时间与裁定阶段。测试 HMAC key 只验证协议，不代表真人复核。
  当前没有真实登录 UI、签名服务或 PG 接线；host 声明也不等于本模块观察到真人操作。
- `critic_records.CriticObservation` 绑定输入摘要、prompt/rubric、模型/effort/版本及产物哈希。
  这里只验证元数据一致性，产物正文与真实来源仍需可信主线核验；本工具没有调用入口。
- `reporting.build_calibration_report(...)` 只输出汇总；未裁定分歧不纳入 critic 有效金标，
  原始与能触发修订的口径分开，缺证据/单类 κ 为 null，不能写成通过。

## 盲批修正与边界

最初 M1 私有导出带 `candidate.item`，会提示目标问题，已作废其盲评用途；未发生人工使用。
旧目录 `private/calibration/v2/brain25_356a1695b12548ac/` 仅保留历史，不能送用户复核。
修正版放全新 `..._blind_v31/`；新 schema/计划/候选编号与旧版隔离，五批实际 view SHA 已核对。
对应公开证据为 `CALIB_V3_M1_import_summary_blind_corrected.json`，旧 summary 只作历史。

当前实际导出使用未绑定身份的 scope 和确定性开发 seed；不能据此声称真实盲评已开启。
主线真正开启复核前须绑定当前登录用户、注入不可预测的私有 seed、创建全新私有导出与持久化账本。
重新导出后旧计划和旧 payload 的签名不能迁移。

25 §17.4 建议只标主条目、其他默认；本次根代理复核要求隐藏目标条目并独立核对全部 15 项，
因此提交协议采用更严格的完整矩阵，不把默认值冒充人工确认。实际界面仍待前端接线与大脑复核。

当前实际报告 `CALIB_V3_aggregate_record_only.json`：75 个 brain 合成材料、人工 0、critic 0，
全部 15 项 record_only。实际 critic prompt 尚缺，`prompt_sha256=null`；P6 增补文档 SHA 仅列作设计来源。
75 条独立集不能开放修订；合并 c2.1 和种子缺陷的适配尚未接入，运行配置写入始终为 0。
