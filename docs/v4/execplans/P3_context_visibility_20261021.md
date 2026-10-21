# P3：事项可见范围变化必须开启新的 L5 epoch

遵循 `.agent/PLANS.md`，时间统一北京时间。仅本机隔离PG/ScriptedPort，无外部模型、飞书或服务器；root负责此片。

## Purpose / Context

真实 case_update 完成后从选中事项切回未选事项查询，BoundedSources正确隐藏带事项绑定的历史，但旧缓存只按人生线程识别，错误抛出context_l5_append_only_violation。Z2要求失效后开启新epoch；不能把隐藏的旧正文重新塞回请求来满足append-only。

复用ContextEpochService.preview/mark_sent、ContextEngine._assemble、RequestLedger.reserve。可见范围取服务端已校验case_ids的集合；不取模型自报。缓存仅追加body-free可见范围指纹，不改ContextEpoch dataclass、冻结信封或已保存模型/上下文快照字节。

## Progress

- [x] (2026-10-21 07:48 +08:00) 两条真实双轮Runtime反例失败：合法paused/closed写入成功，下一无选中事项run在初始上下文阶段失败，尚未到最终引用门。
- [x] (2026-10-21 07:51 +08:00) preview与真实发送按相同服务端case_ids集合重核；不同范围或旧缓存缺身份时保守重开epoch。
- [x] (2026-10-21 07:51 +08:00) 原append-only、撤销、并发发送、双轮Runtime及pending证明最终81通过/22.15s，0skip/告警；Ruff/格式/尺寸通过。
- [ ] 提交后固定头全量与Linux精确CI仍待验。

## Plan / Validation

先修范围身份再重跑原双轮反例，不能设xfail或改成绕过Runtime。预览和发送都比较同一canonical指纹；顺序不同的同集合不重开，新增/移除选择重开，原消息正文/版本不改。旧缓存缺身份只重开一次。原来源/隐私/租约/epoch/发送指纹校验保留；无法解释的同范围L5改写仍硬拒。

## Surprises & Discoveries

范围过滤不是撤销：原消息仍有效，因此原verify_versions检测不到视图变化。生命周期合法索引引用与L5范围缓存是两个独立门，先隔离修复后分别验证，不用组件绿冒充完整双轮。

## Decision Log

2026-10-21 主线：以已校验服务端case_ids作为缓存可见范围身份；沿现有sources_changed失效分支重开，不放宽任意L5改写，不新增依赖或公开Schema字段。缺旧范围证明的缓存保守失效，不改写旧发送账本或模型请求快照。

## Outcomes & Retrospective

事项范围过滤属于可见视图失效，不重新暴露旧正文。真实双轮暂停/关闭后查询索引已通过，旧无解释改写仍拒；完整81项目标范围见evidence/P3/2026-10-21-context-visibility.md。本轮立即引用原e#另有未修证明缺口，不称全部事项闭环或全量绿色。没有迁移/部署/真实调用。

## Recovery

线程缓存增加元数据，不改历史迁移。回退代码不删旧消息或已发步骤；重新启用仍对缺范围身份缓存保守失效。每次mark_sent保留owner事务、lease与线程advisory锁。
