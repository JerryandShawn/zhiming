# B1 publication 离线切片

记录时刻：2026-10-20 23:10 +08:00。**结论：离线控制流可复现；B1仍No-Go。** 本机Linux不可用，生产restore-to-new-DB、最新撤销/收据重放、旧包重绑定与门内核验尚无完整受审入口；Native verify/open/rollback均硬拒绝`NATIVE_PRODUCTION_RESTORE_UNAVAILABLE`。不能手填proof布尔值来解除，更不能拿下列19项替身/临时文件测试当Linux或生产通过。

## 范围与已做事项

新增`tools/b1_publication.py`、`b1_publication_contracts.py`、`b1_publication_native.py`、`b1_publication_pg.py`，不改固定b9发布包。默认`--action verify|open|rollback --plan <JSON>`只校验输入，不构造Native、不连接PG、不发HTTP。显式应用额外要求`--apply --native --approval <0600> --output <新0600>`；31原文/字节hash、用户本人“上线”引用、提前12小时/工作日10–13/北京时间+08:00、plan/action/工具依赖hash都须匹配，不能用approval参数代替授权。

可移植控制器的开门顺序是Web门内启动/健康→重核fence/队列/文件→重核当前时刻→首次Web移门记时→按维护前active/enabled恢复后台→最终健康。它明确非原子，31需额外接受`web_then_background`。报告timer为Persistent、每分钟触发，恢复后台可能恢复正常业务；控制器直接调用为0模型/0外发不代表后台业务流量为0。任意中间失败、取消或最终回执写盘失败都重设维护门并停全部writer。Web健康仅回环、禁代理/重定向，不执行唯一真实冒烟。

新Native边界拟检查准确主机/root、受保护文件与完整b9 manifest、有效unit状态、模型/CHART_PYTHON、原退役stub/备份链；Web启动后用MainPID及子进程socket inode映射PG client_port，拒绝未知writer。**这些系统级路径未真实Linux测试，且生产恢复硬门使实际开门不可达。** 可移植rollback只覆盖外部已恢复schema4之后的配置回退协议，返回保持关闭，不假装已经恢复数据库或重开业务。

## 实际验证

清除该测试子进程所有KEY/TOKEN/SECRET/PASSWORD/PASSWD类环境变量，关闭LANGSMITH/LANGCHAIN/OTEL后运行：

    .venv-core/Scripts/python.exe -m unittest discover -s tests -p 'test_b1_publication*.py' -v
    .venv-core/Scripts/python.exe -m ruff check tools/b1_publication.py tools/b1_publication_contracts.py tools/b1_publication_native.py tools/b1_publication_pg.py tests/test_b1_publication_contracts.py tests/test_b1_publication_boundaries.py

结果：**19 tests passed，0.087秒；Ruff通过。** 包括31 No-Go/变更hash/未审非原子模式、错误scope/action/工具hash、布尔false冒充计数0、时区与12小时提前量、精确文件集合、每个ready维度缺失、跨窗口开门、各阶段失败关门、60分钟配置回退边界、默认CLI零Native构造；另有真实临时文件的门/首次opened记录、记录写失败门不移、最终回执失败回关门、合成proc/socket及PG会话归属反例、错误host与health重定向拒绝。

Windows私有模式检查在CLI写盘失败测试中明确使用替身；临时文件测试只证明文件内容与先后顺序，不证明POSIX0600/0700、fcntl、systemd、PG角色或网络隔离。测试只发合成调用，没有真实模型、真实飞书、服务器访问或合并操作。

工具文件分别139/148/258/52行，函数最大38/21/21/28行，最长行均≤120；新测试文件也符合≤400/函数≤60/宽≤120。当前publication controller hash同时绑定4个新工具与所有`core_incremental*.py`依赖；以实际候选时现场计算为准，不把本文件硬编码hash当永久授权。

## 未完成与后续

1. Linux真实PG15恢复、0600/0700、fcntl、三unit/timer、wrapper跨exec、实际`/proc`会话归属及故障注入，仍阻塞。
2. 生产受审restore-to-new-live-DB入口、最新撤销/sent/uncertain单调重放、旧schema4兼容与精确配置重绑定，仍阻塞；Native不能开门。
3. `web_then_background`非原子偏离及timer恢复风险须大脑写入31明确复核；没有31 Go和原授权条件不碰生产。
4. stage B7另有Windows PG15.19真实对照证据，不替代Linux；只允许stage恢复副本，不能给生产回滚套用。
