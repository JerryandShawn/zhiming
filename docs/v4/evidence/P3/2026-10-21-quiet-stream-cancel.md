# Quiet HTTP 流取消候选

时间：2026-10-21 07:47 北京时间。只用本机 Windows 的真实回环 HTTP、隔离 PG15 和合成输入；无服务器、真实供应商或飞书请求。不是 Linux 通过证明。

失败事实：P6 #11 精确 head `bcc3a2e8282b0a28f0227dc568a0738140578d87`、Actions run 39466824123/job 118780269824，Core/Frontend 步骤成功，v4 失败2项。首个失败已收到真实首片段，位于 `test_dispatcher_http.py:144` 的取消后两秒等待，不能描述成启动夹具慢。另 X04 实际取消评分失败。该次 1626 passed、2 failed、2 warnings；P3/P6 对应传输、dispatcher、测试和 X04 driver 代码一致，合并新 P3 本身不会改变旧取消实现。

已核锁定源码：httpx 0.28.1 的 HTTPTransport 原样传递 httpcore extensions；httpcore 1.0.9 的 HTTP11 响应提供 network_stream，SyncStream.get_extra_info('socket') 返回实际连接，read 直接 recv，close 仅 socket.close。P1b 独立树的同名 transport 也未 shutdown，本片未改该树。

候选只在取消或总期限触发时先对当前响应连接 shutdown(SHUT_RDWR)，再 close。外层 client watcher 也先 shutdown 当前 active response，避免它抢先 close 后另一 watcher 已无法唤醒被阻塞的 read。正常完成保留普通 close；没有 network_stream 的 MockTransport/Closable 保持原 close；预期 socket/metadata 关闭异常不输出正文。没有修改取消期限、重试/模型请求预算、供应商配置或 PG 状态契约。

本机验证：

- 新 `test_socket_cancellation.py` 的14项以及原 stream_safety/protocols 合计 **59 passed / 1.25s**。覆盖 socket shutdown→client close→response close 顺序、cancel/deadline、无扩展、正常完成不 shutdown、metadata/已关闭 socket 的安全处理、两个 watcher，以及真实 quiet HTTP 在服务端尚未放行下一字节前取消；仍要求<2秒、ModelCancelled、只1个回环请求。
- 原真实 PG/quiet HTTP 取消、续租和 X04 单例 **3 passed / 3.17s**。原取消后2秒内 PG cancelled 与 interrupted 正文断言不变，未放宽计时。
- ruff E/F/I/B/UP/SIM、120列 format、diff check 通过；transport 306行、新测试184行，函数均≤60行。

首次运行仅遇到新测试包的相对导入收集错误，改用现有 agent 测试包 quiet fixture 的绝对导入后完成上述目标；没有改生产逻辑或旧断言来迁就该错误。

未验证：本机 Linux 环境不可用，静态候选仍必须由精确提交的 GitHub Linux CI 验证；收到响应头之前的真实系统网络读取仍走原 client.close，本片不扩大到所有连接阶段的跨平台两秒结论。P1b 后续 integration 冲突解决必须保留其中央守卫、permit释放、错误分类、请求体积和重试保护，本片不能覆盖这些功能。
