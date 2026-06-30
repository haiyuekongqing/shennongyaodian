# 查询性能追踪

当前查询每个阶段的时间消耗分析。

## 一、当前性能分析

基于 `test-issues/issue-4.md` 日志：

### 查询 1："人参的功效是什么" — 总耗时 37 秒

| 阶段 | 耗时 | 占比 | 说明 |
|------|------|------|------|
| 意图识别 + Grep | ~0.02s | 0% | 瞬间 |
| **BGE-M3 模型加载** | **~5.4s** | 15% | 仅首次查询触发 |
| 向量检索 | ~3.2s | 9% | 含模型加载共 8.6s |
| **LLM 推理 (Qwen2.5-7B)** | **24.3s** | 66% | ⚠️ 核心瓶颈，生成 284 字符 |
| 其他开销 | ~3s | 8% | Ollama HTTP 传输等 |

### 查询 2："感冒了怎么办" — 总耗时 22 秒

| 阶段 | 耗时 | 占比 | 说明 |
|------|------|------|------|
| 意图识别 | ~0s | — | — |
| 向量检索 | ~0.6s | 3% | 模型已加载，正常速度 |
| Grep | ~0s | — | — |
| LLM 第一次 | 9.7s | 44% | 生成 675 字符 |
| 报错 fallback | ~10s | 45% | graph_results 缺字段 |
| LLM 第二次 | 10.8s | 49% | fallback 再调一次 LLM |

## 二、优化方向

### 1. LLM 推理速度（最大瓶颈）

当前 Qwen2.5-7B 在 Ollama 上 10~24s 明显偏慢。3070 Ti 正常应在 2~5s。

检查 GPU 是否在用：

```bash
# 查看 Ollama 是否加载在 GPU
ollama ps

# 查看 GPU 利用率
nvidia-smi -l 1
```

如果 Ollama 没在用 GPU（nvidia-smi 看不到 ollama 进程）：
- Windows 需安装 CUDA Toolkit 12.x + cuDNN
- 或安装 NVIDIA Container Toolkit（Docker 环境）
- 重启 Ollama 服务后重试

### 2. BGE-M3 首次加载（5.4s）

正常现象。模型 2.3GB 加载到内存需要时间。后续查询只有 0.6s。

### 3. 报错 fallback（已修）

`graph_results` 字段缺失导致额外调了一次 LLM，造成 +10s 浪费。已用 `.get()` 修复。

### 4. 语义缓存写入错误

`'list' object has no attribute 'tolist'` — 不影响功能但每次报错。
修复方式：`src/agents/cache/semantic_cache.py:153` 中 `dot_product = embedding1 @ embedding2` 之后需要 `.tolist()` 调用前检查类型。

## 三、时序追踪方案

不推荐 Prometheus + Grafana（太重）。而是给每个请求加一个 **轻量级时序记录器**：

```python
# 在每个关键步骤记录耗时
timeline = Timeline()
timeline.mark("intent")       # 意图识别
timeline.mark("vector_search") # 向量检索
timeline.mark("llm_start")     # LLM 开始
timeline.mark("llm_end")       # LLM 结束
timeline.report()              # 输出各阶段耗时
```

在响应中返回时序数据，前端可展示。这样既不需要额外基础设施，又能精确定位瓶颈。

## 四、预期优化后性能

| 场景 | 优化前 | 优化后（预期） |
|------|--------|---------------|
| 首次查询（含模型加载） | 37s | 8-12s |
| 后续查询（正常） | 22s | 2-5s |
| 后续查询（修复 fallback） | 22s | 2-5s |
| GPU 加速后 | — | 1-3s |

---

**更新时间**: 2026-06-23
