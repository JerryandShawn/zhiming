# 完整自身 Python 代码覆盖清单与双解释器采样提案

记录：2026-10-21T01:02:21+08:00（北京时间）。**仅只读盘点和设计；本轮没有启动测试、trace、Charts、模型或网络请求。尚未获准实施新 collector/扩大采样。**

## 基线为何要更正

完整读取 AGENTS.md、.agent/PLANS.md、本轮 ExecPlan、现有三个 line_coverage 工具与 Git 历史。固定盘点提交为 `ef5fed9a3fc4e1b727e6077f5b99f41be31e6f7b`，不是浮动 HEAD。

旧分母基线 `f23b942ce698a3f7ee0b98c918d43053fe773433` 已包含 P8 初版实现，它自身只改阶段回执。首次 P8 Python 实现是 `57b00e3ac18ee16ce9f6a9acf0c1b5867e70e980`，其直接父提交 `7fa5e10a4dbe0e2878e28c6f6a115f17d013aaa2` 是本次完整归属盘点的建议起点。

f23→ef5 的净增量有 **204 Python 文件（201 A、3 M）**；首次 P8 前→ef5 有 **214 Python 文件，全部 A、无 M/D/R**。故 214 是目前本分支 P8 历史可界定的完整 Python 自身文件候选清单，204 是后来增量；二者不能混称。初版结转多出的 10 个文件包括 calculations/bazi 七模块、早期两份 v4 测试和 tools/verify_p8_calculators.py，下面明确列出。

完整归属范围均落在本线 Charts、初版 calculations/bazi、skills、P8 测试及其辅助、唯一初版验证工具。不是按导入成功与否筛选；未导入仍在分母。

## 分母定义与固定来源

本次静态清点用 Git ls-tree + cat-file --batch 验证真正 blob SHA1，归一 LF 后 compile(optimize=0)，递归 code objects 取 dis.findlinestarts 的正行号，CPython 3.11；没有导入或执行这些源代码。共 **214 文件 / 22,741 可执行行**。这只是静态候选分母，不是覆盖执行结果；不同 CPython 版本须重新单列，不混用。

每个文件以完整文件作为分母。即使相对 f23 只有几行改动，也纳入该文件全部可执行行；新增行差异只可单独作 changed-line 报表，不代替完整文件分母。0 行的包初始化文件仍保留清单、源码 SHA 与零行解释。当前完整归属比较均为新增文件，但不把“新增物理行”误当“可执行行”。

已发布 6c 的 173 文件/18,006 行与 4.30% 极小节点结果继续只作历史证据，不抹改、不换分母、不并入新的 214 文件报告。旧回执仍可按旧固定 Git 来源作合并校验；新 HEAD 不得冒称重跑 6c。

| 分组 | 文件 | 完整文件可执行行 |
| --- | ---: | ---: |
| Charts适配器/规则/实验工作台 | 59 | 5,289 |
| 研究/重放（含覆盖工具） | 51 | 5,631 |
| 初版八字补充计算 | 7 | 500 |
| Core技能/一致性/学习 | 11 | 1,324 |
| 原生/集成测试 | 13 | 1,729 |
| v4测试辅助 | 3 | 187 |
| v4测试 | 69 | 7,928 |
| 初版验证工具 | 1 | 153 |
| 合计 | 214 | 22,741 |

## 全清单

下表 `Δf23` 的 `—` 表示已存在于 f23 的初版结转；不表示排除。全部行均纳入完整候选分母；LF SHA256 仅绑定源码，不包含正文或私人资料。

| Python 路径 | 分组 | Δf23 | 完整文件可执行行 | LF SHA256 |
| --- | --- | --- | ---: | --- |
| `mingjing_core/adapters/charts/almanac.py` | Charts适配器/规则/实验工作台 | A | 134 | `831a385754ae4d0b2864ca75eb5ffe2441da4869573ed97febd6ab1a4d0e2af7` |
| `mingjing_core/adapters/charts/astro_ephemeris.py` | Charts适配器/规则/实验工作台 | A | 116 | `8fde847c7820d799d56e811e8ad23c39ded61c4797cc08353ab462eccdd29109` |
| `mingjing_core/adapters/charts/astro_progressions.py` | Charts适配器/规则/实验工作台 | A | 43 | `84a640c7ca3fa14e2312dcd262169b1c5adc330b380ec48d8124de0cb979a105` |
| `mingjing_core/adapters/charts/astro_returns.py` | Charts适配器/规则/实验工作台 | A | 114 | `873598193fa3b429b9055c67abe0f4fff59cb28a2f76520e97ac34b15caaab7a` |
| `mingjing_core/adapters/charts/benchmarks/__init__.py` | 研究/重放（含覆盖工具） | A | 1 | `574d9c2aae95f8e394bdcbcd29304222c7cfa7dd10755a1b20ee093e677f4a85` |
| `mingjing_core/adapters/charts/benchmarks/annual_v2.py` | 研究/重放（含覆盖工具） | A | 88 | `bd79d36101d1ac48c0e52e761c6726dc9f2fc08c6e42e826f989c9f9c5a8d741` |
| `mingjing_core/adapters/charts/benchmarks/contexts_v2.py` | 研究/重放（含覆盖工具） | A | 62 | `7eab27fdb177b385748c11d6065b9bc1cbca5d42a4d677016fd85ffc265b25e2` |
| `mingjing_core/adapters/charts/benchmarks/controls_v2.py` | 研究/重放（含覆盖工具） | A | 82 | `06b9496f189811ce98564da237c28b3759d33c776f72833925de7d4a093a003a` |
| `mingjing_core/adapters/charts/benchmarks/crosscheck_v2.py` | 研究/重放（含覆盖工具） | A | 68 | `3a377822de6cf1e7bf110baa7671e060c810be1d040b9b0e19983374148754c6` |
| `mingjing_core/adapters/charts/benchmarks/daily_transit_samples.py` | 研究/重放（含覆盖工具） | A | 67 | `c80acc3b9321dc4bcf90899f6bf33fe4941e1cce9324f83193fac6d38c1e9cb7` |
| `mingjing_core/adapters/charts/benchmarks/eligibility_v2.py` | 研究/重放（含覆盖工具） | A | 113 | `5239f38db7c4329df5d433c7cc77b510826259c35eea4bd3b85c61a48644945b` |
| `mingjing_core/adapters/charts/benchmarks/engine.py` | 研究/重放（含覆盖工具） | A | 68 | `569890bbb4d78a3f0f365991c6592de8ce77630c37fe301209550fa16f53bf75` |
| `mingjing_core/adapters/charts/benchmarks/experiment.py` | 研究/重放（含覆盖工具） | A | 99 | `56773d0a0df01cbe76e67e5c22d468a337c7f11efa1cb1a1dee61c7d3518a230` |
| `mingjing_core/adapters/charts/benchmarks/handoff_boundaries.py` | 研究/重放（含覆盖工具） | A | 56 | `ecc62fe7f1c569597314a00420fd05fd4cf8fdc5c6605b30aa9a99e14a41065a` |
| `mingjing_core/adapters/charts/benchmarks/handoff_build.py` | 研究/重放（含覆盖工具） | A | 222 | `e1c9fd20cb4b041b179aaab8736062755d4fdb46f434b0b15462033831bdbef8` |
| `mingjing_core/adapters/charts/benchmarks/handoff_offline.py` | 研究/重放（含覆盖工具） | A | 56 | `b9d45478ce1bb1e56b3fdc56570600ec0e03cb01fa37dc9b080e6f99f122d45e` |
| `mingjing_core/adapters/charts/benchmarks/handoff_refs.py` | 研究/重放（含覆盖工具） | A | 68 | `c26d46397990bf6f0fa64447ba8604d9e7fe11c3bdd71021d79984c87da50893` |
| `mingjing_core/adapters/charts/benchmarks/handoff_schema.py` | 研究/重放（含覆盖工具） | A | 176 | `68a2a1be356cc681848e71d8a9e95beee74773ac6f9ba46dabfedd24f83f6b8e` |
| `mingjing_core/adapters/charts/benchmarks/handoff_validate.py` | 研究/重放（含覆盖工具） | A | 215 | `08005318e341690309ab804c19cb16c3e981deecad50c8ce1887fef4de1f1528` |
| `mingjing_core/adapters/charts/benchmarks/handoff_validate_data.py` | 研究/重放（含覆盖工具） | A | 142 | `4f198ee96bf2f38ab8eb56b798d1a6394a2ad9bc3ef999e2ebfd7ca31684fdd9` |
| `mingjing_core/adapters/charts/benchmarks/handoff_validate_request.py` | 研究/重放（含覆盖工具） | A | 57 | `2b695cd11857f6b6de420d0dbffeba9a6b369d8c74944f2025d3f1a9afc489fb` |
| `mingjing_core/adapters/charts/benchmarks/inspect_v2.py` | 研究/重放（含覆盖工具） | A | 71 | `dfb64950209698dbbd1f5532204141f69c1670d7cc9955e53eacb9ca8a53aad0` |
| `mingjing_core/adapters/charts/benchmarks/learning_preview.py` | 研究/重放（含覆盖工具） | A | 158 | `865eeedb4d7279ddd50d2e067722df8c29ef44b45389fa36ad7db4daddecf89e` |
| `mingjing_core/adapters/charts/benchmarks/line_coverage_manifest.py` | 研究/重放（含覆盖工具） | A | 214 | `86c3a2e38d2eebb6bc332ffab88ab4ddc93f8eef485b55fa29bf659d15098654` |
| `mingjing_core/adapters/charts/benchmarks/line_coverage_merge.py` | 研究/重放（含覆盖工具） | A | 94 | `08e1453afdc3c005ee2c05418eda796e52feee1f48f62d9bcc4ad7524223d7af` |
| `mingjing_core/adapters/charts/benchmarks/line_coverage_run.py` | 研究/重放（含覆盖工具） | A | 236 | `6f9deeac5af3cc22efb80c6d58fe366fb532b2ad0f1f4c12cc7460535a87b5ea` |
| `mingjing_core/adapters/charts/benchmarks/loaders.py` | 研究/重放（含覆盖工具） | A | 117 | `b3d67efd1daae16374ca79d7ca1f1e70e7f13d94b88861ffe3d5905c9327aabe` |
| `mingjing_core/adapters/charts/benchmarks/loaders_v2.py` | 研究/重放（含覆盖工具） | A | 166 | `9c7ec60f7312860b87dcd644577ee85951c083db69b3196073a3e7ce3840585a` |
| `mingjing_core/adapters/charts/benchmarks/night24_audit.py` | 研究/重放（含覆盖工具） | A | 109 | `ced6c99ce6464291be6ff61b92288c3ab2da2d382f27f3e853c114181ac23a4f` |
| `mingjing_core/adapters/charts/benchmarks/night24_markdown.py` | 研究/重放（含覆盖工具） | A | 91 | `29d4cca794a5b340cc016dadf1ec2a0aa2d209be0bf9499c926d6c01f7165831` |
| `mingjing_core/adapters/charts/benchmarks/night24_performance.py` | 研究/重放（含覆盖工具） | A | 115 | `48508943c6d2b0dc5a0c5111c9be8925035663f498bc85484dacbb219ac91477` |
| `mingjing_core/adapters/charts/benchmarks/night24_placebo.py` | 研究/重放（含覆盖工具） | A | 75 | `d7d3fff1e495a27e1a4814ca9ffb4604557eb6b328ab225eaa7a40d76623a7f4` |
| `mingjing_core/adapters/charts/benchmarks/night24_solar_boundaries.py` | 研究/重放（含覆盖工具） | A | 71 | `3e50ead87eb1e864ca1fb2dc95fc3f557b13712179587eb4754fe132364e3303` |
| `mingjing_core/adapters/charts/benchmarks/night24_solar_independent.py` | 研究/重放（含覆盖工具） | A | 86 | `7000c9763c335601917fc6d923f380d5d7d49a6353fdb401478fcdbf187ce5ff` |
| `mingjing_core/adapters/charts/benchmarks/night24_solar_reference.py` | 研究/重放（含覆盖工具） | A | 124 | `32fd6a2dda763ff5ef8107d568b3ba05b71e258a39f809d4a91c7874fb8ffec0` |
| `mingjing_core/adapters/charts/benchmarks/night24_sources.py` | 研究/重放（含覆盖工具） | A | 139 | `a2171464b3b88a5f9c5d28b140365839ecb44f03965c5803d094a34400a730ef` |
| `mingjing_core/adapters/charts/benchmarks/night28_audit.py` | 研究/重放（含覆盖工具） | A | 94 | `297c67b4ca01a03ef00496053ce703a958e5ca070a956a3755ac33d1cc92afb3` |
| `mingjing_core/adapters/charts/benchmarks/night28_controls.py` | 研究/重放（含覆盖工具） | A | 115 | `634a7e2883d67a968db8679dbe387e7993d91543f67b2658aafa66200228cc49` |
| `mingjing_core/adapters/charts/benchmarks/night28_date_cases.py` | 研究/重放（含覆盖工具） | A | 100 | `24d6210068232c7303871aec7cb2bc6f4bbb56fd5e353e1605e92651099e8a79` |
| `mingjing_core/adapters/charts/benchmarks/night28_date_properties.py` | 研究/重放（含覆盖工具） | A | 208 | `7f755c8f9306b529aa3c23ce2784d3cbb8d4396edc3e7392c9d2a5a2b3543a03` |
| `mingjing_core/adapters/charts/benchmarks/night28_date_properties_cli.py` | 研究/重放（含覆盖工具） | A | 74 | `1e63080ccb4864e8c43188ffc5019dd95c78ae947cd240de6136458e1ac55440` |
| `mingjing_core/adapters/charts/benchmarks/night28_markdown.py` | 研究/重放（含覆盖工具） | A | 78 | `8452dc7234a74a6fee477268e9fad9294458fe4834bc76914d888c19a62d0e19` |
| `mingjing_core/adapters/charts/benchmarks/night28_property_common.py` | 研究/重放（含覆盖工具） | A | 16 | `0d9e60db552ee1ec4199294da565b7ba06c04a4962b5ee127c3555c24bfde22a` |
| `mingjing_core/adapters/charts/benchmarks/night28_skill_samples.py` | 研究/重放（含覆盖工具） | A | 66 | `aedbdc715af4ae4025ae57ce3244d117382b03053f9aeb83d91ecc49a13edc5b` |
| `mingjing_core/adapters/charts/benchmarks/night28_temporal_preflight.py` | 研究/重放（含覆盖工具） | A | 106 | `8b66b789ec81fe2027f4a4b3c680217eeb670f21b92ba1d75ef0fcf96026278a` |
| `mingjing_core/adapters/charts/benchmarks/night28_tools.py` | 研究/重放（含覆盖工具） | A | 118 | `22d14a0041dcd5d0d96d7d240c7808aaff117761dca6c1690678fa89ec495cc7` |
| `mingjing_core/adapters/charts/benchmarks/night28_window_properties.py` | 研究/重放（含覆盖工具） | A | 141 | `35d9897947e7e46dca09fa60b556c152f3977ebcea2f3b97360dd30e9f6f868f` |
| `mingjing_core/adapters/charts/benchmarks/night28_ziwei_crosscheck.py` | 研究/重放（含覆盖工具） | A | 179 | `b6bc4259b3357632f053f189e3fd62fced858216a02e7c34a2d590ada329674c` |
| `mingjing_core/adapters/charts/benchmarks/night28_ziwei_reference.py` | 研究/重放（含覆盖工具） | A | 92 | `b9b180dea5add9abb35c39ff53dd8e955356a7c0a75245054efe8a60eefc4409` |
| `mingjing_core/adapters/charts/benchmarks/protocol_v2.py` | 研究/重放（含覆盖工具） | A | 204 | `116f6938ab337cdd3e08c775b83e77267b5865b60ccf2038b22388f7144deb45` |
| `mingjing_core/adapters/charts/benchmarks/records.py` | 研究/重放（含覆盖工具） | A | 99 | `2a5b56126841c65100f2524ea39f896c0605902adcf75d535e11c1a01609a656` |
| `mingjing_core/adapters/charts/benchmarks/scripted.py` | 研究/重放（含覆盖工具） | A | 147 | `36fabde0f3b2de8697105725c7c92250fb60a92c3520a8cc1a6bbfb68a8207fd` |
| `mingjing_core/adapters/charts/benchmarks/scripted_v2.py` | 研究/重放（含覆盖工具） | A | 155 | `53d7403626d5af977eb99822f053e66980e99ef537845f15af1543f7afa9d995` |
| `mingjing_core/adapters/charts/benchmarks/statistics_v2.py` | 研究/重放（含覆盖工具） | A | 72 | `711f63780acb50a3c801842d9e0449753a6ea3bc1d4ee2bd5354e3d2797984e9` |
| `mingjing_core/adapters/charts/benchmarks/window_search_samples.py` | 研究/重放（含覆盖工具） | A | 61 | `687668cbad466d4604d484be2e34bc3aab4d4e3eac05b05cb2c0eaa24b098dc1` |
| `mingjing_core/adapters/charts/boundary_alerts.py` | Charts适配器/规则/实验工作台 | A | 128 | `f6d3817496778c37d7e3f605b26ca244775a4fa58c9885b63b5bd8dcc4545d69` |
| `mingjing_core/adapters/charts/boundary_candidates.py` | Charts适配器/规则/实验工作台 | A | 80 | `773c78b6458d165d978a4f3bbea97a5f8bd110ed2aee28310f6ba6c48bd604a6` |
| `mingjing_core/adapters/charts/boundary_solar_reference.py` | Charts适配器/规则/实验工作台 | A | 47 | `28af1e0ad0cfba64ecd45b7db7c120f6934f4bd8150e6de4f98a442a42e1c8d1` |
| `mingjing_core/adapters/charts/climate_review.py` | Charts适配器/规则/实验工作台 | A | 14 | `696221592ef59e46cea358286a66b823118ca01c5548e750e54006bf56e1789a` |
| `mingjing_core/adapters/charts/daily_transit.py` | Charts适配器/规则/实验工作台 | A | 45 | `dd5f4db3ce649621f960ae8ca417a6347a1284454ebe451fe7923f6f81630988` |
| `mingjing_core/adapters/charts/daily_transit_astro.py` | Charts适配器/规则/实验工作台 | A | 46 | `0cdbedbf2d4f305f6f4e23e37a293c5d0eda7b6ddf934e166c692854f096581b` |
| `mingjing_core/adapters/charts/daily_transit_bazi.py` | Charts适配器/规则/实验工作台 | A | 74 | `5a6995c28cdd0aa08c62bdec77d57fad88ad67f1c2f6d20d00a2470f83f63c82` |
| `mingjing_core/adapters/charts/daily_transit_natal.py` | Charts适配器/规则/实验工作台 | A | 118 | `b4457f020d15143e546f6ac8faab068d88b895282e0c8d6bf5dd7b6063016a72` |
| `mingjing_core/adapters/charts/daily_transit_ziwei.py` | Charts适配器/规则/实验工作台 | A | 70 | `a588e03881cd88789529e917dcc44d8248f1b92e5181e1c26cb370dd5451f8b0` |
| `mingjing_core/adapters/charts/interactions_bazi.py` | Charts适配器/规则/实验工作台 | A | 146 | `5a59f2da35caa65252828039cb8a7303e3cbf3c158e09559cfa2b53f6fc93418` |
| `mingjing_core/adapters/charts/interactions_transits.py` | Charts适配器/规则/实验工作台 | A | 166 | `5802f12958c0e47658cff04d0c6e7bf576b96f6e4abf17a1bfa38782d20b706e` |
| `mingjing_core/adapters/charts/interactions_ziwei.py` | Charts适配器/规则/实验工作台 | A | 48 | `baa2c814a0b2b1d3e678052a580f0c36e94e91fc3b85742adb7b6863777b05cd` |
| `mingjing_core/adapters/charts/jie_uncertainty.py` | Charts适配器/规则/实验工作台 | A | 87 | `f734d17258a0dcbc3aa1864d7b00e285071a3851f771a67ab99075daf0223060` |
| `mingjing_core/adapters/charts/named_bazi.py` | Charts适配器/规则/实验工作台 | A | 140 | `9f5e1843c10d540ccbd05268980ef00441593e93f19af9e132d6baf5aa4bd382` |
| `mingjing_core/adapters/charts/named_strength.py` | Charts适配器/规则/实验工作台 | A | 107 | `4ceb88bf8d8501f7defc978d5d05244d7c7e45c5c180bc9a2a2785b2042f938e` |
| `mingjing_core/adapters/charts/p8_adapter.py` | Charts适配器/规则/实验工作台 | M | 157 | `3e9acb177fb98b6894e8fbf20d207e005e8f424ab6b858dcc23bb72ca7f07595` |
| `mingjing_core/adapters/charts/p8_analysis.py` | Charts适配器/规则/实验工作台 | A | 31 | `72aae34f25e3ab4d1c9263564d3649eedc96aadc65bb6fef4060b6757caf2f4d` |
| `mingjing_core/adapters/charts/p8_policy.py` | Charts适配器/规则/实验工作台 | A | 30 | `2951cbc243484fae5759ee91e27b16b14ac9e1522721f776953475d3babe1b4c` |
| `mingjing_core/adapters/charts/p8_pure_tools.py` | Charts适配器/规则/实验工作台 | A | 30 | `fbf57c4fb7cfd53c7ca85a02df015c6745fda8d95fde1359014b5e1f393b4ec0` |
| `mingjing_core/adapters/charts/p8_structure.py` | Charts适配器/规则/实验工作台 | A | 110 | `3dcc442a40d13511b2abb61f36e35be6995a898e0cfa6a61640bfe6333c36e07` |
| `mingjing_core/adapters/charts/p8_worker.py` | Charts适配器/规则/实验工作台 | M | 71 | `d3898415ea09a0ec60304abe6a6c25bfb20afa5f4eedb12a31fa8d8a9e48b270` |
| `mingjing_core/adapters/charts/profile_draft.py` | Charts适配器/规则/实验工作台 | A | 48 | `21443d86a5bb4fee45ff65e97ece0dac91fd18cb22016384b58e76de9a6be065` |
| `mingjing_core/adapters/charts/rectification_workbench/__init__.py` | Charts适配器/规则/实验工作台 | A | 1 | `4bd3b498ee34ff4ff9c5aca4dae8ade58869be65744364f7f637ceeddef005b3` |
| `mingjing_core/adapters/charts/rectification_workbench/calibration_scope.py` | Charts适配器/规则/实验工作台 | A | 34 | `e5cb58feb0c1b617bce3e0ba1bcbf4bf76423b48a37055d9445c42f877dd8667` |
| `mingjing_core/adapters/charts/rectification_workbench/chart_grid.py` | Charts适配器/规则/实验工作台 | A | 92 | `c8bb928c30cd5400971597c04df3db83a45fc9ee0cb33c48579460bd9401af8d` |
| `mingjing_core/adapters/charts/rectification_workbench/contracts.py` | Charts适配器/规则/实验工作台 | A | 93 | `2f24f27b55e43f49c432522f0b9fbbdb1537eee463f2c95119c8f6c589d8dee8` |
| `mingjing_core/adapters/charts/rectification_workbench/envelope.py` | Charts适配器/规则/实验工作台 | A | 40 | `9e78132bb335ff70c5f7970436c715b1963187068b72d9dbedc6eed92b4f04ce` |
| `mingjing_core/adapters/charts/rectification_workbench/evaluation.py` | Charts适配器/规则/实验工作台 | A | 203 | `534a20ab180077ea762bb553e08dae13c3cd9de12b80acd9d93f7f33e4703a95` |
| `mingjing_core/adapters/charts/rectification_workbench/evaluation_cases.py` | Charts适配器/规则/实验工作台 | A | 20 | `142d67240aa63088820d0d41070d7d0f67dad721206ad6beb48c33991caa5e3e` |
| `mingjing_core/adapters/charts/rectification_workbench/evaluation_charts.py` | Charts适配器/规则/实验工作台 | A | 217 | `f5a13ce6ae0e3723c9a41c1346e06e160171b068dd6384654b8b9d6c308d2ddf` |
| `mingjing_core/adapters/charts/rectification_workbench/sessions.py` | Charts适配器/规则/实验工作台 | A | 138 | `8175a945a009686e1719bbe2a1525b46196ea4827656c5d613b058d31edacbba` |
| `mingjing_core/adapters/charts/rectification_workbench/signals.py` | Charts适配器/规则/实验工作台 | A | 213 | `87415fd4ce38b002c3056c6bbf51104fdba066345b752b7dd96bffe40291db05` |
| `mingjing_core/adapters/charts/rectification_workbench/statistics.py` | Charts适配器/规则/实验工作台 | A | 259 | `21e04d93b0c20856efc0f4b175f09633fa6d5c4620e9186c98f605b9d8029633` |
| `mingjing_core/adapters/charts/rules/__init__.py` | Charts适配器/规则/实验工作台 | A | 4 | `eff1b36df054bcebc4a4fbec060f60e6075287ed64fb462e3c95bf78043a1a0f` |
| `mingjing_core/adapters/charts/rules/conditions.py` | Charts适配器/规则/实验工作台 | A | 134 | `2ffdac8c1c4f71bf04382d60c9f57956b54f179c6c17172c91a87da61dc2b3f7` |
| `mingjing_core/adapters/charts/rules/engine.py` | Charts适配器/规则/实验工作台 | A | 31 | `b0ecc4067936a0d53ca0b438fb4515da86142b70b856f75258054454029fc913` |
| `mingjing_core/adapters/charts/rules/interaction_metadata.py` | Charts适配器/规则/实验工作台 | A | 47 | `273af6285d3d57c414d8e09cf049f042e8809f73c7e85b6b4e901d0420f4f22c` |
| `mingjing_core/adapters/charts/rules/registry.py` | Charts适配器/规则/实验工作台 | A | 98 | `8e424a1a555eec3b9f9c6d79b70b6fbf4141480023ad0f4f07c63bc9377b8d84` |
| `mingjing_core/adapters/charts/synastry.py` | Charts适配器/规则/实验工作台 | A | 82 | `313012bdbaf63d3c9dca1f07ecd00c420918f45dcb8d96873cf3e1444ee996b6` |
| `mingjing_core/adapters/charts/synastry_bazi.py` | Charts适配器/规则/实验工作台 | A | 117 | `63acf539d608285bcebbb50859dec04e8febb9fe4b444b4dd75c871efed764a5` |
| `mingjing_core/adapters/charts/synastry_ziwei.py` | Charts适配器/规则/实验工作台 | A | 39 | `679b1e69974f0fb803921fe0f91cd05e7fb2a985baa685ca553b9759c60b8f2b` |
| `mingjing_core/adapters/charts/time_basis.py` | Charts适配器/规则/实验工作台 | A | 123 | `e25bb738e292f71e69f2735af237b898438476d0fc6bfb867ca36053a5cfedef` |
| `mingjing_core/adapters/charts/time_basis_candidates.py` | Charts适配器/规则/实验工作台 | A | 131 | `5e3879e420d2d7d8306c373ab44eb2a38395962bea4c06e609c38be81b694267` |
| `mingjing_core/adapters/charts/time_basis_chart.py` | Charts适配器/规则/实验工作台 | A | 57 | `f1360a4e98317be2aaf2c78d01a174b7a64538a2c0372b5253b0bcd84046f7dc` |
| `mingjing_core/adapters/charts/time_basis_readout.py` | Charts适配器/规则/实验工作台 | A | 81 | `a0c3c376892b54c8b36e1f0a30182479d3ca182adb77cdbe2f3626d3fdf38a06` |
| `mingjing_core/adapters/charts/time_basis_request.py` | Charts适配器/规则/实验工作台 | A | 88 | `2f8a81f7e1831924b1e8af036a6f8a0e037fbd586008102ae14fb92eefb5fa70` |
| `mingjing_core/adapters/charts/time_basis_solar.py` | Charts适配器/规则/实验工作台 | A | 61 | `5f6bc82bf1b4dbd218852891a85bf57dbb500cc32a74b6725966318db2e7d08e` |
| `mingjing_core/adapters/charts/time_basis_zones.py` | Charts适配器/规则/实验工作台 | A | 75 | `1d863e985669e74608f571e3fce6f285dc754e07262640fe0839b3e8c08fc173` |
| `mingjing_core/adapters/charts/tool_evidence.py` | Charts适配器/规则/实验工作台 | A | 83 | `c1c0e64b0f4bece18f9477fffec87dd358bcdccc090a5ebdefbce104975ef0fe` |
| `mingjing_core/adapters/charts/western_timing.py` | Charts适配器/规则/实验工作台 | A | 51 | `1257bc2d4b3bd0673ad6846c0e35e0d6a739579c105cfb6da333c9bddef3d808` |
| `mingjing_core/adapters/charts/window_search.py` | Charts适配器/规则/实验工作台 | A | 114 | `d1c0154eec632783551095f461742199bebb6baf9844e9f8697a12a949bcb135` |
| `mingjing_core/adapters/charts/window_search_pagination.py` | Charts适配器/规则/实验工作台 | A | 64 | `6698026825d263e75f5e14e183c94a3986861396954fba31537102a61b1de277` |
| `mingjing_core/adapters/charts/window_search_scoring.py` | Charts适配器/规则/实验工作台 | A | 98 | `98a1cf60f841a9d39848da53a23eaaa6698d0b7c4412177d810e1209a3b85bec` |
| `mingjing_core/adapters/charts/ziwei_flying.py` | Charts适配器/规则/实验工作台 | A | 124 | `18fa4716c423c6781b87a296a32e7b5c3ef87ca3967d186013da2a32071050c0` |
| `mingjing_core/adapters/charts/ziwei_flying_support.py` | Charts适配器/规则/实验工作台 | A | 77 | `62bd34ec4c3776df68d91805d80d8b34c7a64e18046577d7121b966670dcdce9` |
| `mingjing_core/calculations/bazi/__init__.py` | 初版八字补充计算 | — | 3 | `db7bc807b792ac352c41dba311e872816ccd42d4b4246834b64aacef2c32ea15` |
| `mingjing_core/calculations/bazi/calendar_layers.py` | 初版八字补充计算 | — | 119 | `72ca973c0fe853ddae48cadc3d4ace16015b7dd75de48c0a2518540c8add2a6d` |
| `mingjing_core/calculations/bazi/elements.py` | 初版八字补充计算 | — | 75 | `43e40f0906a6f3759b67c26011679dd2d6eec5674542971a336e29387d1d93d0` |
| `mingjing_core/calculations/bazi/stars.py` | 初版八字补充计算 | — | 46 | `817f2313d3c3ce0fdffd597348b3f7b3dc6bfbf923100bb83926b7b9a23b4974` |
| `mingjing_core/calculations/bazi/strength.py` | 初版八字补充计算 | — | 78 | `1bd3e944c6c7e6e9ed5b07068bf1583a669eed0c4b4edf92da3beda50d271ce6` |
| `mingjing_core/calculations/bazi/structure.py` | 初版八字补充计算 | — | 148 | `fd571fb968f5b5204faa89a0824f05d80d67e00d042b521388eebfb54adbaec2` |
| `mingjing_core/calculations/bazi/supplement.py` | 初版八字补充计算 | — | 31 | `1a957ffc07ebac768fbb5520e54347987f0c2f5c6ca6ec072082b47bf0870f6f` |
| `mingjing_core/skills/__init__.py` | Core技能/一致性/学习 | A | 3 | `5ed5d69de6cacfe7a94d891bbc9d754b9249e8c1f53d9484cb71e656b671abd7` |
| `mingjing_core/skills/consistency.py` | Core技能/一致性/学习 | A | 110 | `aff8bf1d192fa10b6b0a020a64096d950a6092f105f0754e5fe774e95ff193e0` |
| `mingjing_core/skills/consistency_eval.py` | Core技能/一致性/学习 | A | 114 | `c57a07dec126be15d0ea2a8377731f6e8ab019b3f6a7f54a76e400befbb4d5af` |
| `mingjing_core/skills/consistency_facts.py` | Core技能/一致性/学习 | A | 169 | `41f2ea620e45ecea81cd3c1716939f08b16d206128e7c8a7aea2c4715db9d2af` |
| `mingjing_core/skills/consistency_text.py` | Core技能/一致性/学习 | A | 225 | `83363f47dc7bf9fe1187f4b72362a11b140d495f3928863c7182574ea961b984` |
| `mingjing_core/skills/consistency_u12.py` | Core技能/一致性/学习 | A | 72 | `7d8bf1942539f7b9b678e19f8a279ea0b8c4e46ec3b265fb6a5a48c6941fb1c3` |
| `mingjing_core/skills/consistency_u12_eval.py` | Core技能/一致性/学习 | A | 122 | `054d1306d7a892fe9513bb96fe68dc907cbc74db3deb55e36f22ee6c5becea43` |
| `mingjing_core/skills/consistency_u12_input.py` | Core技能/一致性/学习 | A | 147 | `d17934c721f146195b1ad84f85c3d780902370cb933398d74354f5e641bd6d64` |
| `mingjing_core/skills/learning.py` | Core技能/一致性/学习 | A | 122 | `175d9eac9dc511aa6b5c38fdabe1eac9409027c6775982025c5307f3913b2695` |
| `mingjing_core/skills/learning_input.py` | Core技能/一致性/学习 | A | 176 | `e8bd303ba8d0663584f2c3884b14af174d11f208bf209b5ff50d862529ac3a00` |
| `mingjing_core/skills/loader.py` | Core技能/一致性/学习 | A | 64 | `a8c0c57fbbd217435144c57242d76cea7d6fdc41c149c6052aba447b89a4c818` |
| `tests/test_p8_astro_native.py` | 原生/集成测试 | A | 174 | `20cb4d9849214b963e93e650b00bdfad575e5e8eee477153d8dc5712552ee4d6` |
| `tests/test_p8_boundary_alerts_native.py` | 原生/集成测试 | A | 187 | `16d6e5846be0c3c5f261e4ac954697ad1c81c1326b0c67639b813570e80338ef` |
| `tests/test_p8_daily_transit_native.py` | 原生/集成测试 | A | 187 | `5b39171fdc22a1e13c51c246370119c6848c1e875b5e4d827d41ba03ceaae1ef` |
| `tests/test_p8_interactions_native.py` | 原生/集成测试 | A | 92 | `ab39a1aa37065a6dc90754d631c1d2a72379d1f9aa1b25a5dc490f160e721afd` |
| `tests/test_p8_jie_geometry_native.py` | 原生/集成测试 | A | 38 | `9405500d67c5369d3bca5e197d5686f7d3debf6e7a05c624d5419e6dc5c56f17` |
| `tests/test_p8_meta_integration.py` | 原生/集成测试 | A | 234 | `af8913c6c2ffa6876f0ce616fbaf00d32ca711639c582e7abd674b320c44529c` |
| `tests/test_p8_named_schools.py` | 原生/集成测试 | A | 93 | `f4a7881827df03459f4fad6795e075e24c055f8f0971568ab3425379634c3685` |
| `tests/test_p8_native_calculations.py` | 原生/集成测试 | M | 175 | `79ca1bc135139e274c9a0e5a5599b2c5ffb6c0223ea961935a4c423f3a069e22` |
| `tests/test_p8_time_basis_native.py` | 原生/集成测试 | A | 118 | `abf66250680016805be4e684265649676f135f7d8a9199c6499019161945e044` |
| `tests/test_p8_window_search_native.py` | 原生/集成测试 | A | 104 | `013581dbb7c348a9b09bc53c8a6248fcb33a66cfe4e9c32eb21ec7f4efc8be2f` |
| `tests/test_p8_workbench_grid_native.py` | 原生/集成测试 | A | 206 | `aa80e97e5df751cba566999d40ebcd0779281e745f98206852d8d1b0014b1f96` |
| `tests/test_p8_ziwei_native.py` | 原生/集成测试 | A | 65 | `61af1e0b69ccd9e03cbb84fcb5871d2b70ffe952be4738f66764a57b33115b01` |
| `tests/test_p8_ziwei_review24_native.py` | 原生/集成测试 | A | 56 | `8aa8f5771f474733a9f582b09dde631d54f46739d5d05b37b3a3213f48572f3c` |
| `tests/v4/p8_rules_sample_context.py` | v4测试辅助 | A | 27 | `df5e102692d8ee1dde0cf5e71cc336c8d3e147c1ee59fc1f634e468f62ed949f` |
| `tests/v4/p8_skill_asset_context.py` | v4测试辅助 | A | 119 | `0b89d0277fd46ab616a2b8b5b95a937362f543976dd59304fe618b3dd28305f4` |
| `tests/v4/p8_u12_assertions_context.py` | v4测试辅助 | A | 41 | `973e2754c3e996f600fb1215adf5493f247f5a82796c0273769ba906a8fca774` |
| `tests/v4/test_p8_almanac.py` | v4测试 | A | 108 | `bda7ccdcbde5732a3558d3a69c1da8598712c1b18e565aa2de24b5a38bf2385c` |
| `tests/v4/test_p8_astro_timing.py` | v4测试 | A | 20 | `94c03b3b12af558771e3e43cd389c7bb8d44fb5e1d53031a67f49af4d1a98cf0` |
| `tests/v4/test_p8_bazi_rules.py` | v4测试 | — | 144 | `b64e5d2af941532264426311a17c80132ed6a09756f16d9fead40bb69dfb768d` |
| `tests/v4/test_p8_boundary_alerts.py` | v4测试 | A | 38 | `3b5f80c12b6d806bc0441d589a361f736e08506c57c81c514121fac2bfdef7a4` |
| `tests/v4/test_p8_calendar_tool_skills.py` | v4测试 | A | 39 | `e3b51d77a0678803da01777681bcdd6d99a1e59a5151c8eb63f4fb5b899f3fa9` |
| `tests/v4/test_p8_chart_process.py` | v4测试 | — | 22 | `976565ffb43abc3eae4407dcde67c37904267e8d13695e3a1a652f54648e0ede` |
| `tests/v4/test_p8_consistency.py` | v4测试 | A | 126 | `0b412942374693517aa4f0b4fcda09563e2edf8db9de3717c76736af624ad708` |
| `tests/v4/test_p8_consistency_boundaries.py` | v4测试 | A | 154 | `063ff7a963e3a013ffac6bf6eaf2274a824601dad1d67eb278e13e2c7a512b1f` |
| `tests/v4/test_p8_consistency_context.py` | v4测试 | A | 57 | `e89e17194c28b6870e174223028a6021003d876c4d411e3ae266454ac5806211` |
| `tests/v4/test_p8_consistency_contract.py` | v4测试 | A | 93 | `27beb73bb2b507cdc23b5c63b06229409a88fba8ca9f550c7da04de98c3b514a` |
| `tests/v4/test_p8_consistency_review.py` | v4测试 | A | 104 | `dc30c4fab03188bae543ad7d42a112170149487d7ca4649db5ff0684c108f33d` |
| `tests/v4/test_p8_daily_transit.py` | v4测试 | A | 84 | `938113175bef6ecb6dfce84a8e41c94d22590a7a4252af8913ccc5216a9258ed` |
| `tests/v4/test_p8_date_properties.py` | v4测试 | A | 77 | `0c30e2736b25980a36ca75cc7572d247451abbf6db08e301bf33e94d90c2f728` |
| `tests/v4/test_p8_e2_adjudication_v2.py` | v4测试 | A | 217 | `998cd8db3f26205074cc0ec5e358ac4b26fe06f503cc87be0f976b9cf7d38f5b` |
| `tests/v4/test_p8_e2_annual_v2.py` | v4测试 | A | 125 | `129326ac8021c5564a946002c86d58eabeb8fd59ef67328dd87d97103dd96aeb` |
| `tests/v4/test_p8_e2_benchmarks.py` | v4测试 | A | 190 | `935921b810cf8324a4182f99bb4d87cda08dcf1301f319b2d5ccb3857439b79a` |
| `tests/v4/test_p8_e2_night28_audit.py` | v4测试 | A | 148 | `420f323dc20e80a53bf397e55c17488c84be57454aeca6426c78c3f2c11f2fd0` |
| `tests/v4/test_p8_e2_night28_controls.py` | v4测试 | A | 127 | `50e2cae17ed20a1d74a064b96c635f6da1904073e6d6d1dcf2b0af1d8afb3fd5` |
| `tests/v4/test_p8_e2_night28_temporal.py` | v4测试 | A | 89 | `ec6fda8b12d4930ef8ed7965187a32ceedd51113938ea0ed9868052829b77bf6` |
| `tests/v4/test_p8_e2_night_integrity.py` | v4测试 | A | 33 | `13fb19898c3d7fd6e313c2521ea47039f681e9dd62cce59890d22275cfc36c21` |
| `tests/v4/test_p8_e2_night_placebo.py` | v4测试 | A | 172 | `ac42f1e7109476e6a5fb739563825695ff62e1448ed6a4f96995f35fd9558dbe` |
| `tests/v4/test_p8_e2_night_sources.py` | v4测试 | A | 257 | `bbe5b25f51ea0e1269621942978ae36312a148eb6c9fe7e628fac3a790f5a85a` |
| `tests/v4/test_p8_e2_protocol_v2.py` | v4测试 | A | 188 | `0ce5f549ee9bab0e2717f71cd56285f294efe0af91ea3da5220dcf6f66a799de` |
| `tests/v4/test_p8_e2_statistics_v2.py` | v4测试 | A | 142 | `76892bc339a1a2c81b4b1fcd8c6e051740139d78981b23fa05fe96ab9b03c6fd` |
| `tests/v4/test_p8_glossary.py` | v4测试 | A | 130 | `24ea9c5270f6eb1cb9a3072672e4783f2e6e0f4aa8197e9a2fbaa94fe107e819` |
| `tests/v4/test_p8_handoff_preview.py` | v4测试 | A | 232 | `ef549e98a7506d4b3ec735e9f1d21b8b15dcc5057fd5fa649e16ca7cb5eaf754` |
| `tests/v4/test_p8_handoff_request_binding.py` | v4测试 | A | 112 | `39a30fe09d6f62465bf87b057b343aab736a4d8caa59eb2a878472c2209f4330` |
| `tests/v4/test_p8_handoff_v11.py` | v4测试 | A | 84 | `89fc31e698a506b49c4cb819256deea8f74576fbe4cd9432a3f9fdfc14077b7b` |
| `tests/v4/test_p8_jie_geometry_process.py` | v4测试 | A | 27 | `d7c4b6385d0dd97a1fa667ffcc26472d5ff38c5270be606e67dc3c47827ff5d1` |
| `tests/v4/test_p8_learning_lessons.py` | v4测试 | A | 225 | `f1c909468dddaf0cdb1513c25bf2f1b07f040bd55f580bacb78d1603dc66bdb1` |
| `tests/v4/test_p8_learning_outline.py` | v4测试 | A | 98 | `199ebd256827d12279d9b7617bad02bf66be037aa3970c94c8ca39ee7edf2145` |
| `tests/v4/test_p8_learning_preview.py` | v4测试 | A | 137 | `5e9293b1d0e88ab3aa282534a14feaa27162de73eef7a2fe29e91bbcf764cbee` |
| `tests/v4/test_p8_learning_review.py` | v4测试 | A | 74 | `a8c5ef5a06e732c82c31e94f13ec416ecfaf4fbf13fba4385755fd82e39d9723` |
| `tests/v4/test_p8_line_coverage.py` | v4测试 | A | 270 | `0e90ebefafdfeff9c8ebc2992d0f62cd3dd71639cfd20ff7b4d938f69581019d` |
| `tests/v4/test_p8_mapping_review_24.py` | v4测试 | A | 107 | `e044249c3937b5da97808bd8cd550827949650b88fc6a7a3fd124eec5b2be469` |
| `tests/v4/test_p8_meta_integration_process.py` | v4测试 | A | 27 | `edef486dc40f43489860b3af4118dbd3199186bc7daac599e73b5061af562758` |
| `tests/v4/test_p8_night28_api_review.py` | v4测试 | A | 139 | `5b885bb2c9822d550dd18387d00f353808accf3f178462881b02d51413b27d42` |
| `tests/v4/test_p8_performance_safety.py` | v4测试 | A | 27 | `534c8f2320a7fbd5eb89e3719dd9072b5c7cb7287832c902714726082cd62537` |
| `tests/v4/test_p8_product_skills.py` | v4测试 | A | 119 | `98f1d9cbf7f22f1664108c91520441cbac7dc41deb72e305b22c88603e558c4c` |
| `tests/v4/test_p8_rectification_calibration_scope.py` | v4测试 | A | 149 | `5daa30d9ffe627e54999a638c0e5afd4d1e761f5eb0684d9ffe247ccbd5d9c65` |
| `tests/v4/test_p8_rectification_fixtures.py` | v4测试 | A | 18 | `4aa1baf28afb1bd68fe06cc170447d583f03d333abe9d8da673e2354e0e40151` |
| `tests/v4/test_p8_rectification_workbench.py` | v4测试 | A | 158 | `1c9f35f08ca309a3d13e76eaae270e13bf16c799a3bfac1bcc992db349a089c4` |
| `tests/v4/test_p8_rectification_workbench_statistics.py` | v4测试 | A | 194 | `da0767191c988473db35d4427937cacb2d09b4ce756259000c44ce3807145392` |
| `tests/v4/test_p8_review23_policy.py` | v4测试 | A | 73 | `dc2d6a870f77dd4991343987e365d340f90ea58fd135b3b6c36d07957cfc490b` |
| `tests/v4/test_p8_rule_hits.py` | v4测试 | A | 102 | `938d94980930b11696a2ae4500ed0ceb037212db623a3ac1a6496d5ef1fc1bf1` |
| `tests/v4/test_p8_rule_review_24.py` | v4测试 | A | 118 | `bc6cff3f277311510a767d0719e62475bf8e6f0419673ff81496c88597b0f8c6` |
| `tests/v4/test_p8_skill_assets_contract.py` | v4测试 | A | 84 | `e69529a991e408c71b1fb51f4ecbfdf67b8c1f87bdf3f84b15ba79af8e5a9d5d` |
| `tests/v4/test_p8_skill_binding_matrix.py` | v4测试 | A | 92 | `f884277c05c11e14ee85d4e357f78bbdc2ad6464de019390aa0073dd78e50393` |
| `tests/v4/test_p8_skill_budget_boundary.py` | v4测试 | A | 38 | `3886bd5ddea2d6f4d43b74f7e51ff56a139982e445393b4d2fc48244681c6a74` |
| `tests/v4/test_p8_skill_field_paths.py` | v4测试 | A | 136 | `5707f8452ce35735ea758a64018913f162bb188bbc6f77f7a9ab2399358ca2a1` |
| `tests/v4/test_p8_solar_independent.py` | v4测试 | A | 80 | `5a023a66dd79d99287ab750c5a0672c0f020e45baecc487b4cc9013374c03900` |
| `tests/v4/test_p8_synastry.py` | v4测试 | A | 126 | `609b64762c116459f9d26c6bfc14ee13d56da1b10bb93308b8c6f05e22eb21a9` |
| `tests/v4/test_p8_synastry_contract.py` | v4测试 | A | 63 | `da2ac9ce06a9497be72cee3a734ce7b4dabbec685a2cf82be2fddac9cb856781` |
| `tests/v4/test_p8_tarot_spreads_asset.py` | v4测试 | A | 138 | `571ac8eceb64dae1c9cbef33953f053329d5fdf35b68e1ed22e101a66ead7a1e` |
| `tests/v4/test_p8_time_basis.py` | v4测试 | A | 158 | `34ba0fa373df5a24561a37b4a442d8c7a1c753ff2710d199a9c6343ca5ed6164` |
| `tests/v4/test_p8_time_basis_entry.py` | v4测试 | A | 144 | `024f09380baf9c00fe49bb206dbc8cb9e187e4b134b61d88090d9239c46e0c22` |
| `tests/v4/test_p8_time_basis_process.py` | v4测试 | A | 66 | `eca423e6c47f11d5ed6c142e4cb494124771bbb24dabe130f2387c8aa3c3e2d6` |
| `tests/v4/test_p8_u12_assertion_boundaries.py` | v4测试 | A | 185 | `50ccba0f501045cb60fe93f404981ad90a9d1ec4fc3dae8f97bef76115db3a92` |
| `tests/v4/test_p8_u12_assertion_contract.py` | v4测试 | A | 86 | `b9e0782e3268b00fc54c1671b14a4ba817d746be3e5236117b54ceeb8f45a1ca` |
| `tests/v4/test_p8_u12_independent_review.py` | v4测试 | A | 103 | `e58bafe76b3b64719cac3ec2162f7a8aaf3e6da87ca3d6752fac507247b1e8ae` |
| `tests/v4/test_p8_u12_rule_assertions.py` | v4测试 | A | 80 | `eda693f7396a8eb6d8d846c45d368ad17e8b59edb6a9ef6d902576ef0724167b` |
| `tests/v4/test_p8_u2_interactions.py` | v4测试 | A | 174 | `44dfd95e7a11c026e163e11d6cb5e0dacd577010db2cf8c8682cf7014929b382` |
| `tests/v4/test_p8_western_timing_entry.py` | v4测试 | A | 79 | `177d0af7580489b017b86afe98c2cbc23cfc567c4f366d12209a28caa81d2ab9` |
| `tests/v4/test_p8_window_public_pages.py` | v4测试 | A | 69 | `b6a1f4ff8d3ffe6ce89de63f057a611555fa80e55a85d98ac8bf5380b2ad2f96` |
| `tests/v4/test_p8_window_search.py` | v4测试 | A | 212 | `54d344adc8624cea95e363a97a728c2331a02b5f7cbe9195baea3d33e221c0ed` |
| `tests/v4/test_p8_window_search_process.py` | v4测试 | A | 48 | `d9f22183b089be9439589deff05dcd16106fe2809a95fb99fb4d0271a3144195` |
| `tests/v4/test_p8_workbench_grid_process.py` | v4测试 | A | 36 | `398933312a5556c9fea2c2e0361eca80d8520debdafd631c57682a7223353868` |
| `tests/v4/test_p8_ziwei_daily_reference.py` | v4测试 | A | 146 | `b9a0358ef7604f6f9af3759e047ae86d51e80ec8e98b0857ffb3a2967eb8620e` |
| `tests/v4/test_p8_ziwei_flying.py` | v4测试 | A | 211 | `b60f4eee7e88f8db1111f4da95b01f28d86c8006229285d946d3e310807fb365` |
| `tools/verify_p8_calculators.py` | 初版验证工具 | — | 153 | `9205d162080545a32e29a0f43b698d03ba16d62a429dc6d74e2762e208349d95` |

## 排除和守卫边界

214 个本线归属 Python 文件之间**没有为了提高比例而排除任何文件**。特别是 tests/test_p8*.py 的 13 文件、tests/v4 的 3 个 p8_*_context.py 辅助和 51 个 benchmarks 文件均在分母；覆盖工具 3 模块也在内，不延续初版“工具尚未提交所以排除”的历史状态。

不纳入这份“本线自身 Python”的内容：

- 7fa 已有且本线未改的 legacy v3 worker/adapter、hermes、其余 Core/测试、其他语言、第三方 site-packages：不是本线新增 Python。可作为只读依赖执行，但不偷算成自身命中。
- knowledge/skills JSON、Markdown、JSON Schema、合成样例：不是 Python 行执行分母；数据正确性/出处/Schema 合约另有证据，不能用 Python 百分比替代。
- private 下草稿/缓存/现场数据、pycache、未跟踪文件与另工作树：不进入已提交完整范围。后续若新增本线 Python 必须先提交、重盘点并显式固定新 SHA，不能静默遗漏。
- 原生 C/Swiss ephemeris内部行、JS、其他线程/子进程：不是此 CPython 主线程行计数能力，报告仍逐项列未采。

未来执行守卫应大于分母：固定所选执行所依赖的全部已提交 Python、pytest.ini、固定入口/插件禁用配置、原生本机 engine 的实际源码与库版本/hash。两解释器的依赖集合不同，分别记录，不声称第三方库已覆盖；禁止为了构建守卫而导入题库正文或输出出生资料。配置、源或 HEAD 在前后不一致就拒绝；仅文档变化的 HEAD 可记录真实 HEAD 后允许，源码变化不能自动迁移到新基线。

## 实施提案：分两阶段，不改 worker/v3/CI/依赖

**阶段 A：完整 inventory 与可审阅的运行注册表。** 建议新增独立 v2 manifest builder，接受明确完整 `base_commit` / `commit`，从 Git 重建并核此归属清单；不要放宽 v1 固定范围或重写 6c 报告。runtime、research、tests（可再分 native/v4/helpers）保持分表，完整并集总表另列。

候选 API：`build_own_manifest(root, *, base_commit, commit, expected_inventory_sha256)`；完整性声明区分 `inventory_complete_for_p8_history` 与 `coverage_collected`，在根代理批准清单前完整性仍 false。即使 inventory 获批，也不能把它当“覆盖率已达到目标”。入口计划用 `SamplingPlan` 静态 JSON，登记 exact node id / interpreter / no-child约束 / fixture和文件hash；不接受任意 `-k`、路径前缀、importname、脚本、callable或pytest参数。新增采样器代码先测试/提交，之后重新显式固定包含该采样器的新 commit；不能让执行工具自身成为未提交遗漏项。

**阶段 B1：纯 Core 定向组。** `collect_core(manifest, plan_id)` 只解析提交内固定注册表。先人工全读所选 exact node 及依赖 fixture，清凭据、禁网络、禁 conftest/第三方插件，禁子进程；逐个小组 baseline+trace 观测开销。可扩到规则正反例、交互表纯规则、技能/词典/20课、契约验证/U12/学习和 E2 scripted 结构，依次显式批准 exact nodes。不得直接 discover 全 tests/v4 或把所有以 test_p8 开头的文件当运行白名单。

现有 3 个 E2 无 fixture 节点可继续作起点；扩展的其他 exact IDs 尚未逐一审批。参数化测试需提交固定函数和各变体身份清单并在实际收集后校验全集，不能允许调用者注入任意参数 ID。需要独立 PG 的节点留单列：本轮无 DB 授权需求，未来只可明确 core_test_meta，不把连接失败当 pass/skip。

特别边界：test_p8_line_coverage 中合成 Git 仓库用例需要 Git 子进程，不能在“禁所有子进程”的 collector 下假称已测；先保留其分母为 0 或只运行不依赖 Git 的具体节点。若将来批准 Git 特许，必须仅固定 Git 子命令、工作树 private/tmp 新仓库、固定参数和脱敏输出，作为单独受审计划，不泛化 Popen 权限。各桥接测试通常启动 Charts，也不能塞入纯 Core 无子进程采样并声称隔离链路覆盖。

**阶段 B2：直接 Charts 原生单进程组。** `collect_charts(manifest, plan_id)` 使用已固定 Charts 解释器、stdlib unittest/trace；Charts无pytest，不安装。从 13 个原生测试文件挑经人工读过的 exact class.method（module/file和方法均白名单），不接受任意 import or unittest discover。只允许实际历法/紫微/西占纯本机计算；输出仍仅路径/行/计数/固定状态，测试失败与异常正文丢弃。

不得把整份原生测试文件直接当安全入口：例如 test_p8_native_calculations 和 named_schools 中有 P8ChartAdapter(...python=sys.executable).calculate，会再启动子进程。首批只能选不启动孩子的确切方法；其余仍在分母并诚实显示未命中。源文件顶层import和setUpClass也须审阅。原生测试方法的父级 unittest fixtures 必须按真实执行，不删断言/改算法追覆盖。

Core→Charts 进程桥接验证与 child trace 是下一独立阶段；当前 Core trace 不会继承到孩子，不伪装成已采。若后续批准，仅新增 test-only bootstrap/invocation shim，固定原 worker +stdin/stdout协议、精确可调用子进程、独立只写计数文件，不改 worker/CI/v3；保留真实 IPC，不能用进程内替身冒充。是否实施须再次由根代理审阅。

**合并：** `merge_own_reports(manifest, receipts)` 只对相同完整提交、清单hash、源LFhash和完整行号集合的成功真实回执求并集；按 runtime 独立表保存，未导入0，失败/超时/skip单列。相同节点重复运行可合计执行次数但不双算执行行。Core/Charts都没采的文件仍完整列出。行被执行不说明断言充分，不叫分支覆盖，不预设90%。对采样器自身的初始化/前置Git/合并路径不人为补1；可由另一个确切纯测试节点在追踪区域内测试这些函数，达不到就保留0。

## 时序、预算与验证门槛

全部操作前报告进程占用；一般顺序 1 Core、0 Charts，或 0 Core、1 Charts。若真桥接单独批准则 1 Core+最多1 Charts，留总并行≤4；任何测试不得暗自继续生孩子。完整回归仅北京时间每小时15–30分窗口，由根代理统一安排，不与其他线满预算并发。完整采样需单独批准其启动时刻与预算；当前01:15完整回归不自动等于批准trace。

每新组先 ≤5秒的小试，再比较开销决定是否扩大；耗时限制/失败只记录固定拒绝标签，不将超时组丢出分母或重试到绿。保持Clock→北京时间记录，专用新UUID private/tmp目录、exclusive新证据文件、零真实模型/服务器/外部消息/网络。

验收应先补：初版结转遗漏保护、完整214清单及额外未登记源拒绝、exact节点和参数清单、库/源/config前后hash、不同解释器拒绝、worker子进程拒绝、路径/符号链接/重复/零行、异常输出丢弃、完整分母冷文件、原生class fixture与自工具源。先边界tests，再单组小试，才考虑更多测试；未经批准不启动。

## 待根代理裁定

建议采纳 P8 首次实现前 `7fa5e10...` 为完整归属起点，并审阅本固定214文件作为当前清单；后续实现采样器会新增文件，届时以明确新提交和重建清单取代此候选。是否批准阶段A，以及先扩哪些具体Core/Charts节点，需单独答复。本文件不是执行许可；原6c/v1工具和所有既有事实均保持。


## 2026-10-21 01:24 续作状态

根代理已批准阶段A并采纳7fa起点；仅新增静态inventory/候选计划与边界验证，未批准B1/B2采样。ef5的214文件保留为历史；新ed5182静态清单为215文件/22,881行，详情见 `night28-full-own-coverage-stage-a.md`。新增A工具/测试提交后还须显式新SHA重建，不冻结未来文件数。
