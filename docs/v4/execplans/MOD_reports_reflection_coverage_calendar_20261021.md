# 报告与反思候选：独立异常与边界补测

本 ExecPlan 是活文档。Progress、Surprises & Discoveries、Decision Log、Outcomes & Retrospective 和修订记录随工作更新。

## Purpose / Big Picture

为模块线已经新增的周/月/季报告及后台反思候选，补充真实使用边界上的异常和拒绝检查。
覆盖率用来发现未走过的行为，不替代契约，也不证明产品已上线。
目标是分别测量 reports_v2 与 reflection_v3 的行及分支合并覆盖率达到 90%；不将两个目录或整 PR 混为一个百分比。
产品、既有测试和冻结黄金不变；任何真实产品缺陷先交主线处理，保留失败。

## Context and Orientation

工作目录固定为 `C:/Users/Administrator/Documents/Codex/zhiming-v4-mod`。
实际复用的公开函数是 `application/reports_v2/compose.py:33` 的 compose_period_report、
`periods.py:11` 的 period_for、`application/reflection_v3/schedule.py:25` 的 schedule_reflection、
`work.py:23` 的 plan_reflection_work，以及 profile_renderer.py 的 render_about_me。
测试只调用这些公开边界及其公开输入类型，复用既有独立 helper；不为了覆盖内部防御行制造不可能到达的对象。

“合并覆盖率”是 `(已执行语句数 + 已执行分支数) / (全部语句数 + 全部分支数)`，同时保留行、分支分项。
本轮参考 raw 为 `docs/v4/evidence/MOD_2026-10-21/REPORTS_REFLECTION_coverage_20261021-082526.json`。
raw 的时间字段未含时区，文件名及本线记录采用北京时间；不能把主机显示的东京时间直接当北京时间。

设计约束来自 33 号第四节第 5、7 项、P5 原提示词及增补、蓝图 §6。
相关 07 评测集的记忆、检索和遗忘类约束仍受保护；本轮只运行新增单元/属性检查，未运行或重新判定该脚本场景集。
真实模型、网络、服务器、数据库、通知和 Git 操作为零。

## Progress

- [x] (2026-10-21 08:47，北京时间) 收到主线全量冻结门禁；仅只读分析和新建本计划，不改测试/产品/fixture、不运行 pytest 或性能。
- [x] (2026-10-21 08:49，北京时间) 分别汇总 raw：reports_v2 combined 85.7571%；reflection_v3 combined 88.1255%，已向主线报告拟覆盖行为。
- [x] (2026-10-21 08:49，北京时间) 主线明确广播三轮全量结束，解除冻结；随后仅新增两个 coverage_calendar 测试文件。
- [x] (2026-10-21 08:52，北京时间) 首次双目录 branch coverage 运行 543/543 通过，3.42 秒，无新增失败，无产品修复。
- [x] (2026-10-21 08:54，北京时间) 分目录最终 reports 92.2039%、reflection 92.3824% combined；源 hash 与先前冻结一致，完成 Ruff/格式/尺寸/类型检查和独立回执。

## Surprises & Discoveries

raw 共包含报告 8 个与反思 18 个 Python 源文件。报告行为主体已较充分，剩余主要是输入投影、身份冲突和象征资料重复处理。
报告行覆盖率 90.3967%，分支 73.9362%，合并 85.7571%；反思行 91.4454%，分支 77.6398%，合并 88.1255%。
仅引用行覆盖率会掩盖拒绝路径不足，故按两个目录分别报告分项及合并值。
新增 63 项真实入口检查首跑全部通过，未发现新产品缺陷。报告与反思均分别达到 combined 90% 目标，
但单独分支覆盖率仍分别为 85.1064% 与 84.7826%，不能省略此限制。

## Decision Log

2026-10-21：尊重 08:47 全量冻结门禁。主线广播结束前不写测试、helper、fixture、产品，不启动 pytest 或性能测量；计划文档是唯一允许新增的文件。

2026-10-21：保留原 reports 16+14、reflection 18 组黄金及现有 231/249 目标测试；新增文件不改旧断言。
若公开 API 的确允许两种安全结果，按契约说明选择，不根据测试失败事后降低原契约。

2026-10-21：优先测试能经公开入口触发的真实导入/恢复错误、当前来源冲突和失效行为；不逐字段照抄实现条件，
不访问私有属性、不修改产品、不用 monkeypatch 强迫不可达分支，不为提升数字覆盖错误状态的内部构造细节。

## Plan of Work

报告补测分为三类。重复输入应去重，重复身份而内容变化应整次安全拒绝；同一天的盘面资料、同一合成条目、同一记录和同文档引用别名分别验证。
非法期间、无时区时刻、不合法范围、未声明的状态/区/类别、缺失或错误类型的当前来源投影需在内容显示前拒绝。
过期、未来或时区不符的历法快照应降级，不把当前历法说成整个周期的依据。

反思补测以真实宿主投影为入口。抽取候选不能来自其他人物、重复 ID、其他线程来源，不能把旧确认用于新来源；
非用户断言、未来事实和缺锚点不能进入自动事实或画像。
已有知识缺口的来源/事实缺失、源集合改变、asked/dismissed 状态应遵守原保护；不会为了补优先级而重新发问。
队列账本冲突、源缺失、过期后台许可和当前资料依赖在实际工作前重新核对。

只新增 `tests/v4/reports_v2/test_*_coverage_calendar_mod.py`、
`tests/v4/reflection_v3/test_*_coverage_calendar_mod.py` 及必要唯一命名 helper。
正文继续从既有显式 synthetic fixture 读取；若确需新语句，只新增显式合成 fixture，保留原数据不改。
先与主线核对全量冻结已结束，再执行上述修改。

## Concrete Steps

主线放行后，在工作目录设置 TEMP/TMP 指向 private/mod-week/tmp、清 provider keys 并关闭追踪。
每次只启动一个 Python 测试进程。目标命令形状如下，实际证据另存时间戳，不覆盖旧 raw：

    <Core Python> -m coverage run --branch --source=mingjing_core/application/reports_v2,mingjing_core/application/reflection_v3 --data-file=private/mod-week/coverage-calendar-<北京时间> -m pytest tests/v4/reports_v2 tests/v4/reflection_v3 -q --basetemp=private/mod-week/tmp/calendar-coverage-<北京时间>
    <Core Python> -m coverage json --data-file=private/mod-week/coverage-calendar-<北京时间> -o docs/v4/evidence/MOD_2026-10-21/REPORTS_REFLECTION_coverage_calendar_<北京时间>.json

Core Python 为 `C:/Users/Administrator/Documents/Codex/zhiming-v4-p2/.venv-core/Scripts/python.exe`。
Ruff 使用本机已锁定环境，显式列出本轮新增文件，避免触及其他线程的测试或产品。

## Validation and Acceptance

观察输入到输出：相同记录只显示一次；同 ID/同日或同文档别名内容换绑不返回混合正文；非法投影以固定消息拒绝且不回显私密内容。
无效历法不进入报告内容，不移除仍有效的用户记录；真实来源和原话时间保持。
反思错误候选不进入事实列表；已有缺口失效不产生新优先级或问题，敏感未确认不自动保存。
所有 effects 继续为实际整数零，未执行模型、通知、队列或数据写入。

coverage 分别统计两个目录。达到 90% 的同时必须保持所有原断言与新行为检查通过；未达标照实列出缺口，不能用删分母、exclude 或禁用 branch 提升百分比。
本轮不宣称 07 评测场景、整个 PR、CI、真实模型质量、PG 或部署验收完成。

## Idempotence and Recovery

测试只创建私有合成快照，重复运行不修改真实状态。新测试失败时保留失败、记录最小合成复现，并通知主线。
产品修复须另获主线明确范围；不改黄金、既有测试或历史 coverage 文件。
若主线重新冻结全量，立即停止源编辑和新运行，先保存只读进度，不抢占测试进程。

## Artifacts and Notes

基线 raw 保留原路径不覆盖；最终新增 raw、分目录边界汇总和回执放 `docs/v4/evidence/MOD_2026-10-21/`。
新证据需注明实际北京时间、目标测试数量、源 hash、行/分支/combined 数值与真实未覆盖项。
本阶段无性能要求，不额外跑性能，不自行 Git 发布。

## Interfaces and Dependencies

不新增产品接口、数据库迁移、API、模型或依赖。现有两个输入投影与纯编排接口保持。
本轮新 helper 只负责生成公开类型的独立合成输入、读取既有公开 fixture 和提取可观察结果；不内嵌产品算法。

## Outcomes & Retrospective

完成两个新增测试文件，保留全部 480 项既有目标测试与冻结黄金；63 项新检查使目标目录合计 543 项通过。
报告 combined 由 85.7571% 至 92.2039%，反思由 88.1255% 至 92.3824%。
已逐目录核对 26 个产品文件与此前冻结 aggregate hash 完全一致，没有改代码、分母、排除配置或旧测试来提高数字。
尚未覆盖的内部输出防御、冗余来源版本分支等继续列在 raw 中，未构造不可达对象强行执行。
本轮不新增接口，无需更改已冻结接线指南；原真实 PG、模型、队列、通知及 UI 的未接线限制继续有效。

## 修订记录

- 2026-10-21 08:49，北京时间：创建自包含计划，记录双目录基线、真实行为优先级与全量冻结门禁。
- 2026-10-21 08:54，北京时间：记录放行后的首次运行与双目录覆盖率、源 hash、实际剩余边界，关闭里程碑。
