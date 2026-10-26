# 离线交付样例：请求与原生内容绑定复核

日期：2026-10-19。范围仅 `benchmarks/handoff_*` 的离线语义检查；没有更改排盘算法、知识表、Schema、样例JSON、API或主线。没有重新构建样例、模型调用、服务器访问或数据库写入。

## 已复现的缺口

在内存中读取既有样例，仅修改顶层request而不重算任何hash：

1. `ayuan_bazi.json` 或 `ayuan_ziwei.json` 的 `request.target_date` 改成2027-10-19，旧检查仍通过；原生 `calendar_layers.day.date` 及规则依据仍为2026-10-19。
2. `ayuan_astro.json` 的 `request.birth.place.lat` 改成-20，旧检查仍通过；实际profile输入和宫位仍使用成都纬度30.67。
3. 三份样例的 `request.birth.gender` 改为女，旧检查仍通过；源内容仍是按原男性参数得到的八字大运/紫微列。

这组缺口是请求标签与实际内容没有完整绑定，不需要攻击者重算内容hash。旧归属、UTC、引用、规则true、有限JSON等检查仍有作用；内容hash本身也不提供来源签名或授权。

## 修复后的明确边界

`validate_preview` 现在明确限定为 `handoff_build.build_preview` 的 **canonical 阿远固定合成请求**，不是任意人物或日期的通用校验器。原生time_basis未回显所有原始输入字段，不能宣称仅凭可见字段已完整验证任意出生资料。因此先核对builder当前固定birth、target_date、time_scale及物理UTC字符串表示；出生日期、报告时分、IANA时区、clock_basis、gender、经纬度都不能被另行改写后继续沿用旧盘。

固定输入为07号的阿远：1994-03-12 08:20、男、Asia/Shanghai、经104.07纬30.67、clock/reported；目标2026-10-19、实际UTC `1994-03-12T00:20:00Z`，time_scale为 `natal_with_explicit_target_layers`。其它合法输入或等价但不同的表示形式需要另行设计通用接口，不能拿这个固定样例校验器当主线API输入验证。

在固定请求核对之外，继续检查原生产物内部对应：

- 每个time_basis分支的 `calendar_layers.day.date`、整数 `requested_gregorian_year` 与目标日一致，诊断分支也不能混入其它目标年；布尔值不能冒充年份整数。
- 西占profile实际输入及declared_birth的经纬度与该固定请求一致；实际目标日、声明日期/时分、采样日期/时分、阳历类型与UTC偏移声明也需一致。保留原有UTC换算检查。
- 次限的实际target_at为固定目标日UTC零时；太阳回归的周年标签为目标年份，地点为本合成样例**显式选择**的成都。这个校验不表示真实回归地点自动等于出生地。
- 原有scope、源码hash、document/claim内容hash、规则与证据Pointer检查仍执行。

通用用户资料的授权、实际输入回显与绑定、撤销/修订、来源签名和生产网络边界仍交主线设计；本补丁不证明排盘数值的外部准确度或现实预测效度。

## 验证

命令：`pytest tests/v4/test_p8_handoff_preview.py tests/v4/test_p8_handoff_request_binding.py -q`

结果：**99 passed，0 skipped，2.56秒**。其中新增专属测试52项，覆盖所有birth字段与目标/时间标签的改写、重新绑定文档hash后的原生日期/输入/西占时序错配，以及三份原样样例继续通过且不被修改。未运行全量v4；全量检查由root统一执行。

新增/修改四个Python文件通过Ruff与88列格式检查；各文件≤400行、函数≤60行。`git diff -- docs/v4/contracts/samples docs/v4/contracts/chart_compute.schema.json`为空；三个原JSON字节保留。样例当前源码hash验证仍通过，没有改动算法fingerprint。

## 给主线契约文档的准确补充文字

附带的 `validate_preview` 语义检查只用于当前builder生成的canonical阿远固定合成请求及其表示形式；它会拒绝其它人物、日期或时间标签。Schema本身仅约束结构；固定输入核对后仍检查原生目标日、西占实际输入与地点、时序目标、内容hash、scope和依据引用。原生time_basis没有完整输入回显，所以这不是任意请求的通用校验器。主线通用接线需要单独设计实际输入回显和内容绑定；不得照搬固定合成输入白名单作为真实用户API。
