# 准确时刻优先：文档与时间口径核对

版本：p8-skills-draft-2026-10-19-v2.2；状态：解释草稿。按用户D3，已有准确出生时刻时先核对记录与换算，不做大事倒推。

## 方法步骤

1. L0先核对出生医学证明、医院记录或家人记忆的来源与确定程度。AA/A级记录按项目来源等级优先，跳过人生事件吻合度，以记录为准；这不是对真实Rodden全部评级的照搬。
2. L1由程序解析出生地时区、当时夏令时、重复/不存在时刻。23号裁定默认真太阳时主解读，北京时间UTC+8结果不同则并列说明“按北京时间则为……”。当地标准时仍供核对，海外不能把它冒称北京时间；不擅改旧v3。
3. 程序生成时柱/日柱/月柱分组与节界不确定分支。只把本轮实际time_basis/items和charts数据当依据；有限采样稳定不证明连续范围完整。单一物理时刻已确认且各口径时柱一致时，可说明“时柱稳定，无需校正”；仍有fold/gap或记录依据未知时，不能用时柱一致代替核对。

## 需要的盘面字段

根对象：`P8ChartAdapter.time_basis(request)`只读envelope，非CalculationArtifact。请求带owner/subject/revision/operation_id/as_of_date和birth的date、reported_time、place(tz/lon/lat)、clock_basis、gender、precision=reported；as_of_date由调用方Clock给出。

- `/time_basis`：换算items/instants与方法、警告。
- `/charts`：逐口径data与ziwei_column。后者独立列示，不与八字得分相加。
- `/interpretation`、`/profile_basis_record`：主解读图、北京时间差异与所用口径的只读档案建议；没有持久化。
- `/release_policy/rectification`：倒推冻结为实验、默认隐藏，仍诚实拒绝。
- `/profile_update_allowed`、`/life_event_scoring_performed`：均为false。
- `/model_calls`、`/writes`：均为0。

当前只读入口核对已报告时刻。夏令时fold仍保留多个实际UTC分支，gap要求核对记录，不因默认口径而自动选时刻。倒推为低优先冻结实验，默认隐藏；档案持久化/API/UI待主线接入。

## 各流派观点与分歧

北京标准时、地方平太阳时、真太阳时及晚子时日界有不同口径。程序能证明换算和结构差异，不能证明某派唯一正确。文档记录与时区/均时差计算的证据层级高于主观“像不像”。

## 适用前提

出生地和钟表基础由本人确认，不默认城市，不把未报告时刻补为中午。资料确认、precision=rectified与档案写入走主线确认服务；只读工具没有写入权，也不能说已改出生资料。

## 反例与常见误读

原“评分→前三候选→合成前三命中率”的方法已被撤回。由同一规则生成事件再回收只证明实现一致，不能证明校正有效；本章不再把25%随机前三作为有效性论证。可靠记录不应因为某盘解读好听就被替换。

## 表达示例

“你有准确记录，我们先以记录为准。〔c1〕核对的是当时钟表时间与不同太阳时口径；有差异我会并列说明，现在没有做人生事件评分，也没有改你的资料。”


## 对应的规则命中 rule_id 列表

本章不新增八字条件规则；本批U12只有八字，不补算其他体系或民间口诀。

## 参考来源

- 设计真相源：18_提示词增补包/P8_增补_时辰校正.md §B/C/H及17号§2；工程步骤与来源等级为项目设计。
- [IANA tz数据库asia原始规则](https://github.com/eggert/tz/blob/main/asia)，PRC与历史时区规则；具体换算必须读取锁定tzdata，不由模型心算。
- [NOAA Solar Calculation Details](https://gml.noaa.gov/grad/solcalc/calcdetails.html)，均时差计算方法背景；不证明任何传统解读的预测效度。

存疑/待核：IANA历史规则、太阳时近似与流派日界不能代替出生记录核验；存在fold/gap或记录依据未知时仍须保留确认状态。真太阳主口径是已裁定的项目选择，不是流派唯一正确的证明。
