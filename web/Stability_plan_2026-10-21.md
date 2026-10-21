# 白天④ · 同一源码三轮稳定性记录

唯一工作树与分支：zhiming-v4-p10 / v4/p10-frontend。北京时间记录，自动续作仍至2026-10-27 22:00；不访问项目远程服务器、模型或飞书，不合并。仅本机core_test_fe:55481/8002脚本替身和静态预览。

## 固定范围

当前运行源码61afdbe，首批证据头7d8e26d；97份已提交TS测试、48份浏览器spec。三轮使用相同源码、测试和构建，不在批次之间混入新功能；文档和报告提交不等于运行源码变化。后续33候选仅在ignored准备，不提前计入验收。

整套包括52离线Python、全部前端TS、常规九套浏览器（static/spaces/components/components-visual/night/overnight/contracts/live-visual/spaces-visual）以及独立Q9三套（static/night/v3）。Q9四尺寸双主题不再被默认配置忽略后冒称已覆盖；最终逐spec核对48文件齐全、原测试文件用例数不减少。

每轮首轮0失败/flaky/跳过、全部suite exit0、受测源/测试/构建及HEAD前后一致，才能计为一次成功。失败保留完整报告/截图与具体项；修复后若源码改变，重新定义稳定源码并从第1轮计，不能混用旧头绿灯。最多4单测/2浏览器workers，套件串行；全量仅北京时间每小时30–45分开始。

## 执行记录

- 原启动器：旧Windows PowerShell把unittest stderr进度当终止错误，浏览器尚未开始；原目录`web/test-results/week-stability-1`保留，不算完整测试轮。
- 第1轮正式：`week-stability-1b`，2026-10-21 10:39:29+08开始、10:56:58+08结束，7d8e26d。52/52 Python、1185/1185 TS（97文件）、856/856浏览器（48文件、常规560+独立Q9296）首轮全绿；失败/flaky/跳过/重跑0，1031项源/测试/构建及HEAD不变。892张显式PNG有指纹。证据`web/evidence/2026-10-21/stability_1_checks.json`与同名receipt；当前成功1/3。
- 第2/3轮：未开始。若第1轮全部通过且源/测试/构建不变，按11:30–45、12:30–45合法窗口继续；若运行延误，使用之后合法窗口并如实记录，不回填时刻。

## 恢复入口

先读指令板、ExecPlan与日报、git状态，确认有无本线仍运行的测试；不要并发重开同一批次。首轮执行脚本为ignored `web/test-results/run-week-stability-1b.ps1`，汇总脚本为`collect-stability-1b.py`；原始路径独占，后续轮必须新run_id与新报告目录，不复用旧输出文件。只用既有PowerShell7/本地node_modules/.bin，offline npm，不再用根目录npx获取临时工具。

计划中的窗口不是完成记录。当前CI仍pending/queued，不能由本机完整回归代替；真实设备、部署、跨刷新真实恢复与预测效度不在这三轮证明范围。

## 11时恢复补充

第1轮证据已普通推送f02fbe2，PR #6已更新且仍Open Draft。另补三张原图引用副本到`stability-1-samples/`（不再计入892），root已查看手机分页、桌面术语Sheet与晚间视口。

第2/3轮独占脚本已经只在ignored准备：`web/test-results/run-week-stability-2.ps1` / `run-week-stability-3.ps1`，对应`collect-stability-2.py` / `collect-stability-3.py`。尚未运行。collector除本轮完整检查外，还核1031项哈希、全部97/48测试清单与第1轮完全相同，并检查7d8以来运行入口/配置的Git差分为空；第3轮额外要求第2轮通过。仍须先直接用现有PowerShell7执行，不能套powershell.exe；收证据前不提交，以保持本轮HEAD不变。

恢复时先确认没有仍运行的测试；在11:30–45启动第2轮、12:30–45启动第3轮，未到窗口只做只读/ignored候选及文档。每轮约18分钟，开始前核40分钟推送期限，必要先提交真实文档检查点；不能为了推送改受测源码。每轮结束先collector再证据提交/普通push/小回执。11:20等自动唤醒若发生在已有批次中，不重复启动。

未来33候选已在ignored准备：`thread-dto-draft`及`thread-dto-tests-draft`、`thread-http-draft`及`thread-http-tests-draft`，只读复核及静态测试清单不等于通过；根线在三遍完成后再统一迁入和验证。H5与20课也只有计划。新版API发现索引及课程别名漂移已经写入正式接线笔记，当前七资产/普通入口未改。

## 11:26 验证器补强（正式受测代码未改）

独立只读审查找到证据收集盲点，已仅改ignored启动/收集脚本：第2/3轮每suite显式`--output`到其独占batch，固定components stage为all，避免继承环境只跑子集；完整97单测文件/1185用例与48浏览器文件/856用例身份逐项对照第1轮，拒绝pending/todo、expected-failure、多attempt或跳过。Q9精确128/112/56，常规560。第1轮原始报告也已只读补核全部实际passed、单attempt、Python裸OK；这不是重跑。

原1031指纹覆盖src/public/scripts/tests/dist，不含全部根入口与配置。后两轮额外对21份根入口/config/package建立实际字节前后快照；从7d8提交核对当前21文件未改，第三轮还要与第二轮相同。第1轮补充只证明原报告完整和当前配置与Git一致，不事后虚构其历史额外快照。原成功批次没有失败trace附件；原共享Playwright诊断目录不能称全独占，后两轮已修。见`stability_1_completeness_supplement.json`。

11:25另用127.0.0.1:4173纯静态GET核HTML、entry JS、React预载、CSS四份字节与冻结dist完全相同，未执行JS或访问API；见`stability_2_preview_preflight.json`。两个收证helper首次分别误用Git工作目录前缀与假设绝对资源路径，已按实际Git/HTML修正，不是产品/测试失败。未新增依赖、未重建、未改断言；仍仅1/3，第二轮尚未开始。
