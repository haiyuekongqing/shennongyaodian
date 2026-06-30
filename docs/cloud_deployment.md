# 中草药 Agent 云服务器部署指南

## 概述

本项目（中草药智能问答 Agent）当前通过 Docker Compose 在本地运行，共包含 **6 个服务**（etcd、MinIO、Milvus、Attu、Neo4j、TCM-API），依赖向量数据库 + 图数据库 + 本地嵌入模型。本文档详细说明将其部署到云服务器所需的全部工作，包括服务器规格选型、配置变更、安全加固和运维方案。

---

## 一、服务器规格推荐

### 最低配置（开发/演示环境）

| 配置项 | 规格 | 说明 |
|--------|------|------|
| **CPU** | 4 核 | Milvus + Neo4j + API 三者并发，2 核会明显卡顿 |
| **内存** | 8 GB | 各服务内存占比如下 |
| **系统盘** | 40 GB | OS + Docker 镜像层 |
| **数据盘** | 100 GB | 向量数据、图谱数据、模型文件、日志 |
| **带宽** | 5 Mbps | API 问答响应够用 |
| **系统** | Ubuntu 22.04 LTS | 推荐，Docker 支持最好 |

### 推荐配置（生产环境）

| 配置项 | 规格 | 说明 |
|--------|------|------|
| **CPU** | 8 核 | 应对并发查询和 Embedding 计算 |
| **内存** | 16 GB | 给 Milvus 和 Neo4j 留出余量 |
| **系统盘** | 60 GB | OS + Docker 镜像 |
| **数据盘** | 200 GB SSD | 向量索引 + 图谱数据长期增长 |
| **带宽** | 10 Mbps | 流式输出场景下体验更好 |
| **系统** | Ubuntu 22.04 LTS | — |

### 各服务内存占用明细

| 服务 | 内存占用 | 说明 |
|------|---------|------|
| Milvus | 2~4 GB | 向量索引驻留内存，数据量大时更高 |
| Neo4j | 2 GB | pagecache 1G + heap 1G（见 `docker-compose.yml`） |
| TCM-API | 2~4 GB | FastAPI + BGE-M3 嵌入模型（CPU 推理） |
| MinIO | 512 MB | 对象存储缓存 |
| etcd | 256 MB | Milvus 元数据存储 |
| Attu | 256 MB | Milvus Web UI |
| Elasticsearch | 512 MB | 日志存储（堆外开销另计） |
| Logstash | 256 MB | 日志采集处理 |
| Kibana | 256 MB | 日志可视化 |
| OS 及其他 | 1~2 GB | 系统开销 |
| **合计** | **~11~16 GB** | **推荐 16 GB 为起步，32 GB 更充裕** |

> **关键判断**：Milvus 是内存大户（所有向量索引需要加载到内存），Neo4j 和 BGE-M3 模型加载也吃内存。**8 GB 勉强能跑，但遇到并发查询容易 OOM，强烈建议 16 GB。**

### 云厂商选择参考

| 厂商 | 推荐机型（16G 配置） | 参考月费 |
|------|---------------------|---------|
| 阿里云 | ecs.g7.xlarge (4C16G) | ~¥500-800 |
| 腾讯云 | S5.LARGE8 (4C16G) | ~¥400-700 |
| AWS | t3.xlarge (4C16G) | ~$120-180 |
| 华为云 | s6.xlarge.2 (4C16G) | ~¥450-750 |

---

## 二、从本地到云端的工作清单

### ▎阶段 1：云服务器初始化（预备工作）

- [ ] 购买云服务器，选择 **Ubuntu 22.04** 系统
- [ ] 配置安全组/防火墙，开放必要端口：
  - **22** — SSH（限制来源 IP）
  - **80** — HTTP（Nginx 反向代理）
  - **443** — HTTPS（Let's Encrypt）
  - **8000** — API 服务（仅内网或白名单）
  - **7474** — Neo4j Browser（仅内网访问，或关闭）
  - **3000** — Attu（仅内网访问，或关闭）
- [ ] 配置 SSH 密钥登录，禁用密码登录
- [ ] 更新系统：`apt update && apt upgrade -y`
- [ ] 安装 Docker 和 Docker Compose 插件
- [ ] 配置 Docker 国内镜像加速（阿里云/腾讯云加速器）
- [ ] 挂载数据盘到 `/data` 或 `/var/lib/docker`

### ▎阶段 2：代码与配置迁移

- [ ] 在服务器上 `git clone` 项目代码（推荐私有仓库）
- [ ] 创建生产环境 `.env` 文件（基于 `.env.example`）

#### 必须修改的配置项

| 配置项 | 本地值 | 生产建议 | 原因 |
|--------|--------|---------|------|
| `OPENAI_API_KEY` | `ollama`（本地测试） | 真实 API Key | 云端没有本地 Ollama |
| `OPENAI_BASE_URL` | `http://host.docker.internal:11434/v1` | 实际 API 地址 | 改为智谱/DeepSeek 等云端 API |
| `MINIO_ROOT_PASSWORD` | `minioadmin` | 高强度密码 | 安全红线 |
| `NEO4J_AUTH` | `neo4j/neo4j123` | 高强度密码 | 安全红线 |
| `ADMIN_USERNAME` / 密码 | 开发测试值 | 重新生成 | 安全红线 |
| `DATABASE_URL` | `sqlite:///./data/tcm.db` | `postgresql://user:pass@postgres:5432/tcm` | 生产环境必须切换 |

#### 数据库：SQLite → PostgreSQL

本地使用 SQLite 方便开发，生产环境**必须切换为 PostgreSQL**：

1. 在 `docker-compose.yml` 中添加 PostgreSQL 服务
2. 修改 `DATABASE_URL` 环境变量
3. PostgreSQL 数据卷单独持久化
4. 迁移现有数据（若本地已有历史对话数据）

```yaml
# docker-compose.yml 新增服务
postgres:
  image: postgres:16-alpine
  container_name: tcm-postgres
  restart: unless-stopped
  networks:
    - tcm-network
  environment:
    POSTGRES_DB: tcm
    POSTGRES_USER: tcm_user
    POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
  volumes:
    - postgres_data:/var/lib/postgresql/data
  healthcheck:
    test: ["CMD-SHELL", "pg_isready -U tcm_user -d tcm"]
    interval: 10s
    timeout: 5s
    retries: 5
```

### ▎阶段 3：Docker Compose 生产化调整

#### 3.1 移除开发专用配置

- 删除 `docker-compose.mirror.yml` 中的镜像源覆盖（生产环境可直接访问 HuggingFace）
- 移除源码热挂载卷 `- ./src:/app/src:ro`（改为镜像内编译）
- 移除 `build: .` 改为 `image: your-registry/tcm-api:latest`（使用镜像仓库）

#### 3.2 添加日志轮转

为每个服务配置日志驱动，**防止日志撑爆磁盘**：

```yaml
x-logging: &default-logging
  driver: "json-file"
  options:
    max-size: "10m"
    max-file: "3"

services:
  etcd:
    logging: *default-logging
  minio:
    logging: *default-logging
  milvus:
    logging: *default-logging
  neo4j:
    logging: *default-logging
  api:
    logging: *default-logging
```

#### 3.3 调整 API 服务资源限制

```yaml
services:
  api:
    deploy:
      resources:
        limits:
          cpus: '4'
          memory: 4G
        reservations:
          cpus: '2'
          memory: 2G
```

#### 3.4 添加健康检查（已有但补充所有关键服务）

`etcd`、`minio`、`milvus`、`api` 已在 `docker-compose.yml` 中配置了健康检查，新增对 `neo4j` 的健康检查：

```yaml
services:
  neo4j:
    healthcheck:
      test: ["CMD-SHELL", "cypher-shell -u neo4j -p ${NEO4J_PASSWORD} 'RETURN 1' || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 5
      start_period: 30s
```

#### 3.5 添加重启策略

所有服务已经配置 `restart: unless-stopped`，生产环境保持即可。

### ▎阶段 4：Nginx 反向代理与 HTTPS

- [ ] 创建 `nginx/nginx.conf` 配置反向代理
- [ ] 使用 Certbot (Let's Encrypt) 申请免费 SSL 证书
- [ ] 配置自动续期 cron job

```nginx
# nginx/nginx.conf
upstream tcm_api {
    server api:8000;
}

server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    client_max_body_size 20M;

    location / {
        proxy_pass http://tcm_api;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # 流式输出支持
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 300s;
    }

    # 可选：限制管理端点为内网
    location /attu/ {
        allow 10.0.0.0/8;
        allow 172.16.0.0/12;
        deny all;
        proxy_pass http://attu:3000/;
    }
}
```

将 Nginx 作为 Docker 服务或直接在宿主机安装均可。推荐**作为 Docker 容器**运行，统一管理：

```yaml
services:
  nginx:
    image: nginx:alpine
    container_name: tcm-nginx
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/conf.d/default.conf:ro
      - /etc/letsencrypt:/etc/letsencrypt:ro
      - certbot_data:/var/www/certbot
    networks:
      - tcm-network
    depends_on:
      - api
```

### ▎阶段 5：嵌入模型与知识库部署

#### 5.1 BGE-M3 嵌入模型

项目中使用了 BGE-M3 模型（约 **2 GB**）进行 Embedding 计算。云端部署时有两种方案：

| 方案 | 做法 | 优缺点 |
|------|------|--------|
| **方案 A：容器内下载** | 启动时自动拉取 HuggingFace 模型 | 初次启动慢（下载 2GB），需科学上网或镜像 |
| **方案 B：挂载预下载模型** | 将模型文件打包到镜像中或挂载数据卷 | 启动快，稳定，推荐 |

推荐方案 B — 构建镜像时使用 `docker-compose.mirror.yml` 的镜像下载模式，首次部署预下载并持久化：

```bash
# 首次部署预下载模型（使用国内镜像）
docker compose -f docker-compose.yml -f docker-compose.mirror.yml up -d api
# 等待模型下载完成（约 2GB）
docker compose logs -f api
# 后续部署使用正常模式（模型文件已缓存到数据卷，无需再次下载）
docker compose down
docker compose up -d
```

#### 5.2 知识库数据迁移

本地知识库文件已挂载在 `./data/knowledge_base/`：

- 主数据：`QASystemOnMedicalKG/medical.json`（45 MB，8808 条记录）
- 古籍文献：`ancient_treatises/伤寒论.txt`（102 KB）、`神农本草经.txt`（251 KB）

迁移方式：

```bash
# 方式1：scp 直接同步（适合首次部署）
scp -r ./data/knowledge_base user@server:/path/to/project/data/

# 方式2：提交到 git（如果知识库不超过仓库限制）
git add data/knowledge_base/
git commit -m "add knowledge base data"
git push
```

注意：`medical.json` 导入后还需执行初始化脚本将数据写入 Neo4j（知识图谱）和 Milvus（向量索引）。通过 `init.sh` 中的 `import_knowledge.py` 自动完成。

**生产环境重要**：导入完成后建议备份 Milvus 和 Neo4j 的数据卷，避免重复导入。

### ▎阶段 6：安全加固清单

- [ ] **修改所有默认密码**
  - MinIO: `minioadmin` → 强密码
  - Neo4j: `neo4j/neo4j123` → 强密码
  - 管理员后台账号 → 重新生成 salt + hash
- [ ] **敏感信息全部使用 `.env` 管理**，`.env` 文件不要提交到 Git
- [ ] **关闭非必要端口公网暴露**
  - `19530`（Milvus 端口）只对内网
  - `7474`/`7687`（Neo4j UI/Bolt）只对内网
  - `3000`（Attu UI）只对内网
  - `9000`/`9001`（MinIO API/UI）只对内网
  - `9091`（Milvus 监控）只对内网
  - `8000`（API）通过 Nginx 反向代理暴露，不直接开端口
- [ ] 配置 Docker 守护进程的 `userns-remap` 增强隔离
- [ ] 定期更新 Docker 镜像（`docker compose pull`）
- [ ] 配置 fail2ban 防止 SSH 暴力破解

### ▎阶段 7：数据备份方案

#### 7.1 需备份的数据卷

| 数据卷 | 内容 | 备份方式 | 重要程度 |
|--------|------|---------|---------|
| `milvus_etcd_data` | Milvus 元数据 | docker volume backup | 高 |
| `milvus_minio_data` | Milvus 向量存储文件 | docker volume backup | 高 |
| `milvus_data` | 向量索引数据 | docker volume backup | 高 |
| `neo4j_data` | 知识图谱数据 | Neo4j dump 或 volume backup | 高 |
| `tcm_api_data` | 数据库 + 嵌入模型缓存 | 单独备份 db 文件 | 中 |
| `postgres_data` | 对话历史（如切换后） | pg_dump | 中 |
| `elasticsearch_data` | 日志索引数据 | volume backup（可重建，优先级低） | 低 |

#### 7.2 备份脚本示例

创建 `/opt/scripts/backup.sh`，通过 cron 定时执行：

```bash
#!/bin/bash
BACKUP_DIR="/backups/$(date +%Y%m%d)"
mkdir -p "$BACKUP_DIR"

# 停止相关容器确保数据一致性
docker compose -f /opt/tcm/docker-compose.yml stop neo4j postgres

# Neo4j 备份（使用 Neo4j dump）
docker run --rm --volumes-from tcm-neo4j -v $BACKUP_DIR:/backup ubuntu tar czf /backup/neo4j_data.tar.gz /data

# PostgreSQL 备份
docker exec tcm-postgres pg_dump -U tcm_user tcm > $BACKUP_DIR/tcm_db.sql

# 重新启动
docker compose -f /opt/tcm/docker-compose.yml start neo4j postgres

# Milvus 相关 volume 备份
docker run --rm --volumes-from tcm-etcd -v $BACKUP_DIR:/backup ubuntu tar czf /backup/etcd_data.tar.gz /etcd
docker run --rm --volumes-from tcm-minio -v $BACKUP_DIR:/backup ubuntu tar czf /backup/minio_data.tar.gz /minio_data
docker run --rm --volumes-from tcm-milvus -v $BACKUP_DIR:/backup ubuntu tar czf /backup/milvus_data.tar.gz /var/lib/milvus

# 清理 7 天前的备份
find /backups -type d -mtime +7 -exec rm -rf {} \;

echo "Backup completed: $BACKUP_DIR"
```

```bash
# crontab -e 添加定时任务
0 3 * * * /opt/scripts/backup.sh >> /var/log/backup.log 2>&1
```

#### 7.3 数据恢复注意事项

- Milvus 的数据恢复**必须保证 etcd + MinIO + Milvus 数据卷三者的时间点一致**，否则索引不匹配
- Neo4j 支持单独 dump/restore，相对灵活
- **强烈建议在首次导入知识库后做一次全量备份**，避免故障后重新导入

### ▎阶段 8：域名与 DNS 配置

- [ ] 购买域名（如 `tcm.yourdomain.com`）
- [ ] 添加 DNS A 记录指向云服务器公网 IP
- [ ] 配置 Nginx `server_name` 为域名
- [ ] 使用 Certbot 申请 SSL 证书

```bash
# 安装 Certbot
apt install certbot python3-certbot-nginx -y

# 申请证书（Nginx 需先就绪）
certbot --nginx -d tcm.yourdomain.com

# 测试自动续期
certbot renew --dry-run
```

---

## 三、生产环境 `docker-compose.yml` 完整参考

将以下变更整合到最终的生产版 `docker-compose.prod.yml`（与本地版共存）：

```yaml
# docker-compose.prod.yml — 生产覆盖配置
# 使用：docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

services:
  # 移除所有公网端口暴露的管理服务
  minio:
    ports:
      # 只暴露给内网其他容器，不从宿主机暴露
      # 移除：- "9001:9001"  - "9000:9000"
      expose:
        - "9000"

  milvus:
    ports:
      # 移除公网端口
      expose:
        - "19530"

  neo4j:
    ports:
      # 移除公网端口，通过 Nginx 内网访问
      expose:
        - "7687"

  attu:
    ports:
      # 不对外暴露
      expose:
        - "3000"

  api:
    # 使用镜像仓库而非本地构建
    image: your-registry/tcm-api:latest
    build:  # 保留 build 用于 CI
      context: .
      dockerfile: Dockerfile
    ports:
      # API 端口只走 Nginx，无需宿主机暴露
      expose:
        - "8000"
    environment:
      # 数据库切换为 PostgreSQL
      DATABASE_URL: postgresql://tcm_user:${POSTGRES_PASSWORD}@postgres:5432/tcm
      # 生产级 Worker 数
      # 注意：多 Worker 下 BGE-M3 模型会被加载多次，需根据内存调整
    deploy:
      resources:
        limits:
          cpus: '4'
          memory: 4G
        reservations:
          cpus: '2'
          memory: 2G

  # 新增 PostgreSQL
  postgres:
    image: postgres:16-alpine
    container_name: tcm-postgres
    restart: unless-stopped
    networks:
      - tcm-network
    environment:
      POSTGRES_DB: tcm
      POSTGRES_USER: tcm_user
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U tcm_user -d tcm"]
      interval: 10s
      timeout: 5s
      retries: 5

  # 新增 Nginx
  nginx:
    image: nginx:alpine
    container_name: tcm-nginx
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/conf.d/default.conf:ro
      - /etc/letsencrypt:/etc/letsencrypt:ro
      - certbot_data:/var/www/certbot
    networks:
      - tcm-network
    depends_on:
      - api

  # 新增日志方案：ELK（Elasticsearch + Logstash + Kibana）
  elasticsearch:
    image: elasticsearch:7.17.25
    container_name: tcm-elasticsearch
    restart: unless-stopped
    networks:
      - tcm-network
    environment:
      ES_JAVA_OPTS: "-Xms512m -Xmx512m"
      discovery.type: single-node
      xpack.security.enabled: "false"
      TZ: Asia/Shanghai
    volumes:
      - elasticsearch_data:/usr/share/elasticsearch/data
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9200/_cluster/health"]
      interval: 30s
      timeout: 10s
      retries: 5

  logstash:
    image: logstash:7.17.25
    container_name: tcm-logstash
    restart: unless-stopped
    networks:
      - tcm-network
    depends_on:
      elasticsearch:
        condition: service_healthy
    volumes:
      - ./logstash/logstash.conf:/usr/share/logstash/pipeline/logstash.conf:ro
      - /var/lib/docker/containers:/var/lib/docker/containers:ro
    environment:
      LS_JAVA_OPTS: "-Xms256m -Xmx256m"

  kibana:
    image: kibana:7.17.25
    container_name: tcm-kibana
    restart: unless-stopped
    networks:
      - tcm-network
    depends_on:
      elasticsearch:
        condition: service_healthy
    environment:
      ELASTICSEARCH_HOSTS: http://elasticsearch:9200
      SERVER_NAME: tcm-kibana
    ports:
      - "5601:5601"

volumes:
  postgres_data:
    name: tcm-postgres-data
  elasticsearch_data:
    name: tcm-elasticsearch-data
  certbot_data:
    name: tcm-certbot-data
```

---

## 四、日志与监控方案

### 4.1 日志管理

参考 `prepare.md` 的日志方案，为 TCM 项目定制：

**基础日志轮转** — 所有服务必须添加日志限制（已在上文列出）。

**结构化日志** — TCM API 的 Python 日志目前是普通文本格式。生产环境建议改为 JSON 格式输出：

```python
# src/api 日志配置修改参考
import json
import logging

class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_entry = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%SZ"),
            "level": record.levelname,
            "service": "tcm-api",
            "message": record.getMessage(),
        }
        if hasattr(record, "request_id"):
            log_entry["request_id"] = record.request_id
        return json.dumps(log_entry)

handler = logging.StreamHandler()
handler.setFormatter(JSONFormatter())
logging.getLogger().addHandler(handler)
```

**集中式日志** — 推荐在 `docker-compose.prod.yml` 中加入 ELK 栈（Elasticsearch + Logstash + Kibana）用于日志搜索。Elasticsearch 负责存储和索引，Logstash 负责收集和解析 Docker 容器日志，Kibana 负责可视化检索。

Logstash 配置文件示例 `./logstash/logstash.conf`：

```conf
input {
  file {
    path => "/var/lib/docker/containers/*/*.log"
    codec => json
    type => "docker"
    start_position => "beginning"
  }
}

filter {
  if [type] == "docker" {
    json {
      source => "message"
      skip_on_invalid_json => true
    }
    mutate {
      add_field => {
        "[@metadata][container_name]" => "%{[attrs][container_name]}"
      }
    }
  }
}

output {
  elasticsearch {
    hosts => ["http://elasticsearch:9200"]
    index => "tcm-logs-%{+YYYY.MM.dd}"
    codec => json
  }
  stdout { codec => rubydebug }
}
```

> **ELK vs Loki 选择参考**：ELK 功能更全面，搜索和分析能力强，但资源消耗较大（Elasticsearch 至少需 1G 内存）。Loki 更轻量，与 Grafana 集成更好。本项目已有 Grafana 监控栈，如果日志量不大，可考虑 Loki 减少资源开销。`docker-compose.prod.yml` 中 ELK 各服务已限制内存：ES 512M、Logstash 256M。

### 4.2 服务监控

推荐 **Prometheus + Grafana + Node Exporter** 栈，方案同 `prepare.md`。

额外可监控 TCM 特有指标：

| 指标 | 说明 | 采集方式 |
|------|------|---------|
| Milvus 健康状态 | 向量库是否可用 | Prometheus `/metrics` |
| Neo4j 连接状态 | 图数据库是否可用 | 自定义 healthcheck |
| 向量检索耗时 | Milvus 查询 P99 延迟 | 应用层 metrics |
| 图谱查询耗时 | Neo4j Cypher 查询耗时 | 应用层 metrics |
| LLM 调用耗时 & Token 用量 | API 调用耗时 | 应用层 metrics |
| 缓存命中率 | L1/L2/L3 缓存命中率 | 应用暴露 metrics |
| 知识库导入状态 | 是否已完成导入 | 检查 `/app/data/.import_completed` |

---

## 五、CI/CD 自动化部署

### 5.1 简易部署脚本（`deploy.sh`）

与 `prepare.md` 一致，一键部署：

```bash
#!/bin/bash
set -e

echo "=== TCM 部署开始: $(date) ==="

cd /opt/tcm

# 拉取最新代码
git pull origin main

# 构建并启动
docker compose -f docker-compose.yml -f docker-compose.prod.yml build
docker compose -f docker-compose.yml -f docker-compose.prod.yml down
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# 健康检查
sleep 10
curl -sf http://localhost:8000/health && echo "✓ 服务运行正常" || echo "✗ 健康检查失败"

echo "=== TCM 部署完成: $(date) ==="
```

### 5.2 GitHub Actions 工作流

```yaml
# .github/workflows/deploy.yml
name: Deploy TCM to Production

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Build Docker image
        run: docker build -t your-registry/tcm-api:${{ github.sha }} .

      - name: Push to registry
        run: |
          docker push your-registry/tcm-api:${{ github.sha }}
          docker tag your-registry/tcm-api:${{ github.sha }} your-registry/tcm-api:latest
          docker push your-registry/tcm-api:latest

      - name: Deploy to server
        uses: appleboy/ssh-action@v1.0.3
        with:
          host: ${{ secrets.SERVER_HOST }}
          username: ${{ secrets.SERVER_USER }}
          key: ${{ secrets.SERVER_SSH_KEY }}
          script: |
            cd /opt/tcm
            echo "IMAGE_TAG=${{ github.sha }}" > .env.prod
            docker compose -f docker-compose.yml -f docker-compose.prod.yml pull
            docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

---

## 六、部署后验证清单

- [ ] **健康检查** — `curl https://tcm.yourdomain.com/health` 返回 `{"status": "healthy"}`
- [ ] **API 文档** — 浏览器访问 `https://tcm.yourdomain.com/docs` 能打开 Swagger UI
- [ ] **问答测试** — 调用 `POST /api/chat` 确认 LLM 回复正常
- [ ] **Milvus 连接** — 检查 API 日志中 Milvus 连接成功
- [ ] **Neo4j 连接** — 检查 API 日志中 Neo4j 连接成功
- [ ] **知识库已导入** — 确认 `.import_completed` 标记文件存在
- [ ] **HTTPS 证书** — 浏览器显示安全锁标志，证书未过期
- [ ] **日志轮转正常** — 检查 `/var/lib/docker/containers/` 日志未无限增长
- [ ] **磁盘空间** — `df -h` 确认各分区使用率正常
- [ ] **内存使用** — `docker stats` 观察各服务内存消耗是否在预期范围内

---

## 七、常见问题与注意事项

### 7.1 BGE-M3 模型加载问题

- BGE-M3 模型约 2 GB，**初次启动需要较长时间下载**
- CPU 模式下单次推理约 100-300ms，如果有 GPU 可大幅提升
- 多 Worker 模式下每个 Worker 都会加载一份模型，**内存倍数增长**，建议 1 Worker 或使用共享内存机制

### 7.2 Milvus 性能与稳定性

- Milvus 在 standalone 模式下是单点，生产建议改为分布式（但成本大增）
- 数据量少于 100 万条向量时，`docker-compose.yml` 中配置的 HNSW 索引够用
- **关键**：重启 Milvus 后，向量索引需要重新加载到内存，首次查询会慢（预热问题）

### 7.3 迁移成本汇总

| 项目 | 预估工作量 | 备注 |
|------|-----------|------|
| 服务器购买与初始化 | 1 小时 | 安全组、Docker、SSH |
| 配置迁移 | 1 小时 | .env、compose 调整 |
| Nginx + HTTPS | 1 小时 | 含域名解析 |
| 数据迁移 | 1~2 小时 | 知识库导入等待模型下载 |
| 日志监控部署 | 1~2 小时 | Grafana 配置 |
| CI/CD | 1 小时 | GitHub Actions |
| 备份方案 | 1 小时 | 脚本 + cron |
| **总计** | **约 1 个工作日** | 熟悉的情况下 |

### 7.4 省成本建议

- **前期可不开监控栈**，先用 `docker stats` 和 `docker compose logs` 手动观察
- **前期可不开 CI/CD**，手动 git pull 后执行 `deploy.sh`
- **前期用 SQLite 先跑**（但不推荐长期使用）
- 如果并发极低（日均 <100 次查询），可尝试 **4C8G 机型**，但需密切监控内存

---

## 八、总结

从本地 Docker Compose 部署到云服务器，核心变化包括：

1. **服务器** — 推荐 **4C16G + 100GB SSD**，Ubuntu 22.04
2. **配置** — 改默认密码、切 PostgreSQL、加 Nginx 反代、加 HTTPS
3. **数据** — 迁移 BGE-M3 模型 + 知识库，建立备份机制
4. **安全** — 关闭非必要端口、敏感信息 .env 管理
5. **运维** — CI/CD 脚本、日志轮转、监控告警

其中**内存是最关键的瓶颈**（Milvus + Neo4j + BGE-M3 三者加起来很容易吃掉 10G+），选型时务必注意。

建议部署顺序：服务器初始化 → Docker 环境 → 配置迁移 → 镜像构建 → 首次启动（等待模型下载）→ Nginx + HTTPS → 备份 → 监控。

---

**相关文档：**
- [DOCKER.md](../DOCKER.md) — 本项目的 Docker 本地部署说明
- [ARCHITECTURE.md](../ARCHITECTURE.md) — 系统架构说明书（各服务依赖关系）
- [NEO4J_SETUP.md](../report/NEO4J_SETUP.md) — 图数据库配置详情
