# P9 新构建器 checkpoint（非整阶段完成）

- 分支：v4/mod-organize；PR #10保持草稿，提交号以本次发布后Git记录为准。
- ExecPlan：docs/v4/execplans/MOD_P9_official_20261021.md。
- 完成：七类新typed builder、官方字面转义、update_multi、非空占位、inner/wire双预算、200组件与动作守卫；旧入口未改。
- 目标验证：`python -m pytest tests/v4/p9_official_v3/test_builders_mod.py -q --basetemp=private/mod-week/tmp/p9official-builders-0220 --tb=short`，63 passed/1.23s，含1000随机Unicode与实际回执/操作保留。当前文件Ruff/format通过。
- 独立旧守卫：test_legacy_freshness_guards_mod.py，98 passed/0.46s，含1000来源/依赖失效组、7scope、partial manifest、metadata篡改、unknown367天不得重发、int32 wire边界。
- 184项官方规范矩阵已先冻结，SHA256 `2fca0ce9b79c45a80106544e85de49c5d95f8a19a9f2317797578b61deec10bb`；矩阵存在不代表184项产品测试均通过，独立状态/wire验收尚在进行。
- 早期大参数测试未设置短ID，触发Windows pytest路径/输出问题；改显式短测试ID后复测。没有改变产品行为或放松预算断言。
- 覆盖报告：DAY_new_code_coverage.json记录此前119个新增产品文件的行92.01%、分支80.07%、综合88.84%，9085测试通过；该测量早于本P9新增入口，不将旧覆盖数字当v3覆盖。
- 未完成/未验证：CardKit v3恢复与namespace独立验收、协议组合全量、v3性能、主线实际接线/PG/HTTP/SDK/回调/飞书/真机、最新CI。真实模型/服务器/飞书请求与合并均0。
- 数据库迁移无；主线后续opt-in/回滚与未核实项见docs/v4/integration/mod/P9_official_20261021.md。当前不能依据本checkpoint宣告P9阶段Done。
