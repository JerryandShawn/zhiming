# Q1：本地整理引擎接入主线

本说明交付纯计算与内存存储接口。P5b B 的实体、PG 迁移、API、工具与分区上下文，必须等完整 P3 上下文引擎完成后由主线接入；本分支没有实现这些运行入口，也没有执行旧历史整理。依据：[22 号设计](../../22_功能区设计_对话与记忆分区.md)、[P5b A/B/E](../../prompts/supplements/P5b_功能区与旧对话整理.md)。

## 接线前先看质量限制

[冻结评测报告](../../evidence/MOD_2026-10-19/Q1_organize_metrics.json)中的 600 条、30 天开发集：明确片段 233/240，准确率 97.08%；全量 ARI 0.729，明确项 ARI 0.758；120 条模糊消息全部待审；关键词模式一次约 0.057 秒。这份开发集在迭代时已使用，不能称为盲评。

独立预先冻结的 98 条、14 个新话题盲评失败：明确片段 2/14，14.29%；消息级准确率 30.61%；ARI 0.0295。保留原标签与失败记录，不能用开发分数替代泛化验收。**当前关键词降级路径只能提供人工审阅候选，不能自动应用生产历史。** 需要本地向量资源或新增开发语料后，用另一份未参与调参的冻结集重新验收。

## 实际入口与依赖

| 入口 | 输入与输出 | 主线负责的依赖 |
| --- | --- | --- |
| [OrganizeEngine](../../../../mingjing_core/organize/engine.py).organize(messages) | 有序 `Sequence[Message]` → `Proposal` | 单 owner/subject、有效且可持久化的授权消息投影 |
| [Message / TopicCatalog](../../../../mingjing_core/organize/contracts.py) | 明确 `owner_id/subject_id`，消息正文、时间、revision、status；目录含有效话题 | PG 字段归一化、源撤销与区间删除、无痕隔离 |
| [configured_vectorizer](../../../../mingjing_core/organize/onnx_vectors.py) | `ZHIMING_EMBEDDING_MODEL` 的本地目录 → `Vectorizer` | 本机 `model.onnx/tokenizer.json` 与 ORT/tokenizers/numpy；模块绝不下载 |
| [Vectorizer](../../../../mingjing_core/organize/local_vectors.py) | `encode(text)`、`mode/degradation` | 可注入纯本地编码器；缺资源退化并显式报告 |
| [Proposal](../../../../mingjing_core/organize/proposal.py) | `summary/rename/move/merge/split/ignore/to_changeset` | 用户审阅后的编辑意图、当前完整目录与稳定 batch_id |
| [Router](../../../../mingjing_core/organize/router.py).route(message, catalog, current_topic_id) | `RouteDecision`；`topic_id=None` 表示建议新建 | 当前有效目录与主线的创建/写入/回执流程；函数不写库 |
| [ChangeSet / MemoryChangeStore](../../../../mingjing_core/organize/changes.py) | 逐字段正/逆操作、来源指纹；`apply/revert` 返回深拷贝 | 主线必须另做持久化 PG 适配器；内存类不是数据库事务或永久账本 |

`OrganizeEngine()` 会取配置编码器；独立 `Router()` 默认关键词编码器。要保持两条路径一致，应显式 `Router(engine.vectorizer)`。默认 7 区和词表在 [spaces.py](../../../../mingjing_core/organize/spaces.py)，此版本 `Proposal.move` 只接受该默认区集合；用户自定义区的传递仍需主线扩展适配。

## 可直接运行的纯本地最小例子

以下只有合成数据，无数据库、服务器、模型请求。它证明接线形状，不证明分类质量。

```python
from copy import deepcopy

from mingjing_core.organize.changes import MemoryChangeStore
from mingjing_core.organize.contracts import Message, TopicCatalog
from mingjing_core.organize.engine import OrganizeEngine
from mingjing_core.organize.local_vectors import KeywordVectorizer
from mingjing_core.organize.router import Router

owner, subject = "synthetic-owner", "synthetic-subject"
messages = [
    Message("m1", "user", "我准备投简历，想练习面试。", 1000, owner, subject),
    Message("m2", "assistant", "可以先列出岗位要求。", 2000, owner, subject),
]
document = {
    "owner_id": owner,
    "subject_id": subject,
    "messages": {
        item.id: {
            "id": item.id, "owner_id": owner, "subject_id": subject,
            "content": item.content, "at_ms": item.at_ms, "role": item.role,
            "revision": item.revision, "status": item.status,
        }
        for item in messages
    },
    "topics": {},
}
engine = OrganizeEngine(KeywordVectorizer())
proposal = engine.organize(messages)
preview = proposal.summary()  # 私有审阅界面使用，不写公共日志。
changes = proposal.to_changeset(document, "synthetic-organize-batch-1")
store = MemoryChangeStore(deepcopy(document))
applied = store.apply(changes)
assert applied != document
assert store.apply(changes) == applied  # 同批同内容重放。
assert store.revert(changes.batch_id) == document

catalog = TopicCatalog(owner, subject, proposal.topics)
next_message = Message("m3", "user", "这次面试还需要练习。", 3000, owner, subject)
decision = Router(engine.vectorizer).route(next_message, catalog, proposal.topics[0].id)
assert decision.space_id
```

撤销后的同 batch_id 不得重新应用；如用户再次批准，应重新生成建议并使用新批次。已应用批次的网络重试要读取已持久化的原始 ChangeSet/结果，不能拿应用后的文档重新 `proposal.to_changeset`：新话题 ID 此时已经存在，构造器会正确拒绝占用冲突。

## PG 事务与回滚顺序

1. 在已认证的 owner/subject 下，读取允许使用的消息投影与**完整话题目录**。输入按 `at_ms` 排序，不能混 owner、人物或临时来源。先排除已撤销消息与区间；被撤回正文不能进入标题、样例、向量和聚类。PG 原文不因整理而覆写。
2. 在事务外运行分类和建议编辑；向用户展示降级、needs_review、话题数量及最多 80 字样例。样例和标题也是私人内容，只进入有权的审阅界面。
3. 用户确认应用后，在一个 PG 事务里锁定批次/幂等记录、被改消息、被改话题以及消息隐式引用的旧/目标话题。核对 expected_revision、来源/区间撤销版本、owner/subject、原文指纹及每个操作的 before 值。
4. 对当前受控投影重新验证整批；任一源、scope 或前置值冲突都不写。只写标签字段和允许的话题元数据，原始消息的正文/ID/作者/时间不变；再持久化 ChangeSet、来源依赖、批次状态和一次回执。operation_id/request_id 与 payload 指纹必须在事务中绑定。
5. 撤销同样先锁定并重验来源，拒绝已删除/撤回/修订的源。通过后只恢复仍等于本批 after 值的字段；后来修改的字段保留。将跳过路径映射为“部分撤销”，保留最小批次墓碑，重复撤销不再修改；已撤销批次不能靠重放恢复。

PG 原始行和分类可见投影可能不同，例如区间已遮蔽。适配器须分别绑定原始行 revision/哈希与授权投影依赖，不能拿遮蔽后的字符串覆写原文，也不能因原始行仍存在就重新使用已撤回片段。`MemoryChangeStore` 的 RLock 只保护当前进程实例；跨进程并发、租约和持久化均由主线事务承担。

### 完整目录和隐式话题守卫

文档格式是 `{owner_id, subject_id, messages:{id:record}, topics:{id:record}, ...}`。每个非空 message.topic_id 必须存在，message.space_id 若存在必须匹配目标 topic.space_id；局部目录不能冒充完整目录。已有不一致应显式报错并由主线做受保护清洗，模块不会静默改旧数据。

[隐式话题补丁](../../evidence/MOD_2026-10-19/Q1_topic_guard_followup.md)提交 `a59597a` 绑定三种来源：消息原话题、topic_id 操作 before/after 引用的已有话题、显式改动的话题。只改 route_confidence 等标签时也绑定原话题。旧/目标话题后来 revoked/withdrawn/deleted 或 revision 改变，apply/revert 整批拒绝；不能把消息撤销回已撤回话题。本批新建话题没有 before 来源，用整对象前置值和逆操作保护。正常 open/closed/archived 状态保留，不强改 active。

字段缺失与 null/空串分别记录。`last_revert_conflicts` 返回路径与原因，不含原值；新话题被后来编辑或被新消息引用时保留，并报告部分撤销。主线 UI/API 不能把“返回了一份文档”一律解释为全部撤销成功。

## 主线需要接入的已有边界

| 已有文件 | 未来主线工作；本模块线没有修改它 |
| --- | --- |
| [repositories/postgres.py](../../../../mingjing_core/repositories/postgres.py) | 在 owner 事务中实现标签更新、revision/源版本核对、幂等批次与撤销墓碑；不能逐条 `put` 后再补批次账本 |
| [application/memory.py](../../../../mingjing_core/application/memory.py) | 复用来源授权、`get_source` 与撤销账本；把删除/更正级联到话题摘要、向量、跨区近况和整理变更集 |
| [memory/threads.py](../../../../mingjing_core/memory/threads.py) | 复用当前线程/来源投影；topic/case 双向兼容与历史归属按 P5b B 决策落地 |
| [adapters/web.py](../../../../mingjing_core/adapters/web.py) | P5b B 的审阅/apply/revert 与路由 API，request_id/expected_revision、鉴权和部分撤销状态 |

P5b B 的迁移、新应用服务、`topic_route`、`route_changed` 和分区 ContextEngine 尚未在此分支实现，路径和迁移编号由主线最新 ExecPlan 分配。`RouteDecision` 只是建议；不等于归属已保存，更不能直接作为成功回执。无痕来源不进入持久整理目录。已有命理、前端与 v3 入口无需为本纯模块修改。

## 未接线与验收命令

未完成：真实 ONNX、本机真人历史审阅、PG 适配器/迁移、API/工具/事件、case 兼容、P3 分区上下文与撤销级联、stage/生产应用。旧历史 stage 试跑与正式应用需用户逐次授权；夜间禁止执行。

在仓库根目录激活 Core Python 3.11，以下命令均为纯本地合成验证：

```powershell
python -m pytest tests/v4/organize -q
python tools/mod_overnight/evaluate_organize.py
python -m ruff check mingjing_core/organize tests/v4/organize --select E,F,I,B,UP,SIM --line-length 120
python -m ruff format --check mingjing_core/organize tests/v4/organize --line-length 120
```

整理测试在隐式守卫补丁后为 148 项；[原开发/盲评报告](../../evidence/MOD_2026-10-19/Q1_organize_metrics.json)保存原评测时点源码，不应篡改成补丁后的身份。PG 接线后还须补真实隔离 PG 的事务冲突、源撤销、跨 owner、并发重放和部分撤销回执集成测试，纯内存通过不能代替这些检查。
