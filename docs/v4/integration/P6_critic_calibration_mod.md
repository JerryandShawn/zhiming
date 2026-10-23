# 模块线接线说明：P6 评审解析、程序裁决与校准统计

本模块只描述请求、解析已取得的文本和计算结果，不发模型/HTTP、不修订回答、不写库。
主线应在完整 P3/P6 分支中接入。夜间没有真实校准标签；**没有创建生产校准报告，也没有开启生产修订项**。

## 入口

- `critic_request.CriticMaterials`：显式投影本轮用户消息、此刻、已授权记忆/盘面/命理档案摘要、
  实际回执与初稿；构造器拒绝任意主运行字段或原始字典摘要。
- `critic.build_critic_request(materials, critic_prompt=...)`：返回独立请求描述，固定
  `role=critic`、`model=k3-256k`、`effort=high`、`new_session=true`，新建两条消息。
  主线必须传大脑 P6 增补中的 **完整 v2.0.0 提示词**；模块只校验版本开头，不替代提示词全文校验。
- `critic.parse_critic_output(raw, draft=..., evidence_ids=materials.evidence_ids)`：严格 JSON/Pydantic。
  模型不得传 verdict、severity、triggered 等字段；15 项 item/type 必须匹配，confidence 是整数 1–3。
  引句必须是初稿的真实子串；E 项证据不能为空，非空证据指针必须恰为投影中提供的白名单 ID。
  这验证的是可观察引用，不能自动证明模型对证据的语义解释正确。
- `critic.parse_attempts(already_obtained_outputs, ...)`：最多两个已取得的字符串，不启动重试；
  两次失败返回空 issues 和安全错误码。额度不足/超时可传空序列。原始输出不进入错误消息。
- `critic.compute_review(parsed, calibration=..., program_issues=..., critic_allowed=..., revisions_used=...)`：
  返回冻结 `ReviewResult`，程序查表计算 severity 与 pass/revise、none/revise/crisis。

## 结构检查接入与次数

结构检查由主线把可信程序发现显式转为 `ProgramIssue(item, quote, rule, evidence, fix_hint, resolved=False)`。
只接受 E1–E6；已经直接修好的星期等用 `resolved=True`，只记录、不重复修订。
同一个 item 的程序问题优先于评审问题，避免双计数。程序证据不需要校准；不得把模型输出
直接伪装成 `ProgramIssue`，否则会绕过校准门。

模型问题只有 severity≥3、confidence≥2、最新校准项 `revision_enabled` 时触发。
普通问题在 `revisions_used>=1` 后仅记录；E6 是唯一次数例外，仍需满足置信度与模型校准门。
程序 E6 可作为独立安全兜底。主线持久化次数、校验 lease，并执行修订/text_reset；本模块不做循环。
没有可信校准报告或其模型/effort/prompt/rubric 变化时一律 record_only；报告过期可传 `calibration_current=False`。

`critic_allowed=False` 时模型问题完全不参与裁决，信封 mode=evidence_only；程序检查仍正常工作。
confidence=1 只进 sample_queue，验收时由主线按隐私规则导出，不通知或追问用户。
`ReviewResult.as_dict()` 含引句/证据，属于受保护运行数据，不应写公共日志、PR 或追踪服务。

## 校准输入与统计

`calibration.calculate_calibration(samples, identity=..., provenance=..., defect_status=...)` 接收独立观测 ID，
每条 15 个真实布尔人工标签与评审标签（True=违反）；缺项/None 不被补成“不违反”。
标签映射会复制并冻结，重复观测 ID 和整数假布尔值被拒绝。

生产启用需全量 ≥60 条、每条 15 项均成对，大脑标注 ID 覆盖全部、用户复核 ≥15、其中随机 ≥10、
已知分歧经裁定，以及匹配的模型/effort/prompt/rubric 身份。`CalibrationProvenance` 是主线核实后的
来源声明，不是模块自行鉴定人类身份；测试中的 synthetic-test-only 声明仅验证门禁计算，不能当真实人标证据。

每项报告 TP/TN/FP/FN、正反例数、成对数、敏感度、特异度、Cohen κ、一致率及其 Wilson 95% 区间。
无正例/反例/可定义 κ 时保留 null，不伪造满分。macro-F1 是 15 项各自“违反”正类 F1 的等权平均，
只有全 15 项成对且 F1 都可定义时给出；否则 null，并报告 macro_defined_items。
完整 v1 的 20 条可以计算历史统计，但不足 60 条不能启用生产项。

E1–E6 的门槛为 κ≥0.7 且敏感度≥0.9；J1–J7 正反例各≥5 且 κ≥0.5；J8/J9 永远 record_only。
`defect_status[item]=False` 将种子缺陷/宽松度失败项降级。未提供真实缺陷结果不代表已验证通过；
主线仍需按 P6 增补完成导出、真实标注/复核、种子缺陷、宽松度和报告，不能仅凭单元测试上线。

## 主线需要改的已有位置

1. Agent finalize：取得已授权材料并投影，调用额度守卫决定 full/evidence_only；所有物理请求仍走主线唯一守卫。
2. v2 critic 提示词与配置：同步完整版本，固定 high 与 k3-256k，配置默认未校准为 record_only。
3. 校准导入/报告：加载真实 labels-v2、用户复核及裁定，绑定确切模型与提示版本，导出 15 项报告。
4. 修订与事件：保存计数/安全状态、最多一次普通修订、危机例外、text_reset 与 review 元数据；始终交付初稿或修订稿。
5. 评测/前端：接种子缺陷及配对统计、只读复核状态；模块线没有改 runner、旧校验器或现有运行入口。

## 离线证据

`test_critic_mod.py`、`test_critic_policy_mod.py`、`test_calibration_mod.py`：446 项通过。
包括完整 15×3 置信×2 校准状态×3 次数表、程序证据/危机/额度门、独立请求、严格引用与
非法 Unicode/大整数/深层 JSON 的安全失败开放，以及手算 κ/Wilson/缺标签/来源和身份变化。
所有测试均无真实模型请求；未验证真实评审质量、真实校准、持久化或 Agent 接线。
