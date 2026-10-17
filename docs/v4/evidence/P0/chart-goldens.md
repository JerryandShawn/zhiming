# P0 中期复核第 4、5 条：时间定稿与命理金标

2026-10-17，依据大脑 `11_大脑复核_P0中期.md` 第 4、5 条落实。未读取密钥、调用真实模型或访问线上。

## T14 定稿

冻结时钟仍为 2026-10-17 10:30（周六），保留合成来源事实“10/21 面试”。问题改为“我这周还有什么安排吗？”。
确定性断言要求“下周”及“10月21日/10/21/21号”，禁止“这周三/本周三”。评审要点明确本周截至 10/18 周日。
回归证明正确的“下周三21号”可通过，而混入“这周三10月21日”的回答会失败。

## C03 只检查结构

不设置固定喜用神、五行或唯一流派答案。`expect.chart_structure` 独立检查有效 `〔c数字〕` 引用、
至少一种命名口径或流派、盘面依据、没有正向绝对断语、没有用规则缺口代替回答。
模型若返回 `RULE_GAP/规则缺口/尚未实现`，按原要求计失败；没有引用或依据也不能通过。

回归使用木火、金水、土等不同候选方向证明没有固定喜用答案；另覆盖缺引用、缺流派、缺依据、
“一定/注定”正向断语、单次否定与明确双重否定。此结构检查不证明某个喜用判断在术数上正确。

## C06 真实隔离计算

资料全部为设计指定的合成画像：男，1994-03-12，成都，经度 104.07、纬度 30.67、UTC+8；
时间区间为民用时间 05:50–07:10。通过现有 `ChartAdapter.calculate` 运行独立 `.venv-charts` 的 `worker.py`，
没有替换计算器，也没有从预期文本制造计算结果。

引擎使用地方平太阳时，仅经度修正，不计均时差；修正为 `(104.07 - 120) × 4 = -63.72 分钟`。
因此原回放“卯时/辰时”是错误的民用时间假设，已更正为**寅时/卯时**。

| 民用采样时刻 | 引擎显示修正时刻 | 时辰序号 | 时辰 | 命宫 | 命宫主星 |
| --- | --- | ---: | --- | --- | --- |
| 05:50 | 04:46 | 2 | 寅 | 丁丑 | 紫微、破军 |
| 06:10 | 05:06 | 3 | 卯 | 丙子 | 天机 |
| 06:30 | 05:26 | 3 | 卯 | 丙子 | 天机 |
| 06:50 | 05:46 | 3 | 卯 | 丙子 | 天机 |
| 07:10 | 06:06 | 3 | 卯 | 丙子 | 天机 |
| 06:03（边界探针） | 04:59 | 2 | 寅 | 丁丑 | 紫微、破军 |
| 06:04（边界探针） | 05:00 | 3 | 卯 | 丙子 | 天机 |

五个等距点的命宫主星不一致，`sampled_stable: false`。覆盖标识为 `sampled_not_continuous`：
这是有限采样加边界探针，不能声称完整连续区间已经穷尽，更不表示人生预测经过验证。

金标保存在 `tools/eval/fixtures/c06_ziwei_golden.yaml`，包含输入、七次观测、分支、版本和源码哈希。
`ChartGolden` 校验摘要稳定性必须由样本推导，分支必须准确覆盖实际样本；不能把金标摘要改成与观测相反的结果。
`expect.chart_stability.fixture: C06` 按此金标判分，拒绝稳定性说反、主星互换及沿用旧卯/辰假设的回答。

## 版本与重放

- py-iztro：0.1.5；pythonmonkey：1.1.0；项目引擎：ziwei-core-3.1。
- 包元数据声明上游 iztro 2.4.4，内嵌文件名却为 `py_iztro/res/iztro-2.5.0.min.js`。
  仅如实记录元数据、文件名及哈希，不把文件名当作已独立核验的上游版本。
- 内嵌 JS SHA256：`09333d6a2da7fff7bd338134c8d17de0d589259c16a70ece1db1d64e17217ea0`。
- 金标文件经 UTF-8/LF 归一后的 SHA256：`538b379313cf8bfef0d7fedc9e54be226f27cabeba3cfa5fb4fe8804e48c266b`。
- `git ls-files --eol` 已确认 `hermes/ziwei.py`、Charts adapter/worker 均为 `i/lf w/lf`，属性为 `text=auto eol=lf`。
  金标 versions 不包含绝对路径、平台名或 Python 补丁版本，包含固定包版本、包内相对文件名和源码内容哈希。

可重复生成并核对：

    .venv-core/Scripts/python.exe tools/eval/build_chart_goldens.py --chart-python .venv-charts/Scripts/python.exe --check

本机实际输出：`{"scenario": "C06", "samples": 5, "sampled_stable": false}`，退出码 0。
默认命令在实际计算后更新金标；`--check` 只比较，漂移即失败。修改引擎或版本后应复核差异，不能改预期迁就错误。

## 验证与未验证

    .venv-core/Scripts/python.exe -m pytest tests/v4/test_eval_chart_goldens.py tests/v4/test_eval_framework.py -q

结果：**73 passed，7.14 秒**。其中金标回归 25 项，含一项调用真实 Charts 隔离计算器，未跳过。
新增/修改五份 Python 文件均通过 Ruff，以及显式 `ruff format --check --line-length 120`。

    .venv-core/Scripts/python.exe tools/eval/runner.py --mode scripted --target fake --output private/p0-chart-golden-eval

结果：**Validated 80/80；Result 80/80**。本机合成报告仅供排查，统一正式报告由主任务在最终源码下重跑。
脚本成绩仍只证明评测框架；不代表 v4 Agent、真实模型或术数解释已通过。

独立外部来源的盘面交叉核对按大脑要求留到 **P8**；尚未完成，不以本次重复运行同一引擎冒充独立来源。
未修改 ExecPlan、运行时命理业务代码或模型适配器；未提交。
