# P1b 人工 scope、收据与 D2 默认路由第三切片

记录：2026-10-21 00:00 +08:00（北京时间）；本机隔离 PG15 + HTTP 替身，真实供应商/SSH/飞书均0。root统一提交推送，PR9保持草稿。

## 可审查结果

`tools.member_start` 仍要求真实本机TTY逐批输入完整句；收据现在 exclusive 创建，POSIX0600，Windows在写入能力ID之前移除继承并仅授当前用户/SYSTEM显式DACL，flush/fsync。父目录必须真实存在且不是解析到别处的路径，记录其位置与ACL摘要（不输出ACL正文）。不创建父目录、不覆盖旧收据。PG授权创建后任何写盘失败，明确返回 `GRANT_CREATED_RECEIPT_WRITE_FAILED`、batch_id/到期时间及需人工收口/到期，不隐瞒为“未授权”，也不自动重开。

`tools.manual_grant.load_manual_grant(path, suite, scenario_ids)` 只读已发收据，核严格schema/有效期/suite/场景子集/最多10个/automatic_next_batch=false；`.scope(id)` 给可信调用方已有batch/auth元数据。最终PG每物理POST核授权，文件不是独立的新授权来源。`MEMBER_GRANT_RECEIPT`仅引用已有文件，`MEMBER_EVAL_SUITE=E1/E2`选择已发suite，不能凭环境确认文字发新授权。

评测engine按场景作用域；QuotaGuard包装强制eval/probe lane；目标/评审构造绑定 evaluation/critic。中央guard显式SystemClock，不受场景FrozenClock影响。旧通用probe必须 `--manual-grant`，仅运行收据指定场景，不自动下一批；不再关闭思考，禁止关闭推理的对照不安排真实请求，none/named仍由U39零POST拒绝；完成当前批才调用中央finish_batch，终止错误后不进入兄弟模型。

Registry六个主动角色默认均为k3-256k，设置model_lock、高effort、reasoning_replay和sampling_fixed；删除main的KIMI_MODEL回退，primary不隐式切其他供应商。能力状态policy_locked_unverified，真实效果仍未验证。显式可信探针对比可仅在克隆handle移除model_lock，不修改默认配置。旧冻结E1显式k3、产物及源身份未伪装为256。

## 验证

首组六目标文件58 passed /1.90s，真实PG scope/Windows DACL、写盘失败保留一个PG批次、未授权零POST、失效/多余字段/场景越界负例、D2锁定与旧probe全停均通过。较大models+eval目标回归进行中，完成后另追加准确结果。Ruff E/F/I/B/UP/SIM、120列通过。

首轮误选老主树Core解释器，缺jieba在收集前退出；没有安装依赖。随后改用既有 `zhiming-v4-p2/.venv-core/Scripts/python.exe`。静态工具用既有主树Ruff解释器，两个环境不混称同一运行环境。

## 待续

历史ConfiguredModel的未显式model默认和旧1024 thinking实际物理body须在第四切片收口，不能以“历史”说明替代U39保护；该路径在第二切片已接中央PG，尚未完成规范wire迁移。root独占的≤20次等价脚本有独立证据，不把其结果算作本片测试。未真实调用、未部署、未合并，不能宣称P1b全阶段完成或256实测切换。

## 最终第三切片复验（2026-10-21 00:04 +08:00）

最终具体失败文件加首组为75 passed /14.10s，零skip。之前models+五份eval宽回归1002 passed、1 failed /111.90s：唯一旧subset_v21正例暗依赖默认k3。按D2新默认保留其旧预算、端口绑定、安全DSN断言，并新增默认256必须拒绝历史k3的负例，再用显式历史k3 fixture完成原离线正例；未改冻结基线产物。失败轮不能当全绿。近千项宽回归开始在23:58左右，未遵守北京00–15启动窗口，此流程错误已通知root，后续宽回归一并按窗口，不再用“目标”放宽解释。

静态Ruff指定规则/120列通过；新增Python均<400行，函数≤60。无需依赖安装。模型能力/默认路由为代码配置验证，无真实供应商证据。
