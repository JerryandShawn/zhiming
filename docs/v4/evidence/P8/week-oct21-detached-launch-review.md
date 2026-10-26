# 无控制台启动诊断：观测已分层，采样未启

本记录时间均为北京时间。root 在协作者全部暂停工具后串行执行三次私有小试；
每次协调器实际加入 cap4 Job，内层固定 cap3，不允许 breakaway，挂起后先核对句柄/PID/映像、assign，再 resume。
只使用当前工作树和只读的已安装 Core 环境，未改生产启动器、collector 或运行时身份门禁。

## 09:40：严格拒绝，并观测第二进程

[原始收据](week-oct21-0940-job-observation-refused.json)：09:40:23.536131 至 09:40:24.491716。
`CREATE_NO_WINDOW | CREATE_SUSPENDED` 下 A 的 Popen PID 为 30688，exit0；内层累计 2、最终 active0，
外层累计3、最终仅协调器 active1。原 `total == 1` 条件拒绝，返回1。

本次空 Job 先关联完成端口，再通过通知和 Job PID 列表观测到 30688、35860。
二者均以保留的进程句柄经过 GetProcessId 与 IsProcessInJob 核对后查询映像和创建时间；
35860 的映像为系统 `conhost.exe`，父 PID 快照为30688。没有按文件名猜进程归属。
这识别的是本次实际进程；09:08那次未记录第二 PID 的历史仍保持未知，不回填它的身份。

通知可能遗漏、PID可能复用，故观察结果始终 `complete=false`，最终仍以 Job accounting 判断。
父 PID 是快照，不是父进程的保留身份；未确认属于本 Job 的句柄不读取映像。
这些边界来自 [Microsoft 的 Job 完成端口说明](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_associate_completion_port)。

## 09:41：独立 detached A，仅身份与生命周期

[原始收据](week-oct21-0941-detached-identity.json)：09:41:24.923470 至 09:41:25.847222。
新具名候选仅把创建标志改为 `DETACHED_PROCESS | CREATE_SUSPENDED`（0xC），保留 DEVNULL 和原数量门槛；
不同时叠加 CREATE_NO_WINDOW。两种标志的含义见 [Microsoft 创建标志](https://learn.microsoft.com/en-us/windows/win32/procthread/process-creation-flags)。

A 的实际 PID52992，exit0；内层累计1、最终active0，外层累计2、最终active1。
原生记录 Core sys.executable、物理 base 的 orig_argv[0]/OS image/DLL、隔离 flags、已消费的 launcher；
没有赋值 sys.executable 或 sys.orig_argv。`-I -S` 下 prefix 是物理 base，不冒称正常 venv prefix。
项目/pytest未导入、trace/profile未启；身份输出后固定停留0.75秒供观测，不启动线程或子任务。
固定解释器、配置、DLL和源文件原始摘要前后相同。结果仅为 `diagnostic_only`，没有采样授权。

## 09:42：独立 detached B，仅固定 bootstrap --help

[原始收据](week-oct21-0942-detached-bootstrap-help.json)：09:42:55.839748 至 09:42:56.469919。
B 先校验 A 收据的固定 SHA、成功数量及 A 钉住的全部文件仍相同，随后执行固定 bootstrap 的 `--help`。
Popen PID46212，挂起映像为固定物理 base，exit0；内层累计1/active0，外层累计2/active1。
观察到的唯一进程也通过本 Job 成员核对。B 的 Python 内部身份没有再单独输出；A/B证据不混成一次采集。

按已逐字审阅的固定 bootstrap/run 代码，帮助参数在 argparse 处退出，未调用 collect_core 或 bootstrap_guard，
没有运行 pytest、baseline、trace 或实际 supervise。结果仅为 `bootstrap_help_only`。
导入 trace 模块不等于启动 trace；本次没有设置追踪器。

## 审阅与留证

- [观测辅助类](week-oct21-job-observer-source.txt)：每次最多64条非阻塞通知、固定16容量 PID 列表、总观测≤15秒；
  已确认身份缓存，独立尝试关闭保留进程句柄、解绑完成端口及关闭端口。
- [固定停留子程序](week-oct21-hold-child-source.txt)、[原标志诊断](week-oct21-job-diagnostic-source.txt)、
  [detached A](week-oct21-detached-diagnostic-source.txt)、[detached B](week-oct21-detached-help-source.txt)。
- 父协议仍采用先清理已拥有内层 Job、再核外层仅剩协调器；无法核清时先写 partial 收据再终止整个自有 Job，
  不按陈旧 PID 杀进程，不另启 taskkill。
- 原09:08整体拒绝、09:40严格拒绝均保留；这两次拒绝不因后续候选通过而变绿。

## 下一步与限制

现有生产 supervisor 仍使用原启动协议，未被本次候选替换；其真实执行和覆盖采样继续0。
新 transport 需要单独协议化并扩充运行时指纹（OS image、orig_argv[0]、pyvenv.cfg、prefix、创建标志），
还需核元数据 Git 子进程的 launcher 清理及超时清理预算。不能让帮助页 exit0 代替这些门禁。
保留全部既有身份拒绝条件，未批准计划 `execution_approved=false`；不报告90%或任何新行覆盖率。

没有真实模型、项目服务器或飞书请求，没有修改 v3、依赖或其他工作树。
