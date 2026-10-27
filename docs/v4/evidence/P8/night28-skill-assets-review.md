# 五包32章：本地结构、真实字段根与预算独立审阅

记录时间：2026-10-21 00:43（北京时间）。范围：本线已交付技能资产和 loader；没有模型、PG、服务器或外部发送。
审阅依据为大脑最新版P8模板的技能部分、18号P8推理/E2增补、现有 loader 与技能测试。
未联网核验 Agent Skills 最新规范，未宣称主线 tokenizer、KnowledgeRegistry 或 Agent 工具已接线。

## 实际发现与处理

1. 原五份入口对非八字结构 r 的禁止说明太宽，不能准确表达已交付真实边界/日历工具命中。
   依 root 批准，五份 `SKILL.md` 与目录升 v2.4：区分八字U12结构 r、真实边界/工具 r 与塔罗 t。
   不改规则条件、38条规则数量或计算结果。
2. 首轮新增结构检查与既有纯Core技能测试共125项，124通过、1失败。
   西占目录 description 与现有 SKILL frontmatter 不同；将目录对齐现有入口的“具名次限、实际UTC/象征时刻”，
   保留严格相等检查，不放宽测试。32章正文和各章自身版本没有修改。
3. 初查已发布阿远样例只有 time_basis，不能冒充八字/紫微旧 CalculationArtifact；只读 profile 也没有发布根。
   按 root 追加授权，从既有公开合成技能输入通过真实 `P8ChartAdapter.calculate` 生成两个原生产物，
   再由真实纯函数 `profile_proposal` 得到只读提案，补齐15组需求；不以“没现成JSON”为阻塞。
   方法明确为旧显式入口平太阳/八字sect2，保留实际profile，不能拿来替换默认真太阳主解释。

## 证据与重现

执行前清空子进程 API_KEY 环境、关闭追踪。原生样例生成仅1Core协调器+最多1Charts子进程，
同伴trace与U12各最多1Core，总并行不超过4。生成1.96秒，2 Artifact、0 errors，输出5个JSON：
两个原样 Artifact、完整 bundle、只读 profile proposal、方法/输入/文件hash manifest。

    python -m mingjing_core.adapters.charts.benchmarks.night28_skill_samples --chart-python <锁定Charts解释器>

输出位于 `docs/v4/contracts/samples/skill-bindings/`。
生成器属于 benchmarks，排除在既有 chart source_hashes 范围外；没有改数学、worker、旧v3或旧六份课程输入。
样例 manifest 保留实际方法、引擎版本与源指纹；原始数据未包装为另一种根。

随后仅1Core，无Charts/PG，运行：

    python -m pytest -q tests/v4/test_p8_skill_assets_contract.py tests/v4/test_p8_skill_binding_matrix.py tests/v4/test_p8_skill_budget_boundary.py tests/v4/test_p8_product_skills.py tests/v4/test_p8_calendar_tool_skills.py

结果：**128 passed、0 skipped、0.93秒**。
检查包含本地Schema、5份manifest、无孤立章节/重复键、来源元数据与尾部保留、37组严格Pointer绑定、
实际Artifact的Pydantic契约、profile的原生判断值和方法回指、原样文件SHA、32正文hash保护、冻结边界和精确字节预算。
这组检查未重复启动既有 `test_p8_skill_field_paths.py` 的Charts测试；真实样例由上面的独立生成步骤产生。
新增Python文件的默认Ruff格式和 `E,F,I,B,UP,SIM` 静态检查通过；最终交付前再核一次文件边界。

## 盘点结果

[skill_bindings.json](../../contracts/skill_bindings.json) 注册32章、37组需求，**204次**严格Pointer解析全部成功。
32组基础需求、3组条件能力、2组独立额外接口均使用各自声明根。
字段存在检查不能证明其自然语言解释或传统学说全部正确。
塔罗使用现有公开合成牌阵经真实公开serializer，不读数据库或private deck来源。

[机器盘点](night28-skill-assets-inventory.json) 逐章列字节、余量及hash；与当时HEAD逐章比较，32正文全部相同。
实际完整上下文最大的五章：

| 章 | UTF-8字节 | 5500字节剩余 |
| --- | ---: | ---: |
| bazi/patterns | 5138 | 362 |
| bazi/basics | 5117 | 383 |
| bazi/climate-useful | 5081 | 419 |
| astro/transits-progressions | 5017 | 483 |
| bazi/rectification-rules | 4558 | 942 |

5500和5501边界各用ASCII、中文、表情、组合字符四种文本验证：正例完整返回来源尾部与hash，反例拒绝且原文件不变。
预算是完整技能标签块的字节数，不是模型token数，也不包含最终prompt的其他段落/元数据。

## 未验证与限制

- 来源记录的标题、定位、HTTPS语法及正文出现得到核对；没有重做所有原典专业审校、原刊/页码或在线可用性校验。
- 本地JSON Schema/两字段frontmatter子集不等于通用YAML或官方最新版规范认证。
- 内容hash和合成owner一致不证明外部授权、撤销、真实用户事实或可信计算来源。
- 37组绑定是有限真实样例；未穷举所有日期、可选方法或任意恶意输入，也不证明预测有效。
- 实际模型tokenizer、ContextEngine、KnowledgeRegistry、Agent端到端由主线接线验证；没有真实模型请求。
- 本次只做定向检查；全量回归、准确提交CI、Git推送由root单独记录。没有数据库迁移，PR仍应保持draft。
