# 运行中“本轮别记”的长期副作用闸门

记录：2026-10-21 00:58 +08:00（北京时间）。仅本机隔离 PG 与脚本模型，真实模型、服务器、飞书调用均为 0。

工具执行前从 PG 重读隐私控制收据，owner 事务锁跨越检查与实际副作用，防止旧 run 快照、重试及飞书延迟 flush 绕过。封锁 memory_write/update、note_write、profile_update_request、case 写、followup/reminder，以及会持久化依据的 chart/tarot 操作；读取、澄清和已授权 memory_forget 仍由既有权限校验负责。

拒绝由真实 mutation_request 记录仅状态/指纹的 stopped 回执，满足最终提交的持久证明要求。已有真实操作回执按原状态重读，不能把已经保存的事实谎报为未保存，也不自动删除历史。

三项真实 PG Runtime E2E：模型 I/O 期间用户说“本轮别记”，控制原话先路由到无痕线程，旧轮随后分别尝试 memory_write、note_write、set_reminder，均未产生事实/笔记/提醒，最终 core4 正常完成并带真实 stopped 回执。3 passed /2.09s。首轮发现无持久证明的口头 stopped 回执会被提交闸门正确拒绝，现已修正；未放松提交校验。

规则/入站的107项与 API 桥的24项另见各自证据；本文件三项不可冒算到它们的测试计数。真实部署和最终精确头全量仍待验证。
