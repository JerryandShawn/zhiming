# 明镜 Core 计算适配

`ChartsAdapter(owner_user_id, python=None, runner=None).run(archive, date, requested_systems, revision, subject)` 返回计算产物、逐字段特征、计算口径、出生时间分支和分类错误。兼容名称 `ChartAdapter` 和方法 `calculate`。生产默认在 `CHART_PYTHON` 指定的隔离解释器中执行 `worker.py`。只复用 `hermes/bazi.py`、`ziwei.py`、`astro.py` 的纯计算，不调用旧 Agent、档案存储、模型、渠道或投递。嵌套 JSON 中的 NaN/Infinity/非JSON值在契约、适配器和进程边界均拒绝。

产物是确定性计算观察，不是现实事实或预测。特征使用 `bazi.pillars@分支ID` 等稳定标识。`path` 是对完整 `artifacts[artifact_id]` 的 JSON Pointer，例如 `/data/pillars`；特征中保存完全相同的值。所有产物、特征、口径和分支都具有 owner、subject 和资料 revision。实际解释仍须知识规则和声明校验。

## 输入与边界

资料形状沿用 `archive.user.birth`；可提供显式 `archive.owner_user_id`、`subject_id`，不匹配时在计算前阻止。服务必须先授权获得此档案；此适配器不负责把匿名档案猜成某个人。经纬度、出生当时 UTC 偏移和八字/紫微所需性别参数不自动补值，不自动猜夏令时，不把阴历日期当作阳历。

出生精度支持 `birth.time_precision`，也接受 `birth.time.precision`：

| 精度 | 输入 | 实际行为 |
| --- | --- | --- |
| exact | `solar_datetime` 到分钟 | 一个明确输入瞬间；不等于自动认证用户资料 |
| approximate | 中心时刻和 `time_uncertainty_minutes` | 下界、中心、上界三个点 |
| interval | `time_interval.start/end` | 最多五个等距点，范围不超过48小时 |
| unknown | `solar_date` 或旧资料明确的出生日期 | 00/06/12/18/23时五个候选点，全部未确认 |

后三种是有限采样，`coverage=sampled_not_continuous`。`sampled_stable` 仅表示所有成功采样点值相同，不证明区间完整稳定；有失败分支时不会标记采样内稳定。未知时刻的中午点从不写回 `solar_datetime` 或升级成已确认出生。只给日期不能按 exact 补成午夜；非零秒不静默截断。精确时刻与非零误差同时声明时返回缺输入错误。

## 实际口径与未支持项

- 八字保留 lunar-python 计算：真实瞬间转换到 UTC+8 节气表决定年/月柱和起运；地方平太阳时决定日/时柱，不计均时差；日界 sect=2，起运 sect=1。藏干和十神从安装库的 `LunarUtil` 表读取。原始干支关系只计算六冲、六合、天干五合，不宣布合化成立。旧五行计数喜用神被移出可解释特征；完整旺衰、格局、调候和用神判断尚无计算覆盖。目标日是 UTC+8 正午快照；`target_month`/`target_year` 另保存该快照所在的真实交节/立春区间。年度列表以目标日期的公历年生成，不读取主机当前年。流月列表中公历月15日样本与其实际交节区间不混称。
- 紫微保留 py-iztro 的 `by_solar` 默认配置，记录时辰序号、默认参数、闰月处理、包装库版本及内嵌 JS 哈希。`topic_palace` 是一个真实主题宫对象，包含两个三合宫及对宫完整内容；`palaces` 另保留12宫。`archive.calculation_topic` 选择结构视角：general/decision/terminology→命宫、career/study→官禄、relationships→夫妻、finance→财帛、family→父母、home→田宅、health→疾厄、personal_growth→福德；education显式归一为study。无法找到唯一真实宫则报错。主题映射不宣布现实事件。本命、大限、流年、流月、流日的特征时间层分别保存。
- 西占保留 Moshier、热带黄道、Placidus；民用时间减显式 UTC 偏移，不再作地方太阳时修正。十个天体本命与行运分别保存实际返回 flags 和 fallback。相位限定0/60/90/120/180度，本命统一6度、行运2度，并按黄经差复核角度和 orb。行运只解释目标日 UTC+8 12时快照；未计算精确入/出相、太阳弧、次限或连续区间应期。高纬 Placidus 失败显式返回错误，未静默替换为另一宫制。

计算 profile 同时记录 requested_method、actual_method、库版本、脚本/适配器 SHA、fallback 和 warnings。知识流派 ID 是解释规则包标识，不冒充计算库对传统流派的完整实现。

## 版本与许可

[py-iztro 0.1.5 官方发行说明](https://pypi.org/project/py-iztro/0.1.5/) 声明基于 iztro 2.4.4。运行时从安装发行说明提取这个声明，并记录内嵌代码哈希；没有把独立上游版本核验或与最新 iztro 等同宣称为已完成。未知元数据仍明确未核验。

[Swiss Ephemeris 官方许可证](https://github.com/aloistr/swisseph/blob/master/LICENSE) 提供 AGPL/Professional 条款；[pyswisseph 包装库许可证](https://github.com/astrorigin/pyswisseph/blob/master/LICENSE.txt) 需单独对应使用方式。Moshier 不自动免除许可要求。项目所有者已在本次执行中确认具备私人使用许可；部署授权按该用户声明记录，不将计算测试写成许可证合同的独立核验。代码未购买许可、未公开仓库。

## 验证

隔离 CPython 3.11 安装 `requirements-charts.lock`，设置 `CHART_PYTHON` 为该环境解释器，运行：

```sh
python -X utf8 tools/verify_core_calculators.py --output core-calculation-validation.json
```

2026-10-11 Windows CPython 3.11.16 已实际验证59项通过、零跳过（22项chart、20项knowledge、17项新增边界）。包括真实四柱向量、同一瞬间不同时区、立春前后、子时sect=2、完整紫微12宫和四时间层、真实西占返回flags、高纬显式失败、全部14条排盘知识规则、冻结塔罗78×2方向和伪造拒绝。此验证不调用模型、数据库或渠道，不代表模型表达或生产部署已通过。
