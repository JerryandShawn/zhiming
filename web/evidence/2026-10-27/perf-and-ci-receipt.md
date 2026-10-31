# P10 局部阶段回执：轻量消息与塔罗CI修复
- 分支 / 受测提交：v4/p10-frontend @ 1848f52bb5a8c19036f06b0e3d8ea79e4fa3090d；PR #6继续Draft。
- ExecPlan：web/ExecPlan_resume_2026-10-27.md。
## 完成了什么
- [x] 原消息气泡抽为轻模块，原Messages导出不变，功能区无需为气泡加载Markdown/示例Composer；无视觉改写。
- [x] 塔罗模拟测试补齐两份仓库SVG，其他/static拒绝；默认截图写ignored独立目录，不覆盖历史证据。
- [x] 性能工具记录课程ready/FCP/LCP元素类别与资源时序；单冷诊断明确p75=null、passed=false，不冒充五冷验收。
- [ ] 课程干净头五冷p75 5020ms、旧页2572ms均未过2500。
## 评测分数
16:41合法窗口全量1291/1291单测、121/121默认浏览器；14目标浏览器30图与原提交逐字节相同，Axe0、朱砂≤3。塔罗4/4两尺寸原行为通过，另2/2默认输出验证；10最终图。不是六套完整CI或历史第三遍稳定性。真实模型0。
## 改了哪些关键文件
components/MessageBubbles.tsx、Messages.tsx、spaces/ChatPreview.tsx；scripts/measure-legacy-lcp.mjs；两个night-tarot测试。
## 数据库迁移与回滚方式
无迁移。恢复本线提交并重建，交主线审查，不操作服务器。
## 偏离设计的地方
无默认字体变更；optional实验无收益已撤回，保留实验源码/结果，08§3 swap与字体二进制不变。原console/GET/不重抽/迟到隔离断言不删。
## 未验证 / 已知风险
课程新五冷5084/4964/5004/5012/5020，p75较5260改善240ms但未达标；课程ready约6.3秒。3fd远端Core绿、frontend取消前存在4塔罗fixture失败，不能仅归因预算。本地修复不等于新CI已绿；六套513项仍需完整CI。/v4和真实API/PG/飞书未验，稳定性仍2/3。
## 需要用户或大脑决定的问题
日报首段请求大脑协调主线把CI15分钟时限提高到25分钟或拆任务，.github超本线文件范围。本线不停工、不等用户。
## 建议后续
核精确头CI；继续静态基址、主线新API与剩余关键路径，保持本地合成验证。

证据：bubbles-and-tarot-checks.json、bubbles-clean-summary.json、courses-performance/1848f52b-clean/、tarot-ci-repair-final/。原30张课程图在courses-final/，重复图转ignored不重复计数。
