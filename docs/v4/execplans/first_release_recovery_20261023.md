# 核心首发包：增量升级与恢复

首发为P1/P1b/P2/P3，按指令板v8推进；记忆2.0是否随首发须按模块就绪门判断。这里的本机证据不授予服务器访问或发布权限；旧B/D均已取消。遵循`.agent/PLANS.md`，所有时间为北京时间。

## Context and Orientation

复用`tools/deploy_core.py:387`的export_withdrawals和`:405`的apply_withdrawals、仓库mutation_request的持久幂等、TarotService的真实删除与现有LangGraph checkpoint清除。旧b9包及其固定恢复工具/测试保留历史事实，不改hash或重签来掩盖已知非空往返限制。最终候选还未冻结，不填写虚构发布SHA。

## Progress

- [x] (2026-10-24 01:11 +08:00) 同call持锁新目标可选候选fresh-process只读预检9/9：完整Git候选包、实际Python3.11 venv与活动Core锁闭包、真实PG15迁移/owner/运行状态/中央空表；预载控制包、源码漂移及四种目标异常均拒绝并保留新目标，完整状态未变。未调用撤销重放，正式完成位仍false。
- [x] (2026-10-24 01:16 +08:00) 交叉审阅修正owner排序的locale边界：实际PG owner行以Python sorted归一化，与输入保持精确集合相等；仅正常预检和owner缺额两个受影响目标2/2，未复跑其余7项。
- [x] (2026-10-24 00:48 +08:00) 非空消息/事实撤销双重放实证发现并最小修复run/Outbox重复updated_at：完整Core、sequence、checkpoint及原始关联行新回归1/1，必要既有纠错/重新生成2/2；不清state_version、不跳过revoked，不改native提交后purge。
- [x] (2026-10-24 00:36 +08:00) 显式同次新库restore→upgrade阶段以真实PG15验证prefix4/7→8、原文/checkpoint保持、四张空额度表及精确ACL；10个新行为和1个默认兼容节点单链11/11通过。失败保持实际阶段，不提供既有库采用入口。
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

活动锁解析必须先按子进程真实PEP508环境筛选，再以canonical name去重并传播extras。Core锁的两个numpy版本分别用于Python<3.12与>=3.12；Windows实际platform_machine=AMD64时hf-xet的纯小写marker不激活，不能用最后一条覆盖或忽略marker误报依赖缺失。新预检在实际venv内核已安装版本、活动Requires-Dist闭包及关键模块site来源，不将锁文本本身当成已安装证明。

交叉审阅发现PG的ORDER BY id使用数据库locale，父进程Python sorted使用Unicode顺序；大小写或中文owner合法时两种顺序可能不同。预检改为对实际读到的owner ID用同一Python sorted，不放宽缺额、额外owner或重复owner契约。

新增真实PG回归先以原生MemoryService保存消息/事实和关联run，带sent/uncertain Outbox及两个epoch的非空checkpoint，实际prefix7备份→新目标升级8，再导入最新非空撤销。新摘要夹具首跑因PG15 sequence不能整行to_jsonb而失败，改为显式last_value/log_cnt/is_called摘要；随后真实业务反例仅core_runs及delivery_outbox全状态变化，关联run和两条Outbox唯一变列均为updated_at。撤销、不可复活/重发、checkpoint清空、第二export稳定、另一owner及四张空额度表/sequence均已在该失败前验证。

原因是保留的state_version仍能正确命中已撤销run，原两条UPDATE无实际差异条件，故每次重复设置updated_at。修复只增加目标字段逐项IS DISTINCT FROM/IS NOT NULL条件，NULL也被识别；含残留正文或未清租约的已revoked行仍会更新，不按status整段跳过，原retry路径的stale/request保留语义不变。现有Core文件仅此两条SQL变化，未整体格式化。

现有Core迁移器从自身模块目录扫描SQL，与外部已审candidate_source不是同一边界；新升级阶段不调用其自动扫描路径，复用validate_history并执行再次校验hash后的候选SQL，所有前向SQL与ledger记录共用一个owner事务。真实PostgresSaver.setup包含CREATE INDEX CONCURRENTLY，故在Core提交后用同一owner连接的独立autocommit阶段显式执行。Core SQL失败回到原prefix；checkpoint失败时Core8已经提交；最终ACL失败时保留已提交授权，三者均固定阶段错误码停止，不自动修正或重试。

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

经主线明确批准，本片触及共享路径mingjing_core/repositories/postgres.py的invalidate_derived两条SQL，是首发恢复完整幂等硬门的必要修复；P5集成时应保留此差异条件。没有改变历史b9或迁移、撤销范围、closure计算、原生apply全owner事务及提交后checkpoint清理，也没有用全表摘要排除时间戳来放宽断言。新回归严格比较全部字段，另核关联原始行逐列相等。

本机原生恢复是独立`tools.first_release_local_restore`入口；旧`first_release_restore`仍只有validate/可选只读ACL。新入口默认零连接/零进程，只有显式--apply-local且local_drill=true才能操作随机新目标；formal及现有对象始终硬拒。源prefix只允许1–7，实际--list预检在任何DDL前拒绝中央额度表/sequence等归档项，故不复制0008账户或usage。任何失败保留角色/库；再次调用拒绝接管，工具无DROP/覆盖/自动恢复重试。测试夹具结束后仅清理其自行创建的精确随机对象，不是工具的失败清理行为。

新增可选--upgrade-local必须与--apply-local同用；内部函数要求同次创建者连接仍持有按本次新库绑定的实际64位advisory锁，且restore及原prefix核验已经在该调用内完成。不能只传现成DSN或普通admin会话来采用目标。现权限服务负责Core最小权，现checkpoint授权函数负责公共表和只读迁移账本，最后两角色只读精确ACL；不增加DELETE来满足旧B1证明。四张0008表实际查询全空，遇非空保留原行并拒绝，不清表、不provision，不形成中央身份迁移或重绑定证明。

凭据边界同时覆盖子进程和SQL：PGPASSWORD仅为显式内存子环境，角色DDL仅含libpq客户端生成的SCRAM verifier，不保留服务端明文加密路径。原CLI负例的参数清单等价压缩为字段映射，保护的PGOPTIONS先拒绝、秘密不回显断言不变，用于保持新测试文件≤400行。

恢复标记仅含owner、draw_id和固定版本的指纹，以及deleted/deleted_ids/kind回执；不保存牌面/问题/正文，不造原HTTP幂等键。复用已有core_mutation_requests，无新表或迁移。0009保留P5，不改变历史1–8。旧b9继续保留独立反例，当前修复只随最终候选发布；首发开门前可以回退，开门后只按另审止损与前向修复方案。

新增`core-only-1-8-v1`只接受外部审核的不可变candidate/manifest/迁移1–8和Core、Charts、K3三锁pin，不把调用者布尔值当作可信证明。P5就绪后若0009纳入候选，必须新增明确审核的profile，不能静默跳过此门。新恢复库仅允许`zhiming_core_first_restore`，本地仅本次operation随机库；原live/stage及旧B1目标均拒绝。新入口没有apply、pg_restore、unit或开门动作，不解除旧B1 Native硬门。

目录路径固定只作用于本次两个核验事务，不永久改变运行角色search_path，也不放宽关系、routine或0008最小权限门。

## Concrete Steps / Plan of Work

2026-10-24下一基础片只做显式local replay preflight，必须同call apply+upgrade且原新目标creator锁仍在；不调用apply_withdrawals，不宣称双重放已接。新增不可变输入绑定candidate/manifest/dump/latest ledger/实际Python及受审控制worker。纯stdlib bootstrap在任何业务导入前固定候选tools namespace与mingjing_core包，拒绝预载控制树业务；前后校验全部候选模块真实路径与manifest字节，控制worker自身不进入tools命名空间。

子进程核实际Python3.11、venv与活动Core锁闭包，须以真实PEP508 marker环境筛选后canonical去重并传播extras，不能覆盖条件重复pin。既有.venv-k3实际Python3.11/AMD64的68活动pin及113活动依赖边已只读盘点满足，可用于本机正例；此盘点不是预检/PG测试，更不是wheel/.pth/Linux供应链认证。目标只读核迁移1–8、完整owner集合、无active run/lease、四张中央空表；任何异常保留新目标，正式完成位仍false。两新tool与一份完整候选/真实Python/PG目标测试，加既有入口最小接线；默认零连接行为不变，不提供现成库adoption。真实重放worker与备份8/中央身份保全继续下一片。

主线自有CI接线将原Core+test锁安装移入RUNNER_TEMP下的真实专用venv（--copies、--require-hashes），导出其bin与FIRST_RELEASE_CANDIDATE_TEST_PYTHON，Charts环境照旧，没有另装第二套Core闭包。这只是待实际CI验证的运行时路径调整；YAML/Bash解析不构成Linux、运行时供应链或正式发布门通过。

2026-10-24重放幂等实证后的最小共享路径修复：仅调整mingjing_core/repositories/postgres.py中invalidate_derived的core_runs及delivery_outbox两条UPDATE，目标字段含NULL以IS DISTINCT FROM比较，仅实际需要清理/改变时更新updated_at。不跳过已revoked记录，不清空state_version，不改变closure、retry/stale语义或native apply事务提交后checkpoint purge边界。原因是实际非空消息/事实撤销双重放已证明第二遍仅重复改动run和Outbox的updated_at；共享repo路径须由主线在P5集成时说明此边界。先复跑唯一新PG回归，再仅两个必要既有纠错/重新生成节点，不宽测、不改旧b9。

2026-10-24下一小片增加显式--upgrade-local，必须同时--apply-local，仅在同一次调用已创建新目标、仍持有原操作锁且真实restore/原prefix核验后执行。默认保留原prefix恢复；不新增采用既有库的命令。只执行同一外部审核候选的迁移SQL，复用validate_history校验历史，保持全部前向迁移和版本记录在一个owner事务内。PostgresRepository.initialize固定扫描其包目录，不能冒充外部候选SQL执行器，故本片只复用其历史契约而不调用其自动迁移路径。

升级后复用真实PostgresSaver.setup的显式checkpoint迁移（包含CONCURRENTLY索引，不能嵌入Core迁移事务），随后复用权限服务和checkpoint授权，再以两角色只读精确ACL核验。0008仅建空的四张表和sequence，不provision/复制/清理账户，不把空表当作中央身份保全或重绑定证明。任何失败保留新库/角色及已提交阶段，不修权限重试、不删除或回退；最新撤销/送达收据双重放另片，formal/native/Linux证明始终false。本片最多两个新tool/一个新PG测试文件，加现有入口小接线；定向验证prefix4/7→8、原文/checkpoint保持、精确权限及阶段失败，不全量。

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

`private/safe-narrow-645cf96374aa41ca876ec8c6c25e00e0/metadata.json`记录本片唯一链9/9（170.50秒，2026-10-24 01:08–01:11 +08:00）。夹具仅一次打包当前真实Git候选完整源码，各目标独立受pin副本；actual Python为本机既有`.venv-k3`的Python3.11，真实Windows PG15与实际dump/restore。正常只读预检、两个控制树namespace预载、升级后源码漂移、缺同call gate及owner/active/lease/central四个目标拒绝全部通过；Core全部字段、checkpoint及sequence独立摘要均不变。安全runner清凭据/关追踪、测试时区Tokyo，模型/外发/服务器0；没有重跑旧幂等业务、全量或Linux证明。

`private/safe-narrow-d39d12338be94844967a4df709ac6387/metadata.json`为owner排序修正后的仅2目标复测2/2（44.33秒，01:15–01:16 +08:00）；保留原9目标链记录，没有重复其余7项或扩大为全量。

本次复现与修复证据依次为`private/safe-narrow-c866375ca5154a3f9223fca318ddabfd/metadata.json`（1个新摘要夹具失败）、`private/safe-narrow-4c7135726460421aa6181feafda1b03a/metadata.json`（真实第二遍updated_at回归失败，2.66秒）、`private/safe-narrow-f90c8f6a23ea415689ef1374e6ee009b/metadata.json`（同一目标修复后1/1，2.80秒）、`private/safe-narrow-83409a83e1534dc3a70ad77181938112/metadata.json`（仅两个必要既有纠错/干净epoch节点2/2，1.94秒）。新目标没有给native apply包外层事务；实际Windows PG15/真实备份恢复、有限测试环境、Tokyo测试时区，真实模型/外发/服务器0。没有全量、候选child或Linux证明。

`private/safe-narrow-b8fce224277a4a02bf3e302eb5468163/metadata.json`为本片唯一窄链11/11（16.27秒）：10个新行为加1个受影响默认prefix4兼容节点。两个正常节点实际pg_dump/restore后由4或7升级至8，三张checkpoint数据表及其ledger和原文不变；其余覆盖无apply/无原锁、候选SQL或历史漂移、Core事务与checkpoint故障、额外额度DELETE、非空额度表停止保留。清凭据/关闭追踪，测试时区Tokyo；真实Windows PG15，模型/外部发送/服务器0。无额外全量或旧19项复跑。

本片首链`private/safe-narrow-1fd4430d834d44dda2f2ca74a5547ec2/metadata.json`为13通过/3失败（13.68秒）；私有分类诊断`private/safe-narrow-83d2cbf6f31b484c85c0c33bfe216e6b/metadata.json`为单节点仍失败，确认schema CREATE权限断点。最小新public初始化后，仅3个失败目标复测`private/safe-narrow-d648e09347d44f9f8fd43ad8f0523ae5/metadata.json`为3/3（4.50秒）。必要的public占用/归属漂移负例2项及受影响真实restore失败保留节点1项，在`private/safe-narrow-c6438c08376542d2bdbc361d150a5bdd/metadata.json`为3/3（4.66秒）；合计18个不同节点有通过证据，非一次完整全绿。清凭据/关闭追踪、安全runner测试时区Tokyo，真实模型/消息/服务器均0；测试用实际Windows PG15与实际dump/restore，不作Linux证明。

`private/safe-narrow-dcae469240fa4641b6902ea918d2c263/metadata.json`记录客户端SCRAM/实际DDL日志边界新节点与跨平台发现后的必要prefix4节点2/2（3.58秒）。新增行为合计19个不同节点有通过记录，未声称一次19项全链绿；有限环境、实际Windows PG15及真实dump/restore，不改既有认证/角色权限。

私有metadata位于`private/safe-narrow-e24b119d52034f6b964941d0ff2223f3/`（首链）、`private/safe-narrow-d63fc6d3c64b491287fe0c7c2be93f2e/`（真实恢复复测1通过）、`private/safe-narrow-633554d7fb314b37b3d8efe25f0c1a0a/`（原旧节点1通过）。另一次临时wrapper定位错误未执行业务，记录保留在`private/safe-narrow-6d10d0df18d544708bb4fb6ace80978e/`，wrapper已完全移除。并非一次全链全绿；无模型、飞书或服务器调用。

新发布准备树`private/safe-narrow-f984c1a674c0418287303db71219f5d1/metadata.json`记录15通过/30夹具失败；`private/safe-narrow-3598b8b0a07a4bb08034feeaee499b86/metadata.json`记录短路径复测29通过/1链接夹具失败；`private/safe-narrow-eeb111b1d7074ae7b39143bcf6abf632/metadata.json`记录NTFS junction节点1通过。安全runner测试时区Asia/Tokyo，记录北京时间，真实模型/消息/服务器均0；只使用本测试新建并清理的随机PG15库和两角色，未改变既有角色权限。

`private/safe-narrow-b5e7270f799c4c57855f263c2dc08b73/metadata.json`记录审阅修正后6/6（4.08秒）：两个schema的可更新view反例、SECURITY DEFINER函数与过程反例、实际PGOPTIONS在connect前被拒，以及正常checkpoint/0008最小ACL保留通过。反例只新建本测试对象和授权，不执行破坏性业务DML，结束清理测试库。

`private/safe-narrow-8bb25014e4394185a06bda249989bb50/metadata.json`记录目录伪装负例及双角色默认路径正例2/2（2.11秒）；只运行这两个新增目标，真实模型/消息/服务器均0。

## Interfaces and Dependencies

新增两个tools：first_release_candidate_process绑定不可变候选/manifest/dump/latest ledger/实际Python/受审worker，first_release_replay_worker为纯stdlib bootstrap之后的独立候选只读核验器。现有local_restore显式`--apply-local --upgrade-local --replay-preflight-local`并提供`--preflight-pin --preflight-ledger --candidate-python`，才在原creator锁内新建/恢复/升级后的目标加1个owner只读连接，正常总连接8；默认原始/升级路径仍4/7。子进程不继承用户PG或模型环境，不输出原stderr/DSN。真实候选tools namespace与mingjing_core导入前后核路径及manifest字节；这里只确认候选导入与已安装活动依赖元数据，不认证wheel、.pth、审核人或解释器完整供应链。

新增三个tool：first_release_local_inputs（同源审核dump/program/prefix绑定、严格本机输入）、first_release_local_pg（目标缺席检查、创建/持锁/新public初始化/原prefix及owner后验）、first_release_local_restore（默认校验及显式本机原生restore）。`FIRST_RELEASE_ADMIN_DSN`只允许同一实际loopback 55480/55481的postgres或core_test_main控制库；owner/writer继续使用原显式变量。实际进程与显式环境PG*均拒绝，子进程不继承用户PG配置；仅允许显式内存密码注入子PGPASSWORD，固定空passfile，不进argv/输出/文件。外部审核pin及实际可执行/DLL运行环境仍是受信前提，不声称认证审核人或完整解释器供应链。

可选本机升级新增一个内部tool first_release_local_upgrade；只从同次新库上下文调用_upgrade_new_target(inputs,dsns,creator)。正常路径沿用原4连接，增加1个owner升级连接及2个只读ACL连接，共7；PostgresSaver在该owner连接复用，不另开pool。成功回执区分original_prefix与upgraded_migrations，并保持central_binding_verified、central_provisioned、runtime_verified、native_restore_completed、linux_attestation、publication为false；runtime_acl_verified仅表示当前两角色精确权限已核，不代表运行时或发布已验证。

export保持core3-withdrawals-v2格式，deleted_draws规范化为唯一(owner,draw_id)排序列表。apply新增只读计数draw_tombstones_added；所有旧计数及撤销/收据保护保留。新增helper不引依赖，真实PG15测试用已有本机客户端。

## Outcomes & Retrospective

已完成真实候选fresh-process、Python3.11 venv活动依赖及新目标只读预检基础。外部审核pin仍是受信输入，测试自产pin不构成独立审核；latest ledger仅绑定hash和owner全集，尚不执行撤销/收据双重放。回执明确read_only=true、mutations=0，latest_withdrawals_replayed、runtime_verified、native_restore_completed、linux_attestation、publication全部false。源prefix8/中央账本身份保全、真实候选重放、Linux和正式首发仍No-Go，不能据本片8个连接或9项通过宣称生产恢复就绪。

当前控制树原生业务的非空隐私/回执重放已通过完整数据库及checkpoint严格幂等定向回归；仍未实现外部审核候选Python导入隔离的同call双重放worker，不能将这份本机回归视为已pin候选应用、Linux正式恢复或中央身份保全证明。正式首发仍No-Go。

本机原始prefix恢复及可选同次新目标前向到8、checkpoint显式setup、最小授权和精确ACL均已有定向证据，仍不代表首发恢复全链：没有回填、最新撤销/收据重放、中央账本保全/重绑定、正式Linux/容器端口映射、stage/生产、unit或开门。现有formal硬门不变，Linux容器NAT实际端口与严格身份不匹配时继续拒绝，不能放宽为Linux通过。开门前回退和开门后止损规则不变。

新凭据边界与正常恢复均有定向证据；跨平台CI实际运行和SCRAM认证端点验证由主线CI结果判定，当前不声称已绿。角色verifier也不进入回执，服务端审计日志可能记录verifier，须继续按敏感运行日志保护。

已修最终代码的非空撤销往返，并完成相关Windows PG15实际备份恢复验证。未完成Docker/Linux整链、生产原生恢复入口或可执行的新发布单，首发保持No-Go；不沿用b9的空样本或旧授权放行。

本片补齐了最终候选只校验契约与精确ACL基础，静态检查通过，45个不同定向行为已有通过证据。尚无最终冻结candidate、实际新入口恢复、正式Linux运行时证明、中央账本改址核验或unit切换；JSON输入及本地Windows检查不具有部署授权。

审阅追加5个不同安全反例及1个受影响合法节点通过，合计50个不同定向行为有通过记录；没有把外部审核pin、Windows证据或关系/函数元数据校验升级为可信发布证明。

目录路径补正又有两个不同定向行为通过，累计52个不同通过行为；仍为validate-only，无apply或原生恢复执行。

## 修订记录

- 2026-10-24 01:11 +08:00：新增显式同call候选fresh-process只读预检与9/9真实窄验；记录活动marker、候选namespace/来源、依赖元数据及CI路径边界，未接撤销重放或正式恢复。
- 2026-10-24 00:48 +08:00：记录非空双重放真实失败及共享repo两SQL最小幂等修复，保留全部字段断言和1+2窄验，说明候选worker与正式恢复仍未完成。
- 2026-10-24 00:36 +08:00：新增同次本机新库显式升级阶段和11/11窄验；保留默认原prefix路径、阶段失败现场与中央身份/正式发布硬门。
- 2026-10-24 00:26 +08:00：修复DDL日志中的原口令路径，记录2/2窄验与实际认证证据边界；明确Linux PG15客户端及独立测试库要求。
- 2026-10-24 00:20 +08:00：新增本机local-only原始prefix真实恢复基础与18项定向证据；记录NOINHERIT/public初始化失败及最小修正、失败保留和正式恢复仍阻塞。

- 2026-10-23 23:10 +08:00：记录最终候选删除血缘修复、实际PG定向证据及仍未解除的发布门。
- 2026-10-23 23:38 +08:00：记录独立发布准备树的只校验契约、0008精确ACL、45个定向行为与两次Windows夹具修正；明确未执行任何原生恢复或Linux发布。
- 2026-10-23 23:46 +08:00：修复审阅发现的视图/SECURITY DEFINER与PGOPTIONS绕过，记录6/6定向结果和外部审核pin信任边界。
- 2026-10-23 23:53 +08:00：固定并核验两个ACL事务的pg_catalog路径，记录真实目录伪装反例及双角色自定义路径正例2/2。
