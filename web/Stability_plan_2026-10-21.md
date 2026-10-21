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
