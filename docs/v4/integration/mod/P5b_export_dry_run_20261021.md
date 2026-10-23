# P5b E：合成v3导出dry-run候选接线

依据33号第四节6、18/P5b E、22号§5。入口为新增包
`mingjing_core.organize.export_dry_run_v3`。这是离线转换器，没有apply、删除、数据库、文件扫描、网络或模型入口。
不修改原organize、Q5、supplement、memory2或P9。

## 真实边界

本次只定义并测试`zhiming.v3.synthetic_export.v1`中间格式，尚未核实真实v3导出工具的格式。
合成正文集中于`tools/eval/fixtures/mod_20261021/v3_export_synthetic.json`；独立验收另有明确synthetic fixture。
synthetic标记是host的责任，程序不能凭一个布尔值证明文字是否来自真人。不得把真人正文贴入此入口试跑。
真实导出映射、stage副本、用户逐批审阅、生产应用与实际撤销都归主线，未接线、未验证。

## 公开接口

`ExportSnapshot(scope, revision, source_epoch, document, sources, operations=(), synthetic=False)`

scope复用MemoryScope；sources为当前MemorySource元组。document为完整messages/topics JSON投影；所有输入深冻结。
synthetic默认False并拒绝，测试必须显式True。Snapshot是host当前权限/数据投影，不是自认证授权。

`dry_run_export(payload, *, snapshot, scope, clock, operation_id) -> DryRunPlan`

`preview_dry_run(plan, *, snapshot, scope, clock) -> dict[str, object]`

`plan_undo_dry_run(plan, *, snapshot, scope, clock) -> UndoPreview`

不读取环境变量，不配置ONNX，不下载模型。Clock必须显式注入；时间按原UTC毫秒与原source.at核对，
不以执行now替代原消息时间，也不依赖本机东京时区。

## 输入中间格式

根字段必须恰好为schema、synthetic、export_id、owner_id、subject_id、revision、source_epoch、messages。
schema固定`zhiming.v3.synthetic_export.v1`，synthetic必须为true，messages为1至10000条。

每条message字段必须恰好为：id、owner_id、subject_id、revision、source_id、source_revision、role、content、at_ms、thread_id。
role只支持user/assistant，不把system/tool或空消息默认为用户原话。未知结构拒绝，真实导出映射须由主线补齐。
export/message/source/thread/operation ID是1至200字符ASCII opaque ID，正则为`[A-Za-z0-9][A-Za-z0-9_.:-]{0,199}`。
拒绝把原话混入metadata标识；owner/subject只与host scope逐一比对，不从昵称猜身份。
同批message ID和source ID均不重复。

snapshot.document包含owner_id、subject_id、messages字典和topics字典。
每条当前message必须有上述原始字段，加status=active、incognito=false、retention_scope=persistent；
可选current=true。来源角色、全文、时间、版本和来源ID须与当前MemorySource逐项一致。
撤销、删除、无痕、临时、optout、source future、secret、敏感与出生资料会成为固定原因冲突，不进入操作或样例。
跨owner/subject在任何一行或来源出现，整批固定错误，不返回部分私密预览。

标签before值保留字段缺失与显式null。既有null route_confidence仅作为before值接受；新confidence仍是有限0至1数值。
旧人工归区或已有关联话题不会被覆盖，整候选话题标existing_route_requires_review。
候选topic ID已占用也返回冲突，不覆盖已有topic。

## 分类、回答与预览

只用冻结Q5分类user文本，并复用冻结本地聚类；不调参数，不读盲评B，不声称这套合成功能测试证明分类准确率。
abstain进入waiting，不改归日常。助手回答只能继承同线程中严格更早、最多6小时内的可用user候选。
被阻断的user重置继承链；孤立回答、同刻回答和低置信前文进入waiting。
助手仍有自己独立的原话anchor，永不生成MemoryFact或伪装成user断言。

预览重新读取当前snapshot并重建候选，不能返回旧存储样例。公开keys为：
dry_run、requires_user_review、operation_id、batch_id、fingerprint、expected_revision、source_epoch、counts、topics、
waiting_ids、conflicts、case_migration_strategy。
topics只含ID、区、≤80字标题、消息数、原时间范围及≤80字user样例；冲突只有ID与reason_code，无原话。
不会在异常或repr中打印正文。样例是受owner授权的私密审阅数据，仍不得写日志或追踪服务。
case_migration_strategy固定not_decided_here；不替主线决定case迁移二选一。

## operation与撤销候选

operation_id稳定绑定输入、scope、revision、epoch、变更集、样例及来源anchor摘要。
`DryRunLedger(operation_id, input_fingerprint, plan_fingerprint, state='planned', applied_revision=None, target_revisions=())`
来自可信host。planned同operation/input/plan可重放，返回replayed；更换输入/计划或undone后重用都会拒绝。
applied后的旧review版本不能重新计算成新批次；主线应取回已存储计划，而非重跑覆盖。

撤销只生成inverse_ops。需要host applied ledger匹配，applied_revision大于原expected_revision，
当前snapshot.revision恰好等于applied_revision，epoch不变；target_revisions必须覆盖全部受影响message。
每行当前revision须等于ledger中真实post revision且不低于原revision，不猜标签写入一定使message revision加一。
还要核对原话、来源版本/活性、当前after字段与新话题的后来引用；任一冲突则不返回逆操作。
undone重放只返回already_undone，不重做任何操作。

ChangeSet/FieldValue复用旧标签候选，保留missing/null逆操作。这里的对象和哈希不是用户批准或数据库提交证明。
没有调用MemoryChangeStore.apply/revert。测试与性能中的post-state只是独立合成JSON副本；不能据此声称已验证PG撤销。

## 主线需要补什么

主线新增受保护的真实v3导出映射，建立当前owner/subject与来源查询；不能信任导出JSON自报的owner或模型提供的Snapshot。
审阅页必须显示冲突、待整理、摘要与编辑结果，用户逐次确认后才允许真正应用。
敏感二次确认、修改既有人工归区、用户编辑计划与当前源重新核对由审阅服务处理，本转换器不提供自批入口。
正式应用须在权威PG事务内检查request/operation、expected_revision、source epoch和全部当前source/row版本，
只新增标签/话题，保存批准后的完整指纹与实际post revision ledger；禁止修改或删除原始对话。
真实撤销应重新装载该ledger与当前源，冲突交给用户；不能把inverse_ops当成可绕过来源撤销的脚本。

本阶段无需数据库迁移或线上回滚。停用新入口不影响旧流程；未来已应用批次只能通过审阅后的权威服务撤销。

## 验证与证据

目标自测覆盖scope/源/时刻/角色/敏感/人工标签/幂等/字段presence/并发引用/逆操作，含100组固定种子组合。
独立验收89项通过，原20组规范矩阵未改；唯一测试夹具修正是把并发move补成消息与话题一致的合法目录。
最后整体数字见阶段回执与root回归，不把本地目标测试当作CI、stage或真实数据库证明。

性能脚本为`tools/mod_week/benchmark_export_dry_run_v3.py`，测120/500条消息的真实转换、当前预览、planned重放与逆操作计划。
每项1次预热、5次墙钟观测，单独tracemalloc峰值；包含合成fixture构造与断言。
`P5b_export_dry_run_performance.json`是identifier收紧前观测，保留历史，不与最终源码混用；
终稿使用`docs/v4/evidence/MOD_2026-10-21/P5b_export_dry_run_performance_final.json`及其source hashes。
tracemalloc不是进程RSS，也不是生产服务或真人历史上的性能承诺。
