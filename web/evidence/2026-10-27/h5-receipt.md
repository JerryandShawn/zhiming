# P10 局部回执：独立 H5 假服务预览

- 分支：v4/p10-frontend；功能候选fdf6db25、gzip交付候选d32c8eee，PR #6保持Draft，不合并。
- ExecPlan：web/ExecPlan_resume_2026-10-27.md。
- [x] `?embed=demo`明确独立：假端口与内存会话，不接AuthGate/token/cookie/SDK/真实API。授权→交换、拒绝/超时/取消/迟到/过期/退出、一次性code、草稿保留和刷新清空。
- [x] 80/80相关单测、14/14目标浏览器；四尺寸×双主题24状态图，另7失败/键盘/返回/退出图；Axe全规则0、朱砂≤3、无横溢出，API/外域/模型0。类型、全量lint和构建通过。首轮tsc的mock泛型已修，未改行为断言；首轮13绿报告另存，图片只计最终31。
- [x] H5本机gzip交付五冷1868/1816/1796/1808/1816ms，p75 1816，全<2500；Node22/390×844/DPR2/4G150ms/200000Bps/CPU4。原未压缩p75 3660失败保留。310原始构建文件SHA不变；93 gzip副本精确解压含最终SW，fonts.css 187451→62719B。源/构建/工具快照稳定，不能称用户设备或生产收益。
- [x] 294807b1在10:30窗口全量1264单测（104文件）和默认CI浏览器109首轮全绿，失败/flaky/跳过0；本批旧页20图另存，首批失败证据已恢复保护。后续仅测试默认输出路径改到ignored目录，3定向浏览器/类型/lint绿，不改断言。
- [ ] 当前头CI另查；不是全部浏览器套件/PG验收或历史第三轮，旧稳定性仍2/3。真实P4/测试库缺角色仍阻塞，旧页性能失败仍未解决。

关键文件：embed/H5Demo、demoSignIn、fakeSignInPort；compression.plugin；App显式懒加载入口；h5-demo与compressed-assets测试。静态gzip配置仅建议，服务器未改，零新依赖/迁移。回滚对应前端提交并重建；原资源/旧登录不变。

未验：真实飞书身份、一次性code后端交换/Origin/CSRF/cookie、SDK、真机返回手势、已登录今日页性能、部署。下一按P8 meta v5整包接20课及P10剩余队列；不等待用户。证据：h5-demo-first/、h5-performance/两批报告及comparison.json、H5_demo_integration.md与Static_delivery_notes.md。
