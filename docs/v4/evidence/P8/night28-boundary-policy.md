# M3 时间临界提示的计算口径

依据：大脑交付《28_夜间作业提示词_2026-10-20.md》第二节命理线 M3，用户于北京时间 2026-10-20 夜间明确授权。

真太阳时距奇数整点时辰交界不超过 900 秒，提示时辰临界；距 23:00 晚子换日、00:00 子时内早晚子分界不超过 900 秒，分别提示。阈值包含端点。00:00 在项目默认 sect1 下不换日，保留默认两侧同柱，并另列 lunar-python sect2 两侧以表达具名口径差异，不虚构默认柱变动。

距物理瞬间对应的 UTC+8 节交接不超过 7200 秒，提示节月临界。两侧使用真实节瞬间前后各一秒，年、月柱按物理 UTC+8 精确节界计算；日、时柱按各候选真太阳坐标与 sect1。它是敏感性采样，不是新的出生事实、自动改档或倒推。

均时差旁证以 Swiss Ephemeris 2.10.03 的太阳视赤经和视恒星时路线计算，显式要求 Moshier 历表，纳入库模型推算的 UT1−UTC。若与默认 NOAA/Meeus 坐标产生不同柱，列出同一物理瞬间的另一柱；不把两种计算比较冒充独立天文观测或独立四柱验证。现行默认公式不变。

旁证在已有隔离 Charts 工作进程执行，不调用 `close`、`set_ephe_path`、`set_tid_acc` 等设置函数。它仍读取 Swiss 内部模型状态；不应把该适配器当作支持任意外部 Swiss 全局配置的并发计算沙箱。

出处：

- [Swiss 编程手册 §9.2、§9.4、§17](https://www.astro.com/swisseph/swephprg.htm)：UTC/UT1、均时差符号与恒星时接口。
- [Swiss v2.10.03 原始实现 `swe_time_equ`](https://raw.githubusercontent.com/aloistr/swisseph/v2.10.03/sweph.c)：赤经、恒星时与太阳日小数的组合。这里显式 Moshier，不继承原函数隐式选择历表的行为。
- [NOAA 默认均时差来源](https://gml.noaa.gov/grad/solcalc/calcdetails.html)。
- [lunar-python 1.4.8 EightChar](https://github.com/6tail/lunar-python/blob/v1.4.8/lunar_python/EightChar.py)：sect1/sect2 日界差异；年、月另按精确节界。

存疑/待核：没有使用 IERS UT1 观测，1972 年以前以及未来日期按 Swiss 模型语义处理；太阳时与古籍时辰的对应并非现代天文公式能够证明。新提示只交代算法敏感性，不评价命运准确性。

验证区间端点：已支持的 1901–2099 年 UTC 出生点仍返回原柱。若边界两侧的假设物理时刻越出该范围，该候选明确标为 `not_computed_outside_verified_utc_range`、柱为 `null`，不扩展默认公式范围、不凭空补柱，也不让新增提示使原出生点整体失败。
