# MOD-EVAL-v2.3 阶段回执

- 分支 / 最后提交：沿 root 的 `v4/mod-organize`；提交号待 root 审查提交后登记，本执行者未作 Git 写操作；PR #10 保持草稿。
- ExecPlan：`docs/v4/execplans/MOD_EVAL_MATERIAL_V23_20261021.md`。

## 完成了什么

- [x] 19 号 52 条 + P5b SP01–SP07，共 59 条独立合成材料，189 条显式断言。
- [x] 严格 casebook / observation schema、SHA manifest、重复键/非有限数拒绝，不改旧契约或 runner。
- [x] 缺失/空观察不能通过，caller 不能改 gold 或擅自解除固定阻塞；scope 与时区显式绑定。
- [x] RT05–RT08/RT10 仅材料；PR02 blocked_decision、PR06/J02 blocked_dependency；CR04 仅 2025；校准 record_only。
- [x] 112 项检查器目标测试通过（来源更正后 0.54 秒），Ruff/format/AST 通过。
- [ ] 59 条产品实际脚本运行、人工要点评审与主线接线尚未执行。

## 评测分数

这不是产品评分报告。无实际观察时：51 unverified、1 blocked_decision、7 blocked_dependency、0 observed_pass。
112 项是材料加载器/检查器的合成单测，不能当成 59 个产品场景通过。

```text
python -m pytest tests/v4/eval_material_v23 -q --basetemp=private/mod-week/tmp/eval-material-v23-truth-corrected
python -m tools.eval_material_v23 --output docs/v4/evidence/MOD_2026-10-21/EVAL_V23_material_readiness_truth_corrected.json
ruff check --line-length 120 --select E,F,I,B,UP,SIM tools/eval_material_v23 tests/v4/eval_material_v23
ruff format --check --line-length 120 tools/eval_material_v23 tests/v4/eval_material_v23
```

最终 readiness：`EVAL_V23_material_readiness_truth_corrected.json`，SHA256：
`0f9fa1192e073b8ea1029b58b6538a0caaaf7177d3d8b2497873e1e644dfd26e`。

## 改了哪些关键文件

- 新目录 `tools/eval_material_v23/`：59 条 YAML 材料、2 schemas、manifest、loader、observer、readiness CLI。
- 新目录 `tests/v4/eval_material_v23/`：112 项离线反例/完整性/观察检查及网络禁用 fixture。
- 新计划与本证据目录；没有旧源码/测试修改。

材料 SHA256：`8aeee2948e3a0221ba127c69921ad436fb0166e85759655926de75999d071e21`。
manifest SHA256：`fbb79ebe460536b64b0f63d033f97497f58ebd2aa2192dca1d8baa25af65e81a`。

## 数据库迁移与回滚方式

无迁移，不读写数据库。主线尚未接入，新材料不影响现有运行；回滚只需停止显式使用新入口。

## 偏离设计的地方及理由

采用 JSON-compatible YAML 1.2 子集以保持无新依赖；材料仍为合法 YAML。
将人工要点也要求为独立观察，整体观察通过口径比关键词命中保守；不修改原评测契约评分。

## 未验证 / 已知风险

- 模型、真实 PG、HTTP/飞书、服务器、实际产品运行与人工标签均未验证，真实请求 0。
- 没有真实脚本观察适配器；setup 与步骤仍由主线按契约装载，不是旧 runner 即插即用的改版。
- artifact SHA 与 scope 只核对给定观察一致性，不认证数据库或人工身份。
- 局部否定词法检查不覆盖所有自然语言表达，须保留人工复核。
- 没有运行全量或覆盖复测；未读取 Q5 B。

## 需要用户或大脑决定的问题

25 号 §16 已提供 J02 的20条 brain 样本/标签，manifest 已加入该来源 SHA；当前仅私有导出与可信观察适配未接，且 brain 标签不等于 human 批准。J02 保持依赖阻塞。PR02 的 D4 冲突和 PR06 前置条件也保持阻塞，不等待离线用户。

07:34 readiness 与 `_final` 原始报告保留为历史，其“脑20答案/标签尚缺”是错误事实；本 truth-corrected 报告取代它们，不覆盖历史。

## 建议后续

主线显式接脚本观察适配器后分阶段跑确定性断言，再补人工要点评审。按各契约分别报告，不与 v2.1/v2.2 直接相减。
