# BGE-M3 Embedding 模型配置与部署说明

## 概述

本项目使用 BAAI/bge-m3 作为 Embedding 模型，用于将文本转化为向量，支撑 Milvus 向量数据库的语义检索。为降低运行时网络依赖和启动延迟，建议优先使用本地已下载的模型文件。

---

## 一、当前状态（2026-06-17）

### 模型文件

BGE-M3 模型已通过 ModelScope 下载到本地，路径：`data/embeddings/bge-m3/`

```
data/embeddings/bge-m3/
├── pytorch_model.bin         (2.27 GB)  # 主模型权重
├── colbert_linear.pt         (2.1 MB)   # BGE-M3 ColBERT 向量头
├── sparse_linear.pt          (3.5 KB)   # BGE-M3 稀疏向量头
├── sentencepiece.bpe.model   (4.8 MB)   # 分词器
├── config.json                          # 模型配置
├── tokenizer.json                       # tokenizer
├── tokenizer_config.json                # tokenizer 配置
├── modules.json                         # 模块定义
├── 1_Pooling/                           # pooling 层
├── onnx/                                # ONNX 导出格式
└── README.md
```

**下载方式**（参考，已执行）：
```bash
pip install modelscope
python -c "from modelscope import snapshot_download; snapshot_download('BAAI/bge-m3', cache_dir='./data/embeddings/')"
```

### Docker 配置（已就绪）

`docker-compose.yml` 中已配置好本地模型路径：

```yaml
# docker-compose.yml line 170
EMBEDDING_MODEL: /app/data/embeddings/bge-m3

# docker-compose.yml line 184
volumes:
  - ./data/embeddings:/app/data/embeddings:ro
```

### 代码实现

Embedding 模型通过 `src/retrieval/embedding.py` 中的 `EmbeddingModel` 类加载：

1. **优先**使用 `FlagEmbedding.BGEM3FlagModel`（官方推荐，支持稠密+稀疏+ColBERT 多向量）
2. **降级**使用 `sentence-transformers.SentenceTransformer`
3. **懒加载**：首次调用 `encode_documents()` 或 `encode_queries()` 时加载模型
4. **容错**：加载失败返回零向量，不阻塞主流程

路径来源：`settings.EMBEDDING_MODEL`（默认 `"BAAI/bge-m3"`，Docker 环境覆盖为本地路径）

---

## 二、部署方式对比

项目提供两种 Docker 启动方式（方案 1 / 方案 2）以及一种本地开发方式（方案 3）。

---

### 方案 1：在线下载 + 镜像加速（特殊命令启动）

通过 HuggingFace 国内镜像（hf-mirror.com）在线下载模型，适合首次部署或未下载本地模型时使用。

| 项目 | 说明 |
|------|------|
| 模型来源 | HuggingFace 国内镜像 `https://hf-mirror.com` |
| 网络依赖 | ⚠️ 首次启动需下载 ~2.3GB，之后从缓存加载 |
| 缓存位置 | 持久卷 `/app/data/hf_cache`（重启不丢失） |
| 启动命令 | `docker compose -f docker-compose.yml -f docker-compose.mirror.yml up -d` |
| 配置位置 | `docker-compose.mirror.yml`（覆盖配置） |

**工作机制：**

`docker-compose.mirror.yml` 是一个 Compose 覆盖文件（override），通过 `-f` 参数叠加到 `docker-compose.yml` 之上，覆盖三项环境变量：

```yaml
# docker-compose.mirror.yml
services:
  api:
    environment:
      HF_ENDPOINT: https://hf-mirror.com       # 国内镜像源
      HF_HOME: /app/data/hf_cache               # 持久化缓存路径
      EMBEDDING_MODEL: BAAI/bge-m3               # HuggingFace 模型名（在线模式）
```

它**覆盖**了 `docker-compose.yml` 中的 `EMBEDDING_MODEL: /app/data/embeddings/bge-m3`（本地路径），改回 `BAAI/bge-m3` 让模型从镜像站下载。首次启动后模型缓存在 `hf_cache` 持久卷中，后续重启无需重复下载。

---

### 方案 2：本地模型（默认推荐）

使用已下载到 `data/embeddings/bge-m3/` 的本地模型，零网络依赖。

| 项目 | 说明 |
|------|------|
| 模型路径 | `/app/data/embeddings/bge-m3`（已挂载） |
| 网络依赖 | ❌ 无 — 使用本地模型文件 |
| 启动命令 | `docker compose up -d` |
| 配置位置 | `docker-compose.yml` environment 段（已配置） |

**当前 Docker Compose 默认配置就是方案 2**，直接启动即可：

```bash
# 默认启动（使用本地模型）
docker compose up -d
```

---

### 方案 3：本地开发（uvicorn 直接运行）

不在容器中运行，直接用 Python 启动服务。

| 项目 | 说明 |
|------|------|
| 模型路径 | 默认 `"BAAI/bge-m3"`（HuggingFace 模型名） |
| 网络依赖 | ⚠️ 首次启动需下载模型 |
| 启动命令 | `uvicorn src.api.main:app` |
| 配置方式 | 项目根目录创建 `.env` 文件 |

要使用本地模型，需修改 `.env`：

```bash
echo "EMBEDDING_MODEL=./data/embeddings/bge-m3" >> .env
```

不设置 `.env` 的话，默认从 HuggingFace 在线下载。

---

### 三种方式速查

```bash
# 方案 1（在线镜像下载）- 使用 docker-compose.mirror.yml
docker compose -f docker-compose.yml -f docker-compose.mirror.yml up -d

# 方案 2（本地模型，默认）- 仅使用 docker-compose.yml
docker compose up -d

# 方案 3（本地开发）- 直接用 Python 启动
# 先确保 .env 中有 EMBEDDING_MODEL=./data/embeddings/bge-m3（可选）
uvicorn src.api.main:app
```

---

## 三、快速排查

### 当前使用哪个模型？

```bash
# 检查环境变量
docker exec tcm-api env | grep EMBEDDING_MODEL

# 或查看容器日志
docker logs tcm-api | grep "Embedding"
# 预期输出：✓ Embedding 模型加载完成（FlagEmbedding）: /app/data/embeddings/bge-m3
```

### 模型文件是否完整？

```bash
ls -lh data/embeddings/bge-m3/pytorch_model.bin
# 预期：2.27 GB，文件存在
```

### 模型加载失败怎么办？

1. 检查路径是否正确：`docker exec tcm-api ls /app/data/embeddings/bge-m3/`
2. 检查挂载卷：`docker inspect tcm-api | grep -A5 "embeddings"`
3. 尝试重启：`docker compose restart api`
4. 若 FlagEmbedding 加载失败，会自动降级到 sentence-transformers

---

## 四、相关代码入口

| 文件 | 关键方法/行 | 功能 |
|------|------------|------|
| `src/config/settings.py:31` | `EMBEDDING_MODEL` | 模型路径/名称配置 |
| `src/retrieval/embedding.py:42` | `_load_model()` | 模型懒加载，FlagEmbedding → sentence-transformers 降级 |
| `src/retrieval/embedding.py:86` | `encode_documents()` | 文档编码（入库时调用） |
| `src/retrieval/milvus_client.py:35` | `self.embedding_model_name` | 记录当前使用的模型名 |
| `src/retrieval/milvus_client.py:130` | `embedding_model.encode_documents(texts)` | 生成向量后插入 Milvus |
| `docker-compose.yml:170` | `EMBEDDING_MODEL: /app/data/embeddings/bge-m3` | Docker 环境覆盖为本地路径 |
| `docker-compose.yml:184` | `./data/embeddings:/app/data/embeddings:ro` | 模型目录挂载 |

---

**更新时间**: 2026-06-17
**相关文件**: `src/retrieval/embedding.py`, `src/retrieval/milvus_client.py`, `docker-compose.yml`, `data/embeddings/bge-m3/`
