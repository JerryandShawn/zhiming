# P3 同轮纯读工具并行：本机窄组合回执

记录时间：2026-10-21 07:34（北京时间）。主工作树候选；root统一提交。02点固定快照不含本片，历史M8及全回归报告保持原样。07:28以前额度中断期间没有03–06点连续执行证据，不补造进度。

## 实现与权限边界

- `ToolBatch`把原串行工具逻辑拆为同一条prepare/invoke/accept路径。只有当前实际exposed、registry确认为read_only、并位于保守真纯读白名单的连续工具可进入两个worker：time_context、calendar_lookup、memory_search、profile_get、case_list、date_calc。工具参数带显式引用或“上一步”等依赖标记时保持串行。
- tarot_read有受保护持久缓存，因此即使registry标只读也不并行；写入、忘记、提问、选项、提醒等保持原执行路径，并作为前后纯读组的屏障。无新依赖、无供应商请求。
- 主线程按模型顺序发通用tool_call、验证指纹、暴露与重复限制、预留Journal序号。worker仅调用原registry.execute，不写Journal、aliases、messages或events。主线程按原顺序在同owner事务内完成Journal并登记原引用血缘，事务通过后才把结果交给模型及发通用tool_result。
- 应用纯读路径先短事务执行原authority，再离开owner长事务计算/短查询，随后短事务重核原authority。结果确认仍受原租约、epoch、scope、cancel、deadline和撤销/版本门约束。未授权或迟到结果不登记alias、不进入下轮模型、不产生final。
- 等待Future每50ms检查取消/续租；取消不会等迟到的纯计算，未启动Future取消，已启动只读计算完成后丢弃。没有宣称强杀线程或无限计算资源隔离。

## 真实本机验证

本机回环PG `127.0.0.1:55480/core_test_main`，每例隔离schema；TZ=Asia/Tokyo，业务时钟显式冻结，北京日期不依赖主机时区。执行前清API密钥并关闭LangSmith/LangChain/OTel追踪，脚本模型，禁止HTTP和子进程的既有夹具保持。单个pytest进程，未运行全量或外部调用。

    python -m pytest tests/v4/agent/test_loop_parallel_pg.py \
      tests/v4/agent/test_loop_parallel_recovery_pg.py -q --tb=short

**9 passed / 6.11秒，0skip。** 独立测试用实际日历handler内部Barrier、当前线程无repo事务断言与反序完成控制，证明PG owner锁外真实重叠，而非仅线程池启动；三个纯读最多两个worker。写工具与ask_user有序，重复三次后的后续调用不执行，未暴露/别名依赖/缓存塔罗拒绝并行。

取消及撤销两种跨线程反例在真实handler阻塞时改变PG；Runtime在2秒内停止，迟到结果不完成工具Journal、不发tool_result/final、没有下轮模型和assistant。部分批次SystemExit模拟进程中断：第一读已完成、第二读仅started，失租回收后第一读零再执行，只补第二读且序号/指纹稳定。

    python -m pytest tests/v4/agent/test_loop_parallel_pg.py \
      tests/v4/agent/test_loop_parallel_recovery_pg.py \
      tests/v4/agent/test_loop_cycle_pg.py tests/v4/agent/test_loop_cycle_controls.py \
      tests/v4/agent/test_toolkit_pg.py tests/v4/agent/test_agent_runtime_pg.py -q --tb=short

**74 passed / 25.73秒，0skip、0warning。** 74包含上述9项，不相加成83。既有工具回执、推理回传、模型续轮、控制与Runtime目标均未改断言。另一个代理的自写修订/工具效果恢复组合另行报告，不能拿本组覆盖全部恢复矩阵。

Ruff `E,F,I,B,UP,SIM`、120字符格式检查通过。新测试仅补显式fixture包装以供pytest发现，无旧fixture或冻结场景修改。默认88格式会改变既有120风格，此片使用120且不整体重排旧文件。

## 修复过的交叉回归

早间恢复矩阵指出accept新增的全control.poll在合法case/memory写入已经生效、Journal尚未确认的窗口提前校验依赖，导致自己的版本变化被误判。此新增poll已移除：Journal.complete与_register继续同一owner事务且保留原租约/取消/撤销门；只读Future收集前及prepare前的poll仍保留。不得用该问题证明可以绕过依赖核查。

07:36交叉复验回报：工具效果恢复矩阵/pending证明/原own_revisions三文件**41 passed / 20.32秒**；Snapshot/Runtime/Journal/case_versions另四文件**47 passed / 17.16秒**。真实memory_update旧epoch失效及原完成证明缺失反例原断言保留；accept Git blob `a59e6e84472e57a56f9aac3909fd35620858a69e`。结果由协作代理实际运行，详见[恢复矩阵证据](2026-10-21-tool-effect-recovery.md)，有测试重叠，不与74项相加成唯一总数。

## 源码身份与尺寸

下列为规范LF SHA256，最多291行/函数53行/单行119字符。文件未由本代理提交；最终提交号由root追加发布回执。

| 文件 | 行数 | LF SHA256 |
| --- | ---: | --- |
| agent/loop_batch.py | 156 | 5b9c7e6485b5838c2398e773874327ab30a2e655d3d45844123e381fca4e4e79 |
| agent/loop_cycle.py | 291 | 8ba57011152ceba26f525ce5175e6328aece8e1978ab024950c1ed287409f420 |
| application/agent_tools.py | 199 | f8d26ecac1ee32a981bd1e53c1762bda8143c73164de59aabc139a528eb0925b |
| application/agent_tools_parallel_reads.py | 45 | 27b2a5ede87ac350cec5ef563fc81ba82ebd263299801feb667a71e040e2a8a7 |
| tests/v4/agent/parallel_tools_support.py | 57 | 3e6df7a23c1dbff7b64e15f1578d69f3686da846f1f4f51d57974ae2c58167da |
| tests/v4/agent/test_loop_parallel_pg.py | 158 | 768761186933c8b7e89d8d1eab87afd5a9cc12c1c29e734e34b7e808a713d52d |
| tests/v4/agent/test_loop_parallel_recovery_pg.py | 100 | 5ad90169fd3feaf2944633214e34d3274f65106bf732547845c5b5d2911bd292 |

## 未验证

这是本机隔离PG与ScriptedProvider的功能/恢复证据，不是供应商并行、Linux、真实模型质量、渠道、部署或全库验收。当前只并行保守白名单；跨工具新别名依赖、不独立读取及任何有副作用的工具继续串行。后续root提交后需固定tree回归；没有迁移、服务器、真实Kimi/飞书发送或合并。
