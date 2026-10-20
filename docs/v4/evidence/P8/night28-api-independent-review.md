# 四个公共计算 API 的独立边界复核

记录开始：2026-10-21 00:00；修后复核完成：00:03（北京时间，UTC+08:00）。
范围：本地 `v4/p8-calc` 的 `daily_transit`、`window_search`、`almanac`、`synastry` 原生入口及其
Core隔离入口、契约、既有测试。只新增独立测试和本报告；共享源由 root 修复并统一发布。
全部输入为已有合成阿远/小禾或明确坏形状；不使用真实出生资料。

## 修前最小复现

已有合法 owner、subject、revision、operation、gender，其余合成出生字段不变，
只改 `birth.date`。在 `_basis` 位置安装“不得到达计算”的哨兵，调用公开 daily 或 window：

| 独立反例 | 修前观察 | 影响与限定 |
| --- | --- | --- |
| `birth.date` 缺失 | 两个 API 都泄漏 `KeyError: 'date'` | 还未计算盘，但坏结构没有按公共 ValueError 边界拒绝 |
| `birth.date = null` | 两个 API 都泄漏 `TypeError: fromisoformat: argument must be str` | 同上，没有返回成功盘 |
| `birth.date = true` | 两个 API 都泄漏同一 `TypeError` | bool不能混作日期；没有成功接受或返回越权盘 |
| `birth.date = "19940312"` | 两个 API 均到达 `_basis` 哨兵 | Python宽松日期解析通过旧预检；哨兵停止后续计算，本例没有声称原生最终会接受此格式 |
| synastry 的 B侧 `revision=true`，A侧合法，consent及owner合法 | 用记录调用顺序的出生准备替身，实际调用顺序为 `[A,B]`，再由B拒绝 | 控制流先准备A，再检查B的其余结构；不是未获consent或越权成功。应在任一盘计算前预检两侧 |
| daily/synastry 的 `orb_degrees=10**400` | `OverflowError: int too large to convert to float` | 有限JSON整数在 `math.isfinite` 的浮点转换处溢出；还未进入出生准备 |

这些反例只判断输入和控制流，不用替身冒充历法、排盘或真实模型成功。
缺陷已报 root；修复目标为新工具的预检和数值边界，旧 `time_basis_request` 与 v3 口径保持保护。

修后已只读核对 root 的三个共享文件：`daily_transit_natal.py` 新增 `validate_natal`，
先校验出生日期、时刻、scope、坐标与clock_basis等形状，把坏出生输入归一为
`ValueError: daily_transit_natal_invalid`；`synastry.py` 在任一prepare之前校验两人，仍先核consent；
`astro_ephemeris.py` 先安全转换有限数值并捕获超大整数OverflowError，不改有效相位计算。
本审阅没有直接修改这三个文件，也没有修改旧 `time_basis_request` 或v3。

## 新增保护与验证状态

独立文件：`tests/v4/test_p8_night28_api_review.py`。

| 测试组 | 数量 | 当前实测 |
| --- | --- | --- |
| daily/window 出生日期缺失、null、bool、紧凑格式在计算前拒绝 | 8 | 通过，固定 `daily_transit_natal_invalid` |
| synastry B侧 bool修订、null人物、坏日期和嵌套owner冲突，任一prepare前拒绝 | 5 | 通过，固定 `daily_transit_natal_invalid`，无prepare调用 |
| daily/synastry 正负超大JSON整数orb，准备前以ValueError拒绝 | 4 | 通过，固定“西占计算参数须为有限数值” |
| daily/window 的lat/lon为bool或超大整数，在basis前拒绝 | 8 | 通过，固定 `daily_transit_natal_invalid` |
| daily/window 的clock_basis为数组或对象，在basis前拒绝 | 4 | 通过，不提取其中的clock字符串 |
| consent不得从数组/对象中提取；先拒绝，不读坏出生结构 | 2 | 通过 |
| 公共almanac不将date对象或带sect对象强转为日期 | 2 | 通过 |
| window不把额外sample_time范围字段当作已支持择时 | 1 | 通过 |
| 原生四工具TZ环境、实际32日闰年范围31/1/0页 | 2 | 通过，共用1个Charts子进程 |

截至2026-10-21 00:02（北京时间）已记录修复无关的先行检查：

    python -m pytest tests/v4/test_p8_night28_api_review.py -q -k 'actual_ or consent_is or public_almanac or range_extension'

实际 **7 passed，17 deselected，0 skipped，5.64秒**；1个Core及最多1个Charts子进程，运行结束。
随后补12例坐标/clock_basis反例，并将原反例收紧到上述固定拒绝消息，未降低保护。
共享源修复后，2026-10-21 00:03（北京时间）重新运行整份：

    python -m pytest tests/v4/test_p8_night28_api_review.py -q

实际 **36 passed，0 skipped，5.67秒**；包含原17个反例、新增12个形状反例和7个原生/拒绝路径检查。
同一时刻最多1个Core加1个Charts子进程，现均结束。本次没有启动全量回归。
新增文件Ruff与默认88列格式检查通过；没有通过删测试、接受底层异常或放宽匹配解决反例。

## 原生成功路径实际核对范围

同一Charts进程在 UTC、Asia/Tokyo、America/New_York 三种 `TZ` 环境下，依次实际调用四个公共函数。
每个工具的内容document_id跨这三组相同；流日同时核北京时间正午与04:00Z；
逐别名解析 Pointer、重算其值hash、核全部实际规则的 `met=true` 和只读副作用字段。
合盘使用已经提供的 `consent=user_confirmed` 合成样例，没有把本测试当作真实同意事实证明。

另用2028-02-01至2028-03-03包含端点的32日闰年范围，真实调用window的offset0、31、32：
返回31、1、0行；has_more依次true、false、false；next_offset依次31、null、null。
前两页拼回全区间32条排名，含2月29日，无重复丢日；三页保留同一完整排名与查询hash。
每行总分等于正负贡献和；空页的候选、观测、命中和别名全部为空，保留完整追溯；
各页编码体积均小于现有8MB保护阈值。原请求在跨工具、多次查询后保持不变。

这些是实际纯计算和程序不变量，不能推出排序、合盘或传统解释的现实预测有效性。

## 未验证 / 已知边界

- 完整新增36例已修后通过；只证明上述拒绝路径、程序边界和合成盘成功路径，不借用旧全量绿色。
- 当前环境为Windows；改变TZ环境不能等同于Linux系统级 `tzset` 切换或跨操作系统验证。
- 原生分页检查为具名合成人物及32日范围，不证明所有本命的最坏响应大小或极限时间性能。
- Core适配器拒绝外来owner及进程错误包装已阅读；缺字段进入worker后的一般RuntimeError是现有进程边界，
  本次不把它承诺为已统一的新错误码。未检查主线HTTP注册、已登录身份、subject归属与撤销账本接线。
- consent字符串不是授权事实凭证；内部scope一致性不是外部来源认证，没有扩大他人资料处理范围。
- 没有穷举所有JSON形状，也没有实测模型、服务器、飞书、持久化迁移或真实用户流程。

真实模型请求0；原生验证子进程清空API Key、关闭追踪并阻断常用网络传输。
无数据库访问、无项目服务器访问、无提交/推送/合并；由root统一完成里程碑验证与发布。
