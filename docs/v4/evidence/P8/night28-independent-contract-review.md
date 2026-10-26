# 28号四工具独立契约复核

复核完成：2026-10-20 23:20:46 +08:00（北京时间）。源码冻结期间只读检查；单个Core进程，未启动Charts、未跑pytest全量。

## 结果

**10份实际样例全部通过，0发现错误。** 样例范围是7份daily_transit、1份window_search、1份almanac、1份synastry。
另对synastry合成输入按Schema的Request定义验证，7日日报manifest与结果ID/数量逐项一致。
全量回归是否通过、原生计算准确度、Agent与线上接线状态由root另行报告，不由本审查冒领。

| 样例 | 命中 / c / r | LF内容SHA256 |
| --- | ---: | --- |
| `daily_transit/ayuan_2026-10-21.json` | 40 / 64 / 40 | `0b0984e1a6cf9c48f060071e861da1438d9ee2122a7635095d7f71933a589205` |
| `daily_transit/ayuan_2026-10-22.json` | 37 / 63 / 37 | `1de44c4f5268b6b660ce982064e2fd34b3f2bdfd9cc333cbbe9a8df789778576` |
| `daily_transit/ayuan_2026-10-23.json` | 39 / 65 / 39 | `98ffeb68f3a9d47e0f3c4fab607672e11d78c532d0ef3b8d00dc7a3e2cb8d4d8` |
| `daily_transit/ayuan_2026-10-24.json` | 40 / 67 / 40 | `f20ec9d7c6d5d91ef82e8eaf32235632cf5de95dcf0e5417833ef0b7eeecf353` |
| `daily_transit/ayuan_2026-10-25.json` | 37 / 64 / 37 | `a5c04a2a7d9bb0208e7a5dc0322cedc076a7042c567503f99765df60de0df98f` |
| `daily_transit/ayuan_2026-10-26.json` | 38 / 63 / 38 | `c6a0b32d6badad1cadaa9dad6897e401ced79fe53141e6847d9e247271cde6ac` |
| `daily_transit/ayuan_2026-10-27.json` | 36 / 63 / 36 | `3886f6377f50e14ad25e876c04b6e7d064054341949d057f9aff87e69629d5cc` |
| `window-search-ayuan-contract-20261021-27.json` | 267 / 268 / 267 | `d6c9f82c01fb5be2b24d3c5efce27c4c4ac1cb7638dc2e201618bd14b36d9867` |
| `almanac-20261021.json` | 6 / 7 / 6 | `b309c5742eab56c8a2b80fa0925bb779135fd12a6dd289e449c1250c492a7b42` |
| `synastry-ayuan-xiaohe.json` | 45 / 68 / 45 | `5e707188c19c01948312c66e9b83ed20064bd01b6573905e93f808af3f780254` |

## 独立验证的方法

没有调用产品tool_evidence、评分函数、相位函数或历法函数来验证它们自己。使用独立的json/hashlib/math实现既定契约：

1. 四份Schema自身通过Draft202012Validator检查；逐样例结构验证。递归检查数值有限、对象键为字符串。
2. 按版本/scope/data/rule_hits/sources重算文档ID；独立严格RFC6901解析证据Pointer，拒绝非规范数组索引和非法转义。
3. 所有c别名按实际证据路径排序、覆盖全部路径；重算值SHA和claim_id。所有r逐条绑定真实met=true、有school/source的命中，重算值SHA/claim_id及其c依赖边。
4. 每份effects严格为模型0、写入0、ephemeral_only。算法说明与来源不是现实预测效度的证据。

累计66,350次断言求值包含递归JSON键、Pointer等基础检查，**不是66,350个独立测试用例**，也不是预测样本数。

## daily_transit七日核对

日期严格覆盖2026-10-21至27；每份为北京时间12:00并对应UTC04:00，主坐标true_solar。
使用十干次序、五行生克与阴阳关系独立重算年/月/日流干及所选藏干十神，逐项一致。
逐层核紫微年/月/日各四化的顺序、真实星曜Pointer、实际本命宫索引/宫名、运限宫名；没有把运限名冒充本命宫。
独立按两组黄经求最短角距、五大相位误差及容许度，检查纳入完整性和每项数值；与结果一致。
八字规则必须有本命与目标成员；成员未齐的关系保留complete=false，不把其命中解释成三合/三刑全部成立。

## window_search权重、血缘与分页核对

7日摘要全覆盖、分数降序/同分日期升序、全局rank连续；当前页offset0、limit31、returned7，无后页。
每个候选的正/负/中性贡献号、索引和根命中一致；逐条独立按公开权重与目标层因子重算，不完整组强制贡献0；候选总分与摘要的正负和一致。
所有观测的原daily命中和实际字段均与对应日期的独立daily样例一致。两种样例operation_id不同，所以先把daily scope替换成window scope再独立重算源文档ID，全部匹配。
事实副本SHA、来源Pointer作用域、摘要/权重trace摘要一致。查询trace另外由window scope + 合成阿远出生输入 + 声明范围/用途/权重重算，得到 `61991929ad5b224690a9eb335ac1e25ec18a1d651048d65aae29c40c1ca19ec4`，匹配。

**分页公开样例缺口：当前只有这份7天第一页JSON，没有独立公开的第二页或空页JSON。**
本次检查了现页返回数量、next_offset/has_more和页内r映射；不能把它说成已经验证跨页native调用或最坏31日体积。
现有分页单元/原生测试和年度体积测量由对应里程碑证据给出；建议后续增加第二页及末页之外空页样例供前端直接读。

## almanac核对

日支+6模12得到冲支，独立三合局煞方对应一致；采样、sect=1与民用日方法一致。
按完整相对源码文件摘要图独立重算library_source_sha256，匹配；所有字段命中指向真实字段和方法依据。
本次未重新调用lunar库，原生字段一致性证据仍使用此前24项定向测试，不把JSON自洽冒充新一次原生比对。

## synastry核对

成功结果consent精确user_confirmed，kind/as_of_date与合成输入一致；owner相同且subject/revision/operation的a/b顺序正确。
两侧真太阳主坐标与实际UTC不混用；西占natal_at_utc等于同侧真实出生瞬间；独立相位几何逐条一致。
日干五合、8项表层五行计数、候选与对方透干交集独立核对，均一致；aggregation保持并列候选并集而非共识。
紫微两侧实际夫妻宫与他方命宫名称、宫支相等布尔、共享星名集合都一致；compatibility_score严格null。
没有发现用合盘结构冒充关系成功分数的输出字段。拒绝前不计算的行为由此前原生/适配器测试验证，本次只核成功样例与输入契约，不重复声称执行了拒绝路径。

## 限制与待核

这是已发布合成JSON的独立结构/数值/来源绑定复核，没有运行独立历法或另一套星历。固定合成人物不能代表全部出生边界。
原典版次页码、传统预测效度、主线授权/撤销账本、运行时依赖更新后的指纹、HTTP体积与真实前端读取仍需各自证据。
未修改charts、knowledge或tests；仅写本报告及本机private校验脚本/结果。模型请求0、Charts运行0、服务器/飞书访问0、产品写入0。
