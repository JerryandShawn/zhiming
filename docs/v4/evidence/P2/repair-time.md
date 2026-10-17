# P2 同轮修复时间身份回归

仅本机隔离 PostgreSQL、真实 Core/LangGraph/ConfiguredModel 协议解析与假 HTTP，真实模型调用0。

旧 Core 首轮553有5个repair恢复error（network、503、zero-tool以及重复transient standard/deep），根因是每次 `_synthesis_payload` 调用 `now_context` 重建含ISO微秒的now文本，完整payload纳入repair_identity，因此同epoch后续合法重试被严格guard拒绝。

独立只读审计用真实函数AST与真实renderer证明：仅Clock增加1微秒，now/hash均改变，calls=3/limit=6、合法network旧诊断仍被拒；没有改数据库/模型/预算来迁就。

修复：既有runtime_step按run+epoch保存program_time ISO（来自Clock.now，遵守FrozenClock）；payload里的now、intake.today复用本轮时刻。新run新取时；stale新epoch不会复制这个stage，也新取时。原repair hash包含完整payload/schema/system policy，预算与幂等校验保持原样。

验证：

- 原 `tests.test_core_repair_recovery` 11 tests通过9.453s，包含503/network/zero-tool恢复、预算封顶和不合法身份/契约拒绝；未修改该文件。
- `test_p2_program_time.py` 2项真实PG通过4.15s：固定2030 Clock后网络transient，推进1天+1微秒重试，未变化事实输入下两次完整repair payload相同、identity只有1个、累计calls4；新run读新时刻。stale epoch1保留intake但时间重新取，repair_used/calls仍保留。
- owner纽约跨日实际服务payload `today` 与now日期一致；默认Shanghai保持。

边界：只锚定now/today所用的本轮Clock.now，不冻结整个snapshot。事实有效期仍依当前Clock计算；若真实事实/来源/可见性发生变化，完整payload/版本校验仍严格拒绝不相同的修复，不能借时刻锚定绕过变化。

最终完整553/v4结果见阶段回执；首轮失败及中止轮次不计为通过。
