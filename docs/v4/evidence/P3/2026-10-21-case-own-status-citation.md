# P3 已选事项单次状态写入引用：阶段回执

2026-10-21 07:57，北京时间。root统一提交；不赶08点固定头，不合并、不访问服务器，不发真实模型或飞书。

## 完成了什么

单次真实case_update把本轮已选事项改成paused/closed后，原初始e#现在可通过独立写入证明完成最终引用。没有case_list工具或索引授权：alias必须逐字段吻合同run/epoch受保护initial_context的原case身份，且alias原revision=正规调用expected_revision、当前实际row=+1。

新增`agent_case_write_citations.py`。Finalizer的非活动状态引用分两条受信路径：case_index basis继续原精确completed索引证明；其他仅真正已选Case paused/closed可走严格单次写证明。没有放宽其他实体/状态、未选case正文/写权，不改原L3/alias字节、core4/事件Schema。

`agent_pending_effects.py`只追加明确`completed_case_effect`包装，核当前有效leased run和同epoch真实completed case_update、ok/无error/finished_at、精确saved receipt，然后复用原_initial/_original_call/_attest及来源/效果/血缘核查。它要求原模型与RequestLedger、正规化CaseUpdate/step指纹、同一mutation参数fingerprint/receipt、精确operation+:case及事务时间/currentrev，不能拿无关saved或旧operation前缀放行。**原started/空output pending恢复入口没有改一行条件，也没有补写Journal。**

## 真实本机验证

07:50原复现为2fail/2.13秒：已选事项的真实case_update已saved/rev+1并completed，Finalizer却要求case_index basis而ScopeError，0assistant/result；精确文件为下方原2例。修后同原断言**2pass/2.16秒**。最初反例和后续结果保持时间身份，不改写历史失败。

本机回环PG `127.0.0.1:55480/core_test_main`，每例独立schema；TZ=Asia/Tokyo且显式业务时钟。清API凭据/关闭LangSmith、LangChain、OTel追踪，ScriptedPort，原HTTP/子进程拒绝夹具保留，单个pytest进程。

    python -m pytest tests/v4/agent/test_case_status_own_citation_pending_pg.py \
      tests/v4/agent/test_case_status_write_proofs_pg.py \
      tests/v4/agent/test_pending_case_effects_pg.py \
      tests/v4/agent/test_tool_effect_recovery_matrix_pg.py \
      tests/v4/agent/test_loop_cycle_own_revisions_pg.py -q --tb=short

**75 passed / 39.81秒，0skip、0warning。** 包括34个本片新单次目标和41个原恢复/自写目标，原started恢复的25反例保持。包含预final崩溃后的只读证明回放、缺/错model/ledger/initial、started/error/no-finish、空/伪回执、mutation/op/事务时间不符、alias伪造含case_index借权、旧epoch/失租/未选、外部修订、case/来源撤销、source_refs变造等拒绝；失败不留assistant/result。

另运行`test_case_initial_alias_tamper_pg.py`：修改受保护initial alias的id或revision并重新计算其output_sha256，仍两条拒绝成功。该两例与独立多写链反例合跑：**2 passed / 2 failed，3.53秒**，其中2passed是本片重签alias负例，2failed为下述明确未支持链。不能把混合红组改写全绿，也不与75相加成一次完整回归。

所有job在07:57前结束，之后不开pytest给root08点四槽。Ruff E,F,I,B,UP,SIM、120格式、尺寸及diff检查通过，最大文件316行/函数54行/单行120。尺寸脚本曾因默认GBK读UTF8失败，改显式encoding后通过；不属于产品失败。

## 精确边界：连续同case自写未实现

独立文件`tests/v4/agent/test_case_status_write_chain_pending_pg.py`的`test_two_true_case_writes_then_original_alias_requires_a_full_revision_chain[paused|closed]`真实失败：原alias rev1→goal写rev2→状态写rev3，两个实际写入均成功、3次脚本模型请求，但严格单次门拒绝原e#，0assistant/result。没有xfail。该红文件明确排除本片已绿冻结，不宣称一般连续写闭环；后续需要逐revision完整intent/receipt/mutation/operation链证明，不能仅最后一笔回执授权。

## 文件与LF SHA256

| 文件 | 行数 | LF SHA256 |
| --- | ---: | --- |
| application/agent_case_write_citations.py | 58 | db37d0e613db260f9b0d7216814ea879ffdf41f4146b373ba42a168aafb75ba7 |
| application/agent_pending_effects.py | 316 | 767f73178de389fe2f1b775b49b0eb922745f0f1e5d4116448b6a9514f27d2d0 |
| application/agent_finalization.py | 195 | ea836bbee84c5f5d29224a2a385737232910f4cef8ecd7765ebb0852b0bfd09b |
| tests/v4/agent/case_status_write_support.py | 97 | 5ad25f8bf61da159ff290e46ae4c1401a6c99c7dc569f41dca1944f41abdda5c |
| tests/v4/agent/test_case_status_own_citation_pending_pg.py | 69 | b01d2e1e70658e11221a9a0d6b6632fc346e8983b15dfe41f3281d642650a1b7 |
| tests/v4/agent/test_case_status_write_proofs_pg.py | 207 | 50abf8e67f682b0ea0349fdea53a541d83adba60440a5531eb52b009da79b6db |
| tests/v4/agent/test_case_initial_alias_tamper_pg.py | 44 | 343e19372a001ff6528c5071d858c981172862ee6ea4a43b1b115ba6fdc4f081 |

## 未验证、回退与后续

未执行本片全库、Linux、真实模型质量、网页/飞书或部署验收；case索引/全部Finalizer与新路由的更宽组合待root固定tree合法窗口复验。无迁移或新依赖，移除新委托和completed包装可回退为旧拒绝行为，原pending恢复代码未改。提交号与远端状态由root发布，不以本机目标绿代替PR/CI或上线。
