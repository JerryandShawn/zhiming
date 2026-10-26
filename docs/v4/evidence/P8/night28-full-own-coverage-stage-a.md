# 完整自身代码覆盖阶段 A：静态 inventory 与候选计划

记录：2026-10-21 01:24（北京时间）。阶段 A 独立验证通过；B1/Core 和 B2/Charts 的覆盖采样均未批准、未执行。Charts 解释器、trace、真实模型、网络请求均为 0。

## 交付与来源

只新增 `benchmarks/line_coverage_own_sources.py`、`line_coverage_own_inventory.py`、`line_coverage_own_plan.py` 和专属 `tests/v4/test_p8_line_coverage_own.py`；不修改 v1 固定 6c 工具/回执、worker、v3、CI、锁文件或样例。根代理先发布 ed5182 里程碑后才移入；此前一直保存在 private 草稿中，因此不借原 2728 全量或 80 脚本结果作为这些新模块的验证。

根代理批准采用 P8 首次实现前 `7fa5e10a4dbe0e2878e28c6f6a115f17d013aaa2` 作为历史归属起点，f23 仅作初版结转的参考，不得当完整起点。所有入口必须显式传完整 commit SHA，无 HEAD/短 SHA/自动升级默认值。

本次静态产物固定已发布 `ed5182001df2c98893159f2dca023e5920e562e7`：

| 分组 | 文件 | 完整文件可执行行 |
| --- | ---: | ---: |
| Charts适配器/规则/实验工作台 | 59 | 5,319 |
| 八字初版补充计算 | 7 | 500 |
| Core技能/一致性/学习 | 11 | 1,324 |
| 研究/重放（含已提交v1覆盖工具） | 51 | 5,631 |
| 原生/集成测试 | 13 | 1,729 |
| v4测试辅助 | 3 | 187 |
| v4测试 | 70 | 8,038 |
| 初版验证工具 | 1 | 153 |
| 合计 | 215 | 22,881 |

初版结转 10 文件保留；没有执行观测或覆盖百分比。完整性只指该显式提交的当前 P8 历史归属 Python，未导入文件也完整列入；不是当前全部工作树已覆盖。**新增 A 的 3 模块、作者/独立审阅新增测试尚未进入 ed5182，提交后必须重新显式指定新提交重建清单，不能继续拿 215 冒充未来固定数量。** 旧提案 214 对应 ef5，仍是正确历史。

## 真实 blob、边界与静态计划

Inventory 逐文件含原始 Git blob identity/raw SHA256、归一 LF SHA256、完整文件 CPython3.11 正行号与分组；从固定 Git 重建而非信任调用者摘要。固定历史范围之外的新 Python 要求范围复核，不能静默排除以抬高比例。非正规 Git blob/链接拒绝；区间内先新增后删除的文件也进入删除台账，不因净 diff 已消失就漏记。当前 ed5182 删除台账 0，已有未改 Python 排除清单 202，静态源/pytest配置守卫 418。

Plan 仅 AST 解析候选的确切函数/方法、参数及生命周期 hooks，绑定源码/配置摘要，不导入目标、不收集或执行测试。当前只登记历史 Core 3 个 E2 无 fixture 候选和 Charts `NativeDailyTransit::test_daily_day_pillars_advance_one_sexagenary_step` 1 个方法，统一 `execution_approved=false`、`coverage_collected=false`。候选不是执行许可；AST 不证明间接 helper/import 无副作用，此限制写在每份计划中。原生 class 的 unittest.TestCase 形状需要核对，不能跳过 setUpClass 等真实 fixture；后续运行仍需单独批准精确节点、解释器/库指纹和资源预算。

API：

- `build_own_inventory(root, *, base_commit, commit) -> dict`
- `validate_own_inventory(root, inventory) -> None`
- `build_static_plan(root, inventory, *, runtime, node_ids) -> dict`
- `validate_static_plan(root, inventory, plan) -> None`

没有 collector/execute/trace API，也没有把静态候选计划交给旧 v1 当运行许可的通路。

## 静态产物

- `night28-own-inventory-ed5182-static.json`：inventory SHA `9e11c56fe8579f7662d2d2580c2755b392974a95dbbbb73b0c541131ccbf587b`。
- `night28-own-plan-core-ed5182-static.json`：plan SHA `3b510635dcf63829f9a7f346cac59ce8a92838cd7aa48f3c8bb517d0da4b8345`。
- `night28-own-plan-charts-ed5182-static.json`：plan SHA `c97d924d6a2a601efc4578bd01709e4a353d3651c9b365e2eaed52990975d21f`。生成此 JSON 用 Core 解析 AST，未启动 Charts。

三产物均使用独占新文件创建；已从 Git/AST 重建验证，不覆盖任何旧采样事实。生成时刻 2026-10-21T01:24:08+08:00，来源本机 Clock。

## 验证与实现来源

独立作者专属检查：`pytest --noconftest -q tests/v4/test_p8_line_coverage_own.py`，清凭据/禁追踪/插件、拦截网络后 **42/42（13.51 秒）**。首轮 42/42（14.92 秒）也通过，随后仅增加合成 Git commit 的空 hooksPath 硬化，再重跑同 42 项。Git 操作限本仓库只读元数据及 private/tmp 下新合成仓库，不启用用户全局钩子，不递归删除。

保护内容包括：f23-base 明确拒绝、初版10与冷文件/工具/原生/helper不遗漏、零行文件保留、删除台账、未来新显式提交动态扩清单且旧 SHA 不自动前进、重签漏文件/重复/假hash/同值 bool/float行号、CPython版本、未知范围/路径、精确节点/参数/fixture、原生基类/lifecycle、重签执行批准与 AST/config/分母元数据。测试中会 raise 的合成目标只编译/解析，不导入或执行。不把字段断言数另算用例数。

Ruff 默认88格式与静态检查通过，硬预算如下；各 SHA 是实现来源，未混入 ed5182 的历史分母：

| 文件 | 行数 / 最大函数行数 | LF SHA256 |
| --- | ---: | --- |
| line_coverage_own_sources.py | 142 / 25 | `cfaacf5ecccf31df111abc824c684ed1d054ec44a767d36d2d195744ced810dd` |
| line_coverage_own_inventory.py | 168 / 38 | `381fb18cf944fc94773955538405229ca12e631bd1dcea5edde5be4d9ec81a87` |
| line_coverage_own_plan.py | 197 / 44 | `56a885abeaee9f0f9175186d467e2fc66fc4cf4dd881454e03c8f400edbc3b9e` |
| test_p8_line_coverage_own.py | 385 / 36 | `d6db697a6a4efc033ada413fc8933445a2a0b92db99102fb40a12a1521da94d8` |

独立审阅线另实跑 **10/10、0skip（5.08秒）**，未发现新增源缺陷；详见 `night28-own-inventory-independent-review.md` 与 `test_p8_own_inventory_independent.py`。这是引用独立线已到达的结果，与作者42项分开记录，未冒充新的全量回归。阶段 A 是静态清单和计划交付，不等于完整自身代码已采样或达到90%；B1/B2、实际前后运行时/库指纹、进程桥接追踪均未实施。


## 根代理聚合复核（2026-10-21T01:35:44.309423+08:00）

冻结实现后，作者42、独立10、旧v1保护38合并为同一次 **90/90、0skip、22.88秒**。
这是定向集合，不与历史2728相加冒充新全量；完整记录见 `night28-own-static-stage-a-validation.json`。
210个Python的严格120字符Ruff/格式、141旧文件保护和密钥模式检查通过。

作者默认88检查与仓库120规则在三个长`with`上给出SIM117差异。根代理仅合并上下文写法，
所有断言、样本、用例数量不变，之后重跑上述90项。旧v1测试合成Git helper限制private/tmp路径，
并仅在自建合成仓库使用空hooksPath，避免用户全局钩子影响合成commit；未改真实仓库hook或使用--no-verify。
这是测试夹具硬化，不是删除、放宽行为断言。

三份ed静态JSON从28140行改为966行，解析对象和内含canonical摘要逐值相等；
原序列化私有保留。上表作者测试SHA对应独立作者阶段；当前最终测试LF摘要为：
- `tests/v4/test_p8_line_coverage.py`：`f23c431fc984890300c58ce3e3f6c4284b001c123cf885ffa77fa748ab065a70`。
- `tests/v4/test_p8_line_coverage_own.py`：`151440deed31fdaf4cd55a6d288ad0f69a6e087920cf8e3f66f7665aec145184`。
- `tests/v4/test_p8_own_inventory_independent.py`：`b8d574141ff74a1360f11c87ae3f16c2d7cda60de06b12da5b92dc173d0c15c5`。
