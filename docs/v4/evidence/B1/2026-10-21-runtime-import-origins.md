# B1 App第三方import来源：执行后位置诊断

记录：2026-10-21 10:44 +08:00，北京时间。本片仅新增来源helper/support/测试并最小改runtime.critical_imports；runtime_capability、CLI/process、旧App测试、收据ABI、b9包、Charts和B3来源hash闭包未改。

## 验证结果

接线前单例 **1 failed/0.20s**（10:42:54–55）：三个Core来源都合法，外部pydantic来源仍被旧检查放过。接线后新纯/真实临时目录目标 **33 passed/0.50s**（10:43:15–16）；随后原App纯契约 **40 passed/3.99s**（10:43:41–46），含既有实际本机Python runtime-only对照，均退出0，无warning/skip。单一窄链串行，结束即释放，不跑八个PG或整库。

四个明确叶子为psycopg、langgraph.graph、langgraph.checkpoint.postgres、pydantic；两个namespace祖先为langgraph、langgraph.checkpoint。叶子必须有真实文件/spec匹配位置；namespace仅在合法spec及非空、全部同根且一致的spec搜索目录/__path__观察成立时可无__file__。普通包也核全部搜索位置。目录逐项有界，超16项固定拒绝，不先无界收集。固定码拒外部位置、前缀碰撞、缺spec/name错误、空/None/不一致搜索目录及无效路径，异常不含实际源路径或内容。

formal唯一根是固定Core lib/python3.11/site-packages，并核当前sys.prefix/sysconfig位置一致；local来自实际运行解释器的sys.prefix/sysconfig默认purelib/platlib，caller的candidate字段不能重定向根。正式根正反例使用替身常量与临时目录，**不是实际Linux观察**。旧真实本机runtime-only链通过，local的admissible_linux仍false；没有升级formal身份或新增收据字段，返回的原七项名单不变。

helper在runtime顶层导入，worker prepend candidate前就绑定controller tools路径。原Core来源检查优先，旧外部Core反例保持原码/原断言；静态AST证明dependencies/runtime_capability完全未变，旧App纯/PG两个测试文件字节原样。严格Ruff/格式、AST400/60/120与diff通过：helper93行、runtime114行、support30行、新test251行，最长函数34行。

## 原始证据

任务私有目录：`C:/Users/Administrator/Documents/Codex/2026-10-17/v4-ai-claude-c-users-administrator-4/private/b1-runtime-import-origins-20261021/`。JUnit自动时间戳原样为主机Tokyo +09，公开记录与metadata统一北京+08；未改原件。

| 原件 | bytes | SHA-256 |
| --- | ---: | --- |
| red-1.log | 749 | ee622e1f1d8f8c8889d80f1aa5464acd14f86d7ebb7b5c646a20f48c657ceaff |
| red-1.xml | 756 | f6636902c4efb3d44a6c5c595b44e5d886650a42474553ebb32f6d722bb95276 |
| red-1.json | 929 | 323551139763a7aadef88586c4df19b5fcee191e44749f7f96c046bb4210a277 |
| models-1.log | 101 | 00431d91ffc82b23d691d628db6d8672eae6bc082fe030547ee9b7166ff6710e |
| models-1.xml | 5791 | 3c55d1eeb3b8cdb51cd7f51caa6cf703487ff32e9783abfd028ececb5530e307 |
| models-1.json | 855 | 3e8102a1e4921dc7bedd46c98d5a8893254e7b9e8fe89c396b372b35e3a804c9 |
| app-1.log | 101 | 5546de151fc1da4e82dc1a320fc404b09b450d48cc16971399e78930da0d48af |
| app-1.xml | 5914 | f95c69c658b210b095b1f64baea0c093ac481e4c5e7f716a2b2a11f6363cee3b |
| app-1.json | 879 | fd97415194b909965307316f5a3bf52dccadf6f15fd5dfddd2d686afe0328d88 |

定向命令为新test_b1_runtime_import_origins.py和旧test_b1_linux_application_contracts.py两个文件，完整参数/起止时间保留metadata。剥离供应商、PG、能力环境与关闭追踪/飞书，无凭据、完整DSN、库内容或私密原话日志。只读设计时仅核本机六个既有文件的存在性；测试合成源码未被导入，旧实际解释器对照按既有契约导入已装依赖。

## 实际限制

这是**执行后位置诊断**：导入或.pth顶层代码可能已经执行；恶意模块可伪造__file__/spec，位置/版本检查不验证wheel字节、安装来源、所有传递导入、stdlib或共享库。本片没有真实Linux、真实symlink/链接循环或特殊loader的独立实测，formal模型不作Linuxproof。默认plan无新扫描，零PG、服务器、真实模型、飞书或外网请求。B1正式 **No-Go不变**。
