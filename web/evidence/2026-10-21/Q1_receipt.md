# 主队列1回执：冻结事件契约v1

按28第三节新增严格WireEventV1：12类事件，共同v/run_id/seq/+08:00时间，状态phase、稳定call_id、四态记忆、review、2–4决策及unknowns、text_reset revision、心跳注释。显式非法版本不降级；旧无版本v3/core3及历史core4独立兼容。core4历史投影补决策和复核，出生原值继续过滤。

演示流已去临时review flag，使用实际review事件；问卡用askId/optionIds绑定回执，多选显式确认，已回答只读。错ID/错选项/错正文和跨轮迟到ack不能把父状态锁为已答或清草稿。记忆rejected/undone只读，晚saved不复活；模拟端口只为v1的显式sensitive回执补自身CAS上下文，旧缺类别不能自动扩大同类保存权限。

Q1_checks记录最终真实计数、源/构建/PNG指纹。定向111单测（9文件）、6浏览器、11截图通过，Axe0/朱砂≤3/API与外域0；类型、lint、构建通过。浏览器390/1440浅深+修订/恢复。全量回归尚未运行，按错峰在23:30–23:45开始。

Schema在本次fetch的origin/v4/p3-agent-runtime@dc574aa尚未发布，依28实现；不冒充已与JSON Schema验证，稍后重查并补契约对照。现有withReviewPending只保留旧读取测试兼容，正式演示不再通过临时参数驱动复核。

日志、Vitest及Playwright显式Asia/Shanghai，单测≤4、浏览器≤2。无迁移、真实数据写入、真实模型或服务器操作，回退本项前端提交重建即可。后端缺失端口仍模拟，PR #6保持草稿。下一项为整理变更集审阅。
