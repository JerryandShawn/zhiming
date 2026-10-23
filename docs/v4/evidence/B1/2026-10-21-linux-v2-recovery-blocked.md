# 指令板 v2：两次非破坏性环境尝试（仍 No-Go）

2026-10-21，北京时间。08:30:07完整读取30号复核，明确“结论：No-Go”；31号文件不存在。随后完整读取指令板v2（08:16写入），按其队首补齐B1；没有建立SSH或连接任何stage/生产服务。

## 两次尝试

| 次数 | 实际操作与时间 | 实际结果 |
| --- | --- | --- |
| 1 | 08:31:36隐藏正常启动已安装Docker Desktop；08:32:39起用独立20秒上限读取Server版本 | 客户端超时，stdout/stderr均空；没有取得Linux daemon或PG15身份 |
| 2 | 08:33:36对既有salad-enterprise-linux只请求`uname -sr` | 退出4294967295，`Wsl/Service/CreateInstance/MountDisk/HCS/E_ACCESSDENIED`，未进入Linux shell |

第二次输出为Windows UTF-16文本，私有探测脚本误按UTF-8解码，中文显示损坏；英文错误码在去NUL后可确认。保留原诊断JSON，不补造完整错误译文或为重新编码再启动第三次。私有探测记录位于本聊天工作目录的`private/b1-v2-environment/`；公开只保留操作、安全元数据及已辨认错误码，不复制环境变量。

08:33:52只读观察到Docker Desktop/backend进程及Linux引擎pipe存在；**进程或pipe存在不等于daemon健康**，没有把它记为成功。没有第三次恢复尝试，也未停止任何服务或他线测试库；本次普通启动的Desktop保持当时状态，不强杀后台。

## 待用户与后续

需要用户回家在本机检查Docker Desktop启动诊断及既有WSL虚拟磁盘访问问题。若处理需要Reset、删除容器/卷/镜像、修改ACL/全局权限或wsl shutdown，由用户另行决定；主线不会自动执行。现有本机Windows隔离PG继续保留，不能把其测试称为Linux容器演练。

已执行指令板v2的No-Go闸门与队列调整；环境尝试达到两次上限，后续不空等。切到第4项恢复proof生成器和第5项B6 SQL/unit/env/出站隔离文本；二者可先做Windows PG/契约或静态检查，实际Linux门仍不解除。不得创建声称通过的`2026-10-21-linux-actual.json`，不得手填restore proof的true字段。

固定发布仍b9a89b6、只0005–0007；0008另轨。生产Native restore按v2排在stage之后，在31号复核前解除，不能混成stage专属阻塞。stage目前仍因真实Linux演练、B3 proof和B6可执行细节未齐而No-Go。

服务器/SSH、真实模型、飞书发送、主干合并、删除/重置/ACL修改均0。没有拉镜像、创建容器/卷或运行B1真实Linux演练。
