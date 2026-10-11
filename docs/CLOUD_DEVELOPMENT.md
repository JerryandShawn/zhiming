# 隔离开发

Core v3 使用 `requirements-core.lock` 的独立 Web 环境、`requirements-charts.lock` 的独立计算环境，以及专用 PostgreSQL 数据库。配置与启动见仓库 README 和 `.env.example`。开发只使用合成数据，不读取生产私有资料；CI 不调用真实模型或飞书。

GitHub 私有仓库保存源码、测试、规则和素材。开发环境配置 `CORE_TEST_DSN`、`ZHIMING_DATABASE_URL`、开发专用 `MINGJING_TOKEN`，以 `CHART_PYTHON` 指向计算解释器。不得复用生产口令。旧 SQLite/JSON 只供迁移测试，不能作为运行时备用库。

运行 `python -m unittest discover -s tests -p 'test_core*.py' -v`、`npm test`、`node tests/dom.test.cjs`、`node --check static/app.js` 和 `npm run build`。任何 skip 或外部依赖缺失必须单独记录，不能视为已通过。生产迁移、消息投递和部署属于明确授权的发布流程。
