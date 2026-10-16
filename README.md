# 知命明镜台 Core v3

AI 接手请先阅读 [完整项目交接说明](docs/AI_HANDOFF.md)，其中包含 GitHub 版本、架构、API、数据库、部署、测试证据与已知限制。

独立 Core v3 保留 FastAPI、原生前端、X-Token 登录、既有模型配置和完整塔罗素材。生产入口 `main.py` 只创建 `mingjing_core.adapters.web`，网站、飞书、Hermes 适配器和报告统一调用 `ConsultationService`。PostgreSQL 是唯一权威数据库；LangGraph 是唯一业务执行链。旧总控仅保留为迁移/对比样本，不被生产入口调用。

原话、明确授权事实、人物、选中事项和各实体 revision 分别保存。单事实更正只使依赖它的结果失效；整来源删除清除派生正文并写入不含正文的撤销账本。备份恢复后必须先重放最新撤销账本。旧档案来源无法确认时标记 `legacy_unverified`，出生信息需在命盘页面核对并明确确认后才进入计算。

运行的业务 operation 固定，技术尝试单独记录。fast/standard/deep 调用上限为 2/6/10，失败调用、专科、深度复核和最多一轮全局修复均计入预算。重复成功请求读持久结果；合法更正后重新构建快照，显式撤销不可恢复。浏览器断线不取消后台任务。Checkpoint 只存 ID、阶段与版本；节点错误同样经过正文清洗。

三盘计算在独立解释器中运行，保留真实方法、时区、候选时刻、返回标志和回退警告。知识包为版本化公开来源、规则前提和反例，未实现技术返回 RULE_GAP。专业声明需重验实际字段与规则；象征解释不成为现实事实或事件概率。

塔罗问题、选项、方向和牌阵在选牌前冻结。私有洗牌、opaque 牌背、固定牌面与请求映射原子保存。Draw 与 ReadingVersion 独立，解释恢复保留原牌。Outbox 只发送经过校验且当前版本仍有效的原正文；送达不明保持 DELIVERY_UNCERTAIN，须核验后才能重试。

## 本地运行

使用可丢弃 PostgreSQL、开发专用口令和合成资料。安装 `requirements-core.lock`，计算依赖单独安装 `requirements-charts.lock`，以 `CHART_PYTHON` 指向计算环境。配置字段见 `.env.example`；程序读取进程环境，不自动加载 `.env`。

```bash
python -m pip install -r requirements-core.lock
npm ci
npm run build
export ZHIMING_DATABASE_URL=postgresql://core_dev:local_password@127.0.0.1:5432/core_dev
export MINGJING_TOKEN=local_development_token
export CHART_PYTHON=/absolute/path/to/chart-venv/bin/python
python -m uvicorn main:app --host 127.0.0.1 --port 8000 --workers 1
```

未配置模型时返回明确故障，抽牌不会因为解释失败而改变。服务器采用单 Web worker、池大小 4 与单任务恢复队列；扩大并发需先测量。

## 验证与发布

```bash
python -m unittest discover -s tests -p 'test_core*.py' -v
npm test
node tests/dom.test.cjs
node --check static/app.js
npm run build
```

集成测试必须配置隔离 PG，测试替身仅替代模型或外部传输。原 102 项行为迁移证据见 `docs/CORE_V3_BEHAVIOR_COVERAGE.json`，真实计算证据由 `tools/verify_core_calculators.py` 生成。真实模型、迁移、渠道和上线结果独立记录，自动测试不能替代这些验收。飞书入口见 `docs/CORE_FEISHU_GATEWAY.md`，发布与维护回退见 `docs/CORE_V3_RELEASE.md`。

生产私有资料、密钥、数据库、上传和备份不入库。迁移只读 SQLite/JSON 源，先处理更正和撤销，再处理原话与事实；切换后的源仅作为受保护归档。发布固定 commit、依赖和规则/素材哈希，一次切换网站与渠道，不发布 v6 过渡版。
