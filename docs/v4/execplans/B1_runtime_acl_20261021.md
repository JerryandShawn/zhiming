# B1：拒绝运行角色的非 CRUD 表权限

本 ExecPlan 遵循 `.agent/PLANS.md`。2026-10-21 09:42 +08:00 创建；记录使用北京时间。工作树 `C:/Users/Administrator/Documents/Codex/zhiming-v4`，本任务仅拥有两处只读权限聚合、新窄测试、本计划与独立证据；root统一暂存、提交、推送。

## Purpose / Big Picture

运行writer只能拥有业务表SELECT、INSERT、UPDATE、DELETE及两本账本SELECT。TRIGGER允许DDL，REFERENCES及TRUNCATE也超出既定CRUD权限；这些权利无论直接授给writer还是通过PUBLIC生效，都必须让增量控制器和恢复证明的权限门拒绝。检查只读，不自动撤正式权限，也不改变实际恢复、迁移或5个拒绝探针的定义和计数。

## Progress

- [x] (2026-10-21 09:42 +08:00) 完整读App六模块、固定b9回填/事务/跨exec代码、TEMP补丁及真实PG测试；发现两门只对账本拒部分额外表权限，业务表可被额外授权却误判安全。
- [x] (2026-10-21 09:42 +08:00) root确认CRUD-only口径并授权本片；先写计划/真实PG负例，再改两个生产聚合。保留TEMP检查、全部旧断言、正式允许库/角色/端口和receipt ABI。
- [x] (2026-10-21 09:43 +08:00) 首轮8 setup errors/2.17秒：进程清环境方式留下空PGSERVICE，libpq拒绝空service文件名；尚未连接admin或创建本例对象。原件保留，改用真正移除进程Env项后重开独立红原件，未改业务断言或生产SQL。
- [x] (2026-10-21 09:45 +08:00) 旧SQL真实业务红：8 failed/79.27秒，另public checkpoint账本2 failed/22.21秒；每例两门都误报true，分别覆盖writer/PUBLIC、三种额外业务特权和两本账本REFERENCES，撤回自身新增授权后安全基线恢复。不是setup失败或被跳过。
- [x] (2026-10-21 09:48 +08:00) 两门最小EXISTS检查后组合28 passed +4 subtests /194.93秒（新ACL10、TEMP2、原PG port5、原B3 PG11），0失败/错误/跳过；原五探针仍为5，旧断言不改。严格Ruff/format/尺寸/diff通过，独立原始hash见证据。
- [ ] root统一暂存、提交和推送五件冻结文件；不自行git add/commit/push。
- [ ] Linux/服务器正式验证仍阻塞，不以Windows PG结果放行。

## Surprises & Discoveries

`PostgresPort._runtime_safe`已有TEMP、schema CREATE、owner/继承和账本写权限门，但业务表只核四项CRUD存在，没有拒额外TRIGGER/REFERENCES/TRUNCATE；`b1_restore_proof_pg.writer_permissions`相同。固定b9的grant_runtime_tables只增加CRUD并撤schema/账本部分写权，不撤额外表特权，因此不能用“执行过grant”替代有效权限检查。随后10种真实绑定均观察旧两门误报true，新只读聚合均拒绝；不是只凭SQL文字推断。

Windows本轮用SetEnvironmentVariable(null)清理进程环境仍留下空PGSERVICE，libpq将其解释为service空名；8例在admin连接阶段同样拒绝。换用Remove-Item Env:逐项真正移除后再试；这是测试启动器修正，不把setup error算作ACL业务红，也不改旧夹具。

App默认计划没有worker/PG边界；真实回填被精确合成marker、primary外层事务和相关表锁约束，原文/secondary/非回填表均核摘要；fence用固定b9真实锁和exec但惰性CLI替换，不代表systemd。venv包文件/pyvenv.cfg的完整写权限并未在App/B3门全面核验，已单独报root，当前ACL片不扩为解释器或依赖完整性改造。

另有未核实的schema USAGE有效权限检查边界：现方法没有独立USAGE门，部分text关系名称查询也可能因缺USAGE已失败关闭，不能仅凭静态缺检查认定误放行。root已授权下一独立片先做真实判定，再按观察补明确门；不混入本片28/4计数。JUnit包含4个subtest时tests总数为32，pytest主计数为28，不能说32个主用例。

## Decision Log

2026-10-21 09:42 +08:00 / root、Codex：在两个原有只读elevated聚合中各增加一个EXISTS，对mingjing_core/public中的有效表拒额外TRUNCATE、REFERENCES、TRIGGER。用pg_tables及quote_ident避免将索引/序列当业务表或拼不受控SQL。保留5个实际拒绝探针，不添加手填probe成功数；没有新正式receipt字段，不需改consumer或旧fixture。正式若失败保持现状停审，不自动REVOKE。

2026-10-21 09:48 +08:00 / Codex：真实旧误放行8+2绑定与新28主用例/4子断言均独立留原件；schema USAGE和venv保护待证保持独立后续，未为扩大绿数改旧测试或跳过PG。只有通过新增实际ACL观察及原5探针后生成器才可继续runtime_safe=true。证明JSON仍须受保护路径/hash与人工审查，不是密码签名，不把可手填JSON当不可伪造信任。

## Context and Orientation / Plan of Work

复用 `tools/core_incremental_pg.py::PostgresPort._runtime_safe` 和 `tools/b1_restore_proof_pg.py::writer_permissions`，保留ROOT已补TEMP行。新测试复用 `b1_restore_proof_support.proof_db`、真实schema4 dump/restore/migration7/latest replay准备与安全基线；只在该例自己创建的随机恢复库追加精确权限并在finally撤回这项测试授权。生产代码没有修复权限动作。

先执行新测试观察两门旧值均true，保留独立红JUnit。再加最小只读SQL，要求两门都拒；只撤回自身追加授权后恢复通过，且B3五probe数量仍为5。随后串行相关旧检查，不启动非窗口全库；实际PG只用显式loopback55480/55481和独立owner/writer，绝不构造NativePort或正式5432连接。

## Concrete Steps / Validation and Acceptance

在锁定Core Python、清除模型/渠道及隐式PG环境、关闭追踪后，显式传入B1_PROOF_TEST_ADMIN_DSN/BIN/CANDIDATE，运行：

    python -m pytest tests/v4/release/test_b1_incremental_runtime_acl_pg.py -q
    python -m pytest tests/v4/release/test_b1_incremental_runtime_temp_pg.py tests/test_core_incremental_pg_port.py -q

场景依据07号R02/F01的权限、撤销和停写不变量；本片无模型评分变化。验收观察值为：基线两门true；额外特权有效时两门false/固定安全码；撤回测试新增特权后恢复true，原5probe不变。不能通过改旧断言、跳过真实PG或将Windows标签升级Linux取得通过。

## Idempotence and Recovery / Interfaces and Dependencies

只强化只读判断，无迁移、依赖、配置、正式授权或运行时写行为。生成器/consumer JSON字段不变。测试仅由既有夹具清理自身随机数据库/角色；未知对象不删。红日志保留，不重写历史结果。团队测试≤4，本任务≤1窄进程；10:00宽回归前与root协调。

## Artifacts and Notes

私有原件 `private/b1-restore-proof-20261021/runtime-acl-*.xml`；公开证据 `docs/v4/evidence/B1/2026-10-21-runtime-acl.md`。不得写出DSN、口令、聊天正文或推理。父任务独占日报和汇总。

## Outcomes & Retrospective

本片已完成两门最小只读检查与先红后绿：10种额外有效表权限（直接writer/PUBLIC、三种业务权利和两本账本REFERENCES）原两门均误报安全，修复后都拒绝，撤回测试自身新增权限后安全恢复；28主用例+4子断言通过。保留TEMP、原5探针数、全部旧断言和receipt ABI；生产不自动更权。真实验证只有Windows隔离PG，Linux/Native/正式服务均未运行，五门仍No-Go，模型/飞书/服务器0。五件冻结交root统一提交；USAGE真实边界判定和venv保护列独立后续，不冒称完成。

## 修订记录

- 2026-10-21 09:42 +08:00 创建；按root确认的四项CRUD-only口径同时保护增量与正式恢复权限门，明确真实红绿、无自动修复及ABI不变。
- 2026-10-21 09:43 +08:00 记录首轮环境setup失败，保留原件并更正仅进程清环境方法，业务反例仍未完成，生产SQL不提前改。
- 2026-10-21 09:48 +08:00 完成10种绑定旧误放行实证及28主用例/4子断言通过，冻结两SQL聚合/新测试/计划/证据；原5探针、ABI和旧断言保留，另列USAGE与venv未验边界。
