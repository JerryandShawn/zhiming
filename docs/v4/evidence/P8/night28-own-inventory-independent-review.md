# 静态覆盖A：独立10项复核

记录：2026-10-21 01:27（北京时间，UTC+08:00）。
只读审阅作者三模块、底层Git/行表工具及42项作者测试；本子任务只新增
`tests/v4/test_p8_own_inventory_independent.py` 和本报告，没有改作者源码。
先向root提出10项反例并获批准，再等待作者显式确认静态JSON生成进程均退出。
本轮最多1Core+顺序Git1，Charts=0、trace=0，不启动pytest目标收集或覆盖采样。

## 固定历史与原10文件

- 受准起点：`7fa5e10a4dbe0e2878e28c6f6a115f17d013aaa2`。
- cutover仅作分界：`f23b942ce698a3f7ee0b98c918d43053fe773433`，不能替代起点。
- 独立真实历史盘点点：`ef5fed9a3fc4e1b727e6077f5b99f41be31e6f7b`。

独立用Git两段差异的实际路径集合计算“初版已有、后续未改”的10项，
核它们全部属于inventory.files及全源static_source_guards，不只断言某个总数恰好为10：

    mingjing_core/calculations/bazi/__init__.py
    mingjing_core/calculations/bazi/calendar_layers.py
    mingjing_core/calculations/bazi/elements.py
    mingjing_core/calculations/bazi/stars.py
    mingjing_core/calculations/bazi/strength.py
    mingjing_core/calculations/bazi/structure.py
    mingjing_core/calculations/bazi/supplement.py
    tests/v4/test_p8_bazi_rules.py
    tests/v4/test_p8_chart_process.py
    tools/verify_p8_calculators.py

这些文件留在当前分母，不会因f23之后没改而被静默排除。
对固定提交的完整性不能扩张为包括尚未提交的新A文件或整个仓库所有代码。

## 十项实际结果

| 独立保护 | 例数 | 实际结果 |
| --- | ---: | --- |
| 初版10条按实际路径集合及全源guard核对 | 1 | 全部保留 |
| 将已完整盘点的history_base改成f23，再重签inventory SHA | 1 | approved_origin_required，不能以新起点抹掉初版代码 |
| 在受准起点就有、之后从未改过的Python软链接 | 1 | nonregular_source_refused；使用合成Git index mode120000，无需Windows创建真实链接，全树检查不只看changed路径 |
| cat-file返回正确OID/类型/长度头，但内容同长度替换或截断 | 2 | git_blob_content_invalid，两种都不能用头部冒充全blob校验 |
| 范围内先新增再删除Python，最终相对起点净diff无此路径；再重签删除台账为空 | 1 | 历史删除仍在台账，重签删台账被pinned_source_mismatch拒绝 |
| 把静态计划target.start_line改为数值相等的float，再重签 | 1 | pinned_source_mismatch；hash与固定AST重建共同保护，不靠Python数值相等 |
| execution_approved/coverage_collected分别改为整数0，再重签 | 2 | static_state_invalid，0不能充当明确False |
| 白名单候选模块导入即抛异常，额外拦截候选import和pytest.main | 1 | 只做AST计划，未尝试导入/收集候选；保持execution_approved=false、coverage_collected=false、间接效果未证明安全 |

合成Git仓库只建于本线 `private/tmp/own-independent/`，测试中的起点/cutover替换
只作用于相应合成仓库和临时patch上下文；实际历史10项及f23拒绝使用真实固定SHA。
全blob坏响应是专门故障注入，不伪造成功Git元数据或命盘结果。
合成Git命令显式给临时身份、关闭GPG并把hooksPath限定到该夹具自己的空路径，
防用户全局Git钩子产生意外副作用；没有改本工作树Git配置或提交产品代码。

## 实跑证据

执行前清空API_KEY环境、关闭模型追踪。仅运行独立文件：

    python -m pytest -q tests/v4/test_p8_own_inventory_independent.py
    python -m ruff format --check tests/v4/test_p8_own_inventory_independent.py
    python -m ruff check --select E,F,I,B,UP,SIM tests/v4/test_p8_own_inventory_independent.py

最终：**10 passed、0 skipped、5.08秒**；格式与全部指定Ruff规则通过。
测试文件274行，函数≤60行，单行≤120。
首次同10项也已通过；当时本测试有4项样式问题，修短函数名/合并with后再次通过，
随后补临时Git钩子隔离并运行最终10项。重复运行仍是10个独立用例，不计成30项。
没有发现需修改作者三模块的新失败。

本次读取的三个源码UTF-8文本/LF SHA256：

| 模块 | SHA256 |
| --- | --- |
| line_coverage_own_sources.py | cfaacf5ecccf31df111abc824c684ed1d054ec44a767d36d2d195744ced810dd |
| line_coverage_own_inventory.py | 381fb18cf944fc94773955538405229ca12e631bd1dcea5edde5be4d9ec81a87 |
| line_coverage_own_plan.py | 56a885abeaee9f0f9175186d467e2fc66fc4cf4dd881454e03c8f400edbc3b9e |

## 执行和覆盖率边界

- `compile/dis/ast.parse`用于分母与静态定位，不等于执行被测模块。候选的生命周期钩子列入计划，也没有被跳过后假称实际测试通过。
- 静态计划的digest不是执行许可。必须另外取得B1/B2的具体批准、依赖/fixture/进程与采样预算，才可开始下一阶段；本审阅没有授予许可。
- 本次没有trace hits、命中行数、覆盖率百分比或≥90%结论，也没有分支覆盖证据。
- 作者42项的结果与原完整2728属于各自运行；原2728完成在A新增之前，不能借它宣称A已经全量验收。本轮只实际执行独立10项，聚合由root另记。
- 旧manifest/coverage试验的有限选区与本次完整历史盘点是不同版本，不能混合分母、hits或把陈旧worktree状态自动升级到新HEAD。
- 未证明任意恶意Git对象、任意编码/路径、所有间接导入/钩子效果或未来候选安全。未来新提交须按显式commit重新生成静态盘点；本次不自动选样、不扩大执行范围。

未访问模型、服务器、飞书、数据库或其他工作树，未合并、提交或推送分支；Core与Git进程已结束。
