# 视觉与真实 Provider 交接

## 标准结果 JSON

机器契约：`docs/cow-agent-brief/02-模型结果协议.schema.json`。示例是 `03-模型结果样例.json`，包含占位指纹，不能直接导入真实视频。

1. 通过 POST `/api/videos` 上传视频，记录服务器 video_id、sha256 与媒体信息。
2. 上游提供 schema_version=1.0、video_id、analysis_id、source_kind、model_version、video_sha256、duration_s、sample_interval_s、behavior_catalog、tracks、detections、warnings。
3. tracks 包含 observed_intervals 与完整互斥 segments，无法分类显式 unknown；片段并集须等于观察并集。只有图片级标签而没有轨迹/视频时间/区间时，不足以导入时长分析。
4. POST `/api/videos/{id}/analyses/import` 上传 JSON。服务器仅重绑定 analysis_id，原 ID 留作 external_analysis_id；video_id 与指纹必须匹配。导入 mock 不会变成 model。
5. GET `/api/analyses/{id}` 等待终态，再查看 stats、segments、detections。失败保留原任务，新建任务重试。

时间区间为视频内秒 `[start_s,end_s)`，不能使用 UTC 时间戳替代。catalog 动态传入，unknown 是保留值。检测框为归一化 `[cx,cy,w,h]`，完整框须位于画面内且时间属于有效观察区间。没有坐标则不画框。行为分段应互斥，重叠多标签需先协商协议。

## 外部命令

`.env` 中设置 JSON 数组，例如 `VISION_COMMAND=["/absolute/python","/absolute/runner.py"]`。浏览器只能选择 provider，不能设置命令。

worker 执行：

```text
configured_runner --input VIDEO_PATH --output RESULT_PATH --video-id SERVER_VIDEO_ID --analysis-id SERVER_ANALYSIS_ID
```

退出码为 0 并写出合法 JSON 才算成功。command 只接受 source_kind=model。模型日志不直接暴露给页面；超时终止所属进程组。`VISION_TIMEOUT_S` 是模型总超时，`WORKER_STALE_S` 是失联检测，二者不同。测试已覆盖临时 runner 成功、非零退出、超时、非法 JSON、错指纹；真实 runner 需另行联调。

## LLM 与 embedding

服务端 `.env` 配置兼容 Chat Completions 的 LLM 和 embeddings 接口；模型名由部署方填写，不写死未经验证型号。密钥不进入浏览器和 git。

`.venv/bin/python -m backend.check_providers` 检查配置、LLM tool_call/tool_call_id 往返、embedding 维度。无配置返回 NOT_CONFIGURED；调用失败返回非零退出码，不切回 mock。

切换 `RETRIEVAL_PROVIDER=vector` 后，需要为原先 lexical 文档建立向量索引。在当前本地单实例停止期间运行维护脚本：

```bash
.venv/bin/python -m backend.reindex_vectors
```

脚本须在真实 embedding 配置齐全且 API 停止时使用，统一使用相同 index_version/collection 指纹。失败保持已存在旧 ready 版本；查看日志再重试。不将 stub 协议测试当作真实模型效果验证。

## 真实验收还需要

视觉同学真实输出与样本视频、人工核对的区间/身份、可用 LLM/embedding 凭证、适用且经专家确认的专业资料。上传视频轨迹与既有五天牛号没有自动关联功能；确认身份需要单独证据。
