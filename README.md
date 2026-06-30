# 中草药 Agent 开发

基于 **混合检索架构** 的中草药智能问答系统。

## 当前架构

**双检索引擎 + 18类意图识别 + 多层缓存 + 异步任务系统**
- 🗄️ **向量检索**: Milvus + BGE-M3 Embedding（语义匹配）
- 🕸️ **图数据库**: Neo4j（结构化数据、多跳推理）
- 🎯 **18类意图识别**: 症状、用药、疾病、检查等精准路由
- 🔀 **混合检索**: 图谱 + 向量 + Grep智能融合
- 💾 **多层缓存**: LLM缓存、语义缓存、Embedding缓存（计划中）
- ⚡ **异步导入**: 后台线程执行+任务状态追踪（知识库/图谱导入）
- 🌐 **Web UI**: 药典风格前端界面（`static/`）

## 快速开始

### 1. 环境配置

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑 .env 文件，填写真实的 API Key
```

### 2. 启动服务

```bash
# 构建并启动（包括 Attu 可视化管理界面）
docker-compose --profile dev up -d

# 或者只启动 API 服务（不包含 Attu）
docker-compose up -d

# 查看日志
docker-compose logs -f api
```

### 3. 访问服务

- **API 文档**: http://localhost:8000/docs
- **API 健康检查**: http://localhost:8000/health
- **灵境问药 (玄幻问答)**: http://localhost:8000/magic
- **Milvus 管理界面 (Attu)**: http://localhost:3000
  - 用户名: `root`
  - 密码: `Milvus@123`
- **Neo4j Browser**: http://localhost:7474
  - 用户名: `neo4j`
  - 密码: `neo4j123`

## 技术栈

### 核心框架
- **Agent 编排**: LangChain (ReAct 模式)
- **Web 框架**: FastAPI + Uvicorn
- **向量数据库**: Milvus + BGE-M3 Embedding
- **图数据库**: Neo4j（医疗知识图谱）
- **精确检索**: Grep + SQLite FTS5
- **LLM**: OpenAI API (GLM-4.7-Flash) / 本地模型（可选）
- **缓存系统**: Redis（计划中）

### 架构特点
- **混合检索**: 语义检索 + 精确匹配 + 图谱推理
- **双层知识库**: 向量数据库 + 图数据库
- **18类意图识别**: 症状、用药、疾病、检查等精准路由
- **智能路由**: 根据问题类型选择最佳检索策略
- **结果融合**: 加权融合算法（图谱 60% + 向量 40%）
- **医疗安全**: 免责声明注入 + 禁止编造医学知识

## 项目结构

```
ShenNongYaoDian/
├── src/
│   ├── agents/              # Agent 编排层
│   │   ├── medical_agent.py     # 医疗问答 Agent
│   │   ├── intent_recognizer.py # 意图识别器
│   │   ├── security_filter.py   # 安全过滤器
│   │   └── tools/               # 工具模块
│   │       ├── llm_tool.py      # LLM 调用工具
│   │       ├── vector_tool.py   # 向量检索工具
│   │       ├── grep_tool.py     # Grep 检索工具
│   │       ├── cache_tool.py    # 缓存工具
│   │       └── neo4j_tool.py    # Neo4j检索工具
│   ├── api/                 # API 接口层
│   │   ├── main.py               # FastAPI 主应用
│   │   ├── schemas.py            # 数据模型
│   │   └── routes/               # 路由模块
│   │       ├── graph.py          # 图谱管理
│   │       └── cache.py          # 缓存管理
│   ├── models/              # 数据模型
│   │   └── medica_data.py        # 中草药数据模型
│   ├── retrieval/           # 检索层
│   │   ├── milvus_client.py      # Milvus 客户端
│   │   ├── vector_store.py       # 向量存储管理器
│   │   ├── grep_retriever.py     # Grep 检索器
│   │   └── neo4j_store.py        # Neo4j存储
│   ├── task_manager.py      # 异步任务管理器
│   └── config/              # 配置管理
├── static/                  # 药典 Web UI
│   ├── index.html
│   ├── css/
│   └── js/
├── docs/                    # 技术文档
├── data/
│   ├── embeddings/          # BGE-M3 本地模型
│   └── knowledge_base/      # 知识库数据
├── docker-compose.yml       # Docker 编排配置
├── Dockerfile               # Docker 镜像构建
└── requirements.txt         # Python 依赖
```

## API 接口

### 问答接口

```bash
POST /api/chat
Content-Type: application/json

{
  "message": "人参有什么功效？它归什么经？",
  "session_id": "session-123"
}
```

**响应格式：**
```json
{
  "answer": "人参是微温的药，性甘、微苦，归脾、肺、心经。功效包括补气固表、利尿托毒、生肌敛疮、排脓...",
  "success": true,
  "disclaimer": "免责声明：本系统提供的信息仅供参考，不构成医疗建议。如遇健康问题，请咨询专业医生或药师。",
  "intent": "ingredient_query",
  "retrieval_type": "hybrid",
  "retrieval_stats": {
    "graph_results": 5,
    "vector_results": 8,
    "cache_hit": false
  }
}
```

### 知识图谱接口（新增）

```bash
# 获取图谱统计信息
GET /api/graph/stats

# 图谱查询（通过名称）
POST /api/graph/query
{
  "entity_type": "Drug",
  "name": "黄芪",
  "fields": ["name", "nature", "meridian", "effects"]
}

# 多跳查询（症状 → 疾病 → 用药）
POST /api/graph/multi-hop
{
  "start_entity": "乏力",
  "hop_count": 3,
  "path_types": ["HAS_SYMPTOM", "TREATS_WITH"]
}
```

### 知识库接口

```bash
# 获取知识库状态
GET /api/knowledge/status

# 批量导入知识（同步）
POST /api/knowledge/batch-import
{
  "directory": "ancient_treatises",
  "chunk_size": 500,
  "overlap": 50
}
```

### 异步任务接口（推荐）

导入接口改为异步执行，避免阻塞 API 服务：

```bash
# 异步导入知识库（文件路径方式）
POST /api/tasks/import-knowledge
{
  "file_paths": ["ancient_treatises/伤寒论.txt"],
  "chunk_size": 500,
  "overlap": 50
}
# 返回: {"success": true, "data": {"task_id": "task_xxx", "status": "pending", ...}}

# 异步上传导入知识库（多文件）
POST /api/tasks/upload-knowledge
# Form: files=@file1.txt files=@file2.txt

# 异步导入图谱
POST /api/tasks/import-graph
{
  "file_path": "medical.json",
  "mode": "full_import"
}

# 异步上传图谱
POST /api/tasks/upload-graph
# Form: file=@medical.json mode=full_import

# 查询任务状态
GET /api/tasks/{task_id}
# 返回: {"success": true, "data": {"status": "running", "message": "正在导入...", ...}}

# 任务历史列表（通知中心）
GET /api/tasks?limit=50
```

### Milvus 管理接口

```bash
# 获取集合信息
GET /api/milvus/collections

# 查询向量数据
GET /api/milvus/query?limit=10
```

## 开发约束

### 医疗安全
- 任何返回给用户的医药建议接口，必须在数据结构中预留 disclaimer 字段
- 所有的系统 Prompt 模板中必须包含："如果你不知道答案，或者提供的参考资料中没有相关信息，请直接回答'抱歉，我目前无法确认该信息'，严禁编造医学知识。"

### 架构原则
- LLM 调用、向量检索、Grep 检索均为独立 Tool
- 所有外部 API Key 必须通过 .env 文件读取

## 部署架构

### 开发环境 (使用 Attu)
```bash
# 启动完整服务（包括 Attu）
docker-compose --profile dev up -d

# 访问 Attu 管理界面
http://localhost:3000
```

### 生产环境（仅 API 服务）
```bash
# 只启动 API 服务
docker-compose up -d

# 通过 API 端点访问 Milvus 数据
GET http://localhost:8000/api/milvus/collections
```

## 监控和管理

### Attu Milvus 管理界面
- **URL**: http://localhost:3000
- **功能**:
  - 可视化查看向量数据
  - 管理集合和索引
  - 执行向量搜索
  - 查看统计信息

### API 健康检查
```bash
curl http://localhost:8000/health
```

### 知识库统计
```bash
curl http://localhost:8000/api/knowledge/statistics
```

## 故障排查

### CPU 使用率过高
```bash
# 重新构建并启动
docker-compose build api
docker-compose up -d api

# 查看 CPU 使用率
docker stats tcm-api
```

### Milvus 连接失败
```bash
# 检查 Milvus 状态
docker logs tcm-milvus

# 检查 Milvus 健康状态
curl http://localhost:9091/healthz
```

### 数据库保存错误
```bash
# 查看日志
docker logs tcm-api | grep ERROR

# 重新启动
docker-compose restart api
```

## 相关文档

- [Docker 部署指南](DOCKER.md)
- [架构设计](ARCHITECTURE.md)
- [知识库导入](KNOWLEDGE_BASE.md)
- [开发约束](CLAUDE.md)
- [性能优化方案](tasks/task1.md)
- [混合检索架构](tasks/task2.md)
- [BGE-M3 模型部署](docs/bge-m3-embedding-setup.md)
- [药典 UI 设计方案](docs/pharmacopoeia-ui-plan.md)
- [后端优化分析](docs/backend-optimization-plan.md)
- [本地大模型部署（离线运行）](docs/local-llm-deployment.md)
