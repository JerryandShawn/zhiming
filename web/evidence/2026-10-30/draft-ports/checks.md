# 整理与研习 draft 端口检查（2026-10-30，北京时间）

- 契约来源：`daccd26c` 的 `api_organize_draft.md` / `api_study_draft.md` 0.1.0；均未冻结、未实现真实后端。
- 整理：严格 proposal、编辑、24 小时审阅、apply/revert 回执投影与内存合成服务；审阅绑定 batch 和精确计划指纹，`record_only` 下 apply 返回 `QUALITY_GATE_CLOSED`，不绕过质量门。
- 研习：独立个人进度 GET/PUT，支持 null/revision 0 初态、课程版本、书签、expected_revision、稳定 request_id 和课程隔离；公共课程内容不可由进度载荷注入。
- `npm test -- tests/organize-http.test.ts tests/study-progress-http.test.ts --maxWorkers=2`：17/17，含真实 loopback HTTP 与合成服务。类型检查、定向 lint、生产构建通过。
- 未接真实 UI/PG；没有新页面视觉变化，因此未新增截图或宣称新的视觉/性能里程碑。
