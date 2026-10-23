# 核心首发包：增量升级与恢复

首发为P1/P1b/P2/P3，按指令板v8推进；记忆2.0是否随首发须按模块就绪门判断。这里的本机证据不授予服务器访问或发布权限；旧B/D均已取消。遵循`.agent/PLANS.md`，所有时间为北京时间。

## Context and Orientation

复用`tools/deploy_core.py:387`的export_withdrawals和`:405`的apply_withdrawals、仓库mutation_request的持久幂等、TarotService的真实删除与现有LangGraph checkpoint清除。旧b9包及其固定恢复工具/测试保留历史事实，不改hash或重签来掩盖已知非空往返限制。最终候选还未冻结，不填写虚构发布SHA。

## Progress

- [x] (2026-10-24 00:20 +08:00) 新增显式local-only原生恢复基础：真实PG15 pg_dump/pg_restore保持prefix4/7，新库/两角色、不可接管及失败保留边界共18个不同定向行为有通过证据；无前向迁移、重放或正式发布放行。
- [x] (2026-10-24 00:26 +08:00) 两角色密码在客户端生成SCRAM verifier后才进入DDL；实际会话DDL日志边界及受影响prefix4恢复2/2通过。补齐PG15客户端/独立测试库的跨平台发现，未重复18项绿节点。

- [x] (2026-10-23 23:10 +08:00) 最终代码已补owner+draw稳定、无正文的恢复标记；导出去重排序，同一全体owner事务内写入，重复不再增加标记。
- [x] (2026-10-23 23:10 +08:00) 7个新PG行为及3个既有兼容行为均有通过证据（8+1+1定向复测）。真实pg_dump→pg_restore→重放→再导出满足原单调校验，第二次所有表状态不变；跨owner及篡改整批回滚。
- [x] (2026-10-23 23:38 +08:00) 隔离发布准备树新增只校验的首发契约与实际PG15精确ACL核验；45个行为以15+29+1定向记录通过。默认零连接，无apply命令，不构成恢复或发布证明。
- [x] (2026-10-23 23:46 +08:00) 审阅补正视图/SECURITY DEFINER与实际进程PGOPTIONS绕过；新增5个反例及1个受影响合法ACL节点定向6/6通过，未重复旧45项。
- [x] (2026-10-23 23:53 +08:00) 两个ACL事务在identity前固定pg_catalog并核实际路径；目录伪装反例与双角色自定义路径正例2/2通过。
- [ ] 冻结最终首发候选，核实增量升级适用迁移、owner/writer、回填与实际解释器。
- [ ] 本机Docker Linux PG15全链、最终候选原生新库恢复、维护门与writer栅栏演练。
- [x] (2026-10-24 00:03 +08:00) 两份首发stage/prod草案已提交ef3d2e2，明确No-Go、现有校验命令与缺失入口；本片只补本机原始prefix恢复命令。
- [ ] 完成可执行的增量/恢复/停写切换与Linux证据，再复核两份首发操作单；stage/生产等待用户另行授权。

## Surprises & Discoveries

审阅指出服务端password_encryption不能防止log_statement=ddl/all记录CREATE ROLE中的原口令。实际安装psycopg3.3.6的PGconn.encrypt_password(passwd,user,algorithm=None)返回bytes；现显式使用客户端scram-sha-256，只把verifier交给SQL。新反例在发送前核DDL没有原口令，再将实际admin会话log_statement设为ddl；pg_authid双key与随机密码相符，两个角色实际密码连接成功，回执不含原密码或verifier。未改本机pg_hba，不把现有认证下的成功连接宣称为已实证SCRAM协商。

既有CI隔离库实际5432/core_test，不符合本片实际55480/55481的身份门；不能降级skip或放宽工具。测试优先显式FIRST_RELEASE_LOCAL_TEST_ADMIN_DSN，只有原CORE_TEST_DSN本身符合严格控制库/端口时才兼容使用；客户端优先FIRST_RELEASE_TEST_PG_BIN，Windows已核路径、Linux PATH发现均须实际--version=PG15，缺失即失败。主线另持CI修改，建立独立实际55480/core_test_main服务并选择PG15客户端；本机定向通过不能代替CI/Linux通过。

本机恢复首链16项中13通过、3失败：新owner的NOINHERIT不继承PG15默认public目录的pg_database_owner权限，实际pg_restore创建checkpoint表被拒。私有诊断单节点只输出已知错误类别布尔值，没有SQL/正文/凭据；未修改角色继承、pg_hba或旧库。经主线确认，仅在本工具刚创建且身份匹配的新库、public为空且原owner精确为pg_database_owner时，由新增一次admin连接把public归属设为本次新owner；后验同时核schema owner。实际成功路径4个连接（admin控制库、admin新库初始化、pg_restore新owner、owner只读后验）。writer没有CREATE，NOINHERIT保留。

2026-10-23 23:53 +08:00：本机Docker PG15仍已启动，但Linux Python依赖镜像准备失败。仅尝试拉取官方`python:3.11-slim-bookworm`一次，Docker Hub解析到本机网络的198.18地址后连接超时；未更改Docker代理、ACL、WSL或任何既有服务，未重试/换源。记录`private/linux-runtime-preparation-41f56c4646f14f88bbd5e60e552a65ba/metadata.json`及同目录日志位于主线集成工作树。本片未因此执行迁移、restore或应用服务，Linux应用轨继续阻塞；不将已就绪的Linux PG存储升级成完整演练证明。

旧恢复只删除draw，没有留下下一次export可见的原生删除旁账，故原verify_monotone会拒绝STALE_WITHDRAWALS。最终代码新增`tools/deploy_core_withdrawals.py`，保留原export格式及校验，不删除旧断言。已有draw和既有异owner tombstone均阻止换owner重绑定；所有标记冲突导致全体事务回滚。外部checkpoint清除仍是既有提交后边界，须纳入后续Linux全链失败演练。

首链8通过/2失败/1清理错误：新测试的pg_restore缺少显式dbname模式参数；既有兼容节点先缺PG15 PATH，后因安全runner未传USERPROFILE而在Path.home失败。只修新夹具；私有runner为原旧节点补PG15 PATH与指向新临时目录的USERPROFILE，其余凭据清理不变，不修改旧测试、用户环境或公共runner，不提交重复wrapper。

Docker Linux Engine本轮实际可读（29.5.2），此前环境失败记录不能当作当前故障；PG15镜像下载尚在进行，不代表Linux恢复或应用演练成功。

旧B1权限证明要求普通Core表具备完整DML，但0008额度表刻意只授予其必要权限；最终核验不能补DELETE来迁就旧证明。新检查逐表、列、序列核验有效权限及grant option，检测PUBLIC来源和角色继承，两个迁移账本只读、checkpoint三表DML、禁止DDL/TEMP/owner权限。真实PG15的正确最小授权已通过，越权及缺权均拒绝。

新链首跑15个PG行为通过，30个合成源码夹具因Windows MAX_PATH失败；缩短新测试临时目录后29通过，剩余symlink夹具缺少Windows创建符号链接权限。未提升权限，改用真实NTFS directory junction覆盖同一reparse-point拒绝契约，单节点通过；Linux仍使用实际symlink。记录保留全部失败，未重复PG绿项。

审阅发现只核验base table不能阻止owner视图透出权限，SECURITY DEFINER入口也能绕过底层DML限制。当前core-only profile改为精确24张Core表、4张checkpoint表及0008单个sequence，拒绝额外public/Core视图、外表、关系或rewrite rule；唯一合法routine为0007的clear_retired_embeddings()，核验固定函数体SHA、invoker、trigger返回类型、语言及search_path等签名，拒绝可执行的用户SECURITY DEFINER函数/过程。实际进程PG*与显式environment均检查，传入clean mapping不能掩盖libpq继承PGOPTIONS。

后续只读复核发现角色默认search_path可把pg_class指向owner视图，过滤真实后门目录行。两个只读事务现于任何identity查询前SET LOCAL search_path=pg_catalog，并核对实际配置及实际schema数组。真实反例证实伪目录隐藏public.quota_bypass，view的空谓词DELETE/UPDATE可成功而base DELETE被拒；固定目录后的检查仍发现并拒绝后门。正常owner/writer自定义默认路径不影响合法核验，测试只改本测试角色默认设置并恢复，没有改业务行。

## Decision Log

本机原生恢复是独立`tools.first_release_local_restore`入口；旧`first_release_restore`仍只有validate/可选只读ACL。新入口默认零连接/零进程，只有显式--apply-local且local_drill=true才能操作随机新目标；formal及现有对象始终硬拒。源prefix只允许1–7，实际--list预检在任何DDL前拒绝中央额度表/sequence等归档项，故不复制0008账户或usage。任何失败保留角色/库；再次调用拒绝接管，工具无DROP/覆盖/自动恢复重试。测试夹具结束后仅清理其自行创建的精确随机对象，不是工具的失败清理行为。

凭据边界同时覆盖子进程和SQL：PGPASSWORD仅为显式内存子环境，角色DDL仅含libpq客户端生成的SCRAM verifier，不保留服务端明文加密路径。原CLI负例的参数清单等价压缩为字段映射，保护的PGOPTIONS先拒绝、秘密不回显断言不变，用于保持新测试文件≤400行。

恢复标记仅含owner、draw_id和固定版本的指纹，以及deleted/deleted_ids/kind回执；不保存牌面/问题/正文，不造原HTTP幂等键。复用已有core_mutation_requests，无新表或迁移。0009保留P5，不改变历史1–8。旧b9继续保留独立反例，当前修复只随最终候选发布；首发开门前可以回退，开门后只按另审止损与前向修复方案。

新增`core-only-1-8-v1`只接受外部审核的不可变candidate/manifest/迁移1–8和Core、Charts、K3三锁pin，不把调用者布尔值当作可信证明。P5就绪后若0009纳入候选，必须新增明确审核的profile，不能静默跳过此门。新恢复库仅允许`zhiming_core_first_restore`，本地仅本次operation随机库；原live/stage及旧B1目标均拒绝。新入口没有apply、pg_restore、unit或开门动作，不解除旧B1 Native硬门。

目录路径固定只作用于本次两个核验事务，不永久改变运行角色search_path，也不放宽关系、routine或0008最小权限门。

## Concrete Steps / Plan of Work

2026-10-24下一片限定为本机新库原生恢复基础：仅显式local_drill=true、严格operation随机库/角色、loopback 55480/55481；同一外部审核输入绑定候选/manifest、custom dump和PG15 pg_restore原始hash及源迁移前缀。默认零连接校验，显式本机apply才创建本次非特权角色与全新库并由新owner恢复；发现任一既有库/角色即拒绝，失败保留新对象且不自动删除或重跑。最多新增三个tool与一个定向PG测试文件，不改旧B1或正式目标边界。

实际pg_restore限定no-owner/no-acl/exit-on-error/single-transaction/no-password，无shell；仅通过有限子环境传递显式内存凭据，不把凭据放argv、输出或文件，不继承PG隐式环境。首片源prefix只允许连续1–7，实测4或7；审核pin声明8或archive目录出现中央额度关系均在创建任何库/角色前拒绝，避免在未保全时复制额度身份。恢复后只读核原prefix与对象owner，不迁至8、不重放撤销/收据、不重绑定或provision中央账户、不接正式stage/生产、unit或开门。真实本机PG与pg_dump/restore测试完成前本片未验证；Windows证据不解除Linux/生产门。角色生命周期或认证不能满足此边界时保留现场、报告具体阻塞，不修改既有认证/角色权限。

相关验证使用清凭据的私有安全runner和本机隔离PG15。代码审阅、定向验证、提交推送之后才进入Linux演练；最终候选增量入口不得复用freeze/install/publish去覆盖既有Core库。Native入口须恢复到全新明确allowlist数据库，验证备份、最新撤销/发送收据、同源解释器、角色权限与重复无变化；旧Native入口仍主动拒绝缺失的生产恢复证明，不能用JSON布尔值解除。

本片`python -m tools.first_release_restore --pin <绝对审核pin路径> --contract <绝对契约路径>`只校验输入，默认不连接PG；显式`--check-acl`才使用`FIRST_RELEASE_OWNER_DSN`及`FIRST_RELEASE_WRITER_DSN`各开一次只读事务。不继承PG隐式环境、不接受远端host、services、options、改址、默认passfile或不匹配角色。外部运行目录venv/artifacts仍须后片独立真实性核验，本片永不声明runtime_verified或linux_attestation。

本片将外部审核pin视为可信输入，只验证字节与其一致；不认证审核人、pin文件的保护权限、真实Git tree归属或审核新鲜度。这些与最终运行时审计、维护门、writer栅栏均是未来apply的前置门，不能从当前validation JSON推导批准或原生恢复已完成。

## Validation and Acceptance

场景F01–F04与X03的“不复活、不重复”约束同样适用于恢复。非空备份恢复后实际删除目标、其他owner牌与正文不变、重导出保留所有删除、第二次全表摘要及旁账行均不变；坏指纹/收据/owner须在整体事务内失败。Windows PG证据只解除该代码分支验证项；Linux、正式候选、Web/飞书/报告三个unit、CHART_PYTHON、Hermes wrapper和checkpoint权限仍需各自真实离线演练。

## Idempotence and Recovery

标记key由owner+draw+版本确定，重放返回draw_tombstones_added=0。输入冲突时整个SQL事务回滚；不删除用户数据库或Docker卷，不自动清理失败演练。部署任何异常保持维护门/栅栏并记录，服务器操作须等新授权。

## Artifacts and Notes

本片首链`private/safe-narrow-1fd4430d834d44dda2f2ca74a5547ec2/metadata.json`为13通过/3失败（13.68秒）；私有分类诊断`private/safe-narrow-83d2cbf6f31b484c85c0c33bfe216e6b/metadata.json`为单节点仍失败，确认schema CREATE权限断点。最小新public初始化后，仅3个失败目标复测`private/safe-narrow-d648e09347d44f9f8fd43ad8f0523ae5/metadata.json`为3/3（4.50秒）。必要的public占用/归属漂移负例2项及受影响真实restore失败保留节点1项，在`private/safe-narrow-c6438c08376542d2bdbc361d150a5bdd/metadata.json`为3/3（4.66秒）；合计18个不同节点有通过证据，非一次完整全绿。清凭据/关闭追踪、安全runner测试时区Tokyo，真实模型/消息/服务器均0；测试用实际Windows PG15与实际dump/restore，不作Linux证明。

`private/safe-narrow-dcae469240fa4641b6902ea918d2c263/metadata.json`记录客户端SCRAM/实际DDL日志边界新节点与跨平台发现后的必要prefix4节点2/2（3.58秒）。新增行为合计19个不同节点有通过记录，未声称一次19项全链绿；有限环境、实际Windows PG15及真实dump/restore，不改既有认证/角色权限。

私有metadata位于`private/safe-narrow-e24b119d52034f6b964941d0ff2223f3/`（首链）、`private/safe-narrow-d63fc6d3c64b491287fe0c7c2be93f2e/`（真实恢复复测1通过）、`private/safe-narrow-633554d7fb314b37b3d8efe25f0c1a0a/`（原旧节点1通过）。另一次临时wrapper定位错误未执行业务，记录保留在`private/safe-narrow-6d10d0df18d544708bb4fb6ace80978e/`，wrapper已完全移除。并非一次全链全绿；无模型、飞书或服务器调用。

新发布准备树`private/safe-narrow-f984c1a674c0418287303db71219f5d1/metadata.json`记录15通过/30夹具失败；`private/safe-narrow-3598b8b0a07a4bb08034feeaee499b86/metadata.json`记录短路径复测29通过/1链接夹具失败；`private/safe-narrow-eeb111b1d7074ae7b39143bcf6abf632/metadata.json`记录NTFS junction节点1通过。安全runner测试时区Asia/Tokyo，记录北京时间，真实模型/消息/服务器均0；只使用本测试新建并清理的随机PG15库和两角色，未改变既有角色权限。

`private/safe-narrow-b5e7270f799c4c57855f263c2dc08b73/metadata.json`记录审阅修正后6/6（4.08秒）：两个schema的可更新view反例、SECURITY DEFINER函数与过程反例、实际PGOPTIONS在connect前被拒，以及正常checkpoint/0008最小ACL保留通过。反例只新建本测试对象和授权，不执行破坏性业务DML，结束清理测试库。

`private/safe-narrow-8bb25014e4394185a06bda249989bb50/metadata.json`记录目录伪装负例及双角色默认路径正例2/2（2.11秒）；只运行这两个新增目标，真实模型/消息/服务器均0。

## Interfaces and Dependencies

新增三个tool：first_release_local_inputs（同源审核dump/program/prefix绑定、严格本机输入）、first_release_local_pg（目标缺席检查、创建/持锁/新public初始化/原prefix及owner后验）、first_release_local_restore（默认校验及显式本机原生restore）。`FIRST_RELEASE_ADMIN_DSN`只允许同一实际loopback 55480/55481的postgres或core_test_main控制库；owner/writer继续使用原显式变量。实际进程与显式环境PG*均拒绝，子进程不继承用户PG配置；仅允许显式内存密码注入子PGPASSWORD，固定空passfile，不进argv/输出/文件。外部审核pin及实际可执行/DLL运行环境仍是受信前提，不声称认证审核人或完整解释器供应链。

export保持core3-withdrawals-v2格式，deleted_draws规范化为唯一(owner,draw_id)排序列表。apply新增只读计数draw_tombstones_added；所有旧计数及撤销/收据保护保留。新增helper不引依赖，真实PG15测试用已有本机客户端。

## Outcomes & Retrospective

本片已实现并定向验证本机原始prefix恢复，不代表首发恢复全链：没有前向到8、回填、最新撤销/收据重放、中央账本保全/重绑定、runtime ACL重授、正式Linux/容器端口映射、stage/生产、unit或开门。现有formal硬门不变，Linux容器NAT实际端口与严格身份不匹配时继续拒绝，不能放宽为Linux通过。开门前回退和开门后止损规则不变。

新凭据边界与正常恢复均有定向证据；跨平台CI实际运行和SCRAM认证端点验证由主线CI结果判定，当前不声称已绿。角色verifier也不进入回执，服务端审计日志可能记录verifier，须继续按敏感运行日志保护。

已修最终代码的非空撤销往返，并完成相关Windows PG15实际备份恢复验证。未完成Docker/Linux整链、生产原生恢复入口或可执行的新发布单，首发保持No-Go；不沿用b9的空样本或旧授权放行。

本片补齐了最终候选只校验契约与精确ACL基础，静态检查通过，45个不同定向行为已有通过证据。尚无最终冻结candidate、实际新入口恢复、正式Linux运行时证明、中央账本改址核验或unit切换；JSON输入及本地Windows检查不具有部署授权。

审阅追加5个不同安全反例及1个受影响合法节点通过，合计50个不同定向行为有通过记录；没有把外部审核pin、Windows证据或关系/函数元数据校验升级为可信发布证明。

目录路径补正又有两个不同定向行为通过，累计52个不同通过行为；仍为validate-only，无apply或原生恢复执行。

## 修订记录

- 2026-10-24 00:26 +08:00：修复DDL日志中的原口令路径，记录2/2窄验与实际认证证据边界；明确Linux PG15客户端及独立测试库要求。
- 2026-10-24 00:20 +08:00：新增本机local-only原始prefix真实恢复基础与18项定向证据；记录NOINHERIT/public初始化失败及最小修正、失败保留和正式恢复仍阻塞。

- 2026-10-23 23:10 +08:00：记录最终候选删除血缘修复、实际PG定向证据及仍未解除的发布门。
- 2026-10-23 23:38 +08:00：记录独立发布准备树的只校验契约、0008精确ACL、45个定向行为与两次Windows夹具修正；明确未执行任何原生恢复或Linux发布。
- 2026-10-23 23:46 +08:00：修复审阅发现的视图/SECURITY DEFINER与PGOPTIONS绕过，记录6/6定向结果和外部审核pin信任边界。
- 2026-10-23 23:53 +08:00：固定并核验两个ACL事务的pg_catalog路径，记录真实目录伪装反例及双角色自定义路径正例2/2。
