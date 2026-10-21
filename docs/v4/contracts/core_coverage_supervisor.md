# Core覆盖监督候选契约 v1（未实采）

这是研究工具契约，不注册Agent工具，也不产生排盘事实或c/r/t别名。
入口`charts.benchmarks.line_coverage_core_supervisor.supervise`：

```python
supervise(commit=full_40_sha, inventory=Path(...), plan=Path(...),
          node=exact_core_node, mode="baseline" | "trace", output=Path(...))
```

只允许静态计划已有的三个Core节点、固定Core/引导文件与完整SHA。
输入、计划及新的collector输出均在本线`docs/v4/evidence/P8/*.json`，不允许别名/符号链接、
重用输出或相同输入输出；临时缓存和started/final监督收据只放唯一`private/tmp`目录。
固定Core、bootstrap、自身监督模块、输入计划及taskkill内容绑定SHA，执行前后核对。

## 生命周期与返回

先建KILL_ON_JOB_CLOSE且不准breakaway的Windows Job；CREATE_SUSPENDED启动固定Core。
保留Popen handle核PID，先assign Job，核只有一个进程与唯一主线程，才resume。
stdout/stderr/stdin均DEVNULL，不保存测试正文；凭据与追踪关闭。

等待45秒，父启动器已退出也必须继续等Job active=0。
到期仅对本次仍活且handle/PID相符的父进程调用固定System32 taskkill /PID /T /F，
再用Job终止并核清空；父进程已退出则不按旧PID调用taskkill，Job负责其后代。
任何失败均逐项尝试终止/等待/关Job/关进程handle，不能因第一步失败跳过后续清理。
启动哨兵为`started_not_final`；失败收据只含阶段、固定代码与WinError，不含任意异常正文。

监督收据`version=p8-core-supervisor-v1`，有commit/node/mode/fixed_sha256、
state/timed_out/child_exit_code/job_active、清理失败、北京时间时间戳及内容SHA。
`actual_coverage_acceptance`始终false；该收据不能独自证明pytest或执行覆盖成功。
root未来还必须同时核正常Job空、无超时、exit0、无清理失败，才检查独占的collector收据，
并由原merger验证完整清单/实际节点生命周期/源/依赖/前后状态。失败或partial不得聚合。

## 当前已验范围与未验范围

55个合成WinAPI/Popen/时间负例已验；root与塔罗143组合198项通过，两个数字有包含关系。
另在本机对Job原语分别验证：空Job、真实Core合成进程挂起assign/resume后退出，
终止sleep进程，以及父进程exit0后仍存活的后代被所属Job清空。它们没有调用supervise。
真实supervisor整体生命周期/taskkill路径、collector baseline/trace、Charts采样仍为0。

sleep探针Job内实际3进程，早先总4估计已撤回；历史总峰值未量测，可能超过4。
当前真实Core入口是启动器，不能按文件名预估进程数。
后续本地验证使用同一base镜像的Core启动上下文、inline运行，并以Windows Job
ACTIVE_PROCESS_LIMIT=4限制协调器与全部后代，未配置breakaway。
相关限制语义见[Microsoft Job限制结构文档](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_basic_limit_information)。
这个验证Job与本监督器的KILL_ON_CLOSE Job用途不同，不据此宣称原supervise已满足全局预算。
仍须在真实采样前确定外层、Core启动链及metadata Git同时存在时的预算。

Python守卫不是OS安全沙箱，SHA不是身份认证；Job也不证明业务断言质量。
当前完整归属固定3424036：239文件/26572行，Core/Charts静态计划execution_approved=false。
静态分母不是执行覆盖率，不沿用旧局部4.30%或声称达到90%。
