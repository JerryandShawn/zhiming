# v2.3 候选评测材料（独立目录）

本目录承接 33 号模块线第 3 项：19 号的 52 条与 P5b 的 SP01–SP07，共 59 条。
仅生成合成材料、严格格式和离线观察断言；不改 v2.1/v2.2、旧 runner 或产品入口。
材料完整、格式通过、合成观察通过分别记录，均不表示产品场景已经通过。

计划公开入口：`load_materials()` 验证清单与 SHA 后载入；
`evaluate_observation(case, observation)` 只核对显式离线观察，不调用模型、工具、数据库或服务。
缺失或空证据不得给 pass。语气要点单列，不能用关键词命中冒充人工评审。

固定约束：

- RT05–RT08、RT10 仅保存材料，阻塞于校正功能冻结/所需生成器与记录；不执行校正。
- 用户 D4 关闭使用提醒：PR02 为 `blocked_decision`；依赖它的 PR06 为 `blocked_dependency`。
- 25 号 §16 已提供 J02 的 20 条 brain 样本/标签；私有导出与可信观察适配未接：`blocked_dependency`。
  brain 标签不等于 human 批准；没有真实人工复核仍保持 record_only。
- CR04 的 E2 范围仅 2025 年；未经证据核对不宣称统计验收。
- J01/J02 保持 record_only；没有人工复核不启用评审修订。
- 默认冻结时钟 2026-10-17 10:30 +08；所有画像和历史均为明确合成资料。

已交付 59 条逐项材料与 189 条显式断言、两份 JSON Schema、来源/内容 SHA 清单、纯观察检查器。
`scenarios.v23.yaml` 使用 JSON-compatible YAML 1.2，避免添加解析依赖；加载器拒绝重复键和非有限数。
`observed_pass` 只表示给定离线观察符合材料，绝不等同产品验收；语气要点也需要显式人工观察。
观察必须带同 case 的 owner/subject/thread/run、aware 时刻、类别与 artifact SHA；未知字段、重复路径拒绝。
检查器不认证数据库或人工身份，artifact SHA 也不等于本工具已读过或验证了外部证据文件。
已加载材料的策略和期望不可由调用者改写，固定阻塞不接受 observation 充当批准。

```text
python -m tools.eval_material_v23 --output docs/v4/evidence/MOD_2026-10-21/<new_report>.json
python -m pytest tests/v4/eval_material_v23 -q
```

无观察报告固定为 51 条未验证、1 条决定阻塞、7 条依赖阻塞、0 条观察通过。
后续接线仍需主线提供真实脚本观察适配器（仅替身模型，不是本目录自动执行），并单独评审语气要点。
词语否定识别仅覆盖保守的局部形式，不能当作完整中文语义判断。
