# MetadataGit原生读取观测：不放行覆盖采样

北京时间2026-10-21 11:07:04.655963至11:07:04.748778，root独占执行；协作者全部冻结。
实际Windows Job cap4包含协调器及全部后代，不允许breakaway。
本轮没有改变MetadataGit、supervisor、collector、默认命令或创建标志。

## 实际执行

直接调用现有MetadataGit构造器的两次配置定位和一次HEAD读取：
`rev-parse --git-dir`、`rev-parse --git-common-dir`、`rev-parse HEAD`。
保留原生Popen句柄，逐个核PID、创建FILETIME、IsProcessInJob、实际映像和文件SHA。
三次直接映像均为本机 `C:/Program Files/Git/cmd/git.exe`，原CREATE_NO_WINDOW不变。
实际HEAD为b9f07426cac3de993b0552c3a43eddcf75b2d06f。

实际传给每个Git的环境中，五个Python身份键均不存在；不记录任何任意环境值。
Git二进制SHA和配置文件摘要保持，目标执行阶段及非白名单status读取均先拒绝，
这两负例未增加直接调用或Job累计进程。没有执行pytest target、collector或trace。

## 尚未识别的成员

Job累计由total5增加到14，**本阶段累计新增9个进程**；仅三次直接Git保留了可核句柄，
因此还存在6个本探针未识别的成员。不按名字或进程数推测它们是Git relay或conhost，
也不把早前另一次conhost观测回填为这些PID的身份。

阶段读取结束及负例后active仍为2，表明报告时除协调器还有成员未退出；
外层验证harness正常收尾时已active1。没有证明完整生命周期或瞬时实际峰值；
硬上限只证明并行不会超过4，累计9不等于同时9。
**strict_transport_accepted=false**，旧A/B total1门槛不放宽。

下一步须以本Job的事件/PID来源保留其余成员身份并区分元数据阶段与target阶段；
不能凭三次读取成功，把整个collector链认定为已验证。当前实际supervisor、collector、
baseline/trace和Charts覆盖采样仍为0。本地原生MetadataGit有限观测为3次，和旧消费者替身测试分开。

## 契约说明补充

本轮只补两处既有API表现：

- 黄历文档的day JSON是Charts函数参数；Core的P8ChartAdapter.almanac参数为date，不可直接解包day。
- window_*细码只由Charts纯函数抛出，Core本地归属/有限JSON先验与worker统一chart_engine_failure另分；不得解析stderr作业务控制。

没有改计算、版本、Schema、旧v3或样例。两份新文档摘要将在随后11:15–29完整回归中固定，
先前387定向仍绑定77353，不冒称它已经测试新文档。

## 依据

- [原生JSON观测](week-oct21-native-metadata-git-probe.json)
- [外层过程收据](week-oct21-native-metadata-git-process.json)
- [私有探针源码归档](week-oct21-native-metadata-git-probe-source.txt)
- [有界harness源码归档](week-oct21-native-metadata-git-harness-source.txt)
- [既有transport静态设计](week-oct21-detached-transport-design.md)

11:09按真实77353提交重建的静态自身范围为246文件/27424可执行行、449源守卫、旧10结转、
排除202、删除0；Core/Charts计划仍execution_approved=false、coverage_collected=false。
这不是覆盖率、专业预测效度或部署验收。本轮项目服务器、真实模型和飞书请求均0。
