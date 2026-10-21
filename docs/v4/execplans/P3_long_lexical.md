# P3：超长无标点原话的本地分词边界

遵循 `.agent/PLANS.md`。北京时间2026-10-21；仅本机合成验证。

## Purpose / Big Picture

防止181k无标点的生僻汉字原话拖住入库。只改变派生搜索索引的计算边界，原话、来源区间与隐私策略保持。

## Progress

- [x] (2026-10-21 01:20) 独立子进程复现181k生僻汉字分词超过12秒；拉丁、常见汉字和领域词串当时均正常，不能夸大为全部长文本失败。
- [x] (2026-10-21 01:22) 对长于4096字符的独立lexical run采用512字符窗口、32字符重叠；短文本完全保留旧调用。
- [x] (2026-10-21 01:23) 12项目标/5.22秒通过，含三种181k原话的真实PG入库、完整回读、查询和幂等重导。
- [ ] 下一整库允许窗口复核；已有长历史的索引重建未执行。

## Surprises & Discoveries

jieba已锁版本的HMM对长未知汉字串维护增长路径，特定输入明显慢；普通拉丁/常见汉字的181k样例都不复现。不得以单个正常样例宣布问题不存在，也不能把所有普通消息切碎。

## Decision Log

复用jieba已有lexical run边界与领域词表。只有超长单run分窗，重叠保护常见边界词；去重仍按原顺序。长run的词界结果可能与旧全局HMM不同，这是派生索引的有界降级，不是语言准确率证明。512/32远大于本项目专用术语长度，跨窗口的喜用神反例有实际覆盖。原字符/UTF-8正文和来源偏移完全不裁剪。

## Outcomes & Retrospective

同一机器预热后，生僻汉字181k由12秒超时降到1.100788秒；其他三种为0.103695–0.228357秒。结果是本机测量，不能外推生产负载。PG/纯规则12项目标通过。K3发送计量独立，不能拿搜索词数量替代供应商token。

## Context and Orientation

复用 `memory/tokenize.py::tokenizer/searchable_data`、`memory/projections.py::tokenized_payload/project_search` 和 `MemoryService.receive/get_source`。不改变owner/subject、撤销、无痕跳过、原文指纹或来源授权。

## Plan of Work / Concrete Steps

先单进程有界超时复现，再给派生索引加窗口；真实PG三种文本均181000字符，查询包含边界词，重复source_id不新建。测试清凭据/关追踪。

    python -m pytest tests/v4/agent/test_long_lexical.py tests/v4/agent/test_long_lexical_pg.py -q

## Validation and Acceptance

普通六种文本与原jieba输出逐字相同；长未知串传给HMM的窗口≤512；重叠保留边界术语；长自然分句保持原结果；无痕不进入分词器。PG原文完整且查询、幂等重导和无事实写入通过。上述为R07/万消息压力之外的实际入库补充。

## Idempotence and Recovery

无迁移/依赖。回滚代码不改原文；旧长行的派生索引可能需未来授权的重建，当前不自动改真实历史。不停止共享PG，只清测试schema。

## Artifacts / Interfaces

证据 `docs/v4/evidence/P3/2026-10-21-long-lexical.{md,json}`。分词入口签名不变；新内部边界不对模型或前端提供权威事实。

## 修订记录

- 2026-10-21 01:25 +08:00：记录复现、窗口策略、真实PG目标与未覆盖历史索引。
