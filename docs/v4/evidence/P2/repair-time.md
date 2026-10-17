# P2 同轮修复时间身份与安全持久化

仅本机隔离PostgreSQL、真实Core/LangGraph/ConfiguredModel协议解析与假HTTP，真实模型调用0。

## 实际问题与修复

旧553首轮的5个repair恢复error源自now含ISO微秒，每次重建使同epoch完整repair_identity变化。独立真实函数/renderer AST复现仅Clock增加1微秒便触发严格guard。没有放宽hash、预算或合法恢复证明。

第二次完整553另有4个native ID errors与3个取消/过期failures：普通put写新时间行额外增加语义revision，native claim_id因此变化；提前写行使取消前出现runtime_step。显式selection.date固定，**不是午夜日期**。保留sealed fixture/精确ID与取消0steps断言，修复元数据生命周期。

最终路径：

1. intake先以当前owner/run/epoch/lease只读已有时间，或在内存捕获Clock.now，生成now/today。
2. _call仅新增可选program_at参数，在**本次**diagnostic已成功保存之后、同lease事务内用固定program_time专用writer保存ISO。成功与已记录network/503/zero-tool/契约失败均保留；未知未诊断异常不借历史日志写入。
3. writer只写既有runtime_step固定stage、稳定run/epoch ID、只含ISO时间；不增语义revision、不计模型预算、不覆盖旧锚点。普通entity put照旧。owner/epoch/lease/ISO校验均失败关闭。
4. 同epoch synthesis/review/repair复用时间；新run、新stale epoch重新取Clock。取消/过期/错误lease在安全边界前拒绝，零额外步骤写入。

该_call接线为payload时间生命周期的一项窄范围偏离，记录于ExecPlan供大脑复核。未改from_base、模型构造、预算、repair hash/身份或原校验逻辑。P1合并时须保留provider诊断与此钩子。

## 定向证据

- 原native精确ID四例通过13.803s；未改fixture或映射规则。
- 原native四例+取消/失败诊断两method+repair11项，合计17 tests通过22.630s，全部原断言保留。
- PG13项通过11.78s：同轮repair推进1天+1微秒仍完整payload/identity相同、累计4calls；新run/新epoch新时刻；元数据幂等且owner revision不变、普通put仍增；错误lease/epoch/owner/time拒绝；首intake network/503/zero-tool/contract失败后推进Clock重试完整payload相同；首次intake cancel/expire保留1次charge、0runtime_step。
- 独立真实_call AST九边界：成功/四类已诊断失败各charge1+diag1+anchor1；未知异常charge1+diag0+anchor0；取消/过期charge1+diag0+anchor0且LeaseConflict；错lease三者均0。

边界：仅锚定本轮now/today，不冻结整个snapshot。PG完整payload相等结论针对事实等输入不变的合成场景；事实有效期仍取当前Clock，真实依赖变化仍应触发原严格版本/hash校验，不能借此打开第二repair。

最终完整553/v4与CI以validation.md/receipt.md为准；失败和中止轮不计为通过。
