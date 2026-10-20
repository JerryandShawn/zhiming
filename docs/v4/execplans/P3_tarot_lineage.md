# P3：固定塔罗结果的可复核血缘

本计划遵循 `.agent/PLANS.md`，时间均为北京时间。血缘指一条回答依据实际来自哪个工具步骤、哪副固定牌和哪些原话版本，不能由模型自行声明。

## Purpose / Big Picture

塔罗工具已经复用真实固定牌阵服务，但工具结果还不能像盘面一样提供可验证的引用。先把真实工具输入、数据库牌阵和原话区间绑定，再把确实存在的牌面、原创象征解释注册为专业依据。没有创建 native reading 时保留空身份，不伪造一条解读。所有证明限当前 owner、subject、run、epoch 和有效租约；象征解释不能变成用户事实。

## Context and Orientation

仓库根为 `C:/Users/Administrator/Documents/Codex/zhiming-v4`。复用 `application/agent_tools_tarot.py:execute_tarot/start_effect` 的副作用事务、`adapters/tarot.py:TarotService.get/get_for_reading/get_reading` 的真实牌阵读取、`agent/journal.py:Journal.complete` 的完成步骤、`application/privacy_maintenance.py:PrivacyMaintenance._old_steps` 的三十天清理和 `repositories/postgres.py:invalidate_derived` 的来源撤销清理。设计依据为 P3 提示词 M4 的固定抽牌/解读、M6 真实依据提交与评测 TA01–TA03。不得修改 P8、Charts、前端、Finalizer 或 Runtime，也不得放宽现有盘面 c/r 证明白名单。

## Progress

- [x] (2026-10-21 01:42) 第一片：成功工具事务保存真实输入与 native viewer 摘要，复核完成步骤、来源区间、可选真实 reading。
- [x] (2026-10-21 01:44) 第一片：隔离 PG 正反例与三十天/来源撤销缓存清理验证通过。
- [x] (2026-10-21 01:57) 第二片：真实 allowed-kind artifact/interpretive_claim、受信 c/r 注册和 Runtime 正反例。
- [x] (2026-10-21 01:58) 第二片：native 取消/删除/来源撤销闭包、重复读牌不新抽、真实私密线程拒绝及严格 core4 回填。
- [ ] 下一次固定提交头全量回归；本片已完成相关目标与旧 native 删除目标，不能替代全库回归。

## Surprises & Discoveries

`tarot_read` 当前只读取固定已翻牌结果，并不会调用 `begin_reading`；因此正常证明中的 reading 为 null 是准确结果。旧 native context_snapshot 可能缺少原话区间或混入未适配的历史事实；这些牌阵继续可读，但不能凭问题哈希取得新的专业引用。运行的消息依赖必须在保存缓存的同一个事务落盘，才能让已有撤销闭包立即清空缓存。

取消会清空缓存，之后删除若只找缓存会丢掉原 start run。第二片另查当前 epoch 的实际 `agent_tarot_start` 持久成功回执补链，不以 stage 字符串或模型自报 ID 关联。标准 SourceRef 必须带 quote，故长期 mirror 使用单独 `source_ranges` 元数据并持有真实 source_ids/消息版本，不能把缺 quote 的对象塞进同名字段。

## Decision Log

第一片只证明，不注册别名；避免工具返回中的 ID 自证。缓存使用已有 runtime_step，包含私有工具参数和原话区间，服从三十天保留与同步撤销，公开证据不含正文或推理。新增牌阵除问题区间，还记录选项和明确重抽短语的精确授权区间；撤销这些区间即拒绝，而撤销无关片段仍可沿用固定牌。原画、牌义版本与专业别名将在第二片复核后接入，不把首片验收写成全血缘完成。2026-10-21，开发主线，无需额外用户决定。

第二片只对 ready 且与冻结本机原创 deck/meaning/method、牌位、方向、实际 card_snapshot 一致的牌注册 c/r；待翻牌牌阵没有专业别名。r 明确为 symbolic_reflection/not_user_fact，不生成 fact。mirror 存牌面、时间、真实 reading 身份、问题/选项摘要和真实来源 ID/版本/区间，保留中不复制用户原话。注册同时采用 native case 的 aggregate 版本，仅用于失效检测，不把该事项加入 case_ids 或取得修改权。cancel 在原事务清私有缓存、mirror 和步骤/事件正文，保留 native 牌阵实现 U7，并允许原组件合法终止；delete 撤销完整派生运行、回复和 outbox，不删除同运行中真实 memory_write 保存的独立用户事实。2026-10-21，开发主线，经主协调复核。

## Outcomes & Retrospective

第一片证明实际完成步骤与当前数据库原牌、原话、输入指纹一致。第二片真实 Runtime 已发布 core4 的固定牌面 c 与象征解释 r，严格回填能在删除合成 assistant 后重建相同 used_claim_ids/来源，且不会生成用户事实。重复读牌复用同一套 mirror；取消发生在第二次模型 I/O 时仍不能提交。删除清空相关运行、回复、步骤/事件、缓存和 mirror，并令待投递记录不可领取；同运行的独立 memory_write 用户偏好及普通原话保留。无关片段撤销后，新运行仍能引用未撤销的问题/固定牌，模型输入不含已撤销片段。旧 native 删除回归保持通过。此为离线 PG/ScriptedRuntime 功能证据，无真实模型质量或部署验收。

## Plan of Work

第一片新增 `application/agent_tarot_lineage.py`，`save_tarot_snapshot` 只由实际成功工具事务调用。`attest_tarot_snapshot` 要求本轮完成 journal 输出精确匹配，再复核缓存输入指纹、当前 native viewer、真实可选 reading 身份和精确原话区间。第二片在这些证据之上创建已有允许实体 kind 的牌面与象征解释投影，单独接入 `agent/loop_codec.py` 的 professional 证明分支；最后补 native 删除闭包和真实 ScriptedRuntime 发布测试。

第二片 `application/agent_tarot_records.py` 生成并逐字段复核长期 mirror；`application/tarot.py` 从实际 cache/mirror/成功 start 回执查派生运行，`adapters/tarot.py:cancel` 仅增加 late-import 同事务应用钩子。`loop_codec._registries` 明确分流 chart 与 tarot 原生证明，通用 professional kind 仍不能凭工具输出自证。

## Concrete Steps

在仓库根清除供应商凭据并关闭追踪，仅设置本机回环 `CORE_TEST_DSN`。使用锁定现有 Python 环境运行：

    python -m pytest tests/v4/agent/test_tarot_snapshot_lineage_pg.py tests/v4/agent/test_tool_tarot_pg.py tests/v4/agent/test_tool_tarot_bounds_pg.py -q

使用已有 ruff 检查新增/最小修改的三个 Python 文件，检查列宽 120 与 E,F,I,B,UP,SIM；AST 核每个函数不超过六十行、文件不超过四百行。

## Validation and Acceptance

对应 TA01：真实 create/reveal/get_for_reading 的牌面在缓存与当前 PG 一致。对应 TA02：同一步 replay 不新增牌阵、修订或 reading；篡改输入、结果、牌面、reading 或当前 epoch 时拒绝。对应 TA03：现有显式重抽/24小时测试保持通过。新增实际 PG 测试要求未完成 step 不能证明、private start 零持久牌阵/缓存、来源撤销同事务清空私有缓存、三十天清理清空缓存；不发送真实模型或飞书请求。

## Idempotence and Recovery

缓存 ID 从 owner+稳定 operation_id 得出，写入沿用 `repo.put` 的 operation 幂等性；同一步结果或输入改变则冲突，不能覆盖旧证明。来源已经变化时不重建缓存。此切片无迁移、无服务器变更，回退代码不需要数据回滚；遗留缓存由既有保留策略清理。

## Artifacts and Notes

第一片证据为 `docs/v4/evidence/P3/2026-10-21-tarot-snapshot-lineage.md`。测试只在本机隔离 schema，证据仅记录数量与拒绝类别，不记录原话、模型推理、密钥或 DSN。

第二片证据为 `docs/v4/evidence/P3/2026-10-21-tarot-professional-lineage.md`。无 SourceRefs 或不受支持 deck/meaning/method 的历史牌阵不能获得 c/r；既有标准读端继续兼容 core3/core4，不引入新实体 kind。

## Interfaces and Dependencies

`save_tarot_snapshot(service,ctx,args,result)->None` 是真实副作用事务内钩子；`attest_tarot_snapshot(service,run,name,result)->dict|None` 返回当前已完成步骤的受保护快照，失败工具返回 None。`reading_identity` 仅返回实际 ID、draw ID、version、model、prompt_version 和创建时刻。无新依赖、无新表或 API。

## 修订记录

- 2026-10-21 01:44 创建并记录第一片验证；明确 professional 别名与删除闭包尚未完成。
- 2026-10-21 01:58 第二片接入 c/r 和取消/删除闭包，记录真实 Runtime、严格回填与旧 native 删除验证；全量回归交固定提交头窗口。
