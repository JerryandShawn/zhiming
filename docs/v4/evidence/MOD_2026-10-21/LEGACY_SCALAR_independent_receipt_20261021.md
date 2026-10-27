# MOD旧桥标量五项独立验收阶段回执

- 分支/最后提交/PR：由root统一管理并报告；本子任务未查询或执行Git，不声称新提交或CI状态。
- ExecPlan：`docs/v4/execplans/MOD_legacy_bridge_scalar_independent_20261021.md`。
- 最终观察时刻：`2026-10-21T11:13:18.865285+08:00`（北京时间）。

## 完成了什么

- [x] 先冻结精确IB01–05及独有合成正文，再写公开输入test；calendar原15矩阵、原测试及断言未改。
- [x] source/anchor/entity/review全由公开构造器和审阅API建立；没有私有helper、calendar fixture或伪seal。
- [x] 新test146行、最长函数48行，完整标注；Ruff E/F/I/B/UP/SIM、format120、AST/尺寸检查通过。
- [x] 首轮`3 failed, 2 passed in 0.22s`；IB01/03/04均DID NOT RAISE，原始JSON/raw日志完整保留。
- [x] root仅加4行新bridge标量守卫，未转换/写回raw值；本子任务只读完整文件及最小字节差异。
- [x] 修后仅复跑原五项：`5 passed in 0.11s`，`2026-10-21T11:11:30.777806+08:00`至`2026-10-21T11:11:31.864546+08:00`。
- [x] 两个合法控制（全int2版本、int0时刻）保持放行，仅生成标签白名单ChangeSet；拒绝用例不泄正文、输入不变。
- [x] 首轮28份、修后29份各自前后字节稳定；后者20域源与runner工具单独分组，漂移均空。
- [ ] 必要兼容由calendar/root执行，本子任务没有扩跑；PG、覆盖、性能、真实审阅/业务接线与CI未验证。

## 评测分数

精确五项：首轮2/5通过、3/5真实失败；root修复后原五项5/5，未修改预期。
没有脚本runner、真实模型或场景集产品评测。模型、网络、服务器、PG、通知、Git请求0。
本后补五项和新bridge不能回填为先前10:45的12371三轮或192产品覆盖已验证。

## 改了哪些关键文件

本子任务只新增计划、五行矩阵、tools/eval/fixtures合成正文、单个独立test、两份运行JSON和本回执；无额外helper。
产品修复归root：新`legacy_bridge.py:24–27`严格revision取缺键1/正int与at_ms exact int（含0）。
去掉这4行后精确重建原字节SHA；其余源码没有变化。原Message/ChangeSet、旧测试、两个冻结矩阵与旧黄金不变。

| 原件 | SHA-256 |
| --- | --- |
| 五行冻结矩阵 | `7b164849815b572f2dcbc583b2718c523965df5546b4dc227f3811b4d6a7cff9` |
| cases规范JSON | `2543357173da255a975c00fa7edc60a1f639e1ece6fa654a65dadd8485bdb9a2` |
| 合成正文fixture | `a77296ab9d19a25a79758027ced13928589b1c308ab25ebe53056def1ac15d9b` |
| 独立test | `dda0e8ee5aa798bb0e6e56860b3312d6deda242601f8e6bc5b88723de957246b` |
| 首失败JSON | `cbd7aa1fc7f560a143dae5a44d70fff829b34124a2a3d5c7e606c102504fdc50` |
| 首失败private LF日志 | `22b1e7365c5d04bf00ba6db1038a7df228828367a957819f4e6863e6ad0adc4b` |
| 新postfix JSON | `82d14457481eb7959a0bbb96cc6fdd772d3c9a52dff9b9e1a4ef2dd852778968` |
| 修后private LF日志 | `e41de8dac76eb5c50b59cbc9ceea421ab5e568fa0d6a5270e3e71ce9878ac1fd` |
| 原bridge | `e6b5a98bf95241d29470d2236b899a05bfd86615b130c13445a5529e85451c9b` |
| root修后bridge | `78ec7567a947388968d3d85d8565495aa904bdd8696ca63969ab30a74c3fc793` |

运行证据分别为`LEGACY_SCALAR_independent_first_20261021.json`与`LEGACY_SCALAR_independent_postfix_20261021.json`，
包含精确命令、源码/原测试/两矩阵前后账本及raw日志路径。private日志保留不提交，不删除历史。
计划在各次测后更新；证据中的计划SHA是对应历史原件，不声称始终匹配活文档。
runner.environment移除12类provider key/禁tracing，TEMP/TMP及唯一basetemp均位于本树private；来源Clock固定UTC，不依赖Tokyo。

## 数据库迁移与回滚方式

无数据库、实际apply、迁移或业务删除。只生成纯ChangeSet；不能拿本地通过代替真实事务重读授权及来源版本。
必要回退交root，对原首失败和最终证据保持追加，不覆盖或删除。

## 偏离设计的地方

首轮raw字典数值相等未落实公开Message整数契约；root补通用严格类型检查。
既定设计未改，五项及calendar15均保持原真值。缺revision默认1保留，不对时间0施加正数限制。

## 未验证 / 已知风险

本轮只5项目标；兼容由calendar/root单独报，未运行coverage/全量/性能/PG/CI或真实业务入口。
哈希/ReviewApproval是纯测试注入的证据身份及host收据，不证明真实用户批准或PG权威查询。
修后快照中的runner SHA只代表当次环境工具；root后续合法固定材料清单更新须单独记，不当成域源漂移。
旧10:45报告保留原源码/测试范围，不能冒充包含本次修复。

## 需要用户或大脑决定的问题

无新增产品决定；root已明确契约并完成本次最小修复，不向离线用户等待确认。

## 建议后续

由root合入calendar原15与本5的必要兼容证据、固定材料绑定及后续合法窗口完整回归，再统一提交/推送。
本子任务已冻结，不再扩例或按覆盖率改产品/真值。
