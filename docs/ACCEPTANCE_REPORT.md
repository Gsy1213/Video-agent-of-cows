# 实际验收报告

中断后恢复核查：独立问答任务已完成，无需重做。已核对实际源码、构建时间与文件名、既有构建/测试日志和截图。最新问答页构建passed（6.81秒），3组浏览器测试passed（25.8秒）；后端既有回归48 passed（demo-video-backend-test.log，9.53秒）。本次只读检查当前服务：/chat返回200并与现有dist/index.html完全一致，health返回200且worker正常。以上测试数来自已保存的实际运行日志，本次未重跑全套检查。目录不是Git仓库，因此Git diff检查为不可用，未生成或声称存在差异基线；本次仅补充恢复核查文档，保留所有源码修改。

独立问答页更新验收：新增 `/chat`、侧栏“智能问答”、历史/知识与视频范围选择、目标选择、证据播放、新建对话及刷新恢复。前端类型/构建 passed；真实服务浏览器3组测试全部 passed（25.8秒），见 chat-page-build.log 与 chat-page-e2e.log。当前演示服务直接访问并提问通过，见 chat-page-check.json 与 screenshots/chat-page.png。本次复用后端既有问答接口，未改后端逻辑。

后续素材更新：演示入口已按用户要求改为真实牛舍视频5.mp4，32秒、1280×720。浏览器实测按钮载入和播放通过（30帧已解码，readyState=4），原片与HTTP媒体SHA-256一致，页面无错误。新增证据为 demo-video-check.json、screenshots/demo-5mp4.png；本次48项后端回归与前端构建通过。下文120秒统计与原浏览器截图属于显式合成测试fixture，不能当作5.mp4的真实行为记录。

验收日期：2026-10-29。目标：`/data2/geshuyu/cow-agent`。运行环境：Python **3.11.16**、Node **20.20.2**、npm **10.8.2**。精确依赖版本见 requirements.lock 与 frontend/package-lock.json。默认视觉 mock、对话 mock（规则演示）、检索 lexical。

## 软件离线验收

| 范围 | 状态 | 实际证据 |
|---|---|---|
| 核心Schema、语义校验、两个指定统计窗口、未知分母、伪造引用拒绝 | passed | backend/tests/test_core.py；10个纯函数测试 |
| 视频上传、空/假媒体拒绝、真实Range媒体流、任务与幂等、失败不发布半份轨迹 | passed | backend/tests/test_integration.py |
| command成功/非零/超时/非法JSON/错指纹 | passed | backend/tests/test_providers.py，临时真实子进程 |
| 三类工具、20个问答用例、作用域、跨轮范围、未就绪回复保存 | passed | backend/tests/test_integration.py |
| 文档上传、真实分块、中文检索、更新/删除、无关查询、PDF OCR拒绝 | passed | integration/providers测试 |
| LLM工具调用消息往返、匹配tool_call_id | passed | MockTransport协议测试；不是外部模型实测 |
| embedding返回维度、显式向量、Chroma保存与重新打开 | passed | 实际本地Chroma + MockTransport；不是外部embedding效果测试 |
| 后端合计 | **passed，48项，9.52秒** | [backend-test.log](backend-test.log) |
| OpenAPI生成TypeScript、类型检查 | passed | `npm --prefix frontend run types:api`；`run typecheck` |
| Vite生产构建 | passed | [frontend-build.log](frontend-build.log)，6.20秒；有主包体积提示，不影响构建 |
| 浏览器上传→实际worker→统计→seek→RAG出处→导出→刷新 | passed | Playwright第1组，13.1秒；没有拦截mock API |
| 浏览器真实五天查询、历史智能体工具、文档更新删除、失败页面 | passed | Playwright第2组，8.4秒 |
| 浏览器合计 | **passed，2组，25.2秒** | [e2e.log](e2e.log)、playwright-report/index.html |
| 1024px无横向页面溢出、浏览器无pageerror | passed | 第1组自动断言与截图 |
| API/worker实际停止重启，持久数据与证据一致 | passed | [persistence-check.json](persistence-check.json)：84文档ID、视频、成功分析、消息及事实引用一致 |
| 真实五天统计与历史汇总文本召回 | passed | [real-history-check.json](real-history-check.json)、[retrieval-check.json](retrieval-check.json) |

执行命令：

```bash
.venv/bin/python -m pytest backend/tests -q --tb=short
.venv/bin/python scripts/export_api.py
npm --prefix frontend run types:api
npm --prefix frontend run typecheck
npm --prefix frontend run build
npm --prefix frontend run e2e
.venv/bin/python -m backend.check_providers
```

前两次浏览器运行暴露本机代理和浏览器安装问题，随后实测暴露全天时间格式适配错误与文本定位断言问题，均已修复。最终日志是通过的最后一次完整运行；不将早期失败运行算作通过。聊天局部滚动也已修正，避免自动把整个页面滚到底部。

## 外部真实能力验收

| 项目 | 状态 | 原因 |
|---|---|---|
| 本次新上传视频的真实视觉识别及人工区间核对 | not_run | 未提供真实runner及交接输出；当前视频演示明确为mock |
| 真实LLM规划、解释质量与引用语义 | not_run | LLM_API_KEY/MODEL/BASE_URL未配置；check_providers输出NOT_CONFIGURED |
| 真实embedding召回质量和阈值标定 | not_run | embedding未配置；只完成传输协议与本地Chroma持久化验证 |
| 养殖专业资料专家审定 | not_run | 附2份网页核对过的简短来源摘要，未进行领域专家审定 |
| 历史身份、模型行为标签人工复核 | not_run | 既有数据标记model_prediction、reviewed=false |

## 截图与可复现演示

- [1440px分析页面](screenshots/analysis-1440.png)
- [1024px分析页面](screenshots/analysis-1024.png)
- [五天历史页面](screenshots/history.png)
- [真实失败状态页面](screenshots/failure.png)
- [浏览器下载的报告](screenshots/browser-report.json)
- [浏览器历史工具调用证据](screenshots/e2e-evidence.json)

演示启动：`cd /data2/geshuyu/cow-agent && bash scripts/demo.sh`。入口 http://127.0.0.1:8000/videos。详细五分钟流程见README。接口文档 http://127.0.0.1:8000/docs。实际运行的LangGraph结构见 [agent-graph.mmd](agent-graph.mmd)。

## 已知限制与接入步骤

默认规则演示仅支持明确的行为、秒数范围、牛号与ISO日期等查询，不等同于任意自然语言模型。向量召回效果、真实视觉效果和LLM解释质量未验证。视频播放器面向浏览器兼容的MP4；不自动转码所有可解码但浏览器不兼容的编码。PDF无文本层明确提示OCR，本版不提供OCR。

既有历史模块依赖 `/data2/geshuyu/mmcows/preannotation`，历史库默认路径为用户指定outputs子目录；搬迁应用需要同步这些只读数据/查询模块或改适配器配置。应用没有认证、多租户或公网部署配置，按本机可信环境演示交付。

前端与后端本次未增加视觉训练或跟踪算法。与视觉同学协作顺序：上传视频取得服务器ID/指纹 → 提供协议JSON → import验收 → 配置command runner → 人工核对时序/身份 → 再单列真实模型验收。详见MODEL_INTEGRATION.md。
