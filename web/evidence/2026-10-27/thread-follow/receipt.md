# P10 局部回执：线程 C1 内存订阅

- 分支：v4/p10-frontend；PR #6保持草稿，未合并/部署。
- ExecPlan：web/ExecPlan_resume_2026-10-27.md；已执行指令板v5。

## 完成了什么

- [x] 严格冻结事件和同run/id/seq，允许撤销后的序号缺口，重复去重，消费成功后推进内存游标，resumed全文交消费者替换。
- [x] 显式GET、Last-Event-ID、45秒空闲和ping；断线/5xx有界重连，401/403/坏协议终止，422返回needs_state。已结束的幂等202先回查，不从零重放。
- [x] 归属/abort/迟到释放、异步consumer成功门、consumer失败不重放、无浏览器存储；原连续follower和断言不变。
- [x] 26新单测、1新真实本机HTTP提交→断线→续传检查；连A/B及原回归156/156，失败/跳过0，含2个HTTP检查。类型、定向lint、生产构建通过。
- [x] 416构建文件逐项SHA一致；沿用courses-final/旧页已提交截图，不虚增视觉/Axe/LCP或浏览器验收数字。
- [ ] GET持久状态、HTTP权威停止、epoch恢复、页面与真实PG：下一C2/C3。

## 评测分数

局部目标156/156。未重跑完整前端或v4评测；真实模型请求0。HTTP是假后端在本机临时端口，不是HTTP+PG或服务器联调。

## 关键文件

src/threads/follow.ts、tests/thread-follow.test.ts、tests/thread-http.test.ts。检查与源摘要见checks.json，逐项断言见assertions.json。首批151通过，随后加5项终态门得到156；汇总脚本初始误估153后纠正，无产品测试失败或原断言改动。

## 迁移与回滚

无迁移；新端口尚无普通页面引用，回退本片文件并重建即可。不操作数据库、Docker或服务器。

## 偏离设计

无；P3递增序号用独立端口，与原演示连续策略并存。

## 未验证 / 已知风险

仅可用于新执行的内存投影。retry epoch起点未公开，不能清零重放旧error；needs_state尚待C2调用权威GET。未接普通UI、真实PG、Feishu或部署。CI另待，旧页2572/课程5020ms仍未过2500。

## 需要大脑决定的问题

CI预算已由v5/R47裁定交主线先25分钟、再必要时拆job，本线不改.github。R41归属仍待主线，不改Docker。

## 建议后续

接C2的GET状态与HTTP取消确认、C3的owner投影控制器，然后做页面和浏览器联调；保留模拟端口用于测试。
