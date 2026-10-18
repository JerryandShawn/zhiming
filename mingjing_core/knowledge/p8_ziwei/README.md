# 紫微宫干飞化具名表

`flying_v1.json` 默认表逐项采用 iztro 官方仓库 `v2.5.0` 的十天干四化表，顺序固定为禄、权、科、忌；宫干来自实际排盘，化星落点来自实际主星/辅星数组。此名表示选用的规则表版本，不宣称安装包的内嵌 JS 版本已经独立鉴定。

24号审校新增具名可选表 `quanshu`：壬干化科取天府，默认 `iztro` 仍取左辅，其余39格保留本次审校采用的共同表。默认庚干是太阳禄、武曲权、太阴科、天同忌；先前“庚干太阴化科等异表”限制文字有误，已改为壬干天府化科及其他派别的庚干异表。原刊和其他庚干版本未核，不添加未经裁定的变体。

纯函数可显式调用 `palace_flying_transformations(data, school="quanshu")`；`flying_profile("quanshu")` 可读同一表，未知名称立即拒绝。输出新增 `table_id`，边的 `table_ref` 精确指向所选知识表。`P8ChartAdapter.calculate` 与 `time_basis` 仍调用默认表；公开工具参数尚未接入选表。

生年四化读取原始 `star.mutagen`；大限、流年、流月、流日读取原始 `horoscope` 四化，不强行改成此表。与本表不同的运限层保留原值并输出 `matches_named_table=false`。不存在的层返回 `unavailable`，不从年份猜补。所选表的宫干飞化与时间层四化各自保留，不混成生年四化。

自化只指起化宫和化星实际落宫相同，与官方 `selfMutaged()` 的同宫定义一致；不扩充向心、离心等其他派别概念。“化忌冲”只输出化忌落宫的对宫几何位置，没有事件或吉凶推断。

繁简别名只使用表中的显式映射，输出始终保存原星名及精确原始星曜 JSON Pointer。缺星或重星不能选出唯一目标，状态如实为 `missing` 或 `ambiguous`。这些结果不加入已经冻结的时辰倒推评分。

选表只影响宫干飞化 `edges`，并重新按真实落点生成 `nodes`；不会重排本命盘，不替换生年 `star.mutagen`，也不改写原生运限层。`matches_named_table` 只反映实际运限四化与所选表是否一致，不是一项校正授权。缺少天府时，可选表相应边如实返回 `missing`。

来源：

- [官方 v2.5.0 十天干表](https://raw.githubusercontent.com/SylarLong/iztro/v2.5.0/src/data/heavenlyStems.ts)
- [官方 v2.5.0 宫位飞化与自化实现](https://raw.githubusercontent.com/SylarLong/iztro/v2.5.0/src/astro/FunctionalPalace.ts)
- [官方宫位接口](https://docs.iztro.com/posts/palace)、[官方运限接口](https://docs.iztro.com/posts/horoscope)
- [《紫微斗数全书》卷二](https://zh.wikisource.org/wiki/紫微斗數全書/卷二)：24号审校定位安禄权科忌四星变化诀“壬梁紫府武”，据此命名 `quanshu`；本轮在线正文未定位该段，不能声称独立校勘，原刊待核。

未宣称任一表代表各派唯一传统口径，也未把程序结构验证描述为现实预测验证。
