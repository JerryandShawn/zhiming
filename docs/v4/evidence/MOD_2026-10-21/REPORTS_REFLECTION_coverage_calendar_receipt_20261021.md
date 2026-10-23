# 报告与反思候选：独立覆盖补测回执

北京时间 2026-10-21 08:54。仅测两个新增纯模块目录，不是整个 PR 的覆盖率，也不是主线集成、CI 或部署验收。
ExecPlan：`docs/v4/execplans/MOD_reports_reflection_coverage_calendar_20261021.md`。

## 新增行为与结果

新增两个独立测试文件，共 63 项；原有 480 项目标测试和冻结黄金不动。**543/543 首次通过，3.42 秒**。
运行前先只读分析 raw；08:47 全量冻结期间只新建计划，主线广播三轮全量结束后才写测试和启动单个目标进程。

报告侧检查重复记录/单日盘面/合成素材去重、重复身份内容变化拒绝、同文档别名换绑、未来/过期历法降级、
未类型化宿主输入、非法周期/时区/日期上界、原话时间及区间错误。
这些检查通过公开编排入口和公开输入类型触发，不访问私有状态，不为行数注入不可达对象。

反思侧检查错人物和重复抽取候选、其他线程来源、缺锚点、非用户事实、错 scope 的确认、无类型设置、未来记录、
知识缺口的旧事实/来源/asked/closed 状态、队列账本冲突、错误当前线程 cursor/后台许可、画像导入与来源身份。
检查的是拒绝或省略后的实际结果，未照抄内部原因码或通过 monkeypatch 强迫异常。

## 分目录测量

combined 定义为 `(covered_lines + covered_branches) / (num_statements + num_branches)`。
所有行与分支分母保留，未增加排除规则，也未关闭 branch。

| 范围 | 产品文件 | 行覆盖 | 分支覆盖 | combined | 旧 raw combined |
| --- | ---: | ---: | ---: | ---: | ---: |
| reports_v2 | 8 | 455/479，94.9896% | 160/188，85.1064% | **92.2039%** | 85.7571% |
| reflection_v3 | 18 | 964/1017，94.7886% | 273/322，84.7826% | **92.3824%** | 88.1255% |

两个目录分别达到 combined ≥90% 的本轮目标；分支本身仍低于 90%，不能把 combined 写成分支覆盖率。
执行的是 coverage 指向这两个产品目录的目标测试，未把全 PR 的其他模块并入或删出分母。

## 命令与证据

在仓库根目录清 provider keys、关闭追踪，TEMP/TMP 设为本树 private/mod-week/tmp，使用已有 Core 环境：

    python -m coverage run --branch --source=mingjing_core/application/reports_v2,mingjing_core/application/reflection_v3 --data-file=private/mod-week/coverage-calendar-20261021-085210 -m pytest tests/v4/reports_v2 tests/v4/reflection_v3 -q --basetemp=private/mod-week/tmp/calendar-coverage-20261021-085210
    python -m coverage json --data-file=private/mod-week/coverage-calendar-20261021-085210 -o docs/v4/evidence/MOD_2026-10-21/REPORTS_REFLECTION_coverage_calendar_20261021-085210.json

旧基线 raw：`REPORTS_REFLECTION_coverage_20261021-082526.json`，保留原文件。
新 raw：`REPORTS_REFLECTION_coverage_calendar_20261021-085210.json`。
分目录汇总、时间、全部产品/新测试 hash、旧黄金 hash 及范围：
`REPORTS_REFLECTION_coverage_calendar_boundary_20261021-085210.json`。
coverage 原始 timestamp 没有时区；本回执及 boundary 的业务记录显式用北京时间，不把东京显示直接当北京时间。

26 个产品文件的路径+NUL+正文 aggregate 与先前冻结完全相同：

- reports_v2：`6713661136b4e563b9687d37fcbd3657d7b8b93c90013aaaca2331a49f91a4d2`。
- reflection_v3：`2eee084f643e38d0e32d918e52ecc93c7ce1564558332419a94ffa3321ef390d`。

新增测试仅 `test_reports_coverage_calendar_mod.py`（148 行，最长函数 13 行）和
`test_reflection_coverage_calendar_mod.py`（206 行，最长函数 16 行）。完整函数类型、Ruff、format 与 AST 尺寸检查通过。
新测试正文复用已有显式 synthetic fixture，没有读取真实历史、盲评 B 或 75 条校准材料正文。

## 未验证与剩余边界

完整 missing_lines/missing_branches 保存在新 raw。仍有内部输出对象防御、部分冗余版本检查及少数调用方已先拒绝的分支未执行；
未为了数字调用私有函数、改产品或构造不可能从公共工作流到达的输出。
本轮没有发现产品缺陷，也没有失败后降低真值的改动。

真实模型、服务器、网络、PG、通知、队列、UI、性能与 Git 操作为零。既有产品、旧测试、黄金、接线指南和配置保持。
source/type/hash 一致不等于数据库授权或自然语言正确性；旧的未接线限制继续有效。
提交、草稿 PR、CI 和下一全量回归由主线另行记录，本回执不冒充这些检查。
