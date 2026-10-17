# P0：会员端点评测的分批与额度停止保护

验证日期：2026-10-17（UTC+08:00）。本文件记录评测基础设施回归；全部供应商响应由合成测试替身提供，真实模型请求为 **0**。四项服务回归使用真实隔离 PostgreSQL 15 和原有 ConsultationService / LangGraph。

## 已验证的停止边界

评测入口按最多10个场景分批，批次顺序执行。目标或评审遇到429、quota / usage limit关键词时，安全停止原因记录为`quota`。现有ConfiguredModel不保留错误响应正文，故其余HTTP非200结果也保守停止，原因单独记录为`provider_http_error`，不会一概宣称额度耗尽。

ConfiguredModel关闭重定向且拒绝任何非200状态。独立审查发现初版只拦截400–599，已补齐307重定向及201等非200状态的停止回归。

停止信号只含固定原因和目标/评审角色，不携带供应商正文。它绕过普通`except Exception`，因此旧服务的repair和评审自己的异常转换不能消耗下一次真实请求。边界将结果记录为`incomplete`、退出码2，并停止剩余场景和剩余主模型；不生成`baseline-v3.json`。`KeyboardInterrupt`与`SystemExit`按原意传播，不被该控制机制吞掉。

目标与评审的停止记录均保留安全整数`provider_http_status`，以便直接区分403、404、400等结果；不保留响应正文，也不通过额外模型请求诊断。无法取得数值状态时不编造状态。

## 调用计数与恢复

每批JSON记录场景ID、真实新增目标/评审调用及各自模型耗时、缓存继承调用、批次墙钟耗时。Markdown将顶栏标为“本报告观测调用”，另列本次新增实际调用、缓存继承观测和历史累计实际调用；历史累计包含失败请求。缓存不冒充本批新请求。

停止后的后续执行需要用户明确决定；只有显式`--resume`才读取兼容的已完成观测。额度或其他基础设施失败不能作为成功缓存复用。恢复可以重用此前已完成的业务观测，包括真实业务0分；代码、配置、评审或场景变化仍按原指纹规则失效。

合成端到端回归在第12个适用场景停止：首次实际调用23次；随后显式恢复保留11个已完成观测，新增66次，缓存继承22次，历史累计89次。该回归证明失败请求没有在恢复后被抹掉。完整恢复后报告为80场景、44适用和36个`n/a on v3`；单独`--scenario`子集仍不能生成完整基线。这些次数均为测试替身计数，绝非真实模型账单。

## 命令与结果

新增`tests/v4/test_eval_quota.py`和`test_eval_quota_pg.py`共 **21项** 通过，最终安全HTTP状态链路的针对性复验为 **21 passed in 2.28s**。相关框架、恢复、固定评审契约合计 **130 passed in 9.92s**：

    python -m pytest tests/v4/test_eval_quota.py tests/v4/test_eval_quota_pg.py tests/v4/test_eval_framework.py tests/v4/test_eval_resume_comparison.py tests/v4/test_eval_critic_contract.py -q

真实PG的两项首请求回归覆盖429/403：只调用intake一次，之后显式尝试repair也不会再触达供应商。另两项先让真实validation发现无效引用并进入repair，再由repair返回429/403：实际调用序列严格为intake、synthesis、repair，后续请求仍被熔断。

新增/修改基础设施通过Ruff E,F,I,B,UP,SIM与120列格式检查；没有修改业务模型适配器或User-Agent。完整新测试目录、正式脚本报告及真实基线由主执行者在最终源码冻结后统一记录。

## 未验证

真实Kimi Code会员端点的`k3`调用、实际可用额度与真实基线分数尚待主执行者运行；本文件不能证明这些外部状态。额度停止后不自动等待重试、不自动切换模型、不自动续跑。
