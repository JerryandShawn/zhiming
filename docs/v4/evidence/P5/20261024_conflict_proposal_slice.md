# P5 冲突候选进入真实 memory_write（WIP）

2026-10-24 00:40 +08:00；指令板 v3，v4/p5-memory2，PR #17 草稿。当前只完成候选→待确认提案及拒绝分支，选择新说法的消费与相应撤销尚待完成，不能称为冲突处理验收。

真实写入入口在原话/隐私/绝对日期检查后，识别同一主题的明确相反偏好，先产生同一 P3 proposal，不写第二条相反事实，也不覆盖原事实。工具数据给出“以前你说……，现在说……，以哪个为准？”，回执仅保留 ID/版本/状态。提案携带新旧两侧原话及旧事实依赖，忘记任一来源就沿现有隐私级联清除正文。重放也重新验证目标修订、两侧原话及当前有效性。

限定为纯词法候选：同一剩余主题、单一明确喜恶词、无假设/疑问/复合转折。改变主题、内部词边界或限定条件不分类，工具明确 vector_available=false。未接向量或通用语义矛盾，不声称召回率/准确率达标。没有读取任何冻结盲评集、真实历史或模型。

使用现成 .venv-k3、本机隔离 PG15 独立 schema、注入时间及禁 HTTP 夹具，移除密钥、关闭追踪、Python loopback-only 网络守卫：

```
python -m pytest tests/v4/memory2/test_conflict_candidates.py tests/v4/agent/test_memory2_conflicts_pg.py tests/v4/agent/test_memory2_merge_pg.py tests/v4/agent/test_memory2_proposals_pg.py tests/v4/agent/test_memory2_proposal_undo_pg.py -q -p no:cacheprovider
48 passed in 10.11s

# 写入元数据抽出为小函数，并补充未来来源/不同主题/opt-out 守卫后：
python -m pytest tests/v4/agent/test_memory2_conflicts_pg.py tests/v4/agent/test_toolkit_pg.py tests/v4/agent/test_memory2_categories_pg.py -q -p no:cacheprovider
52 passed in 13.06s

# 新增现有 Agent 依赖闭包检查，仅跑新用例：
python -m pytest tests/v4/agent/test_memory2_conflicts_pg.py::test_existing_loop_lineage_attests_old_fact_and_both_originals -q -p no:cacheprovider
1 passed in 1.12s
```

批次有重复范围，不合计。证明：真实工具仅生成一个待确认提案；旧事实不变；旧来源陈旧/在本轮未来时不产生假冲突；“别记”优先；拒绝复用 MemoryProposalService.reject 清正文；普通“请保存”按钮不能冒充已选新真值；原话/事实被忘记或修改后缓存不复活。调用未修改的 verified_versions，确证提案、旧事实及两侧原话都进入实际依赖闭包，未放宽 Agent/提交守卫。

静态检查 E/F/I/B/UP/SIM、120 列格式、单文件≤400/单函数≤60 行通过。本轮单测试进程，无全量、真实模型/飞书/服务器请求或下载。

测试变更说明：此前本线新增的“不模糊合并”用例期望相反偏好并存两个事实。现在保留“相反文本不能合并/覆盖”的保护，将新增结果改为一条原事实+一条待确认提案，符合 P5 写入冲突要求；没有削弱原话、撤销、owner、revision 断言，见 ExecPlan Decision Log。

未完成：明确选择旧/新说法后的统一消费、敏感类别记住选项与组合撤销、槽参数/updated 提交证明、指定 v4 scripted 场景及全量验收。普通 accept 对冲突提案明确拒绝，防止把敏感“保存”确认误当真值选择。下一步优先补此消费，而非继续堆独立候选。
