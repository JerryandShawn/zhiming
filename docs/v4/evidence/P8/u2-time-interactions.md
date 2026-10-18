# U2 时间交互表：独立计算模块与验证

2026-10-18。仅修改命理线目录，测试用公开日历日期和合成出生资料；未启动服务、未连接数据库、未调用真实模型、未改 v3 引擎或默认适配器。接入 P8 worker 与引用特征由命理线主代理完成，本说明不把独立函数测试说成 Agent 端到端验收。

## 接口与结果

`charts/interactions_bazi.py::bazi_interactions(natal, layers, *, hidden_stems=None)` 接收完整四柱（`year/month/day/hour`）及明确选定的 `decadal/yearly/monthly/daily` 干支。干支时间层的选取由调用方按真实节界和大运表完成，函数不自行从公历年猜流年。选用具名司令法后，调用方可传入完整十二支藏干映射；默认仅沿用现有表，不修改该表。

结果含 `nodes`（柱身份、干支、明藏十神）和 `relations`（稳定 ID、关系种类、具体参与柱）。五合、六合、冲、害、破逐对保留；相克另有 `source/target` 方向。三合、三会、三刑完整/不完整分列，至少需要两个不同支；缺失成员列在 `missing_branches`，从不补入原局。重复支保留不同柱身份，辰午酉亥自刑只在两个不同柱间列出。三刑另保留方向。所有行 `transformation_established=false`，不输出吉凶权重或合化成立。

`charts/interactions_ziwei.py::yearly_mutagen_links(data)` 从真实 `horoscope.yearly.mutagen` 与十二宫主辅星位置重算禄权科忌落宫，同时保存本命宫和流年宫。缺星或重复星显式返回 `missing/ambiguous`，不猜宫。指针 `star_pointer` 指向输入产物实际宫对象。它复用已安装 py-iztro 的运限，不表示已经实现独立四化飞宫。

`charts/interactions_transits.py::transit_windows(natal_longitudes, start_at, end_at, *, moving_bodies, orb=2, step_hours=1)` 仅在 Charts 环境按需加载 Swiss Ephemeris。输入区间必须带时区，最多366日，支持原有十个天体、0/60/90/120/180度主要相位。显式请求 Moshier/速度，记录并核验真实返回 flags，不接受静默换历表。输出每次窗口的入相点、精确点列表、出相点及分阶段区间；区间已截断时入/出相点为 null，另有 `start_clipped/end_clipped`。用速度变号驻点细分区间，保留逆行多次经过。

2秒是数值求根最终括区间，不能解释成天文历表或民用UTC也准确到2秒。有限采样并非数学穷尽证明；切触或极短窗口仍可能遗漏。没有推运、太阳回归和事件预测功能。函数不做宫位计算，也不触碰既有高纬 Placidus 失败行为。

## 验证结果

Core 执行 `pytest tests/v4/test_p8_u2_interactions.py -q`：26 passed。该套内嵌真实 Charts 子进程，子进程5个 unittest 全部通过、0跳过；这5项已包含在桥接测试中，不重复计入 Core 的26项。

原生检查包括：100种明干十神对照已安装 lunar-python；合成盘流年四化四星的实际宫位索引逐一核对；2026春分太阳零黄经日期对照香港天文台日期表；月亮6小时网格与1小时网格的窗口边界差不超过3秒；2026年10月至12月水星逆行对225度固定参考点保留3次精确经过。后两项是数值/网格自洽检查，不是独立天文学引擎交叉验证。

负例覆盖非法干支、缺失藏干表、缺支不补盘、重复星不猜宫、360度绕回、窗口截断无伪造精确点、有限黄经拒绝及驻点多次经过。Ruff E/F/I/B/UP/SIM（行长120）及默认 Ruff format 检查通过；新文件均不超过400行、函数不超过60行。v3 三个 Hermes 引擎、旧 `adapter.py/worker.py` 相对当前 HEAD 归一化换行后的内容未改变。

证据：`u2-validation.json`、`u2-pytest.txt`、`u2-native.txt`、`u2-ruff.txt`、`u2-format.txt`。全部为本次命令实际输出，未运行真实模型、完整 Core/数据库套件或浏览器验收。

## 出处与待补核对

| 范围 | 已读取出处 | 边界 |
| --- | --- | --- |
| 五合、六合、三合、六害、三刑、冲 | [《三命通会》卷二](https://zh.wikisource.org/wiki/三命通會/卷二)：对应原文章节 | 网络公版转录，未逐字核原刊影印本；不引入古籍的人生断语。 |
| 三会概念 | [《滴天髓辑要·方局论》](https://zh.wikisource.org/zh/滴天髓)：同方与三合分列 | 当前四组及六破表仍明确标项目结构口径，未完成全部配对的原刊出处校勘。 |
| 紫微运限 API | [iztro 官方 horoscope 文档](https://docs.iztro.com/posts/horoscope) | 安装版本的真实运限输出是计算事实；未宣称与最新上游版本独立等同。 |
| 行运求黄经 | [Swiss Ephemeris 官方程序文档 §3.1](https://www.astro.com/swisseph/swephprg.htm)：`calc_ut`、UT、黄经与速度 | 统一2度容许度、网格与求根阈值为项目口径。 |
| 太阳零黄经日期 | [香港天文台2026年公历农历对照表](https://www.hko.gov.hk/en/gts/time/calendar/pdf/files/2026e.pdf) | 只对照春分日期2026-03-20，没有宣称独立分钟级时刻核对。 |

需要大脑后续复核：六破与三会表的原刊定位、相刑/不完整组的名称和解释用语。相关计算已有可追溯项目口径标志，不把此待补项目隐藏成专家审核通过；后续修订需升知识表版本，不能重写旧产物。
