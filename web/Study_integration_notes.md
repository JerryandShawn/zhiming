# 命理研习接线说明（本地只读）

核对来源：已存在的本地 `origin/v4/p8-calc`，一次冻结为
`0f1d6e676259b961819de4da5ea3f343d58dbe98`。只使用 `git show/ls-tree`；未fetch、未运行测试/计算、未HTTP或调用模型、未改其他工作树。本笔记不证明前端集成已完成。

## 1. 词典可直接取得

- `docs/v4/contracts/glossary.md`、`glossary.schema.json`、`glossary_sources.schema.json`。
- `mingjing_core/knowledge/p8_glossary/terms_v1.json`：264011 bytes，SHA256 `b1005b6e1748c7cb0dc680ff0b43ea93c4e54819b3a23da49f8e5b3a0cd197b3`。
- 同目录 `sources_v1.json`：19696 bytes，SHA256 `a781219cbf9f364ca6fbe89e82ce5e4640a99851a29bc65988b7ddcfcf67f1f1`。
- 实际212词：bazi72、ziwei55、astro50、tarot35；39来源。`version=p8-glossary-v1`，`stage=draft_complete_200_for_review`，`review_tag=v1_ready_editorial_reviewed`。项目编辑审阅过、等待大脑/所有者抽查，不能称原典/预测效度已验证。
- 顶层另含 `systems`、`entry_count`、`system_counts`、`sources_file=sources_v1.json`、`source_registry_version=p8-glossary-sources-v1`、`planned_system_minimums`、`limits`。
- 每词：`term_id,system,term,aliases[],definition_kind,plain_explanation,example,sources[],school_differences[],pending_review[]`。
- `sources[]`为 `{source_id,locator,support_scope}`；差异为 `{school,note,source_ids[]}`。
- 来源登记每项：`source_id,title,kind,url,path,locator,verification_status,edition_page_status`；url/path可null，但至少一类存在。source_id是登记键，绝不是网络请求地址。
- 例：`bazi-day-master`，“日主”，别名“日元/日干”，白话解释日干是比较十神的参照而非完整性格，source_id=`p8-elements`，定位 `ten_gods: master = pillars[day][0]`。同一词条保留具名差异和待核项。

建议前端内存搜索term+aliases并按system过滤，稳定term_id展示详情；跨体系重名保留多个候选，不默认取第一个。校验版本、ID唯一、声明与实际计数、source_id引用与来源注册版本；异常明确不可用，不能静默隐藏后宣称212词齐全。

## 2. 学习卡已有真实合成输出

- `docs/v4/contracts/learning_outline.md` / `.schema.json`。
- 原Python入口 `mingjing_core.skills.learning.learning_outline(chart_compute, limit=12)`；本线可直接读既有样例，无需调用该函数、重新排盘或启动Python业务服务。
- `docs/v4/contracts/samples/learning-ayuan-bazi.json`：53904 bytes，11卡/13c/10r，SHA256 `3f4ad34140fed9a80b2899c75fe9c736dbfb6a0a40e27bd662cd5d5f52f5b497`。
- `.../learning-ayuan-ziwei.json`：10624 bytes，2卡/4c/1r，SHA256 `f6ec9b9709afa2266e6caebbc306d16eb9f33c970a6b5cc85aa13693b3ec90a0`。
- `.../learning-ayuan-astro.json`：14549 bytes，2卡/4c/1r，SHA256 `1731e7bdeb4d06b29e7bcff3c9bcab0b2c306ebdac57e9e78ee9acf0bcf847a4`。
- 顶层：`version=p8-learning-outline-v1,status=learning_only|insufficient_evidence,scope,points[],aliases{c,r},rule_hits[],source_document_ids[],effects,limits`。
- 每卡：`point_id,kind,title,text,observed,school,source_refs,source_ref,c_aliases,r_aliases,citations`；规则卡另有limits。kind为orientation/matched_condition/boundary。school可字符串或对象；source_refs元素也可字符串或对象，不能直接当URL或React节点。
- effects严格 `model_calls:0,writes:0,alias_registry:reuse_input_projection_no_registration`。
- 当前八字第一卡“先找日主”，实际观察丁酉/丁/酉，c3；紫微第一卡“分清宫名与地支格”，命宫亥/身宫未，c3；西占第一卡“先读计算位置”，真实当前主盘c2（不能沿用旧c1）。
- 八字后续是实际格局候选条件与交界卡；“条件met=true”不等于格局成立，不得改写成格或已修正出生时辰。

**关键：学习输出不是独立账本，没有原documents。** 每个source_ref和aliases.ref依然相对原chart_compute信封的document payload；必须同时从同一固定提交读取 `samples/ayuan_bazi.json`、`ayuan_ziwei.json`、`ayuan_astro.json` 才可解析。c/r维持原登记行、原编号与scope/operation，不重编号、不按数组位置推断，不跨体系合并c1/r1。

若只接正文学习卡而暂不开放原始依据，应诚实标出依据尚未接入，不能画可点击的假证据。更合适是类似择日合盘的离线公开投影：只输出校验后的固定白名单字段与当前case的安全依据摘要，不把原始chart请求/出生/time_basis原值或scope送到浏览器，也不暴露通用Pointer浏览器。observed是任意JSON，boundary里可含多套候选四柱，禁止直接盲目JSON全文渲染。

## 3. 20课已存在（后续周队列可复用）

- `docs/v4/contracts/learning_lessons.md` / `.schema.json`。
- `mingjing_core/knowledge/p8_learning_lessons/curriculum_v1.json`，12188 bytes，SHA256 `172e78899d753d27dcf5a95620a99d5961d5a20c0d09b891956912e13ac32a60`。
- 同目录 `lessons/lesson-01.json` 至 `lesson-20.json`；20课40题，静态合成 `status=draft_for_review`、无学习进度服务/HTTP。
- 目录含 `source_registry` 版本+SHA、三case各自chart/learning路径+SHA+scope、20条精确观察evidence、lessons索引与limits。
- 单课含目标、前置课、paragraphs、worked_examples、quiz、source_ids、school_differences、pending_review、零写/零模型effects。
- quiz用稳定option_id；正确值与basis.expected做保类型的严格比较，不能把false当0。chart_observation/matched_rule与concept三种题分开；concept不可补c/r冒充实盘。
- `evidence.relative_path` 相对该case已有c解析后的值；primary须绑定真实view.primary；rule_input须有真实met=true的r及其输入c。坏路径、SHA、case、引用或题目绑定显示“样例依据已更新，待重新复核”，不回旧答案。
- 第20课astro_sun_sign当前真实主盘c2，旧c1无效。不同case/operation的c3不同。

## 4. 现有前端入口与不应混淆的内容

- 功能区预览已有 `study` / “命理研习”：`web/src/spaces/fixtures.ts`。入口 `/?spaces=demo#/chat?space=study&topic=chart-study`；本轮在原“我的命盘”话题接入对话、术语词典、学习卡三个视图，课程仍待后续。
- `spaces/SpaceNavigation.tsx` 生成区/话题链接；`spaces/ChatPreview.tsx` 负责区内对话；可在研习区增加独立词典/学习入口，保留草稿与归区协议。
- `App.tsx` 的旧 `#/dict` alias 指向 `#/me?section=dictionary`；`night/me/OtherTabs.tsx` 这里是“你自己的联想”，有删除个人联想和来源撤回语义。`live/LegacyPreview.tsx` 的 `/api/dict` 也是旧个人符号存档。两者都不是术语知识库，不能覆盖。
- 聊天正文：`chat/Answers.tsx` → `components/Markdown.tsx`。Markdown经过DOMPurify后转换React节点，禁止innerHTML；术语点击宜在安全文本节点转换阶段添加显式按钮/Sheet，不扫描并替换DOM HTML、不改code/link节点、不自动发送给模型。先消歧体系，详情保留出处范围/待核。
- 已有 `DeferredPanel`/Sheet可复用键盘、返回历史与关闭回焦；terms不是计算证据，详情不得生成c/r，也不写个人记忆。
- 盘面页面已有安全投影 `scripts/prepare-chart-samples.mjs` / `night/charts/{port.ts,samples.json}`；该projection刻意没有导入/合并alias，不能拿当前安全sample假称能解析learning原始c/r。

## 5. 接线约束与缺口

没有词典搜索API、对话术语弹窗API、学习进度存储、真实用户学习卡授权接口；集中typed只读静态端口即可，不猜HTTP。本轮源路径和字段可用，不需要合成200条替代真实词典。

出处URL只作为登记的来源说明，不自动访问/加载。39来源中34是本地实现/原创；5 URL是来源方历史阅读记录，本次本线未外访，不冒称重新原典核验。渲染文本，不加载来源HTML/SDK；仓库源码path作为只读定位文字，不把它拼成公网API。知识本身不授权读取第三人生辰、更新档案、重抽或解冻时辰倒推。

## 6. 本轮实现与验证

导出器 `scripts/export_study_glossary.py` 与 `scripts/learning_samples/export_learning_samples.py` 从上述固定 Git 对象只读导出；所有来源、原Schema、源SHA、document/Pointer/alias/claim、分支和卡片模板通过后才创建新的输出目录。现有目录拒绝覆盖，不启动计算引擎或任何服务。

公开资产仅七个 `public/data/study/{glossary,learning}/*.json`，不含原出生资料、原始时间坐标、任意observed或通用Pointer。学习正文有明确的受控摘要适配，保留具名流派、c/r原编号与来源范围。浏览器的固定七URL GET使用omit/no-store/redirect:error，并核对输出SHA、字节数、完整数量与封闭字段。SHA是资产一致性检查，不是签名或人物授权。

集中接线点为 `src/study/staticLoader.ts` 的load session、`port.ts` 的只读StudyPort与独立scope。每次重载先撤销旧port，切换查询/体系/卸载先失效旧scope；依据须同时匹配sample/document/alias/claim。原对话与composer DOM在视图切换、资料失败/重试后保留。额外的术语点击提示单独标“合成示例”，没有改原消息。

已实际通过34离线Python导出测试、152相关TS单测、14新浏览器+10原功能区浏览器；四尺寸双主题五状态40矩阵截图，加10交互截图，受测画面Axe全规则0、朱砂≤3、横溢出0、API/外域/非GET/真实模型0。精确源/测试/构建1002项哈希和各轮首失败记录在 `evidence/2026-10-21/study_checks.json`，阶段回执同目录 `study_receipt.md`。

首轮发现“关闭后立即重开”新read被旧Back误取消，现显式close先退休自己的read；Back/Forward、迟到与A→B→A负例保留。完整视觉矩阵另发现词典按钮label没有包含可见体系/别名，已修正完整读屏名称而未关闭Axe规则。初轮报告、截图和精确测试名称修正均保留，最终50图位于 `study-verified/`。

PWA外壳88文件中研习JSON为0，运行时数据不写缓存。当前只验证根路径预览；实际部署须把v4 bundle与 `/data/study/` 配置到同一根站点，不能以本地4173代替现有后端静态挂载。可选Python导出测试需要冻结Git对象，浅克隆CI需先取得该对象；Node标准测试直接读取已提交的七个公开资产，无此依赖。尚无学习进度持久化、20课页面或真实个人学习卡接口。
