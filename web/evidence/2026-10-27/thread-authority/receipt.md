# P10 局部回执：线程 C2 持久状态与取消

- 分支：v4/p10-frontend @ 50e82f98（受测C2源码）；PR #6仍草稿，未合并/部署；ExecPlan：web/ExecPlan_resume_2026-10-27.md。

## 完成了什么

- [x] GET run按主线27b8公开十字段核验，只投影runId/status/attempts；succeeded终稿严格core4、只读receipts、可选meta绑定同run/operation。内部字段和非终态旧result不读不输出。
- [x] 显式同run cancel，ack不等于停止：核ack后GET持久状态，cancelled才stopped=true，运行/排队仍pending，完成竞态保留终稿。
- [x] 提取原A/B归属安全有界JSON helper；原79检查/断言不改，错误只交安全code/status，无全局登录/自动重发/隐式删除。
- [x] 55新单测+2实际本机合成HTTP，连A/B/C1/原重连旧页R7共213/213，失败/跳过0，含HTTP4项；类型/定向lint/构建通过。
- [x] 416产物SHA逐项完全不变；沿用已有截图，无新增浏览器/Axe/LCP验收数字。
- [ ] C3 owner控制器、retry epoch安全恢复、普通页面、真实HTTP+PG及飞书未接。

## 评测分数

局部213/213。未运行完整前端/v4评测；没有真实模型请求。HTTP是真实本机传输、合成后端，不能称后端业务服务或PG验收。

## 关键文件

threads/authority.ts、request.ts、submit.ts、contracts.ts；thread-authority.test.ts及thread-authority-http.test.ts。摘要/逐项结果见checks.json/assertions.json。数据库允许call_limit=0，已修正本批新增正数断言并补零/越界例；原断言不变。

## 迁移与回滚

无数据库迁移。回退本片适配器与helper抽取并重建；普通入口没有引用，产物不变。不动服务器、Docker或其他工作树。

## 偏离设计

无。C2只做公开端口，尚未实现用户界面“两秒反馈”；后续C3/UI立即显示正在请求停止，等待权威结果。

## 未验证 / 已知风险

C3/epoch恢复/页面/真实PG未验；2MiB状态上限为本机防御边界，不扩大协议。R47已由主线653fbf82实施Ubuntu24.04/25分钟，本线安全同步仅重放本地未发布提交，前端源码diff0；50e82f98精确头两CIqueued，不称绿。旧页2572/课程5020ms仍失败，历史稳定性仍2/3。

## 需要大脑决定的问题

R47已由主线实施，若25分钟仍不足再由主线拆job；R41归属仍待主线。本线不停、不改.github/Docker。

## 建议后续

接C3：owner投影绑定、422状态回查、旧epoch终态防护、停止竞态协调，再接页面并跑浏览器矩阵。
