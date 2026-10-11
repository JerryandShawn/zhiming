# 云端开发

代码仓库：<https://github.com/JerryandShawn/zhiming>（私有）。`main` 保存当前可运行的 v6 网站代码；`work/core-v3` 保留尚未接入网站入口的领域内核重构。该分支的 LangGraph、PostgreSQL 与统一问事服务尚未形成完整运行链，不能当成已上线功能。

GitHub 保存代码与版本记录。生产聊天、出生资料、数据库、图片上传、密钥、本地备份和机器专用运维脚本不随代码上传。现有网站的部署和数据仍在原服务器；连接仓库到云端开发环境不会自动迁移网站或资料。

## 在云端开始开发

1. 新任务选择 `Work in > Cloud > Select environment > Create environment`，连接 GitHub 并勾选 `JerryandShawn/zhiming`，然后选择 `Get started`。
2. 要求准备 Linux、Python 3.12 与 Node.js 22，并按下列命令安装和测试。
3. 检查结果与配置，补齐缺项后选择 `Publish`，再开始新云端任务。使用 `main`；重构工作明确切换到 `work/core-v3`。本次只上传代码，尚未创建或发布云端环境。流程见 [OpenAI 官方云端环境指南](https://learn.chatgpt.com/docs/environments/cloud-environments)。

普通配置放在 **Environment variables**，程序直接读取；`MINGJING_TOKEN` 使用专门的开发测试口令，不复用生产口令。AI 联调时，将 `KIMI_API_KEY` 配为 **Network secret**，许可域名填写 `KIMI_BASE_URL` 的实际服务主机；程序取得占位符，代理只向许可目的地的 HTTPS 443 请求替换真实密钥。基础测试不用 AI。配置行为见 [OpenAI 官方指南](https://learn.chatgpt.com/docs/environments/cloud-environments#configure-environment-variables-and-network-secrets)。

`.env.example` 仅列出现有程序字段；`main.py` 从进程环境读取，不会自动加载 `.env`。下列命令启动隔离开发实例：

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install fastapi==0.115.12 uvicorn==0.34.3 httpx==0.28.1 Pillow==11.3.0
npm ci
npm run build
export ZHIMING_BASE="$PWD/private/cloud-local"
export ZHIMING_SKILL="$PWD/hermes"
export HERMES_DB="$PWD/private/cloud-local/hermes-not-connected.db"
python -m uvicorn main:app --host 127.0.0.1 --port 8000 --workers 1
```

启动前通过普通环境变量设置开发专用 `MINGJING_TOKEN`；未设置时业务 API 返回 503。上述安装用于基础 Web/API 开发，沿用本地测试的四个根依赖版本，不包含完整生产依赖闭包、三盘环境或向量模型。云端预览如需要代理访问，仅使用开发工具提供的受控预览入口；生产服务配置另见 README。

未配置 AI 密钥时，记忆、事项、抽牌和静态牌意仍可验证，AI 解读会明确失败。模型接口使用 Anthropic 兼容的 `POST <KIMI_BASE_URL>/messages`，需要工具调用与 thinking 支持；`KIMI_MODEL` 应填写实际提供方开放的模型名，不能仅凭默认名称判断可用。

## 完整功能的额外资产

- 三盘需要独立解释器能导入 `lunar_python`、`py_iztro`、`swisseph`，并通过 `CHART_PYTHON` 指向它。`requirements-web.lock` 与 `requirements-charts.lock` 是原 Linux 环境的版本快照，尚未验证从空环境完整安装；两个环境的 Pydantic 版本不同，不应合装。
- 向量检索需要本地 MiniLM 文件及 ONNX/tokenizer 依赖，设置 `ZHIMING_EMBEDDING_MODEL`。缺失时不能声称已验证完整语义检索。
- Hermes/飞书需要真实渠道身份绑定与服务端只读消息库。云端开发默认不连接生产 Hermes 数据库、不运行真实投递任务。
- v6 的 `state.sqlite`、`web.db`、`tarot.db` 等仍是本地状态文件。正式云端运行需要持久化目录和备份；临时任务目录不能代替生产存储。当前网站仅按单 worker 协调活跃请求。

## 提交前检查

```bash
python -m unittest discover -s tests -p 'test_*v6.py' -v
npm test
node tests/dom.test.cjs
node --check static/app.js
npm run build
```

GitHub Actions 在推送与拉取请求时执行上述基础检查，不使用模型或服务器密钥，不部署网站。Python 检查使用合成数据与模拟模型，覆盖真实状态、接口、引用、更正删除和固定牌阵路径；它不代表真实模型、三盘或飞书投递验收。未完成的 `test_core_*.py` 不纳入 v6 基线检查。

`tests/dom.test.cjs` 使用入库的 `tests/fixtures/demo-charts.json` 手写渲染数据，覆盖页面交互并调用实际 Python 回答渲染器；它不验证真实排盘或浏览器画面。真实 HTTP 冒烟脚本 `tests/http_v6_smoke.py` 只用于关闭 AI 的可丢弃实例，会写入合成记录；不要指向生产账号。

网站发布、历史迁移、备份与回滚需单独完成验收和执行。仓库的 CI 不包含生产部署步骤。
