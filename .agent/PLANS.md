# .agent/PLANS.md —— ExecPlan 写作规范（知命明镜台 v4 版）

> 放置位置：仓库 `.agent/PLANS.md`。改编自 OpenAI Cookbook《Using PLANS.md for multi-hour problem solving》，加入本项目的验收与回执要求。
> 本文件**不是**某个计划，而是"怎么写计划"的说明。每个阶段的具体计划写在 `docs/v4/execplans/P<n>_<name>.md`。

## 什么是 ExecPlan

ExecPlan 是你（Codex）为一个阶段写的执行计划，同时也是**活的工作日志**。它必须**自包含**：一个从没见过这个仓库、也没读过任何聊天记录的新手，只拿着当前代码和这一份 ExecPlan，就能把工作继续做完并验证结果。

## 硬性要求

1. **自包含。** 不要写"见上次计划""按之前讨论的"。需要的背景、假设、文件路径都写进来。引用设计文档时写明章节（如"蓝图 §6.2"），并把关键约束复述一遍。
2. **术语首次出现时用一句白话定义。**
3. **活文档。** 下面四节必须随工作进展持续更新，不可省略：*Progress*、*Surprises & Discoveries*、*Decision Log*、*Outcomes & Retrospective*。每次修改计划，在文末"修订记录"加一行：时间、改了什么、为什么。
4. **验收写成可观察的行为**，而不是代码属性。好的例子："冻结时钟到 2026-10-10 09:00，问'今天要上班吗'，回答包含'调休'且评测 T05 通过"；坏的例子："实现了 HolidayService 类"。
5. **每个里程碑都能独立验证**，并且朝最终目标推进。原型类里程碑要标明"原型"，写清转正或丢弃的条件。
6. **步骤可重复执行（幂等）**；有风险的步骤（迁移、回填、删除）必须写回滚或重试路径。
7. **只在 Progress 用勾选清单**，其余部分用叙述性文字。
8. 计划里的命令用缩进书写（不要嵌套代码块），以免破坏外层格式。

## 模板

```md
# P<n>：<简短、动作导向的标题>

本 ExecPlan 是活文档。Progress、Surprises & Discoveries、Decision Log、Outcomes & Retrospective 四节必须随工作更新。遵循 .agent/PLANS.md。

## Purpose / Big Picture（目的与全局）
用 3–6 句话说明：做完以后，用户能做到什么以前做不到的事；怎么亲眼看到它生效。

## Progress（进度）
- [ ] (2026-10-18 10:00) 里程碑 1：……
- [x] (2026-10-18 14:20) ……（已完成）
- [ ] 里程碑 2 —— 已完成：……；剩余：……

## Surprises & Discoveries（意外发现）
- 发现：……　证据：<简短的测试输出或文件:行>　影响：……

## Decision Log（决策记录）
- 决定：……　理由：……　日期/作者：……　是否需要大脑确认：是/否

## Outcomes & Retrospective（结果与复盘）
阶段结束时写：达成了什么、没达成什么、教训、给下一阶段的建议。

## Context and Orientation（背景与定位）
当前代码状态、相关文件（完整路径）、相关设计章节、必须遵守的不变量、术语定义。

## Plan of Work（工作计划）
按里程碑叙述：每个里程碑的目标、要做的改动（文件与函数级别）、结果、证明方式。

## Concrete Steps（具体步骤）
要运行的命令（缩进书写）、在哪个目录运行、预期输出的样子。

## Validation and Acceptance（验证与验收）
逐条对应阶段提示词的验收标准：输入 → 期望的可观察输出；需要跑的测试与评测场景 ID；改动前会失败、改动后会通过的检查。

## Idempotence and Recovery（幂等与恢复）
哪些步骤可以重复执行；迁移/回填/删除的回滚与重试方法；备份要求。

## Artifacts and Notes（产物与备注）
证据文件路径（docs/v4/evidence/P<n>/…）、关键日志摘录（已脱敏）。

## Interfaces and Dependencies（接口与依赖）
新增/修改的公共接口签名、API 路由与载荷、数据库表与列、依赖包及锁文件变更、与其他阶段的接口约定。

## 修订记录
- 2026-10-18 10:00 创建。
```

## 本项目附加要求

- 计划开头的 *Context and Orientation* 必须列出本阶段要**复用**的现有函数（文件:行），以及**不允许改变**的行为契约。
- *Validation and Acceptance* 必须引用 `docs/v4/07_评测场景集.md` 中的场景 ID。
- 阶段结束时，ExecPlan 的 *Outcomes & Retrospective* 与 `AGENTS.md` §11 的阶段回执要一致。
