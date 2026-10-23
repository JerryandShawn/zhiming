# 11点固定源启动器：Windows环境大小写修正

记录：2026-10-21 11:01 +08:00。仅本机离线测试启动器，生产源码、依赖、测试断言均未改。

11:00:11两次首启动在pytest插件导入`asyncio.windows_events`时退出：`OSError [WinError 10106]`，未进入collection，没有测试结果，也没有JUnit。根因是私有启动器在遍历Windows环境键时以区分大小写的白名单匹配，漏保留实际键`SYSTEMROOT`；它原本在允许的`SystemRoot`项中。白名单改成键的大写等价比较，允许的变量集合不扩大；模型凭据、隐式PG路由与追踪配置仍不继承，测试只使用显式本机隔离PG、ScriptedProvider及loopback HTTP。

首启动原始产物保留，未覆盖：

- `private/regression-20261021-1100-main-1fe5149c/{metadata.json,v4.log}`：主树固定`1fe5149cbe9de10632f97f84003ac833a4a4f65f`；11:00:11.739400开始、11:00:12.066947退出1，JUnit未生成。
- `private/regression-20261021-1100-p4-a1270174/{metadata.json,v4.log}`：P4固定`a1270174e6f64cfe1abe915a09836647c1da3484`；11:00:11.790598开始、11:00:12.102175退出1，JUnit未生成。

这些私有路径都位于本聊天工作目录`C:/Users/Administrator/Documents/Codex/2026-10-17/v4-ai-claude-c-users-administrator-4`。日志仅启动堆栈；不含请求正文、密钥或完整DSN，不将原件加入Git。

修正后仍在允许的11点00–15窗口，以同一Git提交重新导出到各自`-env2`目录，真实开始时间见其metadata。两条完整v4和P4同源原47/扩13脚本已启动；结果由独立完成归档记录。不能将首次启动失败算成产品测试失败，也不能将修正后在途说成全绿。没有删除、跳过或弱化任何测试。

11:03 Core私有启动器又在执行unittest之前因缺失`pg_bin`局部定义退出`NameError`；当次没有创建Core日志或测试结果，原错误留在工具转录。补齐已存在的PG工具路径、已有锁定jsdom依赖路径后，三个私有启动器通过Ruff F821未定义名检查；P4同一a127导出随后在11点窗口开始Core。未安装依赖、未修改生产或测试以绕过错误。最终证据分别给出实际启动器SHA与Core真实开始/结束，不把这次启动器错误隐藏为业务失败或成功。
