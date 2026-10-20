# 命理技能本地资产与字段绑定契约

版本：`p8-skills-draft-2026-10-21-v2.4`。状态：本地草稿，待大脑专业审阅与主线接线。
适用入口为 `SkillLibrary.chapters`、`SkillLibrary.load` 和 `chart_skill`，没有新增 HTTP 或 Agent 工具入口。
本契约只约束仓库内五个技能包、32章和本地检查；不代表对官方 Agent Skills 最新规范的完整合规认证。

## 资产与版本

五个包为八字10章、紫微6章、西占5章、塔罗7章、跨体系日历工具4章。
每包有一个 `SKILL.md`，当前采用两个单行 frontmatter 字段 `name`、`description`。
本地检查要求它们与 `catalog.json` 一致，章节注册、文件与链接一一对应，不接受重复键或未登记章节。
这只是项目使用的有限 frontmatter 子集，不实现任意 YAML 解析器。

[skill_assets.schema.json](skill_assets.schema.json) 是目录的 JSON Schema 2020-12 本地档案。
它检查来源标题、定位、HTTPS 地址形状、问题类型、字段 Pointer、可选能力、额外根、状态和规则ID等结构。
Schema 是开发期检查；现有 loader 并未新增运行时 JSON Schema 依赖。
来源地址能通过语法检查，不等于链接在线可用、原文支持全部表述或原刊已校勘。

本次 v2.4 仅调整五份入口的依据类型说明，以及目录中的西占描述使其与现有入口相同。
32章正文、各章自身版本及文本 hash 均保留。
目录版本是本次目录装配版本，不能用它宣称32章正文均在当天重写。
单章 hash 对 Python 文本读取后的 UTF-8 内容计算，包含通用换行规范化；不是原始 CRLF 文件字节 hash。

## 字段绑定

[skill_bindings.json](skill_bindings.json) 登记32章的37组需求：32组必需字段、3组条件能力、2组额外接口。
每组都按目录声明的根解析；204次 Pointer 解析使用实际工具的严格 RFC 6901 解析器。
数组 `0` 是样例中的真实索引，不承诺某星、时段或宫位永远处在该位置。
重复键、无效 `~` 转义、负索引、前导零数组索引和根替换均有反例检查。

| 根/能力 | 样例来源 | 方法与限制 |
| --- | --- | --- |
| 八字、紫微 `CalculationArtifact` | `samples/skill-bindings/` 的原生产物 | 现有公开合成技能夹具，显式 `P8ChartAdapter.calculate`；实际平太阳方法，八字 sect2。保留旧入口方法，不当作默认真太阳主解读 |
| 只读 profile proposal | 同目录真实 bundle 经 `profile_proposal` 生成 | 分支、判断值和 actual_method 回指原生八字产物；`writes=0`，没有保存/用户确认流程 |
| 八字时基/冻结倒推章节 | 已发布 `ayuan_bazi.json` 的 time_basis 文档 | 真太阳、标准时、北京时间的原生分支，不包装成旧 Artifact；倒推仍冻结、隐藏、诚实拒绝 |
| 西占本命 | 已发布 `ayuan_astro.json` 的 calculation_bundle 内 astro Artifact | 物理 UTC 本命；它本身不是太阳回归或次限结果 |
| 显式行运、次限、回归 | 同文件中各自真实能力产物 | 只在相应 capability 被显式提供时解析；次限和回归保留具名技术，不能用本命根代替 |
| 塔罗公开牌阵 | 既有公开合成圣杯侍从 fixture，经真实 `TarotService._viewer` | 固定已揭示牌阵、实际公开序列化；不连接数据库，不重新抽牌 |
| 四个日历工具 | 已发布流日、择日、黄历、合盘样例 | 各自 `P8ToolEvidenceResult`，保持日期、人物、consent、工具和依据来源边界 |

本轮37组均有真实绑定。最初未发布的15组通过本机原生公开入口生成补齐，没有把 time_basis 伪包装成 Artifact。
新增样例全部合成，固定目标日2026-10-21；生成器为
`mingjing_core.adapters.charts.benchmarks.night28_skill_samples`，输入与实际 profiles、文件 hash 见其 manifest。
样例只有字段存在与内部绑定证据，不是外部 owner 授权、现实预测效度或主线端到端验收。
未来某组缺真实根时必须标 `unavailable`，不得为通过测试添加假的字段或将别种根静默替代。

## 依据类型

章节中的 `〔c#〕`、`〔r#〕`、`〔t#〕` 是表达格式示例，运行时须换成本轮已登记且可解析的实际别名。
八字 U12 结构 r 只对应实际 `met=true` 条件；边界/工具 r 可引用，但保留原文档、规则类型与来源，
不能混入38条八字结构规则或升级为完整成格。紫微、西占不凭文字补造 U12 结构命中。
塔罗解释以固定牌阵 t 为依据；另有真实工具 r 也不能说成牌义或新抽牌依据。

技能 loader 不核查用户资料、当前授权、撤销账本或命盘签名，也不产生计算命中。
调用方必须先验证上下文来源与 scope，再向解释层提供可引用依据；普通内容 hash 不能证明授权。
出处清单和存疑/待核说明始终保留；未取得原刊版本、页码时不补造页码。

## 上下文预算

一次仅装配一章，完整 `<技能 ...>` 块最多5500个 UTF-8 字节，包括标签及换行；超过则拒绝，不能截掉出处尾部。
这不是模型 token 实测，也不覆盖返回 JSON 的元数据、重复 text 字段或整份 Agent prompt 的其他开销。
当前最大章为八字格局5138字节，剩余362字节；完整32章清单见
[实际盘点](../evidence/P8/night28-skill-assets-inventory.json)。
专属测试分别用 ASCII、中文、四字节表情和组合字符构造恰好5500/5501字节，验证原文、来源尾部与 hash 保留。
这些是合成预算文本，不能当作真实命盘证据。

主线仍须用实际模型 tokenizer 检查最终总上下文，完成工具注册、ContextEngine 装配、KnowledgeRegistry
审阅门禁和来源授权接线。本线没有执行真实模型请求，也未声称这些主线功能已完成。

## 验证入口

本地新增测试为 `test_p8_skill_assets_contract.py`、`test_p8_skill_binding_matrix.py`、
`test_p8_skill_budget_boundary.py`；与既有 product/calendar 技能检查合计128项通过，0跳过。
具体复现命令、首轮发现、原生生成方法和边界见
[审阅证据](../evidence/P8/night28-skill-assets-review.md)。
