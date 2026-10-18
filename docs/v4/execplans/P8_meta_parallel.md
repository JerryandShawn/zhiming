# P8 命理计算线 ExecPlan

## Purpose / Big Picture

只在zhiming-v4-p8/v4/p8-calc交付可复核的计算、技能与离线评测。最新用户D3已有准确时辰：优先换算核对，不改记录；人生事件倒推放到最后。不是P8完整业务闭环验收。

## Context and Orientation

指定源20、14§H、16 U1/U2/U3/U8/U9、最新P8及后续18两份增补/00索引D3。源文件是设计意图，代码是事实；仅charts/skills/knowledge及测试、必需证据和daily可写。默认v3 adapter/worker/hermes/calculations、zhiming-v4与p10不改。测试PG仅127.0.0.1:55480/core_test_meta，服务器保留8003未启动。0模型、0stage/生产、0合并。

## Progress

- [x] (2026-10-18 +08:00) 读指定文档、代码与分支，复核H具名裁定；初始基准f23b942。
- [x] (2026-10-18 16:26 +08:00) 发现20在16:18加入新18设计；冻结旧前三方案，保留历史源码/失败证据。
- [x] (2026-10-18 +08:00 D3更新) 执行H→time_basis→U12→U2→skills→E2→最后事件倒推。
- [x] H具名表/显式入口与旧口径隔离；time_basis 36定向（桥内8native）、只读入口11、严格节界桥1（内3native）通过。
- [x] U12 35规则各正反例+3教材快照，U2稳定排序与技能28章；定向131通过。
- [x] E2 v2 C0–C4a/b、随机选项/会话/同题统计/外部盘映射；75测试与3题全配置脚本通过，0真实调用。
- [x] 最后补workbench纯冻结/留出/置换与校准拒绝；40单元+真实grid桥1（内10native）通过。
- [x] (2026-10-18 最终) v4全570/570，0skip；脚本80/80；Ruff69文件与141保护文件不变核验通过。
- [x] 旧Core553/553、旧计算60/60在本阶段已实跑；其后受保护旧文件不变。
- [x] 真实排盘合成10人和12格噪声/零事件评测已运行，结果与人工矩阵严格分列。
- [ ] 正式倒推E-R1≥95%：未达（唯一0/10，稳定解并列2/10）；不放宽方法，交大脑复核。
- [ ] 正式200种独立出生盘E-R2/自信错误门槛、跨平台CI、依赖锁与业务接线：未覆盖或归主线；详见daily。

## Surprises & Discoveries

旧v3巳藏干与库次序不一致仍保留，新入口保存原表后按v3表派生旧字段，新具名字段用所选表。徐表申“戊己土十日”不唯一，不能默认阴阳。新时间核对重建精确秒起运会覆盖具名藏干，独立review发现后补归一并保留司令实际节界。DST/真太阳时不可二次应用；八字sect1日界与紫微index12日界分别标明。E2只按ID配对和负索引JSONPointer会误比，已补题面/键指纹及严格索引负例。

旧同规则反推是循环实验。新真实年度信号也无法唯一分出候选，所有十人并列，即使p小仍被唯一领先/留出闸门拒绝；人工12/12不能冒充实际E-R1。外部题库缺地理/时区输入与源标签异常保持阻塞。

## Decision Log

2026-10-18：用户新角色覆盖此前主线任务。其他线/API/持久化/提示词/锁不越界；遇待决写daily后继续，未请求新的外部授权。

2026-10-18 16:26：18号明确替代旧U9，撤下旧RectificationEngine/scoring/input/calendar/eval与25+10旧native/两桥。旧测试保护owner、采样、严格节界、事件确认/分区、上限、排名与不写资料；废止的排名/事件评分契约归档。新time_basis保留归属/不写/日界/节界；新增Jie几何测试保留12节严格两侧和声明范围裁剪；新workbench保护冻结/来源去重/撤销/轮次/三闸。未覆盖业务闭环在回执标明。不是为了提高分数删错例。

2026-10-18：P8显式入口增加巳顺序桥，旧测试同时保留默认v3拒绝与新入口保存差异断言；特征11→12为U2，12→13为U12，数量随新契约更新，逐Pointer/旧产物对照保留。mixed/layered容器明确时间尺度。

2026-10-18 D3：以准确记录为准；两种时间口径并列。E2同年歧义不私自裁定，调用方必须指定birth_year或competition_year。倒推真实0/10保留为失败，不改规则与预定人物，不以框架矩阵替代。

## Plan of Work / Concrete Steps

实现顺序已如Progress，最后是低优先证据工作台。命令：Core `-m pytest tests/v4 -q`；Core `tools/eval/runner.py --mode scripted`；Core `private/p8-validation/check_delivery.py`。原生检查经CHART_PYTHON隔离，模型Key清空/追踪关闭；测试Charts借用Core锁定tzdata的显式路径，未安装共享venv。真实年度预计算由chart_grid+signals，固定独立种子事件集由evaluation_charts，分开人工evaluation矩阵。

## Validation and Acceptance

本机软件检查570/570、脚本80/80。正式E-R1不通过，200种独立出生盘与自信错误率、Linux/Windows一致性未证明；不宣称完整P8 Done。详细命令/输出/指纹见evidence/P8/meta-regression-summary.json与meta-validation.json、time-basis-crosscheck.md、rules-review.md、skills-review.md、e2-v2-scripted-2026-10-18.md、rectification-eval.md。

## Idempotence and Recovery

接口只读，写操作/模型调用为0，无数据库迁移；测试只写隔离库。停止选择P8显式入口即可回退；撤回本线代码和证据提交可恢复原分支。旧实验留本机Git引用/忽略归档，真实题库正文不入库。冻结事件哈希、规则哈希与cache哈希绑定，源撤销使结果失效；业务持久化仍归主线。

## Interfaces and Dependencies

P8ChartAdapter.time_basis(request)；charts.rules.evaluate_rules；bazi_interactions及Ziwei/transit模块；SkillLibrary/chart_skill；benchmarks.protocol_v2；rectification_workbench.sessions/signals/statistics。主线接r#别名/Context/registry/档案/API/资料确认，Charts还需tzdata==2026.5锁和安装。

## Artifacts and Notes

代码基准 `5a5334bcb1426b94fac1016992ab6c6b4cb5ec9e`，本机等价be7ae912，源码树b0698e6d5657740907222544b55d01dfb22d20ce。PR https://github.com/JerryandShawn/zhiming/pull/5 保持draft。证据独立提交，远端CI状态以PR为准。日汇总docs/v4/daily/2026-10-18_meta.md；阶段回执evidence/P8/P8_命理计算线_阶段回执_2026-10-18.md。

## Outcomes & Retrospective

本线交付准确时刻核对、具名计算与规则证据、技能/E2离线框架以及诚实拒绝的工作台。主要限制不是测试跳过，而是倒推信号不能唯一分辨与跨线部署/业务尚未接；本轮保留失败事实供大脑决定，未合并、未部署。

2026-10-18 17:33 Decision/Progress：为保证锁定数据优先，修复Linux包/OS优先级；显式当前环境覆盖严格验证绝对目录，空覆盖禁OS，未锁定回退透明标记。新增9用例与公开固定评测样本/入口；最新聚合570通过、80脚本。source基准5a5334b，正式倒推仍不达标。
