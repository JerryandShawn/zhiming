# MOD v2.3素材CLI阶段回执

- 分支 / 最后提交：`v4/mod-organize`；root统一提交/推送/Draft PR，本子任务没有执行Git。
- ExecPlan：`docs/v4/execplans/MOD_eval_material_cli_public_20261021.md`。

## 完成了什么

- [x] 完整阅读CLI、loader、report、observe与原112项测试后，先冻结8项独立公开预期和原16份来源SHA。
- [x] 新增8项：固定Clock双时区生成、拒覆盖保字节、绝对外路径拒绝、../逃逸拒绝、缺父目录拒绝、必需参数、帮助、干净子进程模块入口。
- [x] 首次harness导入错误exit4原证据保留；8项尚未收集，不是产品失败。只调整新helper/运行harness网络替身，真值/产品不改。
- [x] 原目标8/8与120兼容通过保留为历史，不能覆盖其当时依赖显式private basetemp的前提。
- [x] root确认默认CI无basetemp而原helper要求private；无写入公开反例已保存。这是新测试夹具差额，不是真实CI/CLI产品失败。
- [x] 仅新test模块增加自给private临时目录fixture，原8函数体/断言未改；不传basetemp的8/8通过0.43秒。
- [x] 最新单模块兼容120/120通过1.36秒，结束北京`2026-10-21T10:27:55.589625+08:00`。
- [x] 19材料集合/字节before/after一致；所有测试文件写入仅mod/private，外路径负例未创建文件。
- [x] CLI单文件覆盖：20/21语句=95.23810%，3/4分支=75%，综合92%。干净子进程main guard真分支不在parent覆盖采样内，未补成100%。

## 评测分数

这是CLI/readiness本地检查，不是产品runner验收：59条候选、189断言的报告仍为51未验证、1决定阻塞、
7依赖阻塞、0观察通过；未执行59条产品场景。真实模型、网络、服务器、PG、通知和平台请求均为0。

## 改了哪些关键文件

只新增测试/helper、计划、冻结矩阵和证据。原`tools/eval_material_v23`全部文件、原112项测试与素材未改。

- `tests/v4/eval_material_v23/test_cli_public_core_mod.py`，最新SHA`450f9322b952ea3afbeae8f46c89104722cb57e567363ef2834237aa8676537d`。
- 同test历史SHA`c88129e46c4945818b0457f554d58e34912d0c37a8c69a9f7b86b5f52013f151`；移除仅新增import/fixture可逐字节重建该SHA，8函数体和断言未改。
- `tests/v4/eval_material_v23/cli_public_support_core_mod.py`，SHA`d40a772bb5cc498e2a49a53f0b627bea1829ef2f4e4c1cca8e143e2adc346fd5`。
- 原CLI源SHA仍为`f262fa662fcff745c62867681d51f66ae93a31f6bc031198da2415cbcb89dcc1`。

## 证据

- `CLI_material_frozen_matrix_20261021.json`：SHA`44be447faaa1107705ce6a4a05ffea1f11a5400b8b1fcb767bc2a6f525015a60`，原样保留。
- `CLI_material_first_target_20261021.json`：首次harness exit4，尚未收集测试；原LF日志路径/hash在内。
- `CLI_material_target_after_isolation_20261021.json`：8/8与原来源不变证据，SHA`ee700b16ec2adab6b23f9a9bafc5a14f6011388d6ce64b79f16d2fe2f3f0319c`。
- `CLI_material_compat_coverage_20261021.json`：120兼容、19材料与单文件分母，SHA`47a60bc9984ea54f39071d05a179dcdbb73588b0813074736f2fbd530b8ca6c2`。
- `CLI_material_coverage_final_20261021.json`：覆盖原始JSON，SHA`8b8c2564bc8568e5b22de00d1b1687a4f6b48e92b3ef66ad4dde1d27ff7b6bfe`。

上述10:22兼容/覆盖均保留为历史，不冒充新fixture实测。最新补充：

- `CLI_material_private_fixture_counterexample_20261021.json`：无写helper反例、CI/sharedconftest与旧源SHA，SHA`9fba2c1f64e66c29ae2e5c934e9a46cb87895dfed291d61ae57b964d4d3411fc`。
- `CLI_material_private_fixture_target_20261021.json`：不传basetemp的8/8、6个private唯一目录、8函数体原样证明，SHA`fff9823580fc76086c09a7c9e2d496226fc79432eb59c131409ac79757f8f2ca`。
- `CLI_material_private_fixture_compat_coverage_20261021.json`：新120/19材料及旧新test SHA，SHA`0a1a94b15e67838b8ae21278fecac23507df93883b2a0c30d8f030141ef16d34`。
- `CLI_material_private_fixture_coverage_final_20261021.json`：最新CLI单文件20/21行、3/4分支，SHA`f97d31e013cc731d2982c4f75c5fa5e15231ae66448468b370faf402cb2273c6`。

公开JSON均为UTF-8 LF。计划在测试后更新，冻结矩阵中的计划SHA是测试前版本，不声称始终匹配未来活文档。

## 数据库迁移与回滚方式

无迁移、无产品接线。新增测试和证据可独立撤回；不覆盖原报告、不删除已有数据。

## 偏离设计的地方

无产品改动。测试隔离保留socket类，仅阻止外连方法/DNS，避免破坏合法依赖导入；子进程另设同样离线保护。
新fixture显式`mkdtemp(dir=ROOT/private/mod-week/tmp)`，不使用调用者basetemp；唯一目录保留，不删除数据。

## 未验证 / 已知风险

本次覆盖只针对CLI一文件；不是全部工具或全Core覆盖，没有全项目回归、真实CI或性能结论。
必要120兼容的basetemp仍给原112项使用；新8已另在不传basetemp时验证，TEMP/TMP也保守指向private以防意外OS外写。
报告正确生成与artifact SHA不能认证产品、PG或人工复核；原固定阻塞及J01/J02 record_only保持。

## 需要用户或大脑决定的问题

无。

## 建议后续

由root把新独立测试、helper及冻结矩阵纳入完成模块材料绑定，统一静态/合法窗口回归后提交推送。
