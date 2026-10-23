# 紫微宫干飞化增补核对（2026-10-18）

范围为 P8 显式入口的确定性结构增补，不改变 v3 排盘，不接已冻结的事件倒推评分。真实模型调用、生产访问与资料写入均为 0。

## 已实现与口径

- `palace_flying_transformations(data)` 读取实际十二宫宫干，按具名 `iztro-2.5.0-default-palace-stem-table` 输出 48 条飞化记录、12 宫入/出链。
- 每条记录有来源宫干、化星、实际落宫和精确星曜数组 JSON Pointer。缺星、重复星不猜落点；原始繁简名与显式规范名并列保留。
- 自化严格为来源宫与落宫同一索引。化忌的对宫链只表明 `geometry_only=true`，不推断事件或吉凶；没有向心/离心、自化强度或连续转忌规则。
- 生年四化来自实际 `star.mutagen`；大限、流年、流月、流日各自读取实际 `horoscope` 四化、命宫索引和十二宫名，不移动本命星，不推造缺失层。
- 实际运限四化与具名表不同则保留实际值、标 `matches_named_table=false`。本命图可单独计算，缺运限层明确 `unavailable`。旧 `yearly_mutagen_links` 未改返回契约。

## 可重复验证

Core 环境设置 `CHART_PYTHON` 为已存在的 Charts Python，执行：

```text
python -m pytest tests/v4/test_p8_ziwei_flying.py tests/v4/test_p8_u2_interactions.py -q
```

结果 **47 passed，3.14s，0 skipped**。其中新增飞宫测试 21 个，原 U2 测试 26 个；新增测试中的原生子进程另执行 3 个 Charts 检查，均通过。

公开 API 示例的合成输入为 `2000-08-16`、寅时序号 2、女，预先换算坐标为 `2000-08-16T03:00:00`；此输入用于可重复计算，不是用户资料。实际财帛宫索引 0、宫干支戊寅，宫干四化落点依次为 `[10,9,2,3]`（贪狼、太阴、右弼、天机）；目标 `2026-10-18` 实际流年干支丙午、流年命宫索引 4。

- 48 条边逐一对照安装 JS 的 `fliesTo()` 和 `mutagedPlaces()`；同宫条件对照 `selfMutaged()`，每边加“目标换一宫必须为假”的反例。
- 两个合成日期覆盖十天干全部 40 个表项，并核对四个实际运限层。
- 其余测试覆盖缺星、重星、错误宫序/宫干、布尔索引、缺层、错层、重复四化、繁简别名、精确指针解析、输入不变与重复输出稳定。
- 新增 4 个 Python 文件分别 156/93/197/80 行，无函数超过 60 行；Ruff E/F/I/B/UP/SIM 和 120 列格式检查通过。

## 版本及来源边界

实测 `py-iztro=0.1.5`、`pythonmonkey=1.1.0`。包 Description 声明上游 2.4.4，实际资源文件名为 `iztro-2.5.0.min.js`；两者矛盾，**不宣称内嵌版本已独立核验**。资源 SHA-256：

```text
09333d6a2da7fff7bd338134c8d17de0d589259c16a70ece1db1d64e17217ea0
```

本次只读 `Astro().get_config()` 运行值为 `yearDivide=exact`、`horoscopeDivide=exact`、`ageDivide=normal`、`algorithm=default`、自定义四化表为空。包装模型类定义的默认枚举不能代替实际运行值；新功能读取已经算出的运限层，不重新选择分界或修改 v3 默认值。

具名表 LF 规范化 SHA-256：

```text
a410bbc69452db489b7bd976d6fa137c39db7a582b65d2be113de0b4f0b4c489
```

来源为 [官方 v2.5.0 十天干表](https://raw.githubusercontent.com/SylarLong/iztro/v2.5.0/src/data/heavenlyStems.ts)、[官方 v2.5.0 宫位类](https://raw.githubusercontent.com/SylarLong/iztro/v2.5.0/src/astro/FunctionalPalace.ts)、[官方宫位文档](https://docs.iztro.com/posts/palace)。这是同一上游的源码与运行一致性核对，**不等于独立排盘软件/传统古籍校勘，更不等于现实效度验证**；跨流派独立校盘仍未完成。
