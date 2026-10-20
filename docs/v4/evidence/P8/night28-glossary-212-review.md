# 白天追加：命理术语词典212条交付证据

编辑审阅/验证时间：2026-10-20 23:46 +08:00（北京时间）。
按root已复核的10条方向扩展；夜间主队列与储备池由root统筹，本产物属于29号白天追加准备。

## 完成范围

共212条，分布 `{'bazi': 72, 'ziwei': 55, 'astro': 50, 'tarot': 35}`。stage=`draft_complete_200_for_review`，review_tag=`v1_ready_editorial_reviewed`。
所有词条均逐项编写白话解释、不同的具体例句、来源ID/定位/支持范围、具名差异或未跨派对读说明以及待核。
没有根据标题批量拼接同一段含义，数据装配脚本仅把已写的正文和来源元数据序列化。

四柱与八字合并计一条；塔罗英文名称作别名，不增加条数。十二星座各有角度范围/边界例句，不把它们写成十二种人格。
紫微14主星的提问词明确来自项目原创技能，不冒称古籍逐句原文；塔罗22张大牌逐条绑定现有editorial card_id。

## 文件及指纹

| 文件 | LF归一SHA256 |
| --- | --- |
| `mingjing_core/knowledge/p8_glossary/terms_v1.json` | `723d469516058967dbffb620e035c8ce7762777c8f8e494e865033374aef6eba` |
| `mingjing_core/knowledge/p8_glossary/sources_v1.json` | `c7c5dde7abf270092283b09291993a1d774f323f782fdd6da4a9b17bbf71116a` |

契约：`docs/v4/contracts/glossary.md`，对应terms与sources两份自包含Schema。
专属测试：`tests/v4/test_p8_glossary.py`。没有新增charts模块；词典独立子目录不纳入计算方法指纹，不重定义排盘口径。

## 来源边界

注册32项来源，类别数 `{'project_implementation': 16, 'official_scientific_documentation': 2, 'official_implementation_documentation': 3, 'project_editorial': 11}`。
来源ID每条可解析；本地路径为实际仓库文件且不越目录，外部资料只指具名官方作者的说明。
程序源码证明项目怎么做，项目原创文本证明当前解释版本；两者都不能倒过来证明古籍原文或现实预测。
古籍版次页码、其它门派说法未核就明确待核。没有用现代软件默认代表各派共识，也未把历史书名当项目数值权重的出处。

## 验证

    python -m pytest tests/v4/test_p8_glossary.py -q

最终**252 passed，0 skipped，0.26秒**；Ruff E/F/I/B/UP/SIM与88列format通过。
两份Schema、212逐词字段/来源、来源路径、分布计数、同义重复、不同例句、塔罗原创定位、非计算依据边界均有检查。
首次测试251通过/1失败：逆位引用的support_scope虽正确指原创源，但没有明确写原创范围；补齐该条范围声明后原测试不变重跑全过。
编辑自审另修正了三处措辞替换留下的不自然句子；并把“一日对应一年变体”与太阳/日周期回归名称区分。

## 未验证 / 待核

这份词典不是全部命理术语百科，也不是所有门派原刊校勘。大脑/所有者尚未逐条验收，review_tag只代表项目编辑审阅。
主线/前端的搜索、对话点词弹窗、词典到学习卡的主线集成、真实模型表达和现实效度未在此实现或验证。
词条不是用户盘面事实，不能仅据词典生成c/r计算别名；学习要点需另绑定真实chart_compute结果。
无数据库迁移、无产品数据删除、无模型/服务器/飞书；未修改v3、web、Agent或其它工作树，发布由root统一处理。

## 独立复核后的定点来源修正

修正时间：2026-10-20T23:57:43+08:00（北京时间）。
按独立审阅将年/月/日柱、节界、晚子时直接定位到`time_basis_candidates._candidate`实际精确节界与sect1方法；阳刃同时给出`schools.json:/blade`实表及`named_stars`执行层，阴刃逆行第三说仍保留原典待核；正官/伤官牵制引用`restraint`实际正官/庚辛分支。西占容许度分别引用本命legacy、合盘、流日实际6/6/2默认函数，legacy只读；等宫制明确Ascendant精确度数起每30度，P8当前未实现该可选宫制。

来源由32增至36：31本地路径与相关实现定位本轮已核，5外部URL沿用此前阅读记录，本轮未重新外访。源码定位不替代原典校勘。次限来源标题也改为“一日对应一年”，避免与日回归混用。

词典专属回归 **265 passed，0 skipped，0.28秒**（原252场景、新增4来源路径场景及9项定点来源/等宫制保护）；Ruff及88列format通过。

- 修后`terms_v1.json` LF SHA256：`b9d310c560df92666b9c1f2d4bdcf6c6a821d099908d113cc4a22acfb32e14a4`。
- 修后`sources_v1.json` LF SHA256：`3e1d2035b299548b1b413a707d3bb28c0e5c8991b96ef3b0c0b723eb2c3aaf12`。

可选分类待核：均太阳时、北京时间、夏令时的`definition_kind`目前沿用初稿traditional_concept枚举；正文与源码来源已明确为现代天文/民用时制，未假托古法。本次不扩展枚举，建议后续增civil_time_convention并统一分类。

独立复读更正：合盘默认来源的调用链定位改为实际`synastry -> _comparison_data -> _astro -> aspects`，未再使用不存在的astro_pair名称；词条数据未变。
