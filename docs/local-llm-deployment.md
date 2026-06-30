# 本地大模型部署指南（Ollama）

> 目标：完全离线运行，零外部网络依赖
> GPU: NVIDIA RTX 3070 Ti (8GB VRAM)

---

## 一、方案对比

| 模型 | 量化后显存 | 3070 Ti 表现 | 中文能力 |
|------|-----------|-------------|---------|
| **Qwen2.5-7B-Instruct** ⭐ | ~4.5 GB | 流畅 35-50 t/s | 最佳 |
| **GLM-4-9B-Chat** | ~5.5 GB | 运行偏满 20-30 t/s | 优秀 |
| **Qwen2.5-14B-Instruct** | ~8.5 GB | ❌ 放不下 | — |

**推荐 Qwen2.5-7B**: 10.5GB 空余显存 vs 4.5GB 占用，留足余量给 BGE-M3 嵌入模型。

---

## 二、安装 Ollama

### Windows

```bash
# 1. 下载安装器
#    https://ollama.com/download
#    双击安装，装完后右下角托盘有 Ollama 图标

# 2. 验证安装
ollama --version

# 3. 下载模型（约 4.5 GB）
ollama pull qwen2.5:7b

# 4. 验证模型运行
ollama run qwen2.5:7b
# 输入 "你好" 测试对话，Ctrl+D 退出

# 5. 确认 API 可用
curl http://localhost:11434/v1/models
```

### Linux (服务器/同机)

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen2.5:7b
```

---

## 三、配置应用连接

### 方式 A：Windows 宿主机 + Docker API 容器（推荐）

宿主机装 Ollama，API 在 Docker 容器中，需通过 `host.docker.internal` 访问宿主机。

修改 `.env`：

```ini
# .env 文件

# LLM 配置 — 本地 Ollama（Qwen2.5-7B）
OPENAI_MODEL=qwen2.5:7b
OPENAI_BASE_URL=http://host.docker.internal:11434/v1
# OPENAI_API_KEY 留空即可，Ollama 不检查 key
OPENAI_API_KEY=ollama

# 嵌入模型 — 本地 BGE-M3（已有）
EMBEDDING_MODEL=./data/embeddings/bge-m3
```

不需要改任何代码，因为应用使用 OpenAI 兼容 API 调用 LLM，Ollama 完全兼容。

### 方式 B：全部在宿主机运行（非 Docker）

```bash
# 直接在宿主机启动 API
uvicorn src.api.main:app --host 0.0.0.0 --port 8000
```

`.env` 配置：

```ini
OPENAI_MODEL=qwen2.5:7b
OPENAI_BASE_URL=http://localhost:11434/v1
OPENAI_API_KEY=ollama
```

---

## 四、启动顺序

```bash
# 1. 确保 Ollama 已运行（Windows 右下角托盘图标）
#    或在终端确认：
curl http://localhost:11434/v1/models

# 2. 重启应用
docker compose restart api

# 3. 验证
curl http://localhost:8000/health
# 应返回 "status": "healthy"

# 4. 测试问答
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"人参有什么功效"}'
# 应有完整回答
```

---

## 五、性能调优

### Ollama 并发设置

Ollama 默认使用全部 GPU 显存。如需给 BGE-M3 嵌入模型留显存：

```bash
# 设置 Ollama 最大显存使用（预留 2GB 给嵌入模型）
# Windows 设置环境变量：
set OLLAMA_MAX_VRAM=6GB

# 重启 Ollama 服务后生效
```

### 模型量化级别

```bash
# 查看 qwen2.5 支持的量化版本
ollama pull qwen2.5:7b          # Q4_K_M (默认, 推荐)
ollama pull qwen2.5:7b-q2_K    # 2bit (更快但质量下降)
ollama pull qwen2.5:7b-q8_0    # 8bit (更高质量但更吃显存)
```

8GB 显存建议用默认 `qwen2.5:7b`（Q4_K_M 量化）。

---

## 六、离线使用确认清单

| 项 | 状态 | 说明 |
|----|------|------|
| BGE-M3 嵌入模型 | ✅ 已本地下载 | `data/embeddings/bge-m3/` (2.3 GB) |
| Qwen2.5-7B LLM | ⏳ 需下载一次 | `ollama pull qwen2.5:7b` (4.5 GB) |
| 知识库数据 | ✅ 已导入 | 304 条向量 |
| API 联网检查 | ❌ 不联网 | Ollama 纯本地推理 |

**即使 LAN 断开**，上述全部在本地完成，零外部请求。

---

## 七、常见问题

### Q: Docker 容器连不上 Ollama？

```
ConnectionError: host.docker.internal:11434
```

检查：
1. Ollama 是否在运行：`curl http://localhost:11434/v1/models`
2. Docker Desktop 是否支持 `host.docker.internal`（Windows/macOS 默认支持）
3. Linux 需手动加 `--add-host host.docker.internal:host-gateway`

### Q: 推理速度很慢？

- 确认是否在用 GPU：Ollama 日志应显示 `llm: loaded model with GPU`
- 检查显存占用：`nvidia-smi` 看是否有其他进程占用
- 检查 CPU 占用：系统负载过高时 GPU 利用率上不去

### Q: 模型回答乱码或英文？

确保 `.env` 中 `OPENAI_MODEL=qwen2.5:7b` 拼写正确，Ollama 的模型名区分大小写。

### Q: 想换 GLM-4 本地版？

```bash
ollama pull glm4:9b
```

修改 `.env`：
```ini
OPENAI_MODEL=glm4:9b
```

注意：GLM-4-9B 量化后约 5.5GB，8GB 显存较紧张，可能影响 BGE-M3 嵌入速度。

---

## 八、相关文件

| 文件 | 说明 |
|------|------|
| `.env` | LLM 模型配置（修改 OPENAI_MODEL / OPENAI_BASE_URL）|
| `docker-compose.yml` | API 容器网络配置 |
| `src/config/settings.py` | 配置模型加载参数 |

---

**更新时间**: 2026-06-22
**硬件**: RTX 3070 Ti (8GB)
**推荐模型**: Qwen2.5-7B-Instruct (4-bit 量化)
