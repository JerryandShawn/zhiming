# 临时合盘运行内引用 v1（独立入口，默认关闭）

meta v5/49号命理线第4项授权实现第三批以后的协议；本实现不注册Agent，不改变第二批R33默认：未存档临时合盘不登记c/r、不换前缀、不写长期实体。
代码位于skills/temporary_synastry_references.py和temporary_synastry_scope.py，属于计算后的解释上下文；既有charts.synastry计算、默认v3和主线均未修改。

## 调用契约

构造 `TemporarySynastryReferences(binding, *, clock, run_deadline, revalidate, enabled=False)`。
binding为不可变SynastryBinding：owner_user_id、run_id、双subject_ids/revisions/operation_ids、compute_operation_id、grant_id、kind。
两人可使用临时ID，不要求或创建长期人物实体。禁止把模型提供的birth/consent当作可信输入。

调用方先从可信按钮授权和worker完成结果取得binding，提供每次读取当前账本/当前资料修订的revalidate(binding)函数。
它必须返回ConsumedGrant(binding, confirmed_at, expires_at, consumed_operation_id, revoked=False)；最大24小时，必须已经消费于这一个计算operation。
已消费的同operation可重放/阅读；不是“剩余次数为0就自动失效”，也不授权第二次计算。
本模块不执行计算或消费授权，不能替代主线授权事务，内容指纹也不是来源签名。

`register(result, *, binding)`：仅接受可信p8-synastry-v1结果，核双方scope/kind/consent标志及重建文档指纹、全部Pointer和真命中别名。
重算本次c/r映射；c按实际路径排序，r按真实命中顺序，均在此容器独占的别名空间从1开始。登记结果为run随机document_id、aliases、notice和retention=current_run_only。
每个别名行含新run文档ID、path/value_sha256、该文档绑定的新claim_id；r含实际rule_id/evidence_aliases。
同binding同结果幂等；同operation换结果拒绝TEMPORARY_OPERATION_CONFLICT。不得将本容器局部c/r直接并入主线已有别名表；未来主线须整体保留独占run命名空间或重新分配全部相关引用。

`resolve(alias, *, binding, document_id)`：严格标准c/r，逐次检查owner/run/双方revision/操作/授权，返回所指真实值的深拷贝；r只指met=true、有school/source的命中。
读取前及复制后各重验授权。其他owner、run、缺文档、假短号统一CITATION_UNAVAILABLE，不透露存在性。
到run_deadline或授权到期返回CITATION_EXPIRED并清空；撤销/修订变化/回调异常关闭容器，后续不可恢复。
内部锁保护本容器并发关闭；外部授权账本与最终发送之间的原子性仍由主线事务/闸门保障，不能声称消除了分布式撤销竞态。

## 生命周期和持久化边界

以with容器管理整次run，finally/结束/取消/超时/登出调用close()；异常退出自动关闭。进程重启没有恢复路径。期限到后访问会清空，空闲到期清扫/登出事件仍须未来调用方主动close，不启动后台线程。
禁用pickle/checkpoint序列化；repr不含scope、文档ID或正文。不写SQL、文件、日志、缓存、队列、摘要或记忆，也不提供持久化导出入口。
返回的临时投影/值同样不得被调用方存档；Python无法阻止调用方把深拷贝写文件，此实现不是整个应用的隐私闸门验收。

`seal_generated_text(text, *, generated_for_temporary_synastry=True)` **整段丢弃临时系统解释正文**，只留下“本次合盘是临时计算，没有存档。”；仅删标签仍可能泄漏他人生辰，所以最简默认比草案的白话保留更严格。
仅供系统生成的临时解释封存前处理，不能传入或改写用户原话。流式前端可在当前run展示临时结果，run结束即失效，无展示租约。
完整结果、投影与派生解释须整体排除记忆/笔记/AboutMe/反思/总结/索引/checkpoint；主线未来接入时还需按草案检查所有派生链和外发路径。本线未接这些主线接口，也未授权飞书发送。
内存引用解除不等于操作系统交换区或进程转储的可证明擦除。

## 错误码和来源

TEMPORARY_PROTOCOL_DISABLED（默认关闭）、TEMPORARY_SCOPE_INVALID、TEMPORARY_CLOCK_INVALID、TEMPORARY_RESULT_INVALID、TEMPORARY_OPERATION_CONFLICT、CITATION_UNAVAILABLE、CITATION_EXPIRED、TEMPORARY_RESULT_NOT_PERSISTABLE、TEMPORARY_GENERATED_TEXT_REQUIRED。
错误文本不带出生资料、内容摘要或调用方异常。
规则来源和具名流派来自原synastry真实命中，并通过resolve(r#)读取；本容器不新增命理判断。沿用synastry.md的原典版页/流派与现实效度待核项。
依据：p8_temporary_synastry_references_draft_20261027.md、meta v5、49号第三节命理线第4项。默认R33与倒推冻结保持。
