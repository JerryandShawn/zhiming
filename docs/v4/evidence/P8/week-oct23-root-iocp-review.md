# 原有 Git 元数据调用的独立 Job 观察：有限证据

实际运行时间：2026-10-23 20:57:27，北京时间；源 HEAD 为 c471d4ac89444bcb004e102a8ab026c738c2788c。

## 结果

原 MetadataGit 的三次只读命令、CREATE_NO_WINDOW、环境清理和 communicate/10秒超时均保留。新加的一个观察线程在调用前就绪，结束后先 join 再关句柄；没有新进程承担观察。两项原负例（目标阶段调用、非白名单status）拒绝，调用数保持3。

Job累计 total5→14，即新增9成员；阶段结束 active2，等待收束和观察器关闭后 active1。直接 Popen 的3个实例通过复制其真实句柄固定 PID、FILETIME、Job归属及磁盘映像摘要。另观察到1个 mingw64/bin/git.exe 和3个 conhost.exe 的存活时实例快照；共7个新增实例快照，剩余2个只有晚到事件，身份未知。

这些名字与父PID快照不授权任何进程；IOCP消息与进程世代的绑定始终 false。累计数相等、最终active1和cap4上限都不等于完整生命周期认证或实测峰值。结果 `strict_transport_accepted=false`，实际supervisor、collector、trace和Charts覆盖采样均0。

本轮7个快照属于这一次新执行，不能拿来回填10-21轮的6个未知成员。原生产守卫、旧空Job观察器和数量拒绝门槛均不改。

## 首轮失败与修正

20:57前首轮在 `fingerprints()` 将相对 `__file__` 对绝对仓库根做 `relative_to` 时失败；发生在创建观察器和MetadataGit之前。保留首轮脚本、日志和外层进程回执。只对私有脚本3个路径调用resolve，再以新label运行；后轮输出独立保留，没有删除或覆盖失败原件。

原始报告生产者沿用10-21草稿中预定文件名 `week-oct21-root-iocp-metadata-probe.json`；其中实际开始/结束字段均为10-23 +08:00，文件名不作执行时间依据。

## 文件与校验

- [实际观察报告](week-oct21-root-iocp-metadata-probe.json)
- [首轮脚本](week-oct23-root-iocp-first-driver-source.txt)、[首轮错误日志](week-oct23-root-iocp-first-run.txt)
- [成功轮脚本](week-oct23-root-iocp-driver-source.txt)、[观察线程](week-oct23-root-iocp-observer-source.txt)、[外层约束](week-oct23-root-iocp-harness-source.txt)
- [两轮进程摘要与独立一致性检查](week-oct23-root-iocp-validation.json)

外层Windows Job cap4含协调器及全部后代、无breakaway；协作者在两轮执行前均冻结。两轮项目源快照不变，未改旧v3或计算口径。观察不完整记为阻塞，继续其他工具/契约储备；不为观察求全反复放宽执行许可。

## 另一项只读审校记录

此前协作代理对c471的词典做过定向只读审阅：terms blob f239900ca0afa97d6fe912b07fa920a539c56ce6、sources blob a1ba094b6a63a43894f9daae48dc065341ab0f82。聚焦时间、次限、行运、回归及紫微四化，未发现确定修改项。它不是212词条/全部流派或古籍原刊的全面专业验收；原刊待核继续保留。
