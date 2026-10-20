# Q5 一次盲评前的外部冻结锚

- 实际冻结时间：2026-10-21T00:22:04.840656+08:00。
- 状态：160项Q5目标测试通过；Ruff E/F/I/B/UP/SIM、format、20文件尺寸检查通过。B正文尚未读取，prepare明确输出B_read=false。
- Manifest：Q5_preblind_manifest.json；外部SHA256锚：`a5a131e3adbf698721b4f17967d79cc00f13836659b161e6721f12a1b5cc24cd`。
- 整理完整源码树SHA256：`a0746d5e73edb5872e0f92b3df5689b02c942ebfa800819f3a1af76c665062bc`。
- 分类与话题参数SHA256：`b9d56a12734e95632df291f8c532e4dc1356a52003d1bef6b2ea163ae6b3e1aa`。
- 评测器及两个helper整树SHA256：`864ebce660cb3ce3273dc4c2abf5a70ea545e25934823ba82bccbe99cb1f754a`。
- 既有B冻结SHA256：`db998b7d960af7276c87d45d25ee024a0d3913e72d74e0bd938dfc6f60cd8682`，231条合成记录；映射与真值保持原冻结。

此记录连同产品、测试、评测器先提交推送，然后才可执行final。final必须提供上述外部锚，校验整树与参数，排他取得一次性claim后才读B。失败不重试、不回调产品、阈值、标签或评测器。报告仅聚合指标，不向调参者提供B误例。

区域准确率/弃权/ARI和话题ARI分别报告；话题按真实owner/subject/thread分组，context_group不是聚类特征。真值在预测结束后才用于打分。待整理不算已归类，也不算一个被断言的生活话题。

这份冻结为本地合成验证，不代表真实历史可自动整理；ONNX仍默认关闭，未下载或加载模型。阶段Q5尚待一次最终盲评报告。
