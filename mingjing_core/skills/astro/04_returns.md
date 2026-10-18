# 太阳回归盘：时刻、地点与比较

版本：p8-skills-draft-2026-10-19-v2.2；状态：待所有者抽查的解释草稿，不是模型或现实预测验证。

## 方法步骤

1. 先区分本命、行运快照与太阳回归盘；回归需要求太阳黄经回到本命值的时刻，不能拿生日中午替代。没有回归产物只说明方法，不写个人结论。
2. 读回归解、数值残差、历表、黄道、显式地点和Placidus宫制，再与本命比较。地点会改变宫位，不改变地心回归时刻；高纬失败直接报错，不换宫制。
3. 解释只聚焦少数主题与现实安排。回归盘是传统年度象征技术，不是完整年度事件日程；不从单宫预测重病、死亡或投资结果。

## 需要的盘面字段

旧本命根对象：CalculationArtifact。`/data/planets`、`/data/method`、`/data/asc`、`/data/houses`只能作本命对照，不能据此宣称有回归解。

回归根对象为`P8ChartAdapter.western_timing`只读信封，technique=`solar_return`：

- `/data/actual_UTC`、`/data/root`：出生/回归实际UTC、周年锚点、跨年标记、残差和括区间。
- `/data/planets`、`/data/natal_sun_longitude`：回归十天体、本命太阳黄经。
- `/data/houses`、`/data/houses/location`：宫制、显式经纬度、宫头、ascendant、midheaven。
- `/data/method`、`/data/metadata`：具名方法、历表、Moshier潮汐/Delta-T及时间标准。
- `/data/return_year`、`/data/year_basis`：UTC生日周年标签；2/29遇平年锚点取2/28，前后5日唯一根，可能跨UTC年。
- `/data/aspects`、`/data/aspect_orb_degrees`：回归盘内相位；orb不是求根容差。

西占只用实际UTC，不套真太阳时。主线Agent与界面待接入；当前信封只读，不能自行保存资料。

## 各流派观点与分歧

回归地点、容许度与本命叠盘方法有分歧。Lilly Book III第CLXXII章给出太阳回到本命位置的定义和与本命比较的方法；这不是所有地点选择的统一裁定，也不替本项目数值求解背书。

## 适用前提

本命实际时刻和时区正确，显式地点已确认，专门回归产物求根成功。全部12宫头尚未与独立宫位实现逐项核验；数值残差不等于历表或UTC物理准确度。

## 反例与常见误读

太阳回归不必恰在民用生日当天，回归盘上升也不等于本命上升改变。生日当天行运盘不是自动精确回归盘。

## 表达示例

示例是措辞模板：〔c1〕/〔c2〕须替换成本轮已注册的计算依据别名；未注册就不引用，不制造〔r#〕。

“若本轮〔c2〕已有回归解，我会先说明实际回归时刻和取盘地点，再与本命〔c1〕比较。若没有这份产物，就先不说‘今年回归盘显示什么’。”


“若本轮已算出回归时刻和地点〔c2〕，咱们只挑一两个年度主题，与本命〔c1〕对照，再安排能验证的小行动，不把生日变成必须等答案的节点。”

## 对应的规则命中 rule_id 列表

本章不新增八字条件规则；本批U12只有八字，不补算其他体系或民间口诀。

## 参考来源

- [Ptolemy, Tetrabiblos (Robbins 译本)](https://penelope.uchicago.edu/Thayer/E/Roman/Texts/Ptolemy/Tetrabiblos/1A*.html)，Book I §§1–3：计算与解释边界背景；不作为回归求解或地点选择的出处。

- [William Lilly, Christian Astrology (1647)](https://www.worldastrology.net/wp-content/uploads/2008/12/CA-III.pdf)，Book III, Chapter CLXXII Of Revolutions，原书pp.734–737（本轮核对PDF第248–251页，0基247–250；第734页标题CHAP.CLXXII Of REVOLUTIONS）：太阳回到本命黄经与本命盘比较；不沿用疾病灾祸断语。

- [Astrodienst回归说明](https://www.astro.com/faq/fq_fh_return_e.htm)：年份与地点；[Swiss接口](https://www.astro.com/swisseph/swephprg.htm)§4、§9、§15：太阳过黄经、UTC转换、Placidus错误行为。±5日周年锚和闰日处理是项目约定。

以上白话为项目原创概括；公开转录不等于原刊校勘。传统概念不证明现实预测有效。

存疑/待核：古籍原刊校勘、解释的现实预测效度未验证；字段与版本以本轮实际产物为准。
