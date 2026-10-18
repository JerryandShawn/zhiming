# P2 冻结代码验证

冻结本地实现de082ce1e6af37a706eee6a4596b09d1b6ca49e3，树c25f3951743469702e2539b62379227713da4dca；远端等价提交cc1187e95f3f292c56985c99dac859420af63fcb，代码树已核对相同。后续只补证据，不修改源码。

环境：Python3.11.16、PG15.19、Node22.23.3；本线独立venv，Charts只读复用。所有PG均回环127.0.0.1:55480的本线专用测试库/唯一schema，不连接stage/live。子进程清空KIMI_API_KEY/MOONSHOT_API_KEY；真实模型/飞书调用0。

| 检查 | 实际结果 |
|---|---|
| 最终完整旧Core discovery | **Ran553 tests in826.169s，OK，exit0**；专用core_test_p2_verified，无失败/错误/skip |
| 最终全部v4 | **379 passed,1 warning in159.87s**，core_test_p2_v4；含129项本线新增，无skip |
| 旧前端 | Node22下npm test、dom、report-settings DOM、method-limits DOM、app.js语法、build，6项全部通过 |
| scripted80 +self-test | 80/80；self-test48 passed17.42s，冻结de082ce上执行，报告同目录 |
| 新代码静态/格式 | 32个新模块/辅助文件Ruff E/F/I/B/UP/SIM与format120通过；参数/返回注解缺失0，每文件≤400行、每函数≤60行 |
| 10000消息snapshot | 100样本/10预热，p50=3.714ms，p95=4.155ms，max=4.896ms；最新09999/早期约束保留 |
| 新依赖哈希 | --require-hashes安装/核对64包；原版本不漂移；仅新增lunar-python1.4.8/jieba0.42.1 |
| 最终远端CI | cc1187e的[run39051908909](https://github.com/JerryandShawn/zhiming/actions/runs/39051908909)最后核对为in_progress；首里程碑远端9661376的CI通过不代表最新实现通过 |

## 首轮失败及真实修复

首轮完整553执行949.569s，**7 failures、6 errors**，未记为成功。后续修复未更改035/decision_guarantee/repair_recovery断言：

- 两项背景quote以句号结束时误吃下一句问号：修实现硬句界，补逗号条件、尾空白/闭引号、完整原文引用掩码，防止修误伤同时给转述病历授权。最终策略56项通过；原035四项17.651s、decision_guarantee三项8.870s通过。
- 四项历史顺序测试只调整了run.updated_at，P2成功助手另有权威message.at：只同步合成fixture的助手at/at_ms，原排序/分页/scope断言不变。
- 一项proposal重放消息数：精确核对用户原文+真实助手，仍一个fact/两模型调用。
- 一项无效旧时间接收：保留原at文本，元数据用同PG事务now()，与created_at回退一致，原history与新PG均通过。
- 五个repair恢复errors（含standard/deep subTest）：now微秒漂移改变完整repair_identity；按epoch持久Clock.now，严格hash/预算不变。原repair11项9.453s通过，新PG推进1天+1微秒两项4.15s通过。

历史+proposal原模块共13项15.143s通过。首轮之后另启动过一个仍缺已知修复的替代进程（85c48a3快照），按root指示中止并保留私有日志；它没有完整结果，也不计成功。随后9d15752进行了第二次完整553，完成但仍失败，详见下节；最终de082ce是再下一次完整回归，结果单列上表。

## 第二次完整回归与安全元数据修复

9d15752第二次完整553执行839.975s，3 failures/4 errors，同样不计成功。4 errors由program_time普通put额外增owner revision改变native claim ID导致，显式selection.date固定，排除午夜假设；3 failures为intake取消/过期前时间行提前持久化影响0steps契约。保持原fixture/精确ID/取消断言，改为固定stage专用元数据写且不增语义revision，并在本次_call安全diagnostic同事务才落锚点。

最终定向：原native+取消/失败诊断+repair17 tests通过22.630s；PG13通过11.78s，涵盖首intake已计费四类失败后推进Clock恢复、取消/过期0steps、semantic revision不变与普通put仍增，以及lease/epoch/owner/ISO拒绝。独立真实_call AST九边界0失败；详见repair-time.md。

阶段期间有一个被后续已知修复取代的回归进程被明确中止，未记为成功。最终冻结de082ce完整新一轮553已于826.169s全部通过，exit0；以上历史失败/中止轮单独保留，不计入最终通过数。

## 现有测试契约更新

只有schema版本（4→7）、两个成功消息计数（精确两角色）、历史合成fixture时刻、P0 brief成功助手五个文件调整；所有来源、授权、篡改拒绝、只读、幂等、预算、分页和送达保护保留。逐文件理由见receipt.md/ExecPlan。

## 证据范围

scripted和provider替身用于确定性功能/集成验证，不代表真实v3回答成绩。S01只验证固定配置进入模型接口，真实危机模型回答待大脑安排；T/R/M真实比较未跑，没有生成P2实测分数。未执行stage/生产操作或真实Feishu。API历史扫描候选及全部run元数据的性能边界、P1 rebase哈希锁冲突详见receipt.md。
