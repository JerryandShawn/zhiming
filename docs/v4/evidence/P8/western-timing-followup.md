# P8 西占剩余计算：行运区间、次限、太阳回归

日期：2026-10-18。仅计算线草稿；公开合成历元，不含真实人物资料；真实模型调用 0。

## 计算与口径

- `secondary_progressions(birth_at, target_at, orb=1)`：具名方法 `secondary-direct-UT1-day-per-365.2422-UT1-days-v1`。以 `(目标 JD_UT1 − 出生 JD_UT1)/365.2422` 得到历表推进日数，保留小数年龄；输出十天体实际本命位置、象征历表时刻、次限位置及两套相位。未定义的推运宫位明确为 `null`，没有混入太阳弧或主限。
- `solar_return(birth_at, return_year, longitude=…, latitude=…, orb=6)`：`return_year` 为 **UTC 生日周年标签**，不是自然年全部回归列表。取该年 UTC 出生月日时为锚，2 月 29 日遇平年用 2 月 28 日锚；前后各 5 日内必须只有一个太阳热带视黄经回归根，否则拒绝。输出锚点、实际 UTC、跨年标记、残差和括区间。出生年返回本命时刻。`orb` 只控制回归盘内部五大相位列表，不影响求根。
- 回归地点强制显式提供。十天体用地心视位置；宫制固定 Placidus，黄经按相邻宫头区间落宫。高纬引擎报错直接拒绝，不静默采用 Swiss 内部可能给出的其他宫制。
- 行运区间保留既有入相、精确、出相、逆行多次经过、驻点切分、首尾截断。升级到 `p8-transit-windows-v2-UTC-UT1`，与新方法一起使用 Swiss `utc_to_jd`，分清 UTC、UT1 和 TT；根的时间戳保留微秒是数值表示，不代表微秒准确度。
- 西占所有入口使用实际 UTC，**不套真太阳时**。每个新会话先固定 `TIDAL_MOSEPH=-25.58″/世纪²` 和自动 Delta-T，避免 UTC 转换无 ephemeris flag 时继承先前设置；调用顺序负例覆盖此前自定义潮汐和固定 Delta-T。v3 的 `julday` 将民用 UTC 近似作 UT 的旧口径及代码保持不变。1972 年前 Swiss 将输入按 UT1 处理；未来 UTC 依赖其闰秒及 Delta-T 模型，均在返回值中标明。

## 离线核对结果

- 新增 Charts 原生测试 **21/21**，既有原生交互测试 **5/5**；无跳过。Core 桥接执行相同原生测试，不在 Core 环境导入 Swiss。
- NASA/JPL Horizons DE441，地心 observer quantity 31：太阳、月亮、水星共 **16** 个公开合成历元值已缓存入测试夹具。最大黄经差 **0.939998″**，最大黄纬差 **0.471095″**；未把非零残差抹平。测试容许差预定为 1.5″，仅覆盖这些历元。
- 合成出生历元 `2000-01-01T12:00:00Z`，2025 周年回归为 `2024-12-31T13:31:59.274308Z`，是应保留的跨年结果。黄经残差 **1.56114e−8°**，二分括区间 **0.01030 秒**。与 NASA 两个相邻分钟位置的独立线性插值根差 **0.189433 秒**；另与 Swiss 自带 `solcross_ut` 数值搜索交叉检查，小于 0.02 秒。
- 同合成历元推进一热带年的 UTC 输入，次限历表时刻为 `2000-01-02T12:00:00.000121Z`。UTC 与 UT1 的年度差别被保留，测试不强行要求其数值年龄恰好为 1。
- 水星对固定黄经 225°，2026-10-01 至 12-10 区间保留三次合相：10-13、11-02、11-25；粗细月亮采样、0°/360°交界、入出相及截断的旧测试继续通过。
- 另测时区等价、零年龄、出生前/超过 150 年拒绝、闰日周年、显式地点变化、相位 orb 不改变根、高纬拒绝、非有限输入。Asc/MC 用独立球面恒等式核对。

运行：Charts Python 执行 `tests/test_p8_astro_native.py` 及 `tests/test_p8_interactions_native.py`；Core 在设置 `CHART_PYTHON` 后执行 `tests/v4/test_p8_astro_timing.py`。精确数值与限制见同目录 `western-timing-followup.json`；NASA 查询参数完整保存在 `tests/v4/fixtures/p8_astro_horizons.json`。

## 来源与边界

1. [Swiss 官方编程接口](https://www.astro.com/swisseph/swephprg.htm)：§3 坐标、位置与返回 flags，§4 太阳过黄经搜索，§9.2 UTC/UT1/TT 转换，§15 Placidus 与极圈错误行为。
2. [Astrodienst 图种说明](https://www.astro.com/faq/fq_fh_owtype_e.htm)：次限的一年对应一天原则。365.2422 个 UT1 日这个精确定义为项目具名细化，不声称所有软件使用相同年长或推运宫位方法。
3. [Astrodienst 回归盘说明](https://www.astro.com/faq/fq_fh_return_e.htm)：回归年份与显式参考地点；周年前后 5 日、闰日锚点及 UTC 年标签处理为项目明确约定。
4. [NASA/JPL Horizons 手册](https://ssd.jpl.nasa.gov/horizons/manual.html)及[官方 API](https://ssd-api.jpl.nasa.gov/doc/horizons.html)：quantity 31 为 observer-centered IAU76/80 日期黄道视经纬，包含光行时、偏折及光行差。与 Moshier、Swiss 坐标模型不同，保留差异；运行时不连接这些网站。

16 个缓存值不是全时段、全天体正确性证明。Swiss 自带求根与本实现共享历表，不能算独立历表。全部 12 宫头尚未与另一套独立宫位实现逐项核对，Asc/MC 恒等式检查不能替代该核对。有限步长行运搜索仍可能遗漏切触或极短窗口。出生时刻区间需由上层逐个实际 UTC 分支计算，不能将单盘当作稳定结论。未验证任何人生预测效度、真实专科 Agent 解释质量或主线用户界面。
