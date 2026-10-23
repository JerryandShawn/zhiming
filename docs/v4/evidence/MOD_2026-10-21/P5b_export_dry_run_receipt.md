# MOD P5b E 阶段回执（本地纯模块里程碑）

- 工作分支范围：`v4/mod-organize`；最后提交/PR #10草稿链接由root提交后补写，本agent未操作Git或核验远端CI。
- ExecPlan：`docs/v4/execplans/MOD_P5b_export_dry_run_20261021.md`。

## 完成了什么

- [x] 按33第四节6、P5b E、22§5完整阅读后先落计划与接口。
- [x] 显式synthetic中间格式→离线标签/话题ChangeSet候选，原话与来源anchor保持。
- [x] 当前host scope/row/source/revision/epoch逐项核对；默认不接受synthetic未显式授权的快照。
- [x] 弃权待整理、敏感/secret/撤销/无痕冲突；人工归区/已有话题不自动覆盖。
- [x] assistant仅继承合格前user候选，保留独立原话，不转成用户事实。
- [x] 当前预览、operation幂等、host ledger与逆操作计划；缺失/null逐字段区分，来源失效/并发修改/后来引用不出逆操作。
- [x] 本地合测156项通过，其中自测67、独立89；双方各含100组固定种子组合。
- [x] Ruff E/F/I/B/UP/SIM、format和完整类型/AST通过，9产品最大191行、函数56行。
- [ ] stage/真人历史/正式应用与实际撤销：按任务明确不做，仍归主线逐次授权。

## 评测分数

目标测试：`python -m pytest tests/v4/export_dry_run_v3 -q`，**156 passed / 2.02s**。
正式eval runner和CI未运行；不把这些目标测试冒称真实脚本或平台评测。
真实模型请求0；数据库/服务器/stage/飞书/网络调用0；真实导出读取0。
本阶段不做Q5准确率/ARI评测，也未读取Q5盲评正文、标签或报告。

## 关键文件

新增`mingjing_core/organize/export_dry_run_v3/`九文件，公开dry_run_export、preview_dry_run、plan_undo_dry_run。
新增本线测试、显式synthetic fixture、性能脚本和接线说明；独立验收文件由peer维护，原矩阵未改。
接线：`docs/v4/integration/mod/P5b_export_dry_run_20261021.md`。
产品聚合SHA256：`ae7a40dd8214197a3d383ad3e5643eb079b94302424aec4e7107964ac99bbf7c`。

## 性能证据

`docs/v4/evidence/MOD_2026-10-21/P5b_export_dry_run_performance_final.json`于07:59:50北京时间观测。
120消息链中位0.2831秒，最大0.2889秒，独立tracemalloc峰3608755字节；
500消息链中位1.2482秒，最大1.2636秒，峰12481694字节。
每项1次预热、5次墙钟观测与单独内存观测，含fixture构造/转换/预览/planned重放/逆操作计划及断言；源码hash前后稳定。
07:56旧报告保留为identifier hardening前观测，不能与终稿hash混用。tracemalloc不是RSS或生产性能承诺。

## 数据库迁移与回滚

没有迁移、数据库连接或实际应用；旧代码不变，当前撤下opt-in入口即可。
返回的ChangeSet不是用户批准、事务提交或运行权限。真实服务必须存批准指纹、当前版本与权威ledger。
测试和性能的post-state只是独立合成JSON副本，没有对真实数据执行应用或删除。

## 偏离设计与理由

真实v3导出格式尚未核实，本阶段限定新synthetic中间格式；不冒称已完成真人导出兼容。
只输出dry-run候选。敏感批准后的正式应用、用户编辑建议、真实批次撤销由主线审阅服务接线。
首轮strict JSON tuple编码bug修产品为list，不改真值。identifier加严后的测试用合法opaque thread ID隔离版本匹配；
原话混入metadata另有拒绝测试。独立并发move夹具补全合法目录，不放松产品规则。

## 未验证 / 已知风险

未验证真实v3格式、PG原子性/权限、stage规模、用户审阅页面、实际应用/删除/撤销、CI与整站接线。
Snapshot/ledger对象不自认证；必须由可信host从当前权威存储提供，不能信任模型/导出自报字段。
undo对global revision采取保守冲突策略，后续无关写入也可能要求重审；不能自动绕过。
03至07额度中断不作为持续开发证据。

## 需要用户或大脑决定的问题

本地dry-run范围内无阻塞问题。真人格式映射、stage/正式执行与敏感人工批准接线仍留主线，届时按规则单独授权。

## 建议后续

root提交本地里程碑并在错峰窗口回归；主线对接真实导出映射与审阅服务后再补真实隔离PG测试。
不将合成副本还原或本地绿色测试当作已完成正式迁移。
