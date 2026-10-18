# E2 当前入口：v2 C0-C4 离线请求计划

当前推荐 `protocol_v2.py` / `scripted_v2.py`。下方 v1 三配置说明仅为历史兼容，已弃用，
旧评测证据保留原样。v2 只用脚本替身，没有模型客户端、真实专科 Agent、别名注册或生产接线。

```powershell
$env:LANGSMITH_TRACING='false'
$env:KIMI_API_KEY=''; $env:OPENAI_API_KEY=''; $env:DEEPSEEK_API_KEY=''
python -m mingjing_core.adapters.charts.benchmarks.scripted_v2 `
  --chart-python '<Charts Python 的绝对路径>' --shuffle-options `
  --output docs/v4/evidence/P8/e2-v2-scripted-2026-10-18.json
```

`--shuffle-options` 默认开启；v2 固定随机化，每道题按相同 seed / trial 在各配置中使用相同
选项重排，再把返回字母反向映射到原标签评分。API 支持 1 轮，或 5 轮至少 3 轮正确。
BaziQA 按命主延续五题会话，不向后续题透露标准答案或评分，各命主与重复轮之间清空历史。

| 配置 | 可见内容 |
| --- | --- |
| C0 | 题目与原出生资料，不调用排盘/技能/规则 |
| C1 | 程序盘的文本模板，不给技能与规则命中 |
| C2 | 程序盘与技能章节，剥离程序规则命中 |
| C3 | C2 加当前产物绑定的 `met=true` U12 命中 |
| C4a / C4b | 按体系独立专科请求再综合；仅 C4a 要求按程序时间顺序处理 |

三道明确合成的时支读数题，用真实 P8 隔离引擎、技能文件和 U12 条件层走通六配置。
脚本 C0 固定选 A，其余读取时支字段；C4 返回替身专科结果。结果只证明软件流转，
不代表模型推理、专业题库分数或现实预测效度。

`same_year_placebo(..., year_basis=...)` **必须显式**选择 `birth_year` 或 `competition_year`。
两者存在设计歧义，真实任务待大脑裁定；程序不猜。每个来源/指定年份内做不同命主的双射，
每个供体生辰必须不同，同一命主所有题保持相同供体。无法匹配时拒绝，不跨年补人。
本次合成人物既同出生年又同比赛年，两个模式都测试。真实题面可能泄漏原生辰/原盘，
必须先人工审查；本次没有执行真实题库安慰剂。

`statistics_v2` 提供 Wilson 95%、同题配对差及样本标准误、精确二项 McNemar p 值；
逐题检验未调整同命主题目相关性和多重比较。案例截尾按
[官方页面](https://destinylinker.github.io/MingLi-Bench/) 去掉最好和最差各一个案例，
另标记是否满足 8 案例×5 题；三题合成结果不与排行榜比较。

`crosscheck_v2` 要求显式 JSON Pointer 字段映射，对照只报告值指纹和差异状态。
只有外部盘时用 `external_chart()` 标注为外部输入，不能冒充本项目排盘。
真实外部资料缺历史时区/坐标/精度等输入，尚未算盘、对照或评分；只复用此前忽略目录中的
缓存，没有新增下载。新增下载、真实请求和额度控制均留主线按授权执行。

## 历史 v1 说明（已弃用，只保留兼容与审计）

此模块不导入模型客户端、不读取密钥、不加载 `.env`，CLI 只接受 `--mode scripted`。
没有接入主线的 `tools/eval/**`，也没有伪装成 P3 的真实 Agent 运行。

## 数据与输入

- `load_mingli(Path)` 支持官方 `questions / birth_info / options[{letter,text}]`。
- `load_baziqa(Path)` 支持 Contest8 的元数据头、人物、出生资料与带标签选项。
- 小写选项标签升为大写；标签后的空格和标点去除；选项正文保留。缺标签、重复标签、
  多答案、缺答案或同一人物的出生资料冲突均拒绝，不静默丢题或改变分母。
- `Question` 保存答案，但 `InferenceRequest` 只含题面与四个选项，答案不传给作答函数。
- 出生字段缺失保持 `None`；不从地点猜经度、历史 UTC 偏移或夏令时。
  `P8Engine` 需要按出生资料 fingerprint 提供 `CalculationInputs`，注明来源、明确接受分钟精度。
  本次外部题库只做 schema 检查，没有补齐上述输入，没有对其计算或评分。
- 外部题库下载放在忽略目录 `private/e2-sources/`。报告只保存版本、SHA256、数量与阻塞状态；
  不保存外部题目、选项、答案或出生资料。BaziQA 按用户要求只在本机使用，不再分发。

## 三种配置与控制

`run_configuration` 构造三种 **请求计划**。全部用相同题面和相同的程序命盘，区别在推理流程：
`direct` 单次选择；`single` 单次选择并要求核对字段、时间层级与口径；`deep` 先专科证据、
后综合选择。现在没有调用 v4 Agent Runtime、工具循环、技能检索或真实专科子 Agent。
未来接线需要主线提供真实运行适配与额度控制，本模块不自行发请求。

`placebo_births` 按固定 seed 对不同出生资料做环形错配。同一人物的所有题使用同一供体，
供体与原出生资料不同；保留原题目、选项及答案。至少要有两组不同出生资料。
这一对照只能在来源题面不泄漏原生日、原盘时才有可解释性，真实评测前还需逐题检查泄漏。
所有配置应固定模型版本、预算、技能版本和随机参数，保留配对结果，不能因表现不好重抽供体。

## 运行

在仓库根目录，使用 Core 解释器运行：

```powershell
$env:LANGSMITH_TRACING='false'
$env:KIMI_API_KEY=''; $env:OPENAI_API_KEY=''; $env:DEEPSEEK_API_KEY=''
python -m mingjing_core.adapters.charts.benchmarks.scripted --mode scripted `
  --chart-python '<Charts Python 的绝对路径>' `
  --mingli-root private/e2-sources/mingli --baziqa-root private/e2-sources/baziqa `
  --output docs/v4/evidence/P8/e2-scripted-2026-10-18.json
```

无题库目录参数也能运行合成试验；来源目录必须先由操作者下载，不会自动联网。
合成题只有“时支是哪一个”四题；通过真实隔离引擎生成命盘，再由脚本读取字段作答。
同一个字母选择器验证三种请求计划和错配控制，100% 仅表示该合成流转正常。
报告中的 `professional_corpus_score=null`；没有真实模型推理成绩。

比赛题衡量与职业命理师判断的一致性，不是现实预测的效度。合成字段读数连职业题库
一致性也没有测量；安慰剂出现分数下降只证明此脚本读取了被替换的字段。

## 来源

- [MingLi-Bench 官方仓库](https://github.com/DestinyLinker/MingLi-Bench)，独立 MIT LICENSE。
- [BaziQA 官方仓库](https://github.com/ChenJiangxi/BaziQA)，按用户要求只本地使用。
- [BaziQA 原论文 v1](https://arxiv.org/abs/2602.12889v1)，第二节说明比赛数据与评分协议。
- 固定提交、数据 SHA 与源格式阻塞见 `docs/v4/evidence/P8/e2-sources-2026-10-18.md`。
