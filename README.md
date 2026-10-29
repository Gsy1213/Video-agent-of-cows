# 牧知 · 奶牛行为分析智能体

一个可在本机演示的中文应用：React + TypeScript + Vite、FastAPI + SQLAlchemy + SQLite、独立视觉 worker、LangGraph 和持久化 Chroma 适配器。

源码仓库：https://github.com/Gsy1213/Video-agent-of-cows 。仓库包含源码、依赖锁、测试、文档与验收截图；原始视频、五天数据库、运行数据和密钥不纳入Git。克隆后需通过配置指向本机的视频与历史数据。

应用源码位于 `/data2/geshuyu/cow-agent`。原有 `/data2/geshuyu/mmcows/outputs` 保持只读。需求原文保存在 `brief.txt`；实现协议见 `docs/cow-agent-brief/02-*` 和 `07-*`。

## 快速启动

已安装的环境可以直接使用：

```bash
cd /data2/geshuyu/cow-agent
bash scripts/demo.sh
```

打开 **http://127.0.0.1:8000/videos**。脚本启动 API 与独立 worker，首次经 API 导入 80 份真实牛日汇总、2 份工程说明、2 份有原始来源链接的养殖知识摘要。Ctrl+C 停止脚本管理的子进程。已有数据保存在 `data/`，重复启动不重复导入同标题资料。

独立问答入口：**http://127.0.0.1:8000/chat**，或点击左侧“智能问答”。默认查询五天行为记录与养殖知识，可切换到任一已成功的视频分析、选择目标并播放回答中的视频片段；支持新建对话和刷新后恢复。与分析页内嵌聊天分别保存会话。

前端开发模式：`bash scripts/demo.sh --dev`，前端地址 `http://127.0.0.1:5173`，代理后端 8000。可用 `--port 8001` 切换生产演示 API 端口；开发代理固定为 8000，开发模式保持默认端口。

新机器安装：Python 3.11/3.12、Node 20.19+（本机验证 Python 3.11.16、Node 20.20.2）；使用 `PYTHON_BIN=/path/to/python3.11 bash scripts/bootstrap.sh`。依赖锁为 `requirements.lock` 与 `frontend/package-lock.json`。媒体工具使用 imageio-ffmpeg 随包二进制，无需全局安装。测试浏览器安装：`cd frontend && npx playwright install chromium`。

## 五分钟演示

1. 在“视频分析”点击“载入演示数据”，载入用户指定的 **5.mp4 真实牛舍视频（32秒，1280×720）**，任务异步进入 queued/running/succeeded。也可以上传 MP4 后选择“正常演示”。
2. 该32秒视频使用按实际时长缩放的模拟区间：有效观察约26.67秒、未知约2.67秒、已识别24秒、未观察约5.33秒。模拟采食8秒，占已识别时长1/3。点击采食区间跳到约5.33秒。画面是真实视频，行为区间仍为模拟。
3. 在视频实际0–32秒范围内筛选统计，可导出Markdown或JSON。自动化测试仍显式使用120秒合成fixture，验证原协议指定的两个精确统计窗口。
4. 在对话中问“分析采食情况，给我片段和统计依据”。展开实际工具状态，查看事实卡、播放片段、点开知识原文和版本。刷新页面恢复会话。
5. 打开“五天行为记录”：查询 1 号牛 2023-07-21 至 2023-07-25 每天的采食、覆盖率与未知时间；或问“比较1号牛这五天的采食变化”。选择采食事件并展开原始图像证据。
6. 打开“养殖知识库”，上传 TXT/MD/文本 PDF，检索实际原文；更新文档后新检索使用新版本，删除后新检索不可见。历史回答保留出处快照并标记更新或删除。

所有模拟视觉数据与画面内容无关。无目标、全未知、失败场景可从视频列表的“新建分析”选择。

## 数据与 RAG

- 精确历史统计和事件从 `mmcows/outputs/five_day_preannotation/behavior.sqlite3` 经既有只读 Store 查询，禁止混入独立评测真值和人工复核表。
- 同时将五天 16 头牛的 80 份牛日汇总转为带日期、牛号、来源和限制的知识文档，供文本/向量 RAG 召回。工具计算数值，不从 Top-K 文本推算总时长。
- 默认 `lexical`：NFKC、英文词项与中文 2/3-gram 的真实文本相似度，明确标为离线关键词检索。
- `vector`：真实 embedding 请求 + 本地持久化 Chroma，cosine 集合按 URL/模型/维度隔离，显式传入向量，不下载默认 embedding 模型。当前未配置真实 embedding，召回效果待验证。
- 文档 pending/indexing/ready/failed；新版本 ready 才切 active_version。删除先软删除，后台清理向量。引用保留当时原文与版本。

知识摘要原始出处：[Merck Veterinary Manual：奶牛营养需求](https://www.merckvetmanual.com/management-and-nutrition/nutrition-dairy-cattle/nutritional-requirements-of-dairy-cattle)、[UW–Madison Extension：热应激专题](https://dairy.extension.wisc.edu/articles/heat-stress/)。摘要经过网页原文核对，但未经过养殖专家审定，不代替现场评估。

## 真实接入

复制 `.env.example` 为 `.env`，服务端配置真实服务地址、模型名和密钥。默认不读取其他项目的密钥。

- LLM：`LLM_PROVIDER=api`，填写 `LLM_BASE_URL/LLM_MODEL/LLM_API_KEY`。兼容 Chat Completions tools/tool_calls，失败不降级为规则演示。
- 向量：`RETRIEVAL_PROVIDER=vector`，填写 `EMBEDDING_BASE_URL/EMBEDDING_MODEL/EMBEDDING_API_KEY`。切换后既有 lexical 文档需要建立对应向量版本，见接入指南；不能假定旧文档已有向量。
- 视觉：上传标准 JSON 导入，或设置管理员控制的 `VISION_COMMAND` 参数数组，在列表选择“真实模型接入”。不接受前端/聊天传入任意命令。
- 检查：`.venv/bin/python -m backend.check_providers`。无配置打印 **NOT_CONFIGURED**，不伪报成功。完整交接见 [MODEL_INTEGRATION.md](docs/MODEL_INTEGRATION.md)。

## 验证与开发

```bash
cd /data2/geshuyu/cow-agent
.venv/bin/python -m pytest backend/tests -q
npm --prefix frontend run typecheck
npm --prefix frontend run build
cd frontend && npm run e2e
```

端到端测试使用独立临时数据目录与 8011 端口，操作真实 API、worker 和浏览器，不修改原始历史库。OpenAPI 地址 `/docs`；`docs/openapi.json` 为快照；前端类型由 `npm --prefix frontend run types:api` 生成。修改 API 后运行 `scripts/export_api.py` 并重新生成类型。

查看 [验收报告](docs/ACCEPTANCE_REPORT.md)、[架构说明](docs/ARCHITECTURE.md)、[交接状态](docs/HANDOFF.md)。

## 使用边界

本机、单用户、可信环境演示，默认只监听 127.0.0.1。视频内轨迹不能自动关联到历史牛号；历史跨日身份和模型标签未经人工确认。观察覆盖率不足时不得外推全天行为。对话默认是显式规则演示，真实视觉效果、真实模型解释与真实向量检索效果均需独立接入验收。本版不训练视觉模型、不诊断疾病。

演示素材可通过 `.env` 中的 `DEMO_VIDEO_PATH` 更换。默认 `/data2/geshuyu/5.mp4`，载入时复制到应用数据目录，保留原视频内容和时长。
