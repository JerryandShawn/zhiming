# P2 阶段回执

- 分支 / 实现冻结提交：`v4/p2-foundation @ de082ce1e6af37a706eee6a4596b09d1b6ca49e3`（本地）。精确代码树 `c25f3951743469702e2539b62379227713da4dca`，远端等价提交 `cc1187e95f3f292c56985c99dac859420af63fcb`，代码树已逐字核对相同。本回执为后续证据提交，未改冻结源码。
- PR：https://github.com/JerryandShawn/zhiming/pull/4 ，草稿，目标 `v4/main`，未合并。最终代码CI：[run39051908909](https://github.com/JerryandShawn/zhiming/actions/runs/39051908909)，最后核对为in_progress，未标绿。
- ExecPlan：`docs/v4/execplans/P2_foundation.md`。
- 结论：本地实现完成；最终本地旧Core553、v4 379、前端及scripted均通过；最新远端CI尚未取得完成结论，真实模型比较未执行，**P2 尚未整体验收**。没有 stage/生产操作、真实飞书或真实模型调用。

## 完成了什么（对照阶段提示词的验收标准逐条）

- [x] 1. 时间引擎覆盖附录13行、完整此刻字段、晚子时、交节秒边界、未知2027假日及离线覆盖。最终时间测试26项；年/月干支与物理交节一致，日/时柱使用owner当地。证据：`tests/v4/test_p2_timekit.py`、`timekit.md`。
- [x] 2. 0005–0007空库和旧0001–0004合成库迁移成功；未知版本/缺口/checksum漂移拒绝；实际非超级运行角色可CRUD新表、迁移账本只读。支持倒序/游标/limit、全文simple GIN检索与owner/subject隔离。证据：`tests/v4/test_p2_foundation.py`。
- [x] 3. 300轮合成成功运行dry-run无写入，apply创建300条助手，重复新增0；正文、原始at、revision与话题保留。中断整事务回滚后12轮重跑无重复；已撤销/删除来源不复活；Feishu精确来源核验，损坏/歧义输入跳过。证据：`tests/v4/test_p2_threads_backfill.py`、`test_p2_history_window.py`。
- [x] 4. 一万条消息完整snapshot预热10次、测量100次：p50=3.714ms，p95=4.155ms，max=4.896ms；取到最新09999并保留第5条早期约束，目标p95<150ms通过。证据：`snapshot-benchmark.json`及`tools/benchmark_p2.py`。该值不代表历史API海量查询性能。
- [ ] 5. 真实模型T01–T08/T10/T11/T13至少9项、R02/R03/R06、M03/M09/M10及S01比较：按夜间指令未执行，0真实调用；等待P1契约v2基线有效性和大脑安排。不以替身/scripted冒充实测，不改冻结P0 v1报告。
- [x] 6. 冻结de082ce最终旧Core **553 tests/826.169s，OK**；全部v4 **379 passed in159.87s**（129项P2新增），前端6项通过。此前两次完整失败及单独中止进程均保留记录、不计为成功。证据：`validation.md`、`regression-summary.json`。
- [x] 7. stage准备方案已写：备份→只前进迁移→重新授权→dry-run→apply两次→冒烟→前向修复/备份恢复与撤销重放。证据：`docs/v4/release/P2_stage_plan.md`。未执行部署。
- [x] 8. ExecPlan四段与本回执已建立，记录真实验证范围、失败及未完成项；最终CI结论待回填。

额外审计回归：fact-only/部分原话/整来源/typed恢复账本均迭代传播到助手、note/profile/summary、后续run、步骤、事件和outbox；无lineage旧助手兼容分支同闭包处理。助手输出永不成为用户事实，撤销后检索/向量/回填不能恢复正文。证据：`test_p2_privacy_closure.py`及`foundation.md`。

## 评测分数

- 脚本模式：80/80（100%，target=fake）；自测48项通过。报告：`scripted-report.json`、`scripted-report.md`。这是框架合成模式，不是实际v3问答成绩。
- 实测模式：未运行（0真实模型调用），无P2分数及同口径基线对比表。
- S01：固定12356/120/110配置进入真实服务模型接口的替身边界已验证；真实危机回答是否达标尚未验证。

## 改了哪些关键文件

- `timekit/calendar_cn.py`、`almanac.py`、`now_block.py`及`tools/update_holidays.py`：离线历法与此刻；Core/Test全哈希锁仅新增lunar-python1.4.8/jieba0.42.1，保留原版本。
- `repositories/migrations/0005–0007`、`foundation.py`、`permissions.py`：只前进存储、检索、链校验与重新授权。
- `memory/threads.py`、`backfill.py`、`policy.py`、`projections.py`、`history.py`及privacy辅助模块：双向线程、幂等迁移、窄策略修复和完整撤销闭包。
- `application/consultation_context.py`及consultation允许段落：now/四字段历史、400000字节默认、policy版本、成功助手持久化、同epoch程序时刻；未改from_base或模型构造。
- `config/crisis.yaml`、报告适配器/期间边界、业务Clock接线；`tools/backfill_v4.py`、benchmark、stage方案与129项本线新增测试。

既有测试改动恰为5个文件，均保留核心保护：

| 文件 | 明确P2契约与更新理由 |
|---|---|
| `tests/test_core_memory.py` | schema版本4→7；只读验证和篡改拒绝断言原样保留 |
| `tests/test_core_pg_channels.py` | 两条用户原文仍在，新增精确一条真实助手；重放无额外模型调用 |
| `tests/test_core_history.py` | 合成时刻fixture同步权威助手message.at/at_ms；原排序、跨日、分页、渠道、owner/subject断言均保留 |
| `tests/test_core_memory_proposals.py` | 一条用户+一条真实助手，精确核正文；原事实、授权、幂等、模型调用断言均保留 |
| `tests/v4/test_v3_target.py` | brief精确区分一条系统入站与成功后助手，执行前不虚构助手来源 |

旧035、decision_guarantee和repair_recovery断言未改；实际发现的句界、引号授权与时刻身份错误修在实现中。

## 数据库迁移与回滚方式

0001–0004未改；迁移角色在事务内验证连续已知checksum链并执行0005–0007，随后重授业务DML、新表及序列权限；运行角色对迁移账本只读且无schema CREATE。0005只移除数据库调用数上限，v3应用预算/repair规则未放宽；新Agent表只建立未启用。

只前进，不提供向下SQL；旧代码会拒绝新schema。异常优先向前修复；经授权恢复备份时须先重放最新撤销、sent/uncertain收据，保持写入和投递关闭，绝不自动重发不明送达。具体步骤见stage方案。

## 偏离设计的地方（及理由）

- 原锁文件只有版本无hash，已在版本不漂移前提下补Core/Test全哈希，不局部启用hash造成pip失效。
- 保留report_period旧周期标识，新增report_period_bounds提供起止日期，避免破坏旧调度API。
- schema初始化允许已知连续前缀并迁移已知后缀，运行校验要求完整当前已知链；未知未来、缺口、漂移一律拒绝，未将“超集”解释为接受未知schema。
- 假设判断在同一硬句内保留逗号前置条件/后置问号，避免把“如果…，我…”保存为事实，较分句字面定义保守；是否进一步拆分真实语料留大脑/P5。
- 同epoch固定now/today程序时刻以保持合法repair身份；没有从hash剔除时间，没有冻结整个snapshot或事实有效期。固定时间元数据不增语义revision，_call新增可选program_at，只在本次已安全记录的diagnostic事务追加时间保存；此为payload生命周期的窄偏离，预算/身份与模型构造不动，提交大脑复核。

## 未验证 / 已知风险

- 最终本地553/379全部通过；远端最终代码CI最后核对仍in_progress，未标绿。真实T/R/M/S与stage未验收，当前仅可审查草稿PR。
- history API为兼容未回填/无效旧时间扫描已筛选消息候选；消息窗口最多500，但run元数据仍fetchall。已验证10001旧回填不挤掉近期用户、同毫秒不同微秒游标不漏页，尚无海量历史接口性能承诺。
- 时间锚定不冻结事实有效期。若事实/来源可见性确实改变，完整payload/版本校验仍应拒绝不同修复，不能借此打开第二repair。
- 未来P5 writer必须记录完整source/fact lineage，仅covers_until_message_id不足以完成细粒度撤销；本阶段未开放P5工具。
- 与P1独立并行；P1在test锁新增coverage7.11.0，本线全hash锁会有预期合并冲突。P1验收合并后由P2 rebase保留coverage、重生成完整hash、核无既有版本漂移并重跑；_call同段须同时保留P1 provider诊断和P2本次安全时间钩子，不机械覆盖。
- npm报告旧依赖8项审计告警（2 moderate/6 high），未扩大范围自动升级依赖；没有前端代码/UI改造或真实浏览器视觉验收。

## 需要用户或大脑决定的问题

1. 大脑确认P1契约v2基线有效性、P2真实T/R/M/S比较时机及先后验收；夜间不合并P1+。
2. P1合并后P2 rebase及哈希锁合并顺序；保守句界解释是否需另阶段产品调整。
3. 若将来执行stage，另给专用授权/访问/维护窗口；当前只有方案，不需要用户为本机实现提供密钥。

## 建议后续

先看本地553/v4证据与草稿PR，并等待最终代码CI实际完成；大脑复核数据/隐私与保守句界解释。P1验收后rebase、重锁并复验，再按批准时机真实对比。stage部署及生产切换分别另行授权。
