# P3：严格回填 core3/core4 的已提交回复血缘

本计划按`.agent/PLANS.md`维护，时间均为北京时间。本片独占`mingjing_core/memory/backfill.py`、新增测试和文档，不改读取helper/Finalizer/Runtime/Outbox或其他线文件。

## Purpose / Big Picture

缺失的历史助手消息可从已成功的持久run恢复，但必须保留原话、事实和专业引用的真实血缘。core3明确读取cited_*，core4严格校验后读取used_*；未知schema或无效final不猜版本。私密消息不能借元数据回填移入人生线程或长期历史。默认dry-run，真正apply继续由同一owner事务覆盖，第二次零变化。

## Progress

- [x] (2026-10-21 01:11) 完整读backfill、读结果helper、原300轮/中断回滚/撤销测试、助手持久存储与core3专业声明生成。
- [x] (2026-10-21 01:21) 添加共用严格schema投影、逐引用/原话校验与无痕跳过，保留core3明确历史形状、native claim ID与可验证临时事实。
- [x] (2026-10-21 01:27) 最终28项新真实PG正反例及10项原P2回填/精确来源回归共 **38 passed /22.99s**，无skip；一条既有Starlette/AnyIO弃用警告。含实际私密Runtime→core4→回填不转life与显式validation.schema混版拒绝。只一窄进程，外部请求0。
- [x] (2026-10-21 01:27) Ruff/format/diff及400/60尺寸检查通过，业务358行；证据落`evidence/P3/2026-10-21-core4-backfill.md`，最终冻结交root。
- [ ] root统一提交推送/后续组合回归；本片不执行真实数据回填。

## Context and Orientation

当前backfill_replies仅检查answer是否非空，并只读cited_fact_ids/cited_claim_ids。core4最终信封有严格Schema和used_*，旧代码会漏血缘。backfill_entities会把所有message的thread_id计算为life，需保留无痕身份。复用`application/read_result.py`的严格版本投影、`memory/threads.py:record_assistant`的稳定ID/撤销防复活、PG owner事务和原撤销账本。

## Surprises & Discoveries

core3专业引用使用native claim_id，实际PG interpretive_claim行是run:eN:native；core4用真实entity ID。core3临时事实current_source_*不是长期fact，但已提交evidence带完整原话区间，需对照真实用户消息，不能新建事实伪造兼容。原P2历史最小结果有明确core3 schema和validation.status，不带meta；保留该已定义形状，不将任意缺schema字典视为core3。

新测试初轮24通过、3个fixture错误：跨subject污染必须先有真实subject（不能绕FK）；绑定渠道若放在终稿之后会正确推进owner版本而触发既有Outbox freshness拒绝。修正合成fixture顺序/合法前提，保留原隔离和freshness规则。未修改既有测试断言。另一个新增导入集合错误修正为实际`adapters.delivery.DeliveryUncertain`，未改业务异常类型。

## Decision Log

2026-10-21：只回填持久succeeded且可验证的结果；坏数据计skipped，不把未知schema当core4。core3 native ID与core4实体ID按各自契约保留，逐条核owner/subject/有效状态/撤销和原话区间；不能从正文正则猜引用。无痕的元数据不改life，回复不回填长期。整个apply失败仍事务回滚，不降低原撤销/Outbox不重发行为。

2026-10-21 01:21：core3缺valid字段的旧明确validated形状继续接受；显式False或字符串"true"拒绝。core4额外核runtime=v4、持久run/operation身份、实体采用版本和严格整数epoch。只把可证明的事实原话/声明来源加入助手血缘，不创建新事实，不把context_only临时ID伪装长期实体。core3不同版本的used_*附加字段不能覆盖cited_*。

2026-10-21 01:27：root批准补显式validation.schema冲突拒绝；旧core3缺该字段仍兼容。顶层schema_version、可选顶层schema与显式validation.schema必须一致，不把混版validation当作有效终稿。

## Plan of Work

先补版本投影和真实引用解析，再接原回填循环；保留原计数/稳定ID和跨事务边界。以真实PG构造合法core3和实际Runtime core4终稿，移去合成助手行模拟历史缺失，核血缘/重复零变化；污染schema、引用、owner/subject或撤销后必须跳过。不得改旧断言迁就实现。

## Validation and Acceptance

覆盖core3/core4、事实/专业引用、跨owner/subject/来源撤销、坏final/未知schema、无痕不转长期、dry-run不写、apply重复零变化和中断回滚。只用本机隔离PG、合成模型/禁外网HTTP；新代码尺寸400/60/120与Ruff通过。旧Outbox原行不变，没有外部投递。

## Outcomes & Retrospective

本片补齐core4引用回填及严格旧格式兼容，最终真实PG **38/38** 目标通过；包含实际Chart工具→可信c/r→Loop→core4 Finalizer终稿的回填，原300轮dry-run/apply/重复零变化及中断整体回滚仍绿。实际私密Runtime生成的原话/助手/信封不被回填到life，元数据/FTS保持原样；sent/uncertain真实Outbox行逐列不变且仍拒绝再次claim。

只证明本机合成数据回填程序，不证明真实历史已经回填或stage/生产可执行。没有服务器、真实模型、飞书或真实用户数据操作；没有数据库迁移。整个P3及精确新头全量/CI由root另验，不把本片目标绿作全阶段结论。

## 修订记录

- 2026-10-21 01:11 +08:00：建立本片计划，记录core3 native/临时事实兼容与私密元数据风险，未运行回填。
- 2026-10-21 01:21 +08:00：记录严格投影/私密保护、26新+10旧真实PG回归及保留旧行为的fixture调整原因；候选尚待最后私密E2E，未执行真实历史回填。
- 2026-10-21 01:24 +08:00：最终补实际私密Runtime E2E并完成37项窄回归，检查后冻结；此前36项仅为上一版，不重复相加。
- 2026-10-21 01:27 +08:00：root释放后补validation.schema冲突与core3反例，完整窄目标38/38再冻结；37项为前版历史，不叠加。
