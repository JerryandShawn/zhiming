# B1：schema4源库的独立delta副本方案（仅计划）

本ExecPlan遵循`.agent/PLANS.md`；北京时间2026-10-21 09:54创建。本片仅源码只读审计与设计，未创建delta库、未连接PG、未运行测试/模型/飞书/服务器/WSL/Docker。先前schema4 seed片已8件冻结，最终34 passed/106.63s；这里没有新通过数字。指令板v2/30仍No-Go，两次环境恢复尝试耗尽；本计划不增加任何stage/生产授权。

## Purpose / Big Picture

固定B1候选b9可在Core1–4建立真实合成seed/checkpoint，却不能在1–4执行最新源撤销：实际retire_fact因core_embeddings缺表失败且整事务状态不变。必须保留source4至合格B2及B3的原设计，不能为了得到账本先迁源7。拟把生成最新撤销的动作移到另一独立、受审、同dump的delta副本，只有它迁到固定候选的schema7。通过真实业务得到最新ledger后，再让已有B3恢复原schema4 dump并迁7、重放；后续源库只有在B3合格后才升级并重放同一ledger，再开始回填。

本计划不修改固定b9、迁移1–7、B3/consumer/B7 schema、任何旧样本、评分或App原48目标。拟议接口/文件尚未实现，绝不可直接当可运行命令。

## Context and Orientation

源码基于`C:/Users/Administrator/Documents/Codex/zhiming-v4`与已核固定候选`private/b1-stage-replay-20261021/candidate`。固定commit为`b9a89b6f84f7bebb640de080548010859aae630c`，manifest raw SHA256为`49038f8c0dc6bb293ba688af91018cbe6339b319c388d290fd000a256e36b33c`。

复用而不修改以下真实实现：`tools/b1_bootstrap_replay_fixture.py`的编译合成常量/精确来源和版本集、`tools/b1_bootstrap_replay_seed.py:137`的schema4 seed能力、`tools/b1_restore_proof_pg.py.state_hash`的Core+四checkpoint表canonical算法、固定b9 `PostgresRepository(...initialize=False)`及显式initialize向前迁5–7、MemoryService.retire_fact、TarotService.delete与repo.mutation_request、deploy_core.export_withdrawals/apply_withdrawals、现有B3生成器与consumer和原B7 CLI。所谓delta副本是从同一受保护dump恢复的另一个本机合成库，只用于在兼容schema7执行受审撤销动作，绝不是stage或用户数据库。

重要边界：已冻seed只有受控随机local库门，不能直接拿去建立正式stage/source；固定候选子进程保持清环境、-I/-B/null pycache prefix、实际导入来源检查。现App只接受旧两message profile，仍会正确拒绝共同seed的额外fact/draw/run，未来需单独批准精确共同profile桥。最新撤销全链尚未成立，B7正式allowlist与Linux平台门不因本计划放宽。

## Progress

- [x] (2026-10-21 09:54 +08:00) 接root要求，仅设计独立delta替代，不修schema4候选；已冻seed源码/日志不再编辑。
- [x] (2026-10-21 09:54 +08:00) 只读完整核固定apply/export、B3 replay/verify_monotone与b9 backfill，确定源库回填前必须先重放同一最新ledger，并发现非空deleted_draws导出疑点。
- [ ] root复核下面独立delta实现范围与下一窄验次序；本片未批准实现，不建新库/流程。
- [x] (2026-10-21 09:59 +08:00) root另授独立测试/文档，真实随机PG确认非空deleted_draws首红PINNED_REPLAY_FAILED；直接原verify_monotone得STALE_WITHDRAWALS，目标虽无复活仍不能出proof。不改既有生产/53或55组历史，禁止拼补ledger或放松门。
- [ ] 后续获准才实现合格B2/独立clone/migrate/action/export及App共同profile/source replay桥，各自独立里程碑。

## Surprises & Discoveries

schema4源撤销真实失败是已证实阻塞，证据`docs/v4/evidence/B1/2026-10-21-schema4-bootstrap-seed.md`。不能用默认repo.initialize=True的旧latest辅助悄悄把source迁7；唯一可讨论替代是另建真正独立delta库，保留原source与dump。

09:54提出另一个只读疑点：若最新draw删除通过真实repo.mutation_request(`tarot-delete:<id>`)留下body-free receipt，export_withdrawals会产生非空deleted_draws。固定b9 apply_withdrawals会删除目标draw/补tarot_request tombstone，但未见重建该mutation receipt；目标从删除前dump恢复，原本没有receipt，因此后续export_withdrawals.deleted_draws可能为空。现B3 `replay()`随后verify_monotone(document,exported)要求原deleted_draws仍在，可能报STALE_WITHDRAWALS。旧测试direct TarotService.delete路径的deleted_draws可能为空，不能把它的绿结果当此分支已测。

09:59补充独立子任务实测：同schema4 dump后源迁7、真实mutation包Tarot删除，实际latest.deleted_draws=1，原B3真实恢复/迁7/重放后目标export.deleted_draws=0、mutation_receipt0，原成功要求1 failed/10.07s PINNED_REPLAY_FAILED。直接原verify_monotone确认为STALE_WITHDRAWALS；实体/draw/checkpoint实际已清空仍不能签proof。明确阻塞探针1 passed/10.07s仅验证故障存在，证据`docs/v4/evidence/B1/2026-10-21-nonempty-deleted-draws.md`。固定b9全链继续阻塞，不能删除ledger字段、手插receipt、调整proof或削弱校验凑通过；该新增实际阻塞交大脑裁定，delta方案本身不能解除。

b9回填_run_context要求legacy run.request.message与它指定的原话content精确相等。已冻seed补此固定必要输入并重跑34组，但还未真的回填；未来App桥须证明三项首次counter非零、repeat严格0，不能从必要条件推导完整通过。

## Decision Log

2026-10-21 09:54 +08:00 / root原要求：source保持4直到合格B2/B3；只在另独立本机随机delta克隆迁7，用真实业务生成最新账本，必须绑定同dump/初始ID/操作规范；本计划只设计，未授权创建delta库或执行其流程。

2026-10-21 09:54 +08:00 / Codex建议：不扩SeedRequest/原DSN allowlist来兼任delta。未来另设窄合同，明确source/delta/restore三身份、同一endpoint与各自独立角色。正式B3目标仍只有原生成器可消费；delta恢复到新随机库，绝不能抢用B3的预留空目标。默认入口0连接/0子进程；实现前由root逐文件授权。

2026-10-21 09:54 +08:00 / Codex建议：原schema4 dump、初始账本、seed receipt、B2对象分别绑定原字节hash；clone恢复后先用B3同算法证明完整Core/public状态等于B2 source_state，再迁7。迁后各克隆的migration applied_at/维护元数据可能不同，不要求所有实例的全状态hash相等；按各实例自己的前后hash及严格领域投影比较，不能拿一方hash填另一方回执。

## Plan of Work

### 1. 先形成合格B2，保持原source4

source须来自已受审合成seed，不接受任意额外原话/owner/run/expected_rows。重新核精确Core1–4、public四checkpoint表、实际seed receipt/state/固定candidate/整件controller与profile摘要、无活动run或lease、已知owner集合，以及原两sent/uncertain与新两pending完整四条收据。随机draw/payload更深来源检查是后续App共同profile桥的独立门，当前seed探针边界不能自动晋升生产profile。

备份阶段所有业务writer应已被实际维护门/writer fence隔离。持受信连接对完整Core/checkpoint表加允许读、阻止DML/DDL的共享表锁，在同一受控静止窗口调用固定pg_dump和固定b9真实export_withdrawals；pg_dump与export可以各自读一致快照，但必须以真实锁/fence保证窗口内全体目标表不变，且前后canonical hash相等，不能仅调用方宣称“同一snapshot”。只允许精确识别的备份/导出连接，外来client即停止；不为通过检查给角色追加系统权限。

生成新schema4-checkpoint.dump、backup-ledger.json和`b1-quiesced-backup-v1`对象，原storage纯SQL旧dump完全保留。对象字段仍按已存consumer：operation_id、logical database=zhiming_core_stage、固定target/manifest、实际source_state_sha256、dump/withdrawals原字节hash、0600与body-free exporter事实。实际本机source物理身份另在外层local-only回执记录，不能用logical字段冒充真stage。原source此后禁止继续seed或其它变更，直至B3结果；观察记录它仍1–4且hash未变。

### 2. 独立delta clone，不消费B3空目标

拟创建新的`b1_delta_<32hex>`和独立同名前缀owner/writer，绝不复用已有库、B3正式restore库或source。新合同只允许本机回环55480/55481、PG15、编译完整profile、明确local_rehearsal；未来实际Linux是同容器内部回环5432，并仍需原平台/角色/固定runtime门，本计划不新增其运行许可。controller默认只生成计划，只有新获准apply才创建自己新资源；已有目标/输出一律停止，无drop/reset/覆盖。

用同一pg_restore绝对路径/hash恢复同一B2 dump到仅为本次delta预留的真正空库。恢复后在任何业务或迁移前核精确1–4与完整canonical hash==B2 source_state，并比对seed IDs/全部集合/初始账本及双角色身份。此回执只是delta-clone观察，不能签b1-isolated-restore-proof，不能给B3传“已恢复”。随后固定b9 owner显式迁5–7并逐一核批准七checksum、原正文/修订/角色归属；绝不省略initialize=False后靠构造器隐式升级。

### 3. 在delta7生成真实latest ledger

重核升级后的编译profile、seed三operation原始fingerprint和source/fact/case/run链，所有来源/原文均仍来自同B2 seed。用固定b9真实MemoryService.retire_fact(source scope)、真实Tarot删除与真实mutation_request最小收据；新的pending两条才按受审合成投递状态变化为sent+合成receipt、sending后导出uncertain。原synthetic-sent/uncertain两条不降级，绝不实例化sender、供应商或Feishu。

一个业务事务内实现计划内变更并验证，异常全回滚；checkpoint清理由固定业务/apply正常路径实际观察，不手清表。真实export_withdrawals输出完整owner集合、原撤销超集、真实draw tombstone/deleted_draws、全部保护收据原字节文件。若非空deleted_draws在B3重放后丢失疑点成立，则此处仍可记录delta结果，但不进入B3成功路线或签总通过；停止交root审阅，原b9不改。

delta回执拟仅含dump rawhash/B2对象rawhash/seed rawhash/实际恢复4时hash、独立delta真实身份、source4前后hash、migration checksums、固定action规范摘要/稳定op ID、实际latest原字节hash、body-free计数/观察，以及models/sends=0/admissible=false。它不包含正文、牌序、DSN或成功自报字段，不接受调用者任意expected_rows。若库/输入/ledger被调换或多出原话，即使重算外层hash也必须拒绝。

### 4. B3仍恢复原dump，并验证新latest

交现有B3 CLI的dump永远是source4同一B2原件，latest是delta7真实业务导出。原B3自己观察目标空→pg_restore→核恢复4完整state==B2→迁5–7/授权→真实latest重放两遍/单调导出/权限/无复活；consumer原样验证，任何失败保留现场，不通过外层重写proof补救。

Windows仅用原B3 --local-drill的随机restore库与local schema，consumer必须拒正式admit；不能将其改schema或接原B7固定数据库allowlist。正式Linux完整链仍因环境不可用和No-Go未执行。B3若已实际重放产生变化，后续B7首次changed=false完全可能，第二次仍须false；不用此值伪造“首遍变化”，对应真实B3变化证据另绑定。

### 5. 合格B3之后才处理原source

先核B3/consumer、同dump/latest/seed rawhash及原source仍保持B2的1–4完整hash；任何漂移立即停。后续独立获准动作才将source迁5–7，固定b9显式apply同latest并核真实来源清空、draw与checkpoint无复活、sent/uncertain状态与attempts不退、secondary/legacy原话原样，再导出与latest核单调集合。不能先回填再补ledger，否则可能把已撤回run恢复成新助手正文。

source与delta/restore不需要全表hash逐字相同：迁移时间/owner revision/重放元数据可能不同。它们必须分别有真实前后摘要，并在受审领域投影上匹配同一ledger的revocations/请求tombstone/送达key、active/deleted实体/空正文、无可领取的sent/uncertain及受影响checkpoint清除。非空deleted_draws再次导出疑点同样适用于source，不应跳过。

此后App才接受新增受信共同profile：验证实际post-replay完整集合/精确操作链，无任意忽略字段/额外用户正文。只回填primary active行，保留所有原文与实体修订/secondary/非回填表，实际dry零写、首次message_metadata/search_tokens/assistant_created均非空，第二apply三计数严格整数0。原source4最新失败run在重放后应revoked且无result，不得回填其旧私有输出；旧成功run仅可来自未撤回synthetic-message。现有48目标原样保留，新增共同profile真实PG反例，尚不编码。

## Validation and Acceptance

此计划无新测试结果，对照`07_评测场景集.md` R02/F01来源撤销和旧历史不复活基础；不跑或改模型评分。下一真正窄验应先覆盖非空deleted_draws实际跨dump重放，而非再跑空ledger或复制旧53数字。若固定b9不能保持既有ledger单调契约，明确新的候选阻塞，不能据此松开门。

未来获准实现时先纯合同验证默认零连接、精确源/delta/restore身份和hash链，错误输入拒绝；随后真实随机PG证明：同dump4克隆hash一致、只有delta迁7、source保持4、真实撤销与收据变化、clone失败源不变、完整ledger重放、原目标权限/无复活、源后续迁7先重放再回填。必须覆盖错dump/旧seed/错ID、额外原话、篡改fact ref/operation、unknown/抬高version、同名目标、旧输出、外来连接、取消/半失败、checkpoint不清、送达不可领取和复用其它owner证明。

只有真实Linux同runtime/PG15与正式B3/B7/fcntl/独立回滚全部实跑才可说Linux整链通过；Windows局部、源码设计、替身phase调度或探针34绿不具有这种含义。保持所有原固定失败和精确时间记录。

## Idempotence and Recovery

不覆盖dump/旧receipt/ledger，所有新输出独占创建0700目录/0600文件并fsync，phase只追加实际BJT时间/monotonic耗时、输入输出hash与真实退出码。出现异常保留所有已创建的专用库和状态，停止下一phase，不自动迁源、重跑整链、删库或清卷；pytest仅能清自己本次随机创建的资源。B3正式目标消费一次后不能借原operation重试；需要新目标/操作由root审阅。

独立delta本身不得被误用为生产回滚库，也不作为用户数据删除授权；所有动作仅受审合成fixture。本计划不访问任何服务器，不改变维护门或角色权限。没有新授权就保持No-Go并做其它离线任务。

## Interfaces and Dependencies

以下仅建议所有权，必须root另行逐文件授权才创建/修改；固定b9/迁移/consumer/B7和其它代理文件不动。

| 建议范围 | 职责与限制 |
| --- | --- |
| 新tools/b1_bootstrap_replay_backup*.py与专属tests | 合格schema4+四checkpoint dump与真实export/hash窗口；不把旧storage dump改成合格 |
| 新tools/b1_bootstrap_replay_delta{,_contracts,_observe,_process}.py及专属tests/support | 严格local身份/同dump clone/只迁delta7/固定业务action/export；默认0连接，不复用SeedRequest放宽allowlist |
| 新外层orchestration与有限phase状态 | 绑定source/delta/B3/App/B7的原件，不生成/改写B3proof，不接模型/消息、不新增环境尝试 |
| 受审App共同profile/source replay桥 | root批准后独占相应Apphelper，保留旧48及完整结构/来源/事务门，不吞额外用户原话 |
| B3非空deleted_draws真实复现 | 由B3既有所有者独立目标负责；先首红，再由root裁定，不跨线改其工具/证明 |

无新依赖/迁移，源码≤400行、函数≤60行；Linux能力门仍需真实锁包Core3.11、固定release/venv及受保护controller loader。正式与local receipt继续不同schema、不同admissibility，任何对现接口必要调整先记录差额，不做caller-supplied passed旁路。

## Outcomes & Retrospective

此delta方案没有实现、没有创建delta库或执行其clone/migration/撤销/回填。设计保留源4、B2原件与B3唯一空目标，明确后续源先重放ledger再回填的顺序，以及不同克隆不能互抄状态hash。新增非空deleted_draws疑点已在另授的独立子任务真实复现，原成功要求首红与安全阻塞探针分别保留；此结论不是delta流程验收。下一步先由大脑/root裁定候选真实阻塞和实现文件，当前继续No-Go。

## 修订记录

- 2026-10-21 09:54 +08:00 创建：仅设计独立delta克隆、同dump/ID/操作规范绑定、源4保持与先重放再回填；新增非空deleted_draws静态疑点真实复现门，明确无实现/数据库动作。
- 2026-10-21 09:59 +08:00 追加独立子任务真实非空deleted_draws阻塞：首红1fail与明确故障探针1pass不混计，不改delta为已执行、不绕B3门，待大脑裁定。
