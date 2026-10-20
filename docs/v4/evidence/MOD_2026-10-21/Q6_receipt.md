# Q6 P9纯模块阶段回执

- 分支：v4/mod-organize；实际提交/推送号见日报；PR #10保持草稿。
- ExecPlan：docs/v4/execplans/MOD_2026-10-21_continuation.md。

## 完成了什么

- [x] K3动作allowlist：普通4类24小时，高风险确认15分钟；原子consume/operation重放保持。
- [x] 完全绑定且实际过期才给固定刷新文案与纯意图；错身份/撤销/未知/存储失败统一无效。
- [x] 流式Outbox意图、两阶段freshness、token/fence/revision租约、同卡递增seq、崩溃恢复与unknown不重发。
- [x] 仅明确close拒绝可产生fallback意图；完整版本manifest与原话epoch必须一致。
- [x] reconciliation.cardkit双CAS深合并计划，保留旧对账proof和未知siblings；新指南与六模块索引。

## 评测分数

- 新Q6共1301项本地测试通过，3.68秒；独立201项为子集，矩阵SHA eb97be17d0e19d42757c37783ca2c3db58fdad1776e33eeb4e6e4f72e1159b83。
- 含K3乱序、租约崩溃/Clock与namespace各组1000随机循环；旧token58项另由专线回归通过。
- Ruff E/F/I/B/UP/SIM、format120、22文件尺寸/函数检查通过；六份接线指南链接实际存在。
- 1000 token全签发/首次consume/replay中位0.207545秒、Python峰1148349字节；满容量末尾replay1000次0.113268秒，错owner拒绝1000次0.087415秒。
- 500次namespace CAS中位0.237852秒/峰19568字节；1000次stream metadata roundtrip中位0.037627秒/峰3649字节。纯CPU/分配观测，不是PG或飞书时延。
- 北京00:46:48在合法窗口启动的全量已完成模块回归5841/5841通过，11.66秒，报告Q6_completed_modules_regression_namespaced.json。此前两次测试收集错误原始报告保留；新增memory2测试namespace后解决同名冲突，没有改冻结的Q5测试/产品。
- 真实模型、服务器、飞书0，无模型下载；回归仍只覆盖离线模块。

## 改了哪些关键文件

新增action_token_policy_v2.py、action_token_refresh_v2.py、stream_outbox_v2/、cardkit_reconciliation_v2.py、tests/v4/p9_v2/及两个性能脚本。旧token/CardKit/Outbox/reconciliation writer均未改。

## 数据库迁移与回滚方式

无迁移、无真实发送。namespace返回的是行revision/fingerprint CAS计划，host实际加锁持久化；没有PG租约实现。撤回新增入口引用即可回退，旧路径行为保留。

## 偏离设计的地方

旧namespace schema明确拒绝隐式覆盖，需要主线提供迁移适配。旧15分钟question token不被重新解释成24小时。外部字段保持“待对照飞书官方文档核实”。

## 未验证 / 已知风险

FreshnessEvidence和evidence_ref只能由可信host在权威事务中构造；纯模块无法认证伪造证据或证明数据库确实查询。实际target绑定/来源撤销/原子effect、PG fence、transport和真实断线恢复未验收。现有旧Outbox writer会整块替换reconciliation，主线必须接命名空间安全更新，否则可能抹掉新子树。

## 需要用户或大脑决定的问题

正式外部字段核对、PG接线、旧metadata迁移由后续主线/26号研究处理；本线不等待，不执行外部动作。Q5质量未过的问题仍独立保留。

## 建议后续

主线按Q6指南逐个接可信事务、claim、发送前复核、持久意图和回执；先离线PG/替身故障验证。模块线继续储备池及白天追加，不因主队列结束提前停工。
