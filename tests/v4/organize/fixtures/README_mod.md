# P5b A 独立合成历史与标注说明

本目录所有正文、对象、时间和关系均为虚构，没有生产数据。用途是验证本地纯计算整理模块；
没有调用模型、向量服务、服务器或外部传输。

## 真值如何形成

先按 22 号文档的 7 个区确定 16 个生活话题和主诉，再逐题编写 15 种自然措辞；主区、话题、
副区和明确性由这份提纲预先指定。生成程序只负责把这些已标注问答排入 30 天、编号和时间戳，
**不导入、不运行、不读取分类器的输出**。`history_600_authoring.json` 保留了独立编写的主题与措辞。
这是一份人工式编写的合成真值，不是多人盲标语料，也没有人工一致性研究。

主区按当前要解决的事确定，而不是见到一个家庭/健康词就改区。例如：

- 母亲住院，当前安排家人陪护 → `family/mother_care`，副区 `wellbeing`。
- 因母亲住院而选择少出差岗位，当前比较工作 → `career/job_search`，副区 `family`。
- 因项目焦虑而失眠，当前关注恢复睡眠 → `wellbeing/sleep_routine`，副区 `career`。
- 和家人选房意见不同，但当前计算首付上限 → `finance/home_purchase`，副区 `family`。
- 命理知识学习归 `metaphysics`；睡不着时拒绝继续抽牌、转谈睡前习惯归 `wellbeing`。
- 家常烹饪和小说阅读是有明确内容的日常话题，`clear_assignment=true`；只有告别、停顿、
  未组织好的感受等归日常待确认，`clear_assignment=false`，不用于明确片段分类准确率。

助手的标注继承紧接着的用户主诉；60% 的明确助手答复只用“这件事/刚才说的事”等承接，
没有重复主题标题。不能把这些助手单句当成独立分类题。每个问答对是一个真值片段；
片段之间是语义话题变化或明确的结束/转折，每天结束至次日相隔超过 6 小时。
同一主题每隔两天重访，不因日期不同就创建新真值主题。

## 构成与字段

固定 600 条，300 user + 300 assistant，UTC 日期 2026-09-01 至 2026-09-30（30 天）；
各日 20 条，300 个问答片段；480 条明确归属，120 条模糊待确认；44 条有副区。
有 306 种不同正文：240 个不同明确问题、30 个轮换的模糊转折句、36 种承接答复。
助手答复有意复用，模拟会话衔接；这种复用是合成数据的局限，不能据此主张现实泛化能力。

| 主区 | 全部消息 | 明确消息 | 明确主题 |
| --- | ---: | ---: | --- |
| career | 90 | 90 | job_search / exam_plan / project_delivery |
| relationships | 60 | 60 | partner_talk / friend_boundary |
| family | 60 | 60 | mother_care / household_tasks |
| wellbeing | 60 | 60 | sleep_routine / walking_plan |
| finance | 90 | 90 | monthly_budget / home_purchase / emergency_fund |
| metaphysics | 60 | 60 | bazi_learning / ziwei_learning |
| daily | 180 | 60 | home_cooking / novel_reading |

每个明确主题 30 条消息，跨 15 次访问；额外 `daily_uncertain` 是未明确话题的评测桶，
不是要求运行时把所有模糊对话永久合并成一个主题。

每条记录有：`id`、`role`、`content`、`at_ms`（UTC epoch 毫秒）、
`owner_id=synthetic-owner`、`subject_id=synthetic-subject`、`expected_space`、`expected_topic`、
`clear_assignment`，另有 `expected_segment` 和 `expected_secondary`（无则 null）。

## 评测口径

1. 运行分类器时只输入原始消息字段；不得把 `expected_*`、`clear_assignment` 或文件中的主题提纲
   作为向量、规则、路由或聚类特征。分类器也不应按日期或固定轮次位置猜标签。
2. 按 `expected_segment` 将片段真值与引擎切段结果对齐，注明错切/合并如何计分，避免只挑预测成功的片段。
   若使用消息展开后的结果，也要明确写“消息级”，不能冒称独立的片段级准确率。
3. 明确片段分类准确率门槛 85%；把握度低的预测必须 `needs_review`，
   即使它碰巧猜中日常也不能豁免。单独报告 120 条模糊样本的待审率。
4. ARI 对全部供入记录计算，簇名称可以不同。另报“明确项 ARI”有助于分析真实话题聚类。
   不得悄悄排除 `daily_uncertain` 后把明确项分数称作全部分数，也不得凭其默认大桶刷高 ARI。
5. 指标模块的 `evaluate_assignments` 默认对所有项计算 ARI，分类准确率只取明确项。
   `low_confidence` 应传入**预测的**低把握标志；未提供时只把人工标为模糊的项作为最低待审集合，
   不能据此宣称覆盖了模型所有低把握预测。
6. 单独验证同话题连续 10 轮粘性、应用后撤销逐字段相等，以及 600 条完整整理 ≤60 秒；
   本语料和度量模块本身不会证明这些引擎验收项。

`classification_accuracy` 没有明确项时抛 ValueError，防止空集被当成通过；
ARI 的空集/单项及等价退化分区定义为 1，报告必须同时保留样本计数。
ARI 采用精确整数计数与 Fraction 机会校正，允许负分，长度不一致直接拒绝，避免 zip 静默截断。

## 重建与验证

在仓库根目录运行：

```powershell
python tests/v4/organize/fixtures/build_history_600_mod.py
python -m pytest tests/v4/organize/test_metrics_mod.py -q
python -m ruff check --select E,F,I,B,UP,SIM --line-length 120 mingjing_core/organize/metrics.py tests/v4/organize/test_metrics_mod.py tests/v4/organize/fixtures/build_history_600_mod.py
python -m ruff format --check --line-length 120 mingjing_core/organize/metrics.py tests/v4/organize/test_metrics_mod.py tests/v4/organize/fixtures/build_history_600_mod.py
```

2026-10-18 本地验证：18 项测试通过（含 100 组独立逐对枚举 ARI 对照、标签置换/顺序不变、
100000 项无溢出、长度/空集/漏审拒绝及完整语料计数）；完整 600 条的指标计算 1000 次共
0.1668 秒，平均约 0.167 毫秒/次。该计时**仅是指标计算**，不是引擎整理耗时。

`history_600.json` SHA-256：
`8a549b84f5ebeec8dc4baa42313f458491243f20c704de56af82150f51a2b5b7`。

所有测试都使用纯内存输入；尚未在这里验证真实 ONNX 推理、持久化、API、人工审阅界面或现实用户数据。
