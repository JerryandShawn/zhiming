# almanac v1：黄历只读计算契约

状态：P8 独立纯计算候选，未宣称主线 Agent / HTTP 工具已经接入。
版本 `p8-almanac-v1`；Schema：[almanac.schema.json](almanac.schema.json)。
实际样例：[2026-10-21](samples/almanac-20261021.json)。

## 输入与时间口径

Python 入口为 `mingjing_core.adapters.charts.almanac.almanac(day: str) -> dict`。
原始计算入口 `almanac_data(day) -> (data, hits, sources)` 供适配器组合使用；
必须在现有 Charts 隔离解释器中调用，Core 不安装历法依赖。

```json
{"day":"2026-10-21"}
```

`day` 必须是十位 ASCII `YYYY-MM-DD` 公历日期，支持1901-01-01至2099-12-31。
闰日按公历校验；不接收 datetime、时间戳、隐式今天、宽松日期或宿主时区。
日期表示北京时间的民用日；固定取该日 `12:00:00+08:00` 构造库对象，
普通黄历日期不套出生真太阳时，不随1986–1991历史夏令时改变当天标签。
返回的 noon 是明确的日历采样约定，不代表每个时辰的宜忌相同。

本版本固定 `lunar-python==1.4.8` 的每日宜忌 `sect=1`：采用库按日期划分的月干支。
这和流日功能按精确交节时刻选月柱是不同的具名用途。
`sect=2` 在库内改用精确交节月干支，本接口不隐式切换、不新增可选参数。
日期校验后，首次包身份读取会先核对已安装发行元数据的版本；不等于 `1.4.8` 时，
在导入历法库与生成日期字段前拒绝，不返回违反 v1 Schema 的成功信封。
这项版本检查不认证发行包或源码真伪；实际源码摘要仍单列，也不改变锁文件。

## 输出结构

```json
{
  "version":"p8-almanac-v1",
  "scope":null,
  "data":{
    "date":"2026-10-21",
    "calendar":"gregorian",
    "timezone":"Asia/Shanghai",
    "sample_at":"2026-10-21T12:00:00+08:00",
    "lunar":{"year":2026,"month":9,"day":12,"is_leap_month":false,"display":"二〇二六年九月十二"},
    "ganzhi":{"year":"丙午","month":"戊戌","day":"戊辰"},
    "yi":["祭祀","沐浴","破屋","坏垣","馀事勿取"],
    "ji":["嫁娶","入宅","上梁","出行","安葬"],
    "chong_sha":{"branch":"戌","stem":"壬","zodiac":"狗","display":"(壬戌)狗","sha_direction":"南"},
    "duty":{"deity":"青龙","category":"黄道","luck":"吉","officer":"破"},
    "mansion":{"name":"箕","luminary":"水","animal":"豹","luck":"吉"},
    "pengzu":{"stem":"原文见完整样例","branch":"原文见完整样例"},
    "method":{"library":"lunar-python","library_version":"1.4.8","yi_ji_sect":1}
  }
}
```

上段为节选说明，**不作为完整 Schema 样例**；完整结果还包含来源指纹、真实规则命中、
`document_id`、`aliases`、`sources`、`effects` 和 `limits`。
完整样例由实际安装的历法库计算后写入，不是模型编写的日历资料。

`data` 的业务字段含义：

| 字段 | 含义 / 实际库入口 |
| --- | --- |
| `lunar` | 农历年月日、负月份所标的闰月、原生显示名 |
| `ganzhi.year` | 按立春日期的年干支；不是隐含按农历正月初一 |
| `ganzhi.month` | 按节气日期划分的月干支，与本黄历 sect=1 一致 |
| `ganzhi.day` | 民用日干支；不沿用出生八字晚子换日 |
| `yi` / `ji` | 原样保留 `getDayYi(1)` / `getDayJi(1)` 字符串数组，不添加现代事项、改排名或删除看似矛盾的标签 |
| `chong_sha` | `getDayChong*` 与 `getDaySha`；branch是被冲的地支，stem是库的冲干，display是原生冲描述 |
| `duty` | `getDayTianShen` 值神、`getDayTianShenType/Luck` 标签、`getZhiXing` 建除十二值星 |
| `mansion` | `getXiu` 二十八宿、`getZheng/getAnimal/getXiuLuck` 配套标签；不是当日实际天文月宿测量 |
| `pengzu` | `getPengZuGan/Zhi` 原文，作为可展开历史资料保留，不转换为事件/疾病断言 |
| `method` | 实际库版本、完整包Python源码的相对路径及LF归一 SHA256图、总指纹、sect/日界/月界/时区/未校刊状态 |

`method.library_source_sha256` 算法：按文件相对路径排序，逐 `.py` 文件将 CRLF 归一为LF后取 SHA256；
组成 `path -> digest` 对象，再以 `sort_keys=True,separators=(",",":")` 的 UTF-8 JSON 取 SHA256。
来源图不包含安装绝对路径、用户资料或环境凭据。包身份在当前进程首次使用时读取并缓存；
要验证更换后的安装包须重启 Charts 进程，不能将旧进程缓存用于新的包版本。

## 规则命中与依据别名

本版本的六个 `p8-almanac-*` 规则只表示相应库字段已经存在：
`yi`、`ji`、`duty`、`mansion`、`pengzu`、`chong-sha`。
它们不是“这个人今天会发生某事”的断语。
每项具备 `met=true`、具名 `school`、实际库入口 `source.locator`、计算字段与方法的 `evidence_paths`。

信封采用 `tool_evidence.evidence_result`：

- `〔c#〕` 对应当前信封中实际 `/data/...` 值，按 Pointer 字典序编号，附内容 SHA256。
- `〔r#〕` 对应本结果中真实 `rule_hits`，保留顺序并引用关联 c 别名；不凭空创建命中。
- `claim_id` 同时绑定文档内容、Pointer和字段摘要；短别名只在本结果内有效。
- 主线必须将本次短别名登记到当前上下文；不能和另一天的 c1 直接视为同一依据。

完整10-21样例的 `〔c7〕〔r1〕` 为宜事项，`〔c3〕〔r2〕` 为忌事项，
`〔c1〕〔r6〕` 为日支冲煞结构。措辞可以是：

“如果你想看传统黄历，这份库表把沐浴列在宜项里〔c7〕〔r1〕，出行在忌项里〔c3〕〔r2〕。
咱们把它当一个文化参考；真正出行时，先看天气、车况和你的安排。”

这些别名只对所链接的完整样例成立，换输入后须重读结果。
彭祖百忌含历史灾祸词，原文可作附录，Agent正文不复述或用于健康、死亡、亲属命运断言。
黄道“吉”与建除“破”可同时出现，不能擅自删掉一项来制造一致结论。

## 错误、权限与副作用

| 错误码前缀 | 触发 / 处理 |
| --- | --- |
| `almanac_date_invalid` | 缺失、非字符串、非严格ISO格式或无效公历日期；不导入历法库即拒绝 |
| `almanac_date_out_of_range` | 不在1901–2099；不做外推 |
| `almanac_library_version_unsupported` | 首次读取的发行版本不是严格的1.4.8；不执行该日期的历法计算，修复隔离环境后重启 |
| `almanac_library_inconsistent` | 库输出冲支与独立的日支+6取模12不一致；失败关闭，不悄悄修值 |

本函数不读取用户出生信息，无需他人资料授权，也不支持用人物资料改变黄历。
`effects.model_calls=0`、`writes=0`、`alias_registry=ephemeral_only`。
没有数据库、网络或模型调用；参数不合法时不返回半份黄历。依赖缺失属于 Charts 部署配置问题，
不回退到模型或编造日历，适配器负责转换为其现有配置错误。
直接 Python 入口保留上述错误前缀；当前跨进程 `P8ChartAdapter.almanac` 沿用既有
`chart_engine_failure` 对外分类，不承诺已把新的细分错误透传给 Agent/API。

## 验证证据

    python -m pytest tests/v4/test_p8_almanac.py -q

本次24项通过，0跳过，1.02秒。原生单子进程对固定日期及2026–2027逐周采样逐字段对照库自身，
另独立核日支冲支与煞方、输入/闰日/声明范围、四种TZ环境结果完全一致、真实依据摘要与来源图、
完整 Schema。此处软件一致性不等于传统预测有效性，也不替代本分支完整回归。

## 出处与存疑 / 待核

- [lunar官方API目录](https://6tail.cn/calendar/api.html)：字段定义；实际库版本及源码摘要在样例 method 中。
- [lunar-python官方源码](https://github.com/6tail/lunar-python)：具名程序实现；本接口不自动更新版本。
- [官方 v1.4.8 标签 Lunar.py](https://raw.githubusercontent.com/6tail/lunar-python/v1.4.8/lunar_python/Lunar.py)：
  可供阅读的源码入口。页面行序与本机安装文件不同，实际执行指纹以安装包为准。

原刊/通书版本与纸页尚未校勘，不能声称已核某一版古籍完整表格。
文化标签之间可能存在不同体系或版本分歧，原样呈现并说明方法；不将这些标签当作科学预测或人生命令。
