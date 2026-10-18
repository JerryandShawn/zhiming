# P2 时间引擎里程碑证据

核对时间：2026-10-17 23:04 UTC+08:00；仅使用合成日期，本阶段真实模型/飞书调用 0。

独立 worktree：zhiming-v4-p2，起点 7fa5e10；Python 3.11.16，新建本线 .venv-core。独立 PG 数据库 core_test_p2，只连接 127.0.0.1:55480，不影响 WS1/core_test_p1 或旧回归/core_test。

`python -B -m pytest tests/v4/test_p2_timekit.py -q`：22 passed in 0.57s。覆盖历法附录 13 个日期、晚子时、两个精确交节秒边界、跨时区/跨日、未知年度、离线覆盖优先级、差异导入与重复导入、蓝图此刻块全部字段。2026-10-23 霜降实际时刻为 17:37:57，展示按分钟四舍五入为 17:38；2026-11-07 立冬为 17:52:05，断言没有把整天提前视作交节。

新增时间模块及管理工具通过 Ruff E/F/I/B/UP/SIM，line-length 120 与 formatter。calendar_cn/almanac/now_block 分别为 135/91/142 行，最大函数 21/45/43 行。

Core/Test 锁由原精确版本生成全部发行文件 SHA256，原版本逐项一致。仅新增 lunar-python 1.4.8 与 jieba 0.42.1；Core 锁含 58 个版本、1271 个 SHA256。`uv pip install --require-hashes -r requirements-core.lock -r requirements-test.lock` 在本线环境检查 64 包通过。Charts 环境未修改。

这只是时间引擎首里程碑；数据迁移、线程与回填、完整 v3 接入、全部回归及性能证据尚在进行，不能据此宣称 P2 已验收。真实模型 T/R/M/S 比较与 stage 操作按夜间指令留待授权和大脑安排。
