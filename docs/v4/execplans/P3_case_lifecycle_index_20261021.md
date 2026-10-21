# P3：合法暂停与关闭事项的索引引用

本ExecPlan遵循`.agent/PLANS.md`。记录采用北京时间，测试显式冻结业务时钟；root统一提交，不做服务器/真实模型/飞书/合并操作。

## Purpose / Big Picture

事项的真正生命周期契约是open、paused、closed、deleted。先用真实case_update把选中事项暂停或关闭，完成该轮；新一轮case_list已经能返回这些非删除索引，但最终引用被通用活动状态门误拒。此片把已验证历史索引例外应用到合法paused/closed，保持只读标题/状态、原owner/subject/修订/撤销门和selected_case写权限。

## Context and Orientation

复用`domain/contracts.py:Case.status`与`agent/tools/interaction_parameters.py:CaseChanges.status`的合法枚举、`application/agent_tools_cases.py:mutate_case`的真实写入、`application/agent_case_index_lineage.py:case_index_lineage`和`application/agent_case_index_citations.py:assert_historical_case_index`的精确当前epoch索引证明。前片445b74c已修done/archived；它们并不代替合法Case生命周期，不能与Agent run状态混淆。

不可改变冻结core4/SSE Schema、其他实体状态、L3“进行中”过滤、未选事项正文/写权或公开工具参数。28号主线储备c是case_list缺口，33号一§1是P3收尾；原07号R08场景与评分保持不动。

## Progress

- [x] (2026-10-21 07:44 +08:00) root确认将合法paused/closed纳入精确completed索引只读引用，先独立小片；本轮关闭后的原e#另外复现提案。
- [x] (2026-10-21 07:46 +08:00) 完整双轮Runtime先发现L5 scope改变未换epoch的独立缺口，2条真反例交root接Context，不加xfail或更改断言。
- [x] (2026-10-21 07:46 +08:00) 真实case_update组件+Journal后明确cancel组件run，新Runtime索引修前2fail/3pass，3.02秒；两合法状态精确在helper状态门失败。
- [x] (2026-10-21 07:47 +08:00) helper只扩paused/closed两常量，65项窄组合通过17.35秒；Ruff/120格式/尺寸通过。此结果不代表双轮Runtime闭环。
- [x] (2026-10-21 07:48 +08:00) 4文件证据冻结交root；完整双轮2条复现文件另交root，不混进本片已绿命令。
- [ ] root提交/推送；Context独立缺口处理后双轮真实复验，08:00全量使用固定已验证提交。

## Plan of Work

最初新测试给已选case绑定当前原话，调用真正AgentRuntime→case_update，取得saved且精确版本变化，第一轮回答不引用case以隔离本片目标。下一run没有case_ids，用case_list拿标题/状态e#；实际先在L5 scope改变处失败，尚未到Finalizer。真实完整两轮原断言保存在`test_case_lifecycle_index_pg.py`交root独立修Context，不能删反例或加xfail假装闭环。

经root确认，新`test_case_lifecycle_index_component_pg.py`用实际ToolRegistry→case_update→Journal真实写入与完成，再明确cancel仅组件run（没有发布第一轮对话、没有pin L5），随后新Runtime核索引。此分离目标让paused/closed状态门能被独立复现；不代表完整双轮产品验收。

生产只改`agent_case_index_citations.py`允许状态集合，原真实completed步骤回查与完整PG投影/alias比较保持。拒绝deleted/stopped/superseded/未知状态，非case实体paused/closed仍拒绝。不自动放行本轮case_update产生的非index别名；该独立问题先复现后另提受信写回执证明方案。

## Validation and Acceptance

输入合法暂停/关闭请求→真实case_update保存成功→新run索引引用e#成功；case_ids仍空且未选正文未披露。没有真实索引证明、旧投影、错run/epoch/seq、撤销/修订变化及其他实体状态仍拒绝，无assistant/result落盘。原07号R08不改分数；本片是额外本机PG边界。

    python -m pytest tests/v4/agent/test_case_lifecycle_index_component_pg.py \
      tests/v4/agent/test_historical_case_index_pg.py \
      tests/v4/agent/test_historical_case_index_guards_pg.py \
      tests/v4/agent/test_case_index_lineage_pg.py \
      tests/v4/agent/test_agent_finalization_pg.py -q --tb=short

## Surprises & Discoveries

现有CaseChanges与Case domain都明确定义paused/closed；done/archived只是额外历史行兼容，不能声称它们覆盖合法生命周期。旧历史负例先改变行状态而不重做索引，仍应继续拒绝陈旧索引；不删除该保护。

第一轮已选case的L5含绑定case原话；第二轮未选case使BoundedSources._history过滤这些行，但同life缓存epoch未因case scope变化重开，抛context_l5_append_only_violation。root独占Context修复，索引小片不碰它，也不清缓存绕过。另一本轮关闭后原e#自写引用问题也不借case_list放行。

## Decision Log

2026-10-21 07:44，root批准先完成只读索引小片。本轮已选case_update关闭后引用旧e#不借case_list授权，另复现并提出精确完成步骤+mutation receipt+当前修订证明路径。

## Idempotence and Recovery

没有迁移、外部动作或回填。测试case_update使用原稳定operation_id与真实mutation去重。只读索引完成证明不能伪造或补写。收回新增状态集合即可回退，不改既有Case数据。

## Outcomes & Retrospective

独立真实case_update组件→新Runtime索引目标和原回归共65项已绿，证据在`docs/v4/evidence/P3/2026-10-21-case-lifecycle-index.md`。生产仅1行状态常量差异，真实索引证明全部保持。完整双轮Runtime仍有已交root的L5 scope缺口，未验收、不加xfail；root提交后再固定tree复核。

## 修订记录

2026-10-21 07:44：创建，分开合法生命周期索引和本轮自写引用两种授权来源。

2026-10-21 07:48：记录新发现的真实双轮L5缺口、经批准的组件分离边界和65项目标结果，冻结索引小片。
