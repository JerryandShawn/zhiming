# P6 模块线阶段回执（纯模块完成，完整P6阶段未完成）

- 分支 / 最后代码提交：`v4/mod-organize @ d03465a27019170aea3696afac426a0a4b0f4091`；[草稿PR #10](https://github.com/JerryandShawn/zhiming/pull/10)，不合并。
- ExecPlan：[夜间计划](../../execplans/MOD_2026-10-19_overnight.md)。

## 完成了什么（对照阶段提示词的验收标准逐条）

- [x] 全部13类旧规则复制为只告警lint，保留81种字面regex（99次调用）与原否定/引述/重新肯定/闭合例外；不委托旧函数实现、不改旧入口。
- [x] 结构：未知别名删除、对应成功回执目标绑定/附注、每轮ask_user限一次、空白兜底；星期修正、相对日期核对/附注、告别末段去问句。新增三项各15正15反，保存断言15正15反及独立对抗回归。
- [x] 严格critic v2解析与程序verdict：禁额外severity/verdict，quote/证据ID存在性、item/type/confidence、两次解析失败开放、校准门与一次修订/E6例外、低置信抽检、evidence_only。
- [x] 独立typed请求只描述`k3-256k/high`新会话，保留真实回执的pending/deleted等状态；无模型或传输调用，程序finding须绑定本次草稿与实际证据投影。
- [x] 分项混淆矩阵、敏感度、特异度、κ、Wilson95、macro-F1；缺完整标签、版本或人工复核证明时record_only，undefined不伪造为1/0。
- [ ] 人工60+校准、实际评审/修订率、种子缺陷模型检出、S类实测、Agent/run meta/工具接线：非本夜纯模块范围，均未完成。

## 评测分数

本模块880通过；与整理组合 `python -m pytest tests/v4/organize tests/v4/validation -q --basetemp=private/pytest-mod-q2-final` 共1002通过、1.75秒，无skip。52个新增Python文件Ruff/format120通过。220项legacy专项含26份明确synthetic_only旧转录的96条回答精确差分，以及72条复杂合成否定/引用语料。评审完整270组合与程序证据48组合、独立请求/严格解析/校准手算测试覆盖。结构独立审查先得到14个真实失败，修复后194项通过。

指标/源码校验见[Q2_validation_metrics.json](Q2_validation_metrics.json)。本夜不运行真实模型，未生成冒充人工校准的v2/report.md；真实请求0。旧Core完整PG/全v4未在本机重跑，当前只声明上述纯模块检查；GitHub最终头CI另行核验。

## 改了哪些关键文件

新增`validation/legacy_*`、`structural*`、`critic*`、`calibration.py`和专属测试。补充本轮新增整理对象的repr隐私防护，不改任何基底已有文件。新`hourly_log.py`仅在本工作树追加小时日记，无网络或git操作。

## 数据库迁移与回滚方式

无数据库/配置/提示词/runner/旧业务入口修改，无服务器操作。移除或revert本项新增文件即可，v3旧_validate仍保留原fail-closed契约。模块不假装已经替换AgentLoop。

## 偏离设计的地方（及理由）

旧规则未定义severity/span，新增固定advisory严重度和span=None，只作告警不驱动修订。程序对象的引句/证据绑定在typed材料边界验证；compute_review接收的ProgramIssue是受信程序输入，主线必须绑定当前run/revision，不能把模型dict提升为程序证据。缺revalidator显式告警，绝不当作核验通过。

## 未验证 / 已知风险

quote和证据ID存在性不是语义正确证明，仍需真人校准与实际材料质量。人工重叠标签一致度、评审独立HTTP请求、真实拒配额/超时、前端text_reset、危机完整链路均未验证。已修正的weekday finding不要把旧引句继续作为当前critic材料；其原meta留存须服从撤销闭包。所有输入投影由主线构建，原文不得进入日志。

## 需要用户或大脑决定的问题

真实校准标签与用户15条复核待白天由主线协调；不请求夜间回答。建议大脑审查旧lint临时advisory严重度映射，期间只记录告警。没有真实模型开始/服务器操作请求。

## 建议后续

主线按接线说明连接finalize/工具拒绝/完整危机路径，保持v3入口不变；独立会话、账户守卫与真实校准只在明确授权批次后做。本夜立即转队列3主动规则，不等待标签。
