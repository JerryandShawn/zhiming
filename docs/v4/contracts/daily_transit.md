# daily_transit v1：晨报用三体系流日快照（草稿）

状态：P8 只读计算接线草稿；主线的 Agent 注册、HTTP、档案和依据账本不属于此契约。输入、输出均为有限 JSON。未调用模型、未写资料，也不承诺现实预测结果。

## 输入

Python：`daily_transit(natal, date, *, orb_degrees=2.0)`。`date` 为严格 `YYYY-MM-DD` 阳历日期，1901–2099，不能早于出生日期。当天统一取 **12:00:00 北京时间（UTC+08:00）**。这是一个瞬间的盘面快照，不能称为全天行运区间或择时结果。

`natal` 是明确归属和已报告出生时刻的请求，沿用 `time_basis` 的出生结构。例如完全合成人物阿远：

```json
{
  "owner_user_id": "synthetic-owner-ayuan",
  "subject_id": "synthetic-subject-ayuan",
  "revision": 1,
  "operation_id": "synthetic-ayuan-daily-20261021",
  "birth": {
    "date": "1994-03-12",
    "reported_time": "08:20",
    "gender": "男",
    "place": {"tz": "Asia/Shanghai", "lon": 104.07, "lat": 30.67},
    "clock_basis": "clock",
    "precision": "reported"
  }
}
```

调用方传入的 `date` 是唯一目标日期，不读取本机“今天”。时区来自明确的 IANA 出生时区，夏令时按固定数据源转换；不存在的钟表时刻和有多个物理 UTC 瞬间的时刻拒绝，不自动平移、猜 fold 或倒推。

主解读本命八字与紫微采用真太阳坐标。北京时间同一物理瞬间的本命四柱不同时，保留 `data.time_basis.comparisons`；同盘时该数组为空。西占本命只采用真实出生 UTC，不把真太阳坐标当成另一个物理瞬间。具体时区版本、转换依据及所选坐标见 `data.time_basis.primary`。

## 输出与规则命中

JSON Schema：[`daily_transit.schema.json`](daily_transit.schema.json)。顶层为 `tool_evidence.evidence_result` 的只读信封：

```json
{
  "version": "p8-daily-transit-v1",
  "scope": {"owner_user_id": "...", "subject_id": "...", "revision": 1, "operation_id": "..."},
  "data": {
    "date": "2026-10-21",
    "snapshot_at": "2026-10-21T12:00:00+08:00",
    "snapshot_at_utc": "2026-10-21T04:00:00Z",
    "time_basis": {"primary": {}, "comparisons": []},
    "bazi": {},
    "ziwei": {},
    "astro": {}
  },
  "rule_hits": [],
  "sources": [],
  "document_id": "tool-<sha256>",
  "aliases": {"c": [], "r": []},
  "effects": {"model_calls": 0, "writes": 0, "alias_registry": "ephemeral_only"},
  "limits": []
}
```

此处空对象/数组只是结构缩写，完整实际计算样例在 `samples/daily_transit/ayuan_2026-10-21.json` 至 `ayuan_2026-10-27.json`，不能拿上面缩写当排盘结果。

`data.bazi` 保存真太阳本命四柱、正午的节年/节月/流日柱、各流干及藏干相对本命日干的十神、完整交互图。沿用具名藏干表；与 v3 原有本命计算不互相覆盖。关系图列冲、合、刑、害、破、相克等实际成员，不推断合化、应事或概率。三支未齐时 `complete=false`，只能说成员未齐，不能说三合/三刑全部成立。

`data.ziwei` 保存引擎真实本命十二宫、实际流年/流月/流日运限及四化落点。`horoscope(date, 6)` 显式传入午时时辰索引，避免库默认取当前时辰。沿用安装的 py-iztro 默认口径及其闰月/晚子规则，记录版本与源码指纹。只关联现有星曜，不移动本命宫、不把流年宫名冒充本命宫。缺星或重复落点标为未解析，不补造。

`data.astro` 保存真实出生 UTC 本命行星和北京时间正午行运行星的地心热带黄道视黄经，以及两组间 0°/60°/90°/120°/180° 相位。`orb_limit_degrees` 是调用方显式容许度（默认 2°，允许 0–10°），每项 `orb_degrees` 是实际偏离度，纳入条件为 `<=`，不按天体或吉凶暗改阈值。不计算整日进入/离开时刻、宫位或现实事件。

每个 `rule_hits[]` 都含 `rule_id, met=true, school, source, evidence_paths, context`。`met=true` 只表示该项传统成员或数值条件成立。结构关系与解释建议不能混为事实。

| context.system | context.kind | 稳定字段 |
| --- | --- | --- |
| bazi | relation | relation、complete、natal_pillars、target_layers、transformation_established=false |
| bazi | ten_god | layer（yearly/monthly/daily）、ten_god |
| ziwei | mutagen | layer、mutagen（禄/权/科/忌）、natal_palace、palace_index |
| astro | aspect | aspect、from、to、orb_degrees、orb_limit |

八字关系规则只取含本命与目标层的成员组合；纯目标层之间的结构仍在图中，不能当成与本人原局的关系。紫微只为唯一解析的落点分配规则命中；西占只为容许度内实际相位分配。

## 依据别名与幂等性

`c#` 由所有命中的 `/data/...` 证据 Pointer 去重后按字典序分配；`r#` 按本结果 `rule_hits` 顺序分配。`r#` 明列其所依赖的 `c#`。用法：“当天月亮与本命水星形成一个容许度内相位〔c3〕〔r2〕，可以把它当作提醒自己把话说清楚的象征线索。”数字必须从当次结果取，不能照抄此示例。

Pointer 遵循严格 RFC 6901，别名附所指值 SHA256。文档 ID 绑定版本、scope、完整 data、命中与来源；相同显式输入和相同版本的确定性结果可重放。短别名仅该文档有效，不能跨日、跨人直接合并；主线接入须重新登记。没有持久化或撤销账本写入。

## 拒绝与限制

直接 Python 层抛出 `ValueError`；参数错误不得携带出生原文或私有正文。新增稳定码包括 `daily_transit_date_invalid`、`daily_transit_date_out_of_range`、`daily_transit_before_birth`、`daily_transit_unconfirmed_physical_instant`。原 `time_basis` 校验错误继续沿用；适配器的进程失败仍按其既有错误包装，由主线映射成对人可读提示。

不接受未知出生时刻进行倒推；不改变冻结/隐藏的实验政策。没有投资、疾病、灾祸或关系结局保证。流日结构不能代替真实日程、天气、交通、合同审阅或当事人意愿。实际项目筛选权重由 `window_search` 单独具名，不偷偷写入流日。

## 来源与存疑/待核

- 历法：现有 `lunar-python` 安装版本、`calendar_layers` 的节界与 UTC+8 正午口径；来源 `https://github.com/6tail/lunar-python`。库与口径一致性不等于独立天文实测。
- 八字：项目既有 `ten_god` 五行阴阳算式与 `p8_interactions.json`，后者区分《三命通会》卷二公开转录及项目六破/三会表。原刊版本页码未完成校勘，不补造。
- 紫微：已安装 py-iztro 包及其内嵌 iztro，官方运限接口 `https://docs.iztro.com/posts/horoscope`、项目 `p8_ziwei/flying_v1.json`。壬干《全书》口径不自动改写引擎默认运限四化；流日四化独立算法对照另交研究报告。
- 西占：Swiss Ephemeris 程序说明 `https://www.astro.com/swisseph/swephprg.htm`，显式 Moshier、UTC→UT1/TT、地心热带黄道；几何相位与 2°统一容许度为此项目具名筛选约定，不宣称全流派通用。

样例全部为合成人物；没有公开真实用户或题库出生资料。测试不依赖宿主机时区；跨操作系统与独立引擎的一致性仍须另证，不能把本机通过当跨平台通过。
