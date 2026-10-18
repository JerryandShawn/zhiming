# 模块线：2026-10-18 夜间至 10-19 08:00

本计划遵循 `.agent/PLANS.md`。用户最新夜间范围覆盖旧阶段中服务器、实测模型和修改既有文件的要求。

## Purpose / Big Picture

在完全离线的边界内交付可接线的整理、校验、主动规则、卡片模块。所有模块只计算结果或调用注入的内存替身，不连接数据库、模型、飞书或服务器。主线以后接到真实存储、运行循环、Outbox 和权限检查；本分支不代做接线和部署。

## Context and Orientation

唯一工作目录 `C:/Users/Administrator/Documents/Codex/zhiming-v4-mod`，分支 `v4/mod-organize`，基底 `v4/main@b9a89b6f84f7bebb640de080548010859aae630c`。开工时指定目录和远端模块分支均不存在，独立克隆后创建，不操作其他工作树。

复用 `mingjing_core/timekit/clock.py` 的 Clock/FrozenClock；只读参考 `application/consultation.py:545` 的完整 `_validate` 与 `adapters/channels/feishu.py` 的既有契约。不改变这些文件，不改 owner 隔离、撤销、原话、Outbox uncertain 不重发等不变量。新增文件相对于本基底全为 A；每项发布前检查基底已有文件逐字节不变。

设计依据：22号v4.3、P5b A.1–7/D、P6增补A–D、P7增补、P9、08§9和07场景SP01/SP02/SP04/SP06、X06、S/R/Q相关场景。大脑文件只读参考，不覆盖仓库已有文档。

## Progress

- [x] (2026-10-18 22:05 +08:00) 创建专用克隆与分支，确认纯新增边界。
- [x] (2026-10-18 22:42 +08:00) 队列1开发验收候选：600条/30天，明确片段233/240=97.08%、全量ARI0.729、约0.06秒、120条模糊全部待审；10轮粘性及apply/revert精确还原通过。独立盲评泛化不足，不能宣称生产质量完成。
- [ ] 队列2：legacy lint、结构、critic v2解析/verdict、校准指标，纯单测。
- [ ] 队列3：主动规则与FrozenClock 1000组随机属性测试。
- [ ] 队列4：JSON2卡片、内存token、CardKit替身与单调节流/关闭/同卡恢复。
- [ ] 加分：四份主线接线说明、独立性能/边界测试、跨模块回归与安全复核。
- [ ] 08:00前：逐项草稿发布、§11回执与最终汇总。

## Surprises & Discoveries

指定模块工作树和远端分支开工时不存在，因此队列1没有可跳过的日间实现。P5本地ONNX Encoder目前也未出现在基底，整理模块须提供本地可注入编码端口与显式关键词降级，禁止下载模型或假装向量实测通过。P9无现成CardKit/action-token端口；只按用户要求实现离线候选协议并标明待官方核实。P7旧默认开启时长提醒与D4冲突，以用户D4关闭为准。

关键词初稿在冻结600条开发集仅67.5%，经一般词表、语义词组、主诉转折和停用二元字串迭代，达到97.08%。标签/语料未更改，不能把该分数称为盲评。另由独立代理先冻结98条、14个新话题后再读实现，消息级仅30.61%、ARI0.0295，说明缺向量时新主题泛化不足；列为待改进并按夜间规则切换队列2，不反复调这份盲评来刷分。

## Decision Log

队列按1→2→3→4发布；独立代理可提前只读研究后续设计，但不提前实现或发布后续任务。基底文件保持不可变，新建文件在本次实现内可迭代，日记按用户明确要求追加。所有模型、HTTP、DNS连接在模块测试中禁止；P9传输只用可注入替身。

600条是合成且预先独立标注的测试语料，不冒充真人历史或盲测；分类器不得读取 expected_* 字段，报告同时给样本量、错误分布及语料限制。低置信全部needs_review。聚类ARI采用成对计数的精确调整兰德公式。ONNX不可用时允许按设计降级，实际模型路径与运行时缺失列待决，不阻塞关键词路径和其他队列。

把无法确定的片段放到显式“待确认”审阅容器，不能据此声称它们语义上是同一话题；全量ARI包含此容器，另报明确项ARI0.758。所有建议都必须人工审阅，关键词模式不得自动用于旧历史生产归区。P5b B/E仍由主线推进；真正ONNX模型缺失与盲评低分一起交大脑决定改进资源。

所有真实存储/旧消息整理应用均留主线。纯变更集必须检查作用域、批次幂等、字段前置状态；撤销仅还原自身确实写过且仍匹配的字段，不覆盖用户后续修改。无需用户夜间回答，无法决定的事项记录后切换。

## Outcomes & Retrospective

队列1新增纯整理流水线与变更集，122项单测通过；600开发验收过门但盲评泛化失败，交付为候选而非生产就绪。每项测试、提交、推送后在 evidence/MOD_2026-10-19 新增独立回执；最终CI未结束或外部协议未核实均明确标为未验证。

## Plan of Work

第一项新增 organize/contracts、local_vectors、segmenter、space_classifier、topic_clusterer、router、proposal、changes 与 engine；变化集为纯内存文档，不包含SQL/API。第二项新增 validation 包，复制旧规则分解为小函数但逐条对照，不调用旧运行服务。第三项新增 application/followups_rules 等独立规则文件，依赖Clock与明确输入的历史。第四项新增 channels/cards、cardkit_client 及token/构建辅助文件；token身份绑定、一次性原子消费和可恢复sequence由内存端口证明。

## Concrete Steps

在本工作树用现有只读Python 3.11解释器运行新测试，设置PYTHONDONTWRITEBYTECODE=1、tracing=false，并清除所有provider Key。输出仅合成ID、计数、耗时、hash和错误代码，日志在本工作树private内。Ruff检查所有新增Python；按项目≤400行/函数≤60行/行≤120拆分。

    python -m pytest tests/v4/organize -q
    python -m pytest tests/v4/validation -q
    python -m pytest tests/v4/followups_mod -q
    python -m pytest tests/v4/cards_mod -q
    git diff --name-status b9a89b6f84f7bebb640de080548010859aae630c HEAD

每项执行测试→只暂存该项新增文件→提交→推送自己分支→更新草稿PR和小回执。没有合并操作，没有现有入口变更。

## Validation and Acceptance

P5b A.7/SP01/SP02/SP04/SP06：600条/30天静态标注历史经真实本地引擎处理，明确片段准确率≥85%、ARI≥0.6、低置信漏标0；同话题连续10轮不跳；apply/revert前后规范JSON逐字段相同；性能<60s，报告硬件/编码模式。

P6/X06：原lint全部规则只告警；无回执保存、未知别名、重复ask_user、空回答、日期/告别边界覆盖；critic从程序映射severity/verdict，不信模型额外字段；合成标签只证明κ/Wilson计算，不证明真实校准。

P7：FrozenClock至少1000组种子随机场景检验quiet/日限/明确提醒例外/7天降频/敏感预览/24h重复占卜。P9：全部卡片JSON2、≤4按钮、敏感preview无正文、token身份/期限/原子重放、sequence递增、300–500ms节流、关闭后不写、崩溃后同卡续写。真实飞书字段和持久PG恢复未验证。

## Idempotence and Recovery

不迁移数据库、不执行旧历史回填。纯变更集有batch_id及逆操作；冲突原子拒绝。CardKit对未知投递不盲重发，内存快照只是接口证明，真正持久化由主线按Outbox契约接线。每项可单独revert新增文件；不删除或重置既有内容。git push若普通认证失败，改用GitHub连接器发布同tree对象并保留本机等价提交，写清两种SHA。

## Artifacts and Notes

小时追加记录和最终汇总：`docs/v4/daily/2026-10-19_mod.md`。证据与每项§11回执：`docs/v4/evidence/MOD_2026-10-19/`。主线接线说明：`docs/v4/integration/mod/`。只含合成资料，不提交私密正文或任何环境变量值。

## Interfaces and Dependencies

不变更依赖锁。组织模块以可注入Vectorizer/纯输入输出运行；验证模块不持有repo/model；主动规则的状态由调用者提供与持久化；CardKit必须接注入传输和CheckpointStore。真实topic实体/迁移/API/context、critic调用/校准采样、Outbox/飞书回调与action token持久存储均由主线接线。

## 修订记录

- 2026-10-18 22:05 +08:00 创建夜间计划，记录用户最新纯新增、离线、草稿、顺序和08:00边界。
- 2026-10-18 22:42 +08:00 记录队列1开发门槛、独立盲评失败、撤销/隐私防护与转入后续队列的决定。
