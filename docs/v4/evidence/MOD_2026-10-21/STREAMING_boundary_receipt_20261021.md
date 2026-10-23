# MOD 流式边界储备阶段回执

- 分支 / 最后提交：工作归属 `v4/mod-organize`，本子任务未执行 Git；由 root 独立提交，PR #10 保持草稿。
- ExecPlan：`docs/v4/execplans/MOD_streaming_boundary_20261021.md`。

## 完成了什么

- 新增 131 项独立验收：损坏 SSE、公开事件身份、历史信封只读、严格时钟与缓冲恢复、
  修订 generation、终止状态、清理证明、失真数据库行、游标隔离和同操作竞争。
- 重放按 owner/run 隔离，seq 空洞合法，重复操作不消耗新序号；覆盖 X08 的离线核心行为。
- 清理只输出计划，24 小时从提交计算，不能扩大到 final/reset 或其他 owner/run。
- 单进程新增目标 131 passed/0.22s；全流式 suite 597 passed/2.32s。
- 4 个新 Python 文件 Ruff、format、函数类型标注和文件/函数大小 AST 检查通过。

## 评测分数

仅 20 个 `mingjing_core/streaming/*.py`，08:59:39–08:59:43 北京时间测量：

| 口径 | 覆盖/总数 | 比例 |
| --- | --- | --- |
| 行 | 855/859 | 99.5343% |
| 分支 | 240/244 | 98.3607% |
| 行与分支综合 | 1095/1103 | 99.2747% |

历史 DAY 同范围为行 93.7136%、分支 80.3279%、综合 90.7525%；旧报告保留不覆盖。
本轮源码、完整本套件测试和样例前后 SHA 全相等。没有模型实测，真实调用为 0。
证据 `STREAMING_boundary_coverage_20261021.json` SHA-256：
`f694ccef9ade8da4223f7c187bda66718f73b0ccca31583116308db602c25732`。

## 改了哪些关键文件

仅新增 `coverage_support_acceptance_mod.py` 及 `test_codec_coverage_acceptance_mod.py`、
`test_state_coverage_acceptance_mod.py`、`test_store_coverage_acceptance_mod.py`，位于 `tests/v4/streaming/`。
另新增本计划与证据；原产品、契约、测试、黄金材料未改。

## 数据库迁移与回滚方式

无迁移，无运行态写入。PG 测试使用注入行/事务端口，不连接数据库；删去本轮新增文件即可撤回测试补充。

## 偏离设计的地方

无产品行为偏离。首轮 9 failed/121 passed/2 setup/teardown errors 属新增测试接入：
机器码错误地匹配公开中文异常文本、巨大参数默认 ID 导致 Windows 下测试生命周期报错。
改用 `reason_code` 属性和显式短 ID 后通过；没有放松拒绝行为或更改原真值。
首轮“132”是结果事件相加，独立用例始终为 131：121 passed + 9 failed 是 130 个执行 call
的用例，另 1 个超长 ID 用例在 setup、teardown 各报 ERROR，造成结果事件总和 132。
修正后该用例实际执行并通过，最终 131 passed；没有删除或合并用例、参数或保护断言。
完整巨大错误输出未保留，因此原文“临时路径超长”的具体归因撤回；只记录已知的超长 nodeid
生命周期问题。本机 pytest runner 的 setup/teardown 均会写入完整 `PYTEST_CURRENT_TEST`。

## 未验证 / 已知风险

不证明真实 PG 事务、跨进程序号竞争、HTTP 授权、代理续连或浏览器显示。
仍未执行四条拒绝分支：重复提问选项 ID、重复决策选项 ID、`validation.valid=false`，
以及受严格 +08 格式正则先行约束的二次 offset 检查。覆盖文件内保留全部 missing_lines/branches。
没有读取 Q5 B 或校准 75 条正文，没有网络、模型、通知、业务或运行态写入。

## 需要用户或大脑决定的问题

无。本轮没有新增产品接口，不需要主线接线。

## 建议后续

主线真实接线时继续验证 PG 原子事务与 owner/run 授权，浏览器层核对 Last-Event-ID 先补后随及断线恢复；
不得把本轮替身和进程内线程测试当作这些部署证明。
