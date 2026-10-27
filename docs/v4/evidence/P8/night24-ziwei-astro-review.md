# 24号审校补证：紫微、西占与表达草稿

核对日期：2026-10-18 夜间，Asia/Taipei；命理线 `v4/p8-calc`。
范围：24号 §6 第7、9项，以及紫微6章、西占5章、塔罗7章的表达示例与来源边界。未访问stage/生产，模型调用0，未改v3引擎。

## 第7项：具名四化异表及默认时间口径

| 变更 | 原文依据与实际核对 | 实现边界 |
| --- | --- | --- |
| 新增 `quanshu` 可选表，壬科天府；默认 `iztro` 壬科左辅 | 24号 §4/§6.7定位《全书》卷二安禄权科忌四星变化诀“壬梁紫府武”；[iztro v2.5.0 默认表](https://raw.githubusercontent.com/SylarLong/iztro/v2.5.0/src/data/heavenlyStems.ts)可核壬科左辅 | 默认保持；纯函数 `palace_flying_transformations(data, school="quanshu")` 显式选表，未知名称拒绝。公开适配器参数尚未接入选表 |
| 修正庚/壬限制文字 | 24号指出旧文“庚干太阴化科等异表”把当前默认自身误称异表 | 默认庚仍“太阳、武曲、太阴、天同”；其他庚干版本不新增，原刊待核 |
| 选表与实际引擎数据分开 | [iztro 宫位实现](https://raw.githubusercontent.com/SylarLong/iztro/v2.5.0/src/astro/FunctionalPalace.ts)按宫干生成四化；本地实际星曜和运限另有来源 | 可选表仅改变宫干edges及相应nodes；不重写生年 `star.mutagen` 或实际运限。`matches_named_table=false` 明确保留异表，缺天府返回missing |
| 紫微01改默认真太阳时，北京时间不同并列 | 23号用户裁定、24号 §6.7；`time_basis_chart.ziwei_column` 已接收完成换算的coordinate，零经度/零偏移传给原生引擎 | 只改P8技能说明；原v3 `build` 的平太阳时口径不动，主线用time_basis列实现默认解读 |
| 晚子时核对、明确月末差异 | [iztro utils](https://raw.githubusercontent.com/SylarLong/iztro/v2.5.0/src/utils/index.ts) 的 `timeToIndex` 把23点映为12，`fixLunarDayIndex` 晚子日序+1；[主星起点](https://raw.githubusercontent.com/SylarLong/iztro/v2.5.0/src/star/location.ts) `getStartIndex` 同样加日并处理月末 | 八字sect1同在23点换日的方向，不等于两个体系完整历法一致；保留原生月末差异，不为“统一”修改v3 |

`flying_v1.json`版本为 `p8-ziwei-palace-stem-flying-v1.1-review24`。输出新增 `table_id=iztro|quanshu`；每边 `table_ref` 精确到 `#/table/…` 或 `#/named_tables/quanshu/table/…`。`table_sha256`仍是完整知识文件的LF归一SHA256，并非单独选表的内容哈希。48条边的ID和证据指针契约保留；time_basis的重定位逻辑沿用。

**原典待核如实保留**：本轮打开[维基文库卷二](https://zh.wikisource.org/wiki/紫微斗數全書/卷二)、繁体版及全览，在线正文未能定位安四化口诀；原始文本请求被403拒绝。`quanshu`按用户要求和24号已作出的审校裁定实现，不能称本轮独立校勘了该原刊或全部40格。该表其余39格沿用本次裁定的共同表；不同刻本的庚干异表留待原刊复核。此待核已写入知识 `source_status`、README与技能03。

原生边界实测（合成/公开示例日期，非用户出生资料）：

| 坐标时间比较 | 原生结果 | 解释边界 |
| --- | --- | --- |
| 2000-08-16 22:59 → 23:00 | hour_index 11→12；日时干支改变 | 23点确实走晚子索引，不能当普通亥时 |
| 2000-08-16 23:00 与08-17 00:00 | 日时干支、命宫、14主星位置相同；引擎显示农历日期仍分别为七月十七/十八 | 内部日序前进不等于所有显示日期被重写 |
| 2000-08-28 23:00 与08-29 00:00（农历月末） | 日时干支、14主星位置相同，命宫分别申/酉 | 月字段差异仍影响命宫，不能笼统说晚子与次日早子全盘相同；不增加时辰倒推评分 |

## 第9项：Lilly定位与容许度差异

- [Lilly《Christian Astrology》Book III PDF](https://www.worldastrology.net/wp-content/uploads/2008/12/CA-III.pdf#page=248)共375页，文本层第248页（0基247）有原书页码734与章标题 `CHAP. CLXXII. Of REVOLUTIONS`；原书735–737依次为PDF249–251页。原书738/PDF252进入下一章。故原技能的章号和734–737页范围正确，本轮补了PDF页序定位。
- 原书734页定义摘录：“returne of the Sun to that very poynt”；736页有“Compare the Figure of the Birth”。技能仅借用太阳回到本命位置及与本命比较的方法，不继承历史疾病灾祸断语，也不把Lilly当作本项目Placidus、Moshier或求根精度背书。
- [Astrotheme软件自己的容许度表](https://www.astrotheme.com/astrology_aspects.php)列本命合10.5度、冲10度；行运合2.6度、冲2.5度，说明不同软件、技术可不同。按24号要求补“约8–10度或更宽”的比较语境，同时明确例子的实际数值；未断言所有软件一律8–10度，也未把合盘8度误套成本命规则。本项目本命统一6度保持。

## 技能与表达加分项

18章各增加一则白话、可观察的小行动示例，原有表达与完整出处均保留。各章新增“措辞模板”的声明：紫微/西占的 `〔c1〕/〔c2〕`、塔罗的 `〔t1〕` 必须由本轮真实依据注册后替换，未注册不引用。三体系没有本批八字 `rule_hits`，均不制造 `〔r#〕`。

18章末尾均保留“存疑/待核”，不把原典公开转录说成原刊校勘，也不把象征解释说成已验证的现实预测。紫微06清除旧的候选确认建议，重申倒推冻结、默认隐藏、诚实“分不出来”。3份SKILL和18章均升 `p8-skills-draft-2026-10-19-v2.2`；catalog由root统一更新，来源变更补丁在同目录 `night24-skill-source-patch.json`。

## 验证

- `python -m pytest tests/v4/test_p8_ziwei_flying.py -q`：**30 passed in 3.07s**，显式配置原生Charts Python，**0 skipped**。含旧原生3项和本轮新原生2项；可选表只差壬科一格、原生生年左辅保留、天府定位、月末晚子、缺星拒绝、非法名称均有覆盖。
- 产品技能加载器逐章读取18章通过；最大保守上下文字节数为西占03的 **5017/5500**，没有截断来源或提高上限。
- `python -m pytest tests/v4/test_p8_product_skills.py tests/v4/test_p8_skill_field_paths.py -q`：**21 passed in 5.10s**，实际原生紫微/西占/八字、time_basis及固定牌阵序列化字段均通过。首次运行曾暴露八字`pattern_support`元组不符合JSON契约的问题，规则代理修复后本次复测通过，未改测试迁就实现。
- 本代理修改的2个适配器与2个测试文件Ruff（E/F/I/B/UP/SIM，120列）和format --check通过；完整分支回归由root汇总，不将局部通过说成完整CI。

## 待决/未验证

1. 《全书》原刊及四化段落需后续大脑复核具体版本；当前按24号具名裁定提供可选表，默认iztro不受影响。
2. 晚子跨农历月末的原生差异保留，未修改引擎或把八字/紫微强行统一；主线应展示方法而不是隐藏差异。
3. quanshu公开工具选项、Agent别名注册、前端解读与技能实测模型效果未接入/未验证；本轮真实模型调用0。
