# Docker 部署指南

## 环境要求

- Docker 20.10+
- Docker Compose 2.0+

## 快速启动

### 1. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 文件，填写真实的 API Key
```

### 2. 构建并启动服务

```bash
# 构建镜像
docker-compose build

# 启动所有服务
docker-compose up -d

# 查看日志
docker-compose logs -f api
```

### 3. 访问服务

- API 文档: http://localhost:8000/docs
- Milvus 监控: http://localhost:9001
- API 接口: http://localhost:8000

## 服务说明

| 服务 | 容器名 | 端口 | 说明 |
|------|--------|------|------|
| etcd | tcm-etcd | - | Milvus 依赖 |
| minio | tcm-minio | 9000, 9001 | Milvus 对象存储 |
| milvus | tcm-milvus | 19530, 9091 | 向量数据库 |
| api | tcm-api | 8000 | FastAPI 服务 |

## 知识库导入

详见 [KNOWLEDGE_BASE.md](KNOWLEDGE_BASE.md)

## 数据持久化

数据存储在 Docker volumes 中：
- `tcm-milvus-etcd-data` - etcd 数据
- `tcm-milvus-minio-data` - MinIO 数据
- `tcm-milvus-data` - Milvus 数据
- `tcm-api-data` - API 应用数据

## 停止服务

```bash
docker-compose down
```

## 重启服务

```bash
# 重启所有服务
docker-compose restart

# 重启 API 服务
docker-compose restart api

# 重新构建并启动
docker-compose up -d --build
```

## 清理数据

```bash
# 停止并删除容器
docker-compose down

# 删除数据卷（⚠️ 会清空所有数据）
docker-compose down -v
```

## 常见问题

### Q: 容器启动失败？
A: 检查 .env 配置是否正确，确保有足够的磁盘空间

### Q: 端口被占用？
A: 修改 docker-compose.yml 中的端口映射

### Q: 如何查看日志？
A: `docker-compose logs -f [service_name]`
