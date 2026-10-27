# MOD 晨报公开输入边界阶段回执

- 分支 / 最后提交：`v4/mod-organize`；本轮提交、推送和Draft PR状态由root统一记录，本子任务未执行Git。
- ExecPlan：`docs/v4/execplans/MOD_briefing_public_boundaries_20261021.md`。

## 完成了什么

- [x] 先冻结30项PUBLIC预期及原8源；首轮25过/5失败原证据保留，未修改原矩阵、30断言、既有测试或黄金。
- [x] root逐项审读授权后，修复P2节气日差、未知时区领域错误、P8标量证据异常及全批当前来源两种矛盾。
- [x] 同source一致性检查在交付授权后、正文生成前执行；撤回状态不先过滤，坏/缺单份P8继续省略。
- [x] 原30项通过；晨报、day_pipeline、reports有限兼容471/471通过，34.98秒，结束北京`2026-10-21T10:10:18.116478+08:00`。
- [x] 9产品（明确包含新`current_manifest.py`）行覆盖597/640=93.28125%，分支215/254=84.64567%，综合90.82774%。
- [x] 308材料集合/字节before/after一致，docs矩阵另显式绑定pre/frozen/post同SHA`1f77c413625f6f24c059cd9c7fd372c388b613459fb032632dd2bd1719cdaf9e`。

## 评测分数

- 本轮是纯本地公开边界与兼容检查，非runner脚本评测；新增30/30，有限兼容471/471。
- 真实模型请求0；模型质量、计算准确性、PG/平台发送均未验证。
- 首轮失败、修后目标及最终兼容分别见同目录`BRIEF_public_boundaries_first_target_20261021.json`、
  `BRIEF_public_boundaries_fixed_target_20261021.json`、`BRIEF_public_boundaries_compat_coverage_20261021.json`。

## 改了哪些关键文件

- `mingjing_core/application/briefing_v2/calendar.py`、`contracts.py`、`transit.py`、`compose.py`。
- 新增内部`mingjing_core/application/briefing_v2/current_manifest.py`。
- 新增`tests/v4/briefing_v2/brief_public_support_core_mod.py`、`test_public_boundaries_core_mod.py`。
- 新增冻结矩阵/首次失败/最终9文件覆盖及接线补充；首次8文件报告未被覆盖成9文件。

最终9源canonical-JSON SHA：`b81054bd97d3eeb0f410a0b928a563eafa34d06b109409ebc3a5c183eb10a666`。
覆盖JSON SHA：`ae60ab7caaa723a4f76667f5bdb3cd5a75b14049d8801eec39e73b28cd0402f8`。
兼容报告SHA：`8bd39c666c02ca2abf92e40ec11c0aadaa31e65ab4d10ca8d11ba1951cd4439c`。
所有本轮公开JSON为LF；上述字节SHA属于本次文件，不改原始观测数值、时间或source SHA。

## 数据库迁移与回滚方式

无迁移、无持久化副作用。root可按本轮提交回退产品；保留失败证据和冻结预期。

## 偏离设计的地方

无新增产品口径。同source矛盾采用整批固定领域错误而不是选择一方；此前root明确允许此安全行为。
P8结构验证可能在纯编排中重复执行，本轮没有性能测量或收益结论。

## 未验证 / 已知风险

全项目回归、CI、PG来源真实性、通知/飞书/服务器、真实模型与新源码性能均未在本子任务验证。
当前来源/profile快照仍须主线在权威事务内生成并重查；parse/hash/typed对象不等于真实授权。
原15分钟P2快照保守限制保持，06:45准备需在07:00发送前刷新。

## 需要用户或大脑决定的问题

P8 `context.target_layers`字符串含`daily`子串的语义未冻结；本轮未测、不据此改变产品。

## 建议后续

由root复核9源/证据、更新completed_regression显式材料绑定，在合法窗口统一回归后单独提交推送。
无需为覆盖率追加新口径或强造私有输入。
