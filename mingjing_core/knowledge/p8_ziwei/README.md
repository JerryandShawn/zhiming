# 紫微宫干飞化具名表

`flying_v1.json` 逐项采用 iztro 官方仓库 `v2.5.0` 的十天干四化表，顺序固定为禄、权、科、忌；宫干来自实际排盘，化星落点来自实际主星/辅星数组。此名表示选用的规则表版本，不宣称安装包的内嵌 JS 版本已经独立鉴定。

生年四化读取原始 `star.mutagen`；大限、流年、流月、流日读取原始 `horoscope` 四化，不强行改成此表。与本表不同的运限层保留原值并输出 `matches_named_table=false`。不存在的层返回 `unavailable`，不从年份猜补。所选表的宫干飞化与时间层四化各自保留，不混成生年四化。

自化只指起化宫和化星实际落宫相同，与官方 `selfMutaged()` 的同宫定义一致；不扩充向心、离心等其他派别概念。“化忌冲”只输出化忌落宫的对宫几何位置，没有事件或吉凶推断。

繁简别名只使用表中的显式映射，输出始终保存原星名及精确原始星曜 JSON Pointer。缺星或重星不能选出唯一目标，状态如实为 `missing` 或 `ambiguous`。这些结果不加入已经冻结的时辰倒推评分。

来源：

- [官方 v2.5.0 十天干表](https://raw.githubusercontent.com/SylarLong/iztro/v2.5.0/src/data/heavenlyStems.ts)
- [官方 v2.5.0 宫位飞化与自化实现](https://raw.githubusercontent.com/SylarLong/iztro/v2.5.0/src/astro/FunctionalPalace.ts)
- [官方宫位接口](https://docs.iztro.com/posts/palace)、[官方运限接口](https://docs.iztro.com/posts/horoscope)

未宣称本表代表各派唯一传统口径；未新增古籍出处，也未把程序结构验证描述为现实预测验证。
