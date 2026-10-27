# RPF01 公共输入与测量前提补充审查

本次没有重新测量性能，也不推广原收益。产品3源仍为707ed版本，旧18源、Q2/U4、旧baseline
benchmark_reflection_v3/performance工具均未改变。所有记录JSON使用显式UTF-8 LF字节。

## 公共输入结果

09:38:13+08完成31项只读探针，见RPF01_public_input_readonly_probe_20261021.json。
最大有限/最小subnormal浮点、负零、非有限值、正负巨大int、当前十进制位数限制、naive fold0/1、
aware时间UTC转换越界、date上下界、4时区fold0/1均与oracle接受/拒绝及指纹一致。
深度63/64接受、65/66按已记录的更窄规则拒绝；混合tuple/list共享输入被独立复制，修改一个
结果不改输入/另一路/第二个结果；超深错误文本、参数和格式化traceback未含合成原文marker。
暂无新产品反例；有限集合不是穷尽证明，并发修改输入不在公开保证内，深度也不限制超宽图。

## 实际发现与受控修复

原新工具依赖assert证明部分语义/hash一致性，但未拒绝Python优化模式。两个独立进程只把
新工具自己的semantic_capture暂时替换为不同合成结果，没有执行真实链或改冻结产品：
09:38:50普通模式拒绝差异，09:38:52的-O模式却返回成功；四别名及捕获函数均在进程内恢复。
原始结果分别在assert_mode_normal/optimized_readonly_probe JSON；这是测量复现前提缺口，
不能据此称生产授权漏洞或否定09:07正常模式的已观测数据。

root随后明确授权只修新工具。新增导入期的显式sys.flags.optimize检查，在任何Core导入或
工具入口之前拒绝-O/-OO；不改旧baseline工具，不替换旧报告里的观测工具hash。
09:41前新独立subprocess三例通过1.61秒：默认模式仍比较并拒绝注入差异且恢复别名，
-O和-OO在Core加载前明确拒绝。没有运行完整工作负载或性能；原产品自测不重复执行。
见RPF01_measurement_mode_guard_20261021.json及新增test_measurement_mode_core_mod.py。

旧观测工具SHA为3ea3b1fa6b51899a04a056f2164efb92cc6fc659b67b83e1151ffc82a2348089，原字节
先备份为private/mod-week/evidence-originals/benchmark_reflection_projection_RPF01.pre_opt_guard.py。
新工具SHA为3878721ba37c645cd48924973c756931ac65232f4036351b77b81fcb71393e2d；它尚无新的
完整链性能数据，不能把09:07观测说成由新工具生成。此前EOL谱系和原Windows source_sha快照不改。

## 冻结与交接

代码/测试已在09:41前冻结，单目标测试进程已结束；09:44至root通知期间不写产品/测试/fixture。
root独占Git和completed_regression runner；本线不改runner、不访问模型/网络/数据库。
新增3项测试不是全量/CI证明；接线仍不在本任务内。后续只能在有明确测量窗口时再采集新工具
观测，不能补写或外推性能。本审查的授权修复范围仅新benchmark的解释器模式守卫。
