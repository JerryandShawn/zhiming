# Direct Core预检：记录身份，未通过总流程

北京时间2026-10-21 09:08:47，在全部协作者暂停执行后，root审阅并运行一次私有A/B候选。
它不改现有六模块，不调用supervise、collect_core、pytest或trace。
父协调器加入实际cap4 Job；子候选使用cap3、禁止breakaway、挂起启动、句柄/PID核对、先assign后resume。
超时只使用已拥有Job句柄清理，不另启taskkill；清理不明时先留证据再终止整个自有Job。

A子程序只读取原生stdlib身份。它exit0，实际记录Core sys.executable、physical base的orig_argv[0]与OS image、
CPython3.11.16、完整隔离flags/xoptions、已被原生消费的launcher状态、无trace/profile、没有项目/pytest导入。
在-I -S下prefix与base_prefix均为物理base，不能沿用正常venv协调器的Core prefix说法。
实际Python DLL文件hash与父程序执行前/后钉住的内容相同；Core launcher、pyvenv.cfg与bootstrap原文也前后一致。

**整个候选结果是refused。** 内层累计TotalProcesses=2而候选要求1；外层累计3、最终active=1，内层最终active=0。
第二个进程的PID/image未观测，不能猜成conhost，也不能把约束改成2来得到绿色。
因此B固定bootstrap的--help未运行，collector、trace及整个supervisor仍为0。
这些身份事实只来自A；不能据此宣布B的完整启动、运行时指纹或采样协议已验证。

[整体拒绝收据](week-oct21-0908-direct-launch-refused.json)、[A原生身份](week-oct21-0908-direct-launch-identity.json)、
[子源码](week-oct21-direct-launch-child-source.txt)、[父源码](week-oct21-direct-launch-parent-source.txt)。
待完成的最小后续是捕捉本Job内全部实际PID/image并核清第二进程，再单独审阅是否能纳入具名transport。
不修改生产guard，不赋值sys.executable/sys.orig_argv，不调用真实模型或项目服务器。

## 同期调度缺口

09:04:47.362661至09:05:00.918779的306项定向回归及样式在本地cap4 Job内通过，
但协作者原生Ruff的时间锚点与之可能交叠。未采集全机跨Job峰值，不能把该轮当全局≤4的达标证明。
协作者没有精确逐命令开始时钟，不补造；其报告的末轮完成锚点为09:06:17.794。
现已冻结其所有测试、格式器和解释器启动，09:15完整回归仅由root单一协调器执行。
历史306断言结果保留，预算接受与断言绿色分开。

## 后续独立诊断

09:40 的新同类小试通过本 Job 句柄确认其第二进程为 conhost，仍被 total==1 拒绝；
09:41 的 detached A 与09:42固定 bootstrap --help 各自累计1、收尾为空。
只证明各自启动与有限身份，未修改本页09:08原始未知事实；没有启动 collector/supervisor/采样。
见[新诊断审阅与原始收据](week-oct21-detached-launch-review.md)。
