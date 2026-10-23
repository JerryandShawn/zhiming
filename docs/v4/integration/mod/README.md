# 模块线交接索引

本分支 `v4/mod-organize` 相对 `v4/main@b9a89b6` 只新增文件。运行入口、配置、迁移、前端及服务器没有接线或改动；[草稿PR #10](https://github.com/JerryandShawn/zhiming/pull/10)等待主线/大脑复核，不合并。

| 模块 | 接线说明 | 入口 | 已证实的本地边界 |
| --- | --- | --- | --- |
| P5b A | [整理引擎](Q1_organize_wiring.md) | OrganizeEngine、Router、Proposal、ChangeSet | 148测试；600开发集达门槛，独立盲评泛化失败；必须人工审阅 |
| P6 | [结构/旧lint/critic](Q2_validation_wiring.md) | structural_check、lint、build_critic_request、compute_review、calculate_calibration | 880测试；没有真实评审或人标校准，不启用未校准修订项 |
| P7 | [主动规则](Q3_followups_wiring.md) | decide_delivery、apply_response、repetition_decision、usage_decision | 276测试、4000组随机oracle；不代替PG领取/计数/撤销事务 |
| P9 | [卡片与同卡恢复](Q4_cards_wiring.md) | 七类builder、ActionTokenService、CardKitClient | 200测试；候选外部字段待核实，替身与内存快照不等于真实送达/持久fence |

每份指南列出实际入口、依赖接口、事务顺序和主线需要改的既有文件；这些旧文件在模块线没有改动。P5b B 必须排在主线完整P3上下文引擎之后；前端线和命理线范围未触及。

## 主线接入顺序

1. 先核查真实依赖和当前P3/P4/P5接口，再按对应指南添加受控应用服务/仓储适配器。单元函数输出只是建议或决定，不能包装成“已保存/已发送”的成功回执。
2. 在真实隔离PG补owner、expected_revision、来源撤销、幂等批次、并发领取、token与唯一业务命令、Outbox uncertain和跨进程租约测试；网络调用放事务外。本夜没有连PG来假装这些已验证。
3. P6校准材料和P9官方字段/权限由白天主线核实。模型调用仍受用户“开始”批次授权和额度守卫；飞书/stage/生产保持逐次授权边界。本分支没有代发任何请求。
4. 复核通过后由主线按自己的集成计划引入；保留v3运行边界和旧回归。整理关键词降级不能自动用于真实旧历史，盲评失败证据不可用开发分数覆盖。

## 复现与证据

在仓库根目录的Core Python 3.11运行：

```powershell
python -m pytest tests/v4/organize tests/v4/validation tests/v4/followups_mod tests/v4/cards_mod tests/v4/mod_tools -q
python tools/mod_overnight/evaluate_organize.py
python tools/mod_overnight/benchmark_modules.py --repeats 5 --output private/mod-night/performance-repeat.json
python tools/mod_overnight/audit_additions.py --output private/mod-night/additive-repeat.json
python tools/eval/runner.py --mode scripted --target fake --self-test --output private/mod-night/scripted-repeat
```

测试不需要Key、服务器或真实飞书。性能case的6000条只是冻结语料规模扩展，CardKit使用虚拟时间；不能据此宣称新盲评通过或飞书QPS已测。[性能观测](../../evidence/MOD_2026-10-19/bonus_performance.json)、[只新增审计](../../evidence/MOD_2026-10-19/additive_audit.json)、[日记/总回执](../../daily/2026-10-19_mod.md)保留真实命令与限制。

两份指南的完整Python例子已在socket/DNS禁止下实际执行；其他片段用于说明接口，调用方仍需注入真实授权上下文与经过核实的适配器。
