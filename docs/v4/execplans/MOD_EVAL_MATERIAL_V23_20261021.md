# MOD：v2.3 候选评测材料 ExecPlan

## Purpose / Scope

按 33 号第四节第 3 项，将 19 号 52 条与 P5b SP01–SP07 转成独立材料，提供完整性、格式与显式离线观察断言。
仅新增 `tools/eval_material_v23/**`、`tests/v4/eval_material_v23/**` 及本计划/证据。
旧 v2.1/v2.2、旧 runner、产品代码和数据库均不改；不执行模型、服务器或业务请求。

## Progress

- [x] (2026-10-21 07:28 +08) 恢复续作，完整核对 33 号公共规则/模块线、19 号全文与 P5b 全文。
- [x] (2026-10-21 07:31 +08) 落 59 条材料、189 条显式断言、两份 strict schema 与来源/文件 SHA manifest。
- [x] (2026-10-21 07:34 +08) 首轮 107 项、加入报告后 109 项目标测试通过；只用合成观察。
- [x] (2026-10-21 07:36 +08) 加入 load 后改 gold/解除阻塞拒绝，112 项通过；Ruff/format/AST 通过。
- [x] (2026-10-21 07:36 +08) 最终 readiness：51 未验证、1 决定阻塞、7 依赖阻塞、0 observed_pass。
- [x] (2026-10-21 07:44 +08) 更正 J02 来源事实，manifest 严格纳入25号第四份 source SHA；112项重新通过，新增 truth-corrected 报告，旧报告保留历史。
- [ ] root 统一审查、提交与推送；本执行者未作 Git 写操作。
- [ ] 主线后续提供实际脚本观察适配器与独立人工评审；59 条产品验收尚未运行。

## Surprises & Discoveries

19 的 PR02 仍要求连续使用提醒，但用户 D4 已明确关闭。保留原意图，标为 blocked_decision；PR06 依赖该前提，标为 blocked_dependency。
事实更正：25 号 §16 已提供 J02 的 20 条 brain 样本与标签；当前未接私有导出与可信观察适配，并非脑材料缺失。
brain 标签不能当作 human 批准，J02 仍为依赖阻塞。RT05–RT08/RT10 仅材料，不执行冻结的倒推流程。
CR04 的 E2 只允许 2025；J01/J02 没有已复核人工标签时保持 record_only。
caller 在 loader 返回后改 gold 或 availability 可绕普通 dict 检查，故 observer 绑定只读进程内材料登记，拒绝与载入版本不符的 case。

## Decision Log

- YAML 文件采用 JSON-compatible YAML 1.2 子集；仍为合法 YAML，使用已有 JSON 解析与 jsonschema，拒绝重复键、非有限数和额外字段，不新增依赖。
- `observed_pass` 只指传入的离线观察满足材料。缺失、None、空正文未验证；显式完整空工具轨迹可证明没有调用，不等同“缺证据”。
- 工具、DB、context、meta、事件、离线报告、文本、人工要点分型。语气要点也需显式 manual_annotation，不能仅凭关键词冒充人工评审。
- scope 绑定 owner/subject/thread/run，时刻必须 aware；artifact SHA 仅绑定传入字段，不宣称已读取或认证外部证据文件、PG 或人工身份。
- 文本词语支持局部否定与数字边界，保留其词法能力边界，不冒充完整中文语义判定。
- 07:34 readiness 和后续 `_final` 保留为历史；两者的“脑20材料尚缺”描述有误，已被 truth-corrected 新报告取代。02–07 的额度错误空档不记为开发。

## Outcomes & Retrospective

59 条材料、189 断言与格式/观察守卫已形成可审结果。112 项检查器单测通过不表示 59 个产品场景通过。
原始命令与范围见阶段回执；最终材料 SHA 为 `8aeee2948e3a0221ba127c69921ad436fb0166e85759655926de75999d071e21`。
没有真实模型/PG/HTTP/飞书/服务器请求，没有读取 Q5 B 正文，没有全量或覆盖复测。

## Interfaces / Validation

- `loader.load_materials(root=ROOT)`：严格读取新目录的 manifest、合法 YAML 子集与 schema；返回 59 个 case。
- `observe.evaluate_observation(case, observation=None)`：检查已绑定材料与显式观察，返回不可变 CaseEvaluation；无执行副作用。
- `report.build_readiness(cases, clock=...)`：纯报告；Clock 必须 aware，记录用北京时间。
- `python -m tools.eval_material_v23 --output <new_workspace_file>`：只写一个新 readiness 文件，拒绝覆盖或工作区外路径。
