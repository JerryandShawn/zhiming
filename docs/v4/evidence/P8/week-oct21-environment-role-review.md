# Python 身份继承项清理：有限环境修正

北京时间2026-10-21，承接06582bb与指令板v1。本次只改研究工具的 `safe_environment()`，
按名称大小写不敏感移除 `__PYVENV_LAUNCHER__`、`PYTHONHOME`、`PYTHONEXECUTABLE`、`PYTHONPATH`、`VIRTUAL_ENV`。
它供 MetadataGit 和既有 supervisor/清理辅助环境复用；不新增transport，不改固定Core命令、创建标志、身份guard或数量门槛。

## 修前与修后

- [修前原始日志](week-oct21-1004-env-before.txt)：33 failed / 6 passed，全部为合成普通mapping，
  证明这些输入项会被原函数保留；没有倾倒用户进程环境或证明存在外发。
- [修后首轮](week-oct21-1005-env-first.txt)：170项断言通过，但新测试文件格式检查拒绝，整个命令exit1；
  对应[进程收据](week-oct21-1005-env-first-process-summary.json)准确记录1。
- [格式化证据](week-oct21-1005-env-format-process-summary.json)：只格式化测试，AST相同；
  后加两项消费者连线测试，也经[受控格式化](week-oct21-1009-consumers-format-process-summary.json)保持AST。
- [最终定向日志](week-oct21-1009-env-172.txt)：**172/172、0skip、0.44秒**，含新增39环境角色节点、
  2消费者节点与旧131预算/监督/守卫节点。聚合数不再叠加之前170。
- [同轮样式](week-oct21-1009-env-style.json)：234 Python、141旧文件保护、密钥模式检查通过。
  root独占实际cap4 Job，含协调器和后代，前后active1；385项目源前后一致。
  [协调器摘要](week-oct21-1009-env-172-process-summary.json)、[冻结harness源码](week-oct21-env-harness-source.txt)。

## 保护范围

39项角色测试使用普通dict提供upper/lower/mixed，避免Windows自动大写掩盖真实函数比较。
保持原凭据/provider/Git/pytest/追踪清理和固定Git值，保持正常SYSTEMROOT/TEMP/PATH、
PYTHONUTF8/PYTHONNOUSERSITE与非精确键PYTHONHOME_NOTE；返回新dict，父mapping不变。
没有扩大成所有Python变量的通配过滤，也不是完整OS环境白名单。

2项消费者测试实际经过 MetadataGit 构造/配置与read，和 `_kill_tree()` 的owned/live分支，
截获实际传入的argv/env，核固定配置和清理结果。Git使用临时合成配置和不可执行字节文件，
taskkill使用合成child/job；两者transport均为捕获替身，**没有执行Git或taskkill进程**。
这些测试不证明原生wrapper启动、超时或OS清理成功。

独立只读审阅未发现阻断：五键精确、普通值保留、既有Core命令和pyvenv.cfg定位未变。
这属于静态判断，不能借它宣称旧wrapper历史两失败已修。

## 仍未验证

当前仅定向，下一合法窗口再完整回归。上一3072完整仍属于4dd，不顺延为本次全量。
元数据Git的实际helper/console链、新transport完整身份和超时预算、真实supervisor/collector/覆盖采样仍未验/未启。
默认v3、其他工作树、计算、权重、样例、知识和技能未改；本次没有真实模型、项目服务器或飞书请求。
