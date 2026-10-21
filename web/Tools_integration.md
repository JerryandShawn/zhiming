# 择日、合盘的前端接线与验证

入口：`/?tools=demo#/chart?tool=window_search` 和 `/?tools=demo#/chart?tool=synastry`。明确模拟模式跳过登录与真实业务接口，其他入口继续原有v3行为。工具按路由异步拆包，不在今日首屏载入。

## 数据来源

`web/scripts/export-tool-samples.py --output test-results/<新目录>` 的输出目录相对web根；禁止已有目录和越界。脚本固定一次p8提交，验证根文档、Pointer、依据别名及claim摘要，核验实际排序、权重、分页、相位、结构和四种流派/出处组合；仅导出白名单。当前公开文件来源p8 `e56fcd6c4de96803fc5f6fc1135defd9ac34b1ff`，四源字节与固定测试6292199相同。

`web/public/data/tools/` 是经过导出器校验的公开合成投影，不含出生输入、owner、subject、operation或原始time_basis。浏览器只访问五个固定静态路径，omit credentials/no-store/redirect:error，核对清单、SHA、来源和外层结构。深层科学契约由离线导出器验证，不能称为浏览器完整Schema校验。PWA白名单没有这些JSON，运行时也不缓存。

## 端口与生命周期

`ToolPort` 是集中接线点。目前只有固定签约10/21–27三种分页、固定阿远/小禾亲密关系10/21与6°容许度。修改条件没有对应样例就明确不可用，不重命名、借用、补算或猜HTTP端点。

每个ToolPage创建独立scope；开始新请求、切条件、卸载、撤回和失败清除当前依据激活。结果、短别名和Sheet均绑定当前document与视图代际。Hook同时检查不透明ownership、operation identity及AbortSignal，防A→B→A与迟到回调复活。

合盘的两项本次确认只控制公开样例的展开及依据激活；公开合成字节会预载，预载不代表确认。确认绑定完整query与owner代际，任一条件改变或撤回需重选，历史sample_consent不授予新确认。未来真实资料读取必须另接服务端owner/同意权威，不能复用此演示端口当授权系统。

## 展示边界

择日保留七天总排序、真实第4–6名与末尾空页；启发式分数不表示成功率，也没有搜索全天吉时。合盘两侧独立显示、完整跨盘相位与配对方向、表层/三种候选路径、紫微已返回侧视，不补造完整十二宫或适配总分。流派、出处和限制随当前依据展示；只有两项登记官方链接可点击。没有写入、保存、发送或模型调用。

## 本次验证

18条离线Python测试；37条工具/路由单测加29条PWA兼容单测；16项四尺寸双主题浏览器加3项键盘/失败重试；20张原始截图。Axe全规则0、朱砂≤3、无文档横向溢出、API/外域/页面/控制台0；类型、lint零警告、构建通过。详见 `web/evidence/2026-10-21/tools_checks.json` 与 `tool_projection_checks.json`。旧842/493和296全站矩阵不冒充当前新入口的完整回归；当前头LCP提交后另测。

## 白天②·输入校验与摘要（M2a）

本轮核对纯计算契约到p8 `3e1069fd98317bcdf11f82eb76787f48fc34d712`，公开样例仍冻结e56fcd6，不因读新文档改写来源或别名。集中接线为 `inputValidation.ts`、`inputValidationTypes.ts`、`inputSummary.ts`：只验证当前五字段WindowQuery/SynastryQuery，不冒称整个native Birth/Request已校验。

日期严格ASCII YYYY-MM-DD、1901–2099和实际UTC年月日，起止含两端最多366天；offset/limit沿用整数语义，limit1–31。同一合成对象来自当前viewer规则，容许度有限0–10；0不默认6。输入额外字段不转发，WindowChoice.summary不进入query。日期检查不读Date.now或机器时区。

表单的错误摘要包含字段名与定位链接，逐项aria-invalid/describedby和首错焦点；纠正草稿保留。提交/重试先reset旧依据再校验，invalid零端口读。只有字段通过才显示“本次查询条件”，没有发布样例是独立普通status，不标成字段错误、不借旧结果。合盘另有只核对按钮，未双确认时仍不能读；orb保留原字符串草稿，任一原始参数改变即撤销双方确认。工具专用ToolSelect仅补字段ARIA，不改变全站Select。

160相关单测（新增135+旧25）、23浏览器（新4+旧19）首轮通过；人工复查后为两条相同日期错误补了可见字段名和逐链接回焦断言，最终160/23再次通过，1016项源/测试/构建前后一致。28最终图含16入口矩阵、键盘/失败和8新表单图；初轮28图及报告另存。Axe全规则0/朱砂≤3/API及外域0，类型/lint零警告/构建绿；见 `tools_input_checks.json` / `tools_input_receipt.md`。

完整工具页仍需M2b请求分页及后续资料确认流程。当前三分页只有0/31、3/3、7/3，page2的next_offset实际为6；6/3、0/3尚无发布JSON，应真实请求后明确不可用，不能偷换为7/3空页。更广的本命输入、出生日期先后、准确物理瞬间、owner和服务端同意权威还未接入；不会用字段valid冒称这些已通过。09:30标准九套1006/548属于本轮表单改动之前的新研习/状态源码，不能当成本轮新表单完整回归。

## 白天②·请求分页（M2b）

已接入常驻分页导航与原字符串页大小。query按用途、日期、offset、limit核对成功响应；next只读响应的next_offset，上一页减limit但必须实际前进。3/3的next6/3、prev0/3以及空页7/3的prev4/3均真实走端口并显示unavailable，不替换为已发布附近页。用途/日期/每页编辑归offset0，preset保留精确页；合法页大小应用后立即请求，非法/待应用/加载时零翻页。

常驻按钮用aria-disabled加事件guard，避免结果变化、末页或请求中丢焦；同一代际/owner和旧依据清理机制保持。190相关单测、27浏览器、40截图、1023项源/测试/构建前后一致，详见tools_pagination_checks/receipt。31/1/0仅纯metadata负例，不冒称新样例。M2c结果补全及真实资料适配仍后续。

资料适配的具体依赖：v3只发布本人GET/POST `/api/subjects/self/profile[/confirm]`，确认有request_id/expected_revision/confirmed并写事实与授权；不能放入零业务请求预览。v3 solar_datetime+timezone_offset及exact/approximate/unknown不能直接当P8的IANA tz/clock_basis/reported/唯一物理瞬间；不能凭城市或偏移猜。未见他人出生确认/撤销权威或window_search/synastry HTTP。现有BirthPort.canComputeGift=false，完成初识不解锁计算。以上记录阻塞，继续可验证的合成结果展示，不等用户或假造端点。
