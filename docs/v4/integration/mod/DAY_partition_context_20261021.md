# P5b 分区上下文纯投影候选

新增入口：`organize.partition_context_v2.project_partition_context(records,sources,*,scope,source_epoch,clock)`；契约位于同目录`partition_context_v2_contracts.py`。这是主线P5b B可采用的纯辅助，未注册ContextEngine、API、工具或数据库实体，不能据此称B已接线。

PartitionScope显式包含owner、subject、底层life_thread、当前区与话题。PartitionRecord包装已有SearchUnit，附区/话题/layer/score/实体revision。sources必须是同一主线当前事务的SearchSource；source_epoch必须来自权威账本。输入快照和hash无法自行证明数据库授权，主线须在上下文构造和最终使用前重新读取。

先按SearchUnit的来源规则过滤：owner/subject/life_thread、active/redacted/incognito、source revision、单位valid/deleted和未来said_at。用户事实必须来自current_user的user源；round是已经组装好的用户+助手一整轮，必须依序拥有两类源，不能把两条任意消息当一轮。重复当前source ID整份投影失败关闭；重复unit ID拒绝。

投影输出：

- constraints独立全局置顶，仅接受非推断的用户事实；不能把助手note伪装为约束。
- 当前区profile优先且保留细节，其他区只作120字符内的抽取式单句；进行中的其他区话题只留标题。
- 当前区且当前话题最多最近30个完整round，时间顺序保留。其他区同名topic ID不会混进来。
- 当前区summary保留最新区摘要；其他区仅取滚动7×24小时内每区最近至多两条抽取式近况，边界含恰好7天。摘要必须标为derived_summary/inferred，显示“派生摘要，非新增用户事实”。本模块不生成新的语义摘要。
- retrieval当前区得分精确×1.5，其他区保持原分数；同分按稳定ID。约束另段，不参与普通检索竞争。

ContextLine正文repr隐藏，引用保留source_refs；仍不能将整包对象或正文写日志。projection_key绑定scope、源epoch、选中内容hash/版本/来源/排序；它只用于结果一致性，不是发送、保存或U38额度许可。

`plan_summary_invalidations(...)`对本scope/线程中已失效的派生摘要生成ID+expected_revision的纯失效计划，不删除原话、不执行SQL、不恢复来源。主线须覆盖topic摘要/其他区近况的完整依赖清单、summary_until_message_id和当前epoch事务，不能仅凭本模块有限输入证明依赖齐全。

## 主线接线与限制

主线ContextEngine先从当前可信存储构造完整轮次、有效事实与带依赖的派生摘要，再调用新投影，按constraints→profile→open_topics→rounds/current_summary/recent_elsewhere→retrieval装配。随后仍必须运行18索引§4a的上下文/预算守卫；本模块没有token估算，不会以字符数冒充模型token数，也不暗丢全局约束凑预算。

分区/话题对应关系、case迁移策略、当前资料与摘要依赖的完整性由主线维护；这组纯函数不作迁移决定。没有模型、数据库或外部传输。回退只需撤下主线对新增入口的引用。

最终112项含75自有+37独立、1000随机撤销/排列组、5时区与英文金额小数抽取；独立45矩阵未改。最后全量仍待合法窗口。final性能1000条合成投影中位0.003850秒、峰1250563B；1000条扫描/200摘要失效中位0.002749秒、峰250222B。旧DAY_partition_performance.json是句界补丁前历史，final报告才对应当前源；纯Python分配不代表PG端到端性能。
