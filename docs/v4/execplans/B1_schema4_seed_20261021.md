# B1：固定b9在schema4的checkpoint与撤销兼容性

本ExecPlan遵循`.agent/PLANS.md`，北京时间2026-10-21 09:31创建（CreationTimeUtc=01:31:42；最初预填09:30的误差在09:47按实际元数据更正）。main目录`C:/Users/Administrator/Documents/Codex/zhiming-v4`；只实现root新授的fixture/seed和专属测试，不接总编排、App桥、B2/B3/B7/consumer，不修改旧App48目标或固定b9。指令板v2/30仍No-Go，两次Linux恢复尝试已耗尽；本片仅本机随机隔离PG与固定候选业务，真实模型/飞书/服务器/Docker/WSL均0。

## Purpose / Big Picture

在写完整总编排前，先验证最容易被默认初始化掩盖的前提：Core只含0001–0004时，固定b9能否建立四张LangGraph checkpoint表、保存真实合成checkpoint，并通过真实MemoryService/TarotService撤销及导出最新账本。所有候选repo构造都明确initialize=False，前后核七项批准表中的精确1–4前缀；不为了得到绿结果提前迁5–7、改b9或手写撤销结果。失败是本片的有效结论，必须记录具体阻塞而非隐藏。

## Context and Orientation

复用固定b9的`PostgresRepository(...initialize=False)`、`MemoryService.receive/save_fact/create_case/retire_fact`、`TarotService.create_draw/delete`、`LangGraphRuntime/PostgresSaver`和`tools.deploy_core.export_withdrawals`。`LangGraphRuntime(repo)`只setup checkpoint，不执行consult或模型；repo若省略initialize=False则会偷迁7，所以本片对每阶段实际ledger都断言只有1–4。Core源代码来自完整manifest hash固定的b9，新的工具只放外部controller。

初态复用现storage的精确两message/一个succeeded但无result的legacy run，以及synthetic-sent/uncertain两条已保护收据。它们不能降级pending。共同seed另建一组已知合成source/fact/case/draw/终态失败run和两条新的pending收据，并给旧成功run补固定合成answer/source依赖；后续App桥另片才实现。公开回执只有ID/hash/状态/计数，不带正文、私有牌序、checkpoint值、口令或完整DSN。

## Progress

- [x] (2026-10-21 09:30 +08:00) root授权两新tools及专属测试/support；总计划已单独冻结，不再编辑。
- [x] (2026-10-21 09:30 +08:00) 完整读固定b9的foundation、MemoryService、TarotService、runtime、export/apply withdrawal及原B3样本；确认必须显式initialize=False，setup/put可能独立提交。
- [x] (2026-10-21 09:47 +08:00) 实现纯编译规范、默认0连接计划、独立只读observe、完整初态集合/来源/双角色/前缀验证与新随机本机库；实际候选子进程-I/-B/null pycache prefix。
- [x] (2026-10-21 09:47 +08:00) 真PG已证明schema4 setup/合成业务seed/真实checkpoint/初始withdrawals导出可用；真实retire_fact原子失败，UndefinedTable指向core_embeddings，整个撤销事务/Core/checkpoint状态不变。保持精确1–4，不改候选。
- [x] (2026-10-21 09:51 +08:00) 最终固定6件源码/专属测试34 passed/106.63s（14纯契约+20真实PG目标），0skip/xfail/warning；包含额外/抬高version和重算hash后坏来源反例。Ruff/format/400/60均绿，冻结8件交root；不把探针全绿描述为schema4撤销工作。

## Surprises & Discoveries

旧storage已sent/uncertain收据必须保留；本片只新增2条pending样本，精确共同集合将有4条收据。原B3 latest辅助默认构造repo会初始化7，不能直接复用作本片schema4证明。PostgresSaver.setup/put使用自己的pool连接，不能把整个seed误说为一个可回滚事务；若setup或业务seed已提交后checkpoint写失败，保留部分状态、失败停审且不自动重跑。

直接MemoryService无on_revoke时与完整ConsultationService的checkpoint清理接线不同。本片分别记录真实业务撤销/账本与checkpoint实际剩余数，不手动删checkpoint假装业务清理成功；恢复后apply_withdrawals的清理与B3 proof属于已有/后续路径，不借本片结果冒称全链完整。

真实候选首红为`SEED_PINNED_UNDEFINEDTABLE`：固定b9的`repositories/privacy_foundation.py:93`起无条件DELETE迁7的core_embeddings；存在受影响run时还会操作迁5的core_run_steps/core_run_events。故源库保持4时不能生成真实最新撤销delta。本工具withdraw只是显式失败闭合的能力探针，不是可用的stage撤销入口。测试不加xfail：断言真实业务失败、完整状态原子不变和版本仍1–4；这表示阻塞被复现，绝不等于撤销业务验收通过。

首轮新controller校验自身另有时区字符串相等、source/message operation名称与primitive checkpoint未写blob三个实现错误，已分别修正；不把这些误记成固定候选不兼容。日期现用aware datetime比较绝对时刻，东京会话返回+09不会影响固定UTC合成范围。

## Decision Log

2026-10-21 09:30 +08:00 / root当前授权记录：仅新`tools/b1_bootstrap_replay_fixture.py`、`tools/b1_bootstrap_replay_seed.py`及新专属测试/support。必要只读observe helper先报，不扩App/B3/B7或总执行器。真实schema4不兼容必须记阻塞，不能升级7补救。

2026-10-21 09:30 +08:00 / Codex：严格编译合成规范不接任意正文/SQL/实体白名单；初态先拒完整集合不符再setup。seed实际返回的随机ID须绑定已知operation/来源，并在撤销前核整个seed receipt/current state；未知额外实体或伪receipt即使外层hash被重算也不能授权。只允许本机55480/55481的新随机专属库和独立owner，暂不开放正式stage路径。

2026-10-21 09:47 +08:00 / root批准并复核：新增只读`tools/b1_bootstrap_replay_observe.py`。完整规范核两owner/self、原两message/原run/原保护收据、精确3个写operation、原始source/fact/case payload与fingerprint、真实run依赖及精确版本集合`primary/global:self=1`、`primary/case:<seedcase>=2`；额外或抬高版本不准借重算receipt授权。所有真实业务写前同事务锁住Core表重核，schema setup/put仍明确各自可能已提交。

2026-10-21 09:47 +08:00 / root裁定：本轮随机draw由固定b9真实seed生成，后续绑定原seed receipt的完整state hash；不接调用者expected_rows。当前只核draw身份、question和request/tombstone索引，尚未逐字段证明随机deck/payload完整合法性；受控local UUID库探针可保留，不能宣共同profile已可生产放行。更深draw来源验证排后续App桥。源4撤销阻塞转纯计划研究独立delta克隆方案，未经新批准不建delta库、不迁源7、不手填ledger。

2026-10-21 09:51 +08:00 / Codex：只读b9 backfill._run_context确认真实旧reply回填需要request.message精确等于已选原话，因此共同seed的已知legacy run补此字段，原message行完全不改；相应精确fixture校验同步更新，最终完整34组重跑而不复用更改前34/109.33s。后续App桥仍未执行，不能仅凭该必要输入条件宣称回填通过。

## Plan of Work

先写纯fixture常量/规范摘要、初态与seed结构验证；工具默认只输出计划，缺--apply不建连接。显式apply用固定解释器、-I/-B/null pycache prefix及清环境子进程，校验完整候选、导入来源、PG15/回环/随机库owner、无其它会话/队列、Core精确1–4。先真实setup checkpoint，再实际建立已知seed并写一条真实checkpoint；每个已提交阶段实际记录摘要，不签不实原子性。

第二个显式phase在真实seed回执/当前全状态匹配后，用固定b9实际撤销fact及其source、删除draw，并把新增pending收据变成sent/uncertain可导出的状态，保留原保护收据；实际export_withdrawals结果只作私有/测试内观察，公开输出仅hash和计数。前后schema仍仅1–4、secondary和legacy原话保持、无模型charge/发送。checkpoint剩余数作为观察，不能用手动清表取绿。

## Validation and Acceptance

使用共用`pinned_candidate()`读取已核固定b9原件，测试support只创建自身随机库/独立owner并初始化精确1–4；不依赖有Git的archive源码，不从生产拷数据。时钟/合成日期固定UTC，测试TZ=Asia/Tokyo，记录BJT。至多一个窄pytest进程，与linux代理错峰；不跑整库。真实PG业务不可用替身，外部请求始终0。

对应`07_评测场景集.md`的R02/F01等旧历史/撤销基础，不跑或改模型评分。本片通过仅表示Core4存储兼容，不能解除Linux、正式proof、B7、fence或stage门。新额外原话/owner/run、错前缀/角色/收据、坏来源与重复seed必须在写前拒；source1–4业务失败时保留失败原因与原候选不变。

## Interfaces and Dependencies

`SeedRequest(operation_id,phase,candidate_source,candidate_python)`始终local，只有seed/withdraw两种能力探针phase；专用B1_BOOTSTRAP_OWNER_DSN必须为55480/55481回环随机b1_application_<32hex>与同名_owner，预期另有独立_writer，拒PG*隐式环境。无任意SQL/正文/provider参数。fixture为编译的版本/固定合成模板，seed回执独立local schema、admissible=false、target/规范hash/库身份/实际版本/checkpoint数/状态hash、models/sends=0。无新依赖、迁移、固定候选修改。B3只读state_hash/既有pinned-candidate测试辅助可复用，不改其源码。

## Idempotence and Recovery

初态不符或已有seed/checkpoint不自动覆盖/清除。工具只将body-free JSON输出到stdout，本片不写/覆盖回执文件；其保存由受保护外部controller另行管理。setup/put阶段可能已提交，后续失败保留专属库供审阅，不自动重试或清空。pytest仅清理自己创建的随机资源，不能删除已有库/其它资料。root统一提交/推送；本片不stage、不commit、不合并。

## Outcomes & Retrospective

已实现并实际运行本机schema4 seed能力探针。最终专属组34 passed/106.63s，14纯契约+20真PG目标，无skip/xfail/warning；精确日志`private/b1-schema4-seed-20261021/target-after-legacy-intent.log`，六源码行数399/141/374/88/118/143，最大函数49行，Ruff/format绿。完整证据`docs/v4/evidence/B1/2026-10-21-schema4-bootstrap-seed.md`。固定b9在schema4的最新撤销delta真实失败，事务全状态不变；最新账本生成及总编排明确阻塞。没有修改b9或提前迁7，也没有真正执行Tarot删除或把pending改成sent/sending。实际Linux、正式proof、B7、fence与stage仍未由本片验证。

## 修订记录

- 2026-10-21 09:30 +08:00 创建：固定仅schema4兼容性范围、完整集合规范、原sent/uncertain不降级、PostgresSaver独立提交和真实失败保留边界。
- 2026-10-21 09:47 +08:00 按CreationTimeUtc更正实际创建09:31，保留此前误时说明；记录真实schema4撤销缺表阻塞、原子无变化、精确版本集、draw验证边界及正在复验状态，不修候选/不迁7。
- 2026-10-21 09:51 +08:00 固定最终34/106.63s与8件冻结边界；legacy run实际message必要条件同步后重新全组验证，保留此前红/中期历史，转纯计划不建delta库。
