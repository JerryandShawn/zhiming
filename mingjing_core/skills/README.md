# 命理解释技能草稿

这是产品数据目录，不安装到个人或系统 Codex 技能。四个基础体系与跨体系 `calendar-tools` 的 `SKILL.md` 使用 Agent Skills
开放格式的 `name`、`description` frontmatter；章节正文按需读取。规范来源：
[Agent Skills specification](https://agentskills.io/specification)。

`SkillLibrary().chapters(system)` 只返回章节元数据；`chart_skill(system, topic)` 返回单章、版本、
内容哈希、字段需求和 `<技能 ...>` 上下文块。目录只允许已注册体系/主题，拒绝目录穿越，
不执行章节中的代码，不读取出生资料，不连接模型、数据库、存储或网络。

每次返回完整上下文的 UTF-8 长度最多 5,500 字节，作为低于 6k tokens 的保守代理预算；
这不是 Kimi 或任一模型 tokenizer 的实测 token 数，也不是任意 tokenizer 的数学保证。
主线真正接线时必须在模型适配层使用实际 tokenizer 再检查预算；当前没有接入 Agent 工具或生产入口。

JSON Pointer 对完整 `CalculationArtifact` 使用 `/data/...`；数组索引示范用 `0`，不是保证某颗星
或某一时段固定处于第 0 项。塔罗路径相对于 `TarotService.get_for_reading` 返回的公开牌阵对象。
`required_fields` 只登记代码已有结构；`pending_fields` 记录设计需要但本次尚未核验的接线，
不能当作已获得的依据。别名 `〔c1〕` / `〔t1〕` 都是表达示范，运行时只能使用本轮实际分配的别名。

古籍链接是公开转录或扫描资料，不代表完成原刊校勘。采用白话原创概括；没有复制整段现代著作。
传统断语中的恐吓、阶层/性别成见、疾病和死亡预测均不沿用；相应边界是项目决定，不能归给原典。
U3只读profile_proposal已生成带计算revision、分支、方法、字段依据与改判理由的版本化提案；数据库保存/确认流程由主线接入。conditional_fields只在显式请求相应可选计算能力时要求，additional_interfaces属于不同根对象，不能与CalculationArtifact混用。

28号新增四章归 `calendar-tools`：流日、择日、黄历、合盘。其根对象是独立的
`P8ToolEvidenceResult`，只引用本轮工具输出的真实c/r别名；不能沿用另一日期或另一人物的短别名。
基础28章保留，总数32章；目录版本v2.3不表示旧章节原文也被重写。
