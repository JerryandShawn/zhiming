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
