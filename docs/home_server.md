# 中草药 Agent 本机服务器部署方案（Windows 11）

## 概述

用本机代替云服务器运行本项目，核心思路是将 Windows 开发机同时作为生产服务器，通过内网穿透或 DDNS 实现外网访问。本机配置远超同价位云服务器，且零月费，适合演示、个人使用或小团队内部使用。

---

## 本机配置评估

### 你的机器规格（MSI Vector GP76 12UGSO）

| 配置项 | 本机规格 | 对比云服务器（4C16G） |
|--------|---------|---------------------|
| **CPU** | i7-12700H（14 核 / 20 线程） | **本机性能约为云服务器的 3~5 倍** |
| **内存** | 16 GB DDR5 | 持平 |
| **硬盘** | 1 TB NVMe SSD | 本机更快（本地 NVMe vs 远端云盘） |
| **显卡** | RTX 3070 / 3080 Laptop（?） | **GPU 可加速 BGE-M3 推理** |
| **网络** | 家庭宽带（上行一般 30-50 Mbps） | 云服务器通常 5-10 Mbps |
| **电力** | ~150W 满载 | 云服务器已含在月费中 |
| **费用** | **零额外成本** | ¥400-800/月 |

> **结论**：性能完全过剩。唯一的短板是家庭宽带上行带宽和公网 IP 稳定性，而非机器性能。

### 适合场景 vs 不适合场景

| 适合 | 不适合 |
|------|--------|
| ✅ 个人/小团队内部使用 | ❌ 对外商业服务（需 SLA） |
| ✅ 开发测试/演示环境 | ❌ 高并发生产环境（>100 QPS） |
| ✅ 学习部署流程的过渡方案 | ❌ 需要 7×24 小时无人值守 |
| ✅ 省钱的长期方案 | ❌ 要求固定公网 IP 的场景 |

---

## 方案一：纯内网使用（最简单，推荐先跑起来）

如果仅需在家庭/办公室局域网内访问，不需要外网访问：

```
                    ┌─────────────────────┐
                    │  本机 Windows 11     │
                    │  Docker Compose 运行 │
                    │  所有 6 个服务       │
                    │  API: localhost:8000 │
                    └──────────┬──────────┘
                               │
            ┌──────────────────┼──────────────────┐
            │                  │                  │
            ▼                  ▼                  ▼
      ┌──────────┐      ┌──────────┐      ┌──────────┐
      │ 本机浏览器 │      │ iPad/手机 │      │ 其他电脑  │
      │ localhost  │      │ 同 WiFi   │      │ 同局域网  │
      │ 访问 API   │      │ 192.168.x │      │ 192.168.x │
      └──────────┘      └──────────┘      └──────────┘
```

### 操作步骤

```bash
# 1. 直接启动现有 Docker Compose（已经跑起来了）
docker compose up -d

# 2. 局域网内其他设备访问
# 查看本机局域网 IP
ipconfig
# 找 "无线局域网适配器" 或 "以太网适配器" 的 IPv4 地址
# 其他设备浏览器打开: http://192.168.x.x:8000/docs
```

局域网内访问需要**关闭 Windows 防火墙**或**添加入站规则**放行 8000 端口即可。

---

## 方案二：外网访问（完整服务器方案）

需要让外部网络也能访问你的 API。

### 整体架构

```
互联网用户
     │
     ▼
┌──────────────────────────────────────┐
│      域名解析（DDNS 或服务商域名）      │
│  tcm.your-domain.com  → 你的公网 IP   │
└──────────────────┬───────────────────┘
                   │
                   ▼
┌──────────────────────────────────────┐
│    路由器端口转发（UPnP 或手动配置）    │
│  外网端口 443/80  → 本机 443/80      │
└──────────────────┬───────────────────┘
                   │
                   ▼
┌──────────────────────────────────────┐
│        本机 Windows 11                │
│                                      │
│  ┌──────────────────────────────┐    │
│  │    Nginx (Windows 原生)       │    │
│  │    Port 80 → HTTPS 443        │    │
│  │    反向代理 → api:8000        │    │
│  └────────────┬─────────────────┘    │
│               │                      │
│  ┌────────────▼─────────────────┐    │
│  │    Docker Compose（WSL2）     │    │
│  │    etcd / MinIO / Milvus     │    │
│  │    Neo4j / API / ELK         │    │
│  └──────────────────────────────┘    │
│                                      │
└──────────────────────────────────────┘
```

### 网络拓扑说明

```
互联网
   │
   │ 你家的公网 IP（动态，每次重启路由器可能变化）
   ▼
路由器/光猫
   │
   │ 端口转发：443 → 本机 443, 80 → 本机 80
   │
   ▼
Windows 本机 (192.168.1.xxx)
   │
   ├── Nginx (Windows 原生安装) → 监听 :80 / :443
   │    反向代理 → http://localhost:8000
   │
   └── Docker (WSL2 后端)
         ├── etcd, MinIO, Milvus, Neo4j, API, ELK
         └── 所有容器在 tcm-network 内网互通
```

---

## 详细实现步骤

### ▎Step 1：Docker 后端切换为 WSL2（已完成则跳过）

Windows Docker Desktop 默认已使用 WSL2 后端。确认：

```bash
# Docker Desktop → Settings → General → 勾选 "Use WSL 2 based engine"
# Resources → WSL Integration → 启用你要用的发行版
wsl -l -v  # 确认 WSL2 状态
```

WSL2 的性能优于 Hyper-V 虚拟机，且与 Docker 集成最好。本项目已在 Windows 上通过 Docker Compose 正常运行，说明 WSL2 已配置好。

### ▎Step 2：域名与动态 DNS（DDNS）

家庭宽带一般没有固定公网 IP，需要用 DDNS 解决。

**方案 A：使用 DDNS 服务商（免费，推荐）**

```bash
# 以 AliDDNS 为例（有很多免费实现）
# 1. 在阿里云/腾讯云买一个便宜域名（约 ¥30-50/年）
# 2. 获取 API Key
# 3. 用 DDNS 脚本定时更新 DNS 记录

# 推荐使用 ddns-go（Windows 原生支持）
# 下载地址：https://github.com/jeessy2/ddns-go/releases
# 安装为 Windows 服务，开机自启
```

推荐工具：

| 工具 | 平台 | 特点 |
|------|------|------|
| **ddns-go** | Windows/Linux | Web 配置界面，支持各大云厂商 API |
| **AliDDNS** | 跨平台 | 专门针对阿里云 DNS |
| **DuckDNS** | 免费托管 | 无需自有域名，name.duckdns.org |
| **Cloudflare DDNS** | 跨平台 | 配合 Cloudflare DNS 使用 |

**方案 B：使用 frp 内网穿透（无公网 IP 时）**

如果你的宽带**没有公网 IP**（内网/大内网），需要一台有公网 IP 的云服务器做跳板：

```
用户 → frp 客户端（本机） → frp 服务端（轻量云服务器） → 互联网
```

```bash
# 服务端（云服务器，最低配 2C2G 即可，约 ¥50/月）
# 下载 frps，配置：
# frps.toml
bindPort = 7000
vhostHTTPPort = 80

# 客户端（本机 Windows）
# frpc.toml
serverAddr = "your-cloud-server-ip"
serverPort = 7000

proxies:
  - name: "tcm-api"
    type: "http"
    localPort: 8000
    customDomains: ["tcm.yourdomain.com"]
```

> frp 的优点是解决无公网 IP 问题，缺点是需要一台云服务器中转（但可以用最便宜的 ¥50/月机型）。

### ▎Step 3：Windows 防火墙与路由器端口转发

#### 3.1 查看本机局域网 IP

```bash
ipconfig
# 无线网络适配器 Wi-Fi:
#   IPv4 地址: 192.168.1.xxx
```

#### 3.2 配置 Windows 防火墙（放行端口）

```powershell
# 管理员 PowerShell
# 放行 Nginx 端口（HTTP/HTTPS）
New-NetFirewallRule -DisplayName "Nginx HTTP" -Direction Inbound -Protocol TCP -LocalPort 80 -Action Allow
New-NetFirewallRule -DisplayName "Nginx HTTPS" -Direction Inbound -Protocol TCP -LocalPort 443 -Action Allow

# 如果局域网其他设备需要直接访问 API，放行 8000
New-NetFirewallRule -DisplayName "TCM API" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow

# 如果局域网其他设备需要访问 Kibana 日志
New-NetFirewallRule -DisplayName "Kibana" -Direction Inbound -Protocol TCP -LocalPort 5601 -Action Allow

# 不需要对外暴露的管理端口不要放行（Milvus/Neo4j/MinIO 等）
```

#### 3.3 路由器端口转发

登录路由器管理页面（通常是 192.168.1.1 或 192.168.0.1）：

```
虚拟服务器 / 端口转发 设置：
┌──────────────────────────────────────┐
│ 外部端口  →  内部IP        →  内部端口 │
├──────────────────────────────────────┤
│ 443       →  192.168.1.xxx →  443    │
│ 80        →  192.168.1.xxx →  80     │
└──────────────────────────────────────┘
```

**安全警告**：只转发 Nginx 端口（80/443），**不要转发** Milvus (19530)、Neo4j (7474/7687)、MinIO (9000/9001) 等端口到外网。

### ▎Step 4：Windows 上安装 Nginx

Docker 内跑 Nginx 也可以，但 Windows 原生 Nginx 作为宿主机网关更稳定、更可控，且可以开机自启。

**方式 A：Windows 原生 Nginx（推荐）**

```bash
# 1. 下载 Nginx for Windows
#    http://nginx.org/en/download.html → nginx/Windows-x.x.x.zip
# 2. 解压到 C:\nginx
# 3. 配置 conf\nginx.conf

# 4. 启动：
cd C:\nginx
start nginx

# 5. 设为开机自启：
#    方法1：创建 taskschd.msc 计划任务
#    方法2：放入 shell:startup 启动文件夹
```

**方式 B：Docker 容器 Nginx**

```yaml
# docker-compose 中已有的 nginx 服务，与 prod 方案一致
# 但需要注意端口从 WSL2 转发到 Windows 宿主机的效率问题
```

**Nginx 配置**（`C:\nginx\conf\nginx.conf`）：

```nginx
events {
    worker_connections 1024;
}

http {
    upstream tcm_api {
        server 127.0.0.1:8000;
    }

    # HTTP → HTTPS 重定向
    server {
        listen 80;
        server_name tcm.yourdomain.com;
        return 301 https://$server_name$request_uri;
    }

    server {
        listen 443 ssl http2;
        server_name tcm.yourdomain.com;

        ssl_certificate C:/nginx/ssl/fullchain.pem;
        ssl_certificate_key C:/nginx/ssl/privkey.pem;

        client_max_body_size 20M;

        location / {
            proxy_pass http://tcm_api;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;

            # 流式输出支持（关键，否则 SSE 会缓冲）
            proxy_buffering off;
            proxy_cache off;
            proxy_read_timeout 300s;
        }
    }
}
```

### ▎Step 5：HTTPS 证书（Let's Encrypt）

Windows 上申请 SSL 证书建议使用 **acme.sh**（Git Bash 环境）或 **Certify The Web**（有 GUI）：

**方法：Certify The Web（推荐，有图形界面）**

```bash
# 1. 下载 Certify The Web: https://certifytheweb.com/
# 2. 安装后，添加证书：
#    - 域名: tcm.yourdomain.com
#    - 验证方式: HTTP (需要通过 Nginx 暴露 80 端口)
#    - 绑定绑定到 C:\nginx\ssl\
# 3. 自动续期（软件内置计划任务）
```

**方法：acme.sh（命令行）**

```bash
# 在 Git Bash 中
curl https://get.acme.sh | sh

# 申请证书（HTTP 验证，需要 Nginx 已启动并监听 80 端口）
acme.sh --issue -d tcm.yourdomain.com --webroot C:/nginx/html

# 安装证书到 Nginx 目录
acme.sh --install-cert -d tcm.yourdomain.com \
  --key-file C:/nginx/ssl/privkey.pem \
  --fullchain-file C:/nginx/ssl/fullchain.pem
```

> Windows 上 SSL 证书申请的关键是 80 端口必须能从外网访问到，所以需要路由器端口转发已配置好。

### ▎Step 6：开机自启配置

本机作为服务器需要 7×24 小时运行（或需要时远程唤醒）。需要配置以下项目的开机自启：

| 项目 | 配置方式 | 操作 |
|------|---------|------|
| **Docker Desktop** | Docker 设置 | Settings → General → "Start Docker Desktop when you sign in" |
| **Docker 服务** | `docker compose up -d` | 已在后台运行，Docker 重启后自动恢复（`restart: unless-stopped`） |
| **Nginx** | Windows 计划任务 | `taskschd.msc` → 创建任务 → 触发器"开机" → 启动 `C:\nginx\nginx.exe` |
| **DDNS** | Windows 服务 | ddns-go 安装为服务，开机自启 |
| **系统自动登录** | netplwiz | 取消"要使用本计算机，用户必须输入用户名和密码"（可选） |
| **电源计划** | 控制面板 | 关闭睡眠、关闭显示器，合盖不做操作 |

**电源设置（关键）**：

```powershell
# 管理员 PowerShell — 禁止合盖睡眠
powercfg /change lidclose 0
# 0 = 不操作, 1 = 睡眠, 2 = 休眠

# 禁止自动睡眠
powercfg /change sleep-timeout-ac 0
powercfg /change sleep-timeout-dc 0

# 禁止显示器关闭（可选，可节省屏幕寿命）
powercfg /change monitor-timeout-ac 15
powercfg /change monitor-timeout-dc 5

# 查看所有电源配置
powercfg /list
powercfg /query
```

> **注意**：笔记本合盖运行需要注意散热。建议把笔记本竖放或架高，确保底部进风通畅。

### ▎Step 7：远程管理方案

本机作为服务器，你不可能一直坐在它面前。需要远程管理手段：

#### 7.1 远程桌面（RDP，Windows 原生）

```powershell
# 开启远程桌面
# 设置 → 系统 → 远程桌面 → 启用远程桌面
# 或者在防火墙放行 3389 端口

# 安全加固：不要将 3389 暴露到外网！
# 建议通过 VPN 或跳板机连接内网再 RDP
# 或者使用 Tailscale / ZeroTier 组建虚拟内网
```

#### 7.2 Tailscale 虚拟组网（强烈推荐）

Tailscale 基于 WireGuard，免费版支持 3 用户、100 台设备：

```bash
# 1. 本机 + 你的手机/笔记本 都安装 Tailscale
#    https://tailscale.com/download

# 2. 登录同一账号，设备自动组网

# 3. 从手机上直接访问 Tailscale IP
#    http://100.x.x.x:8000/docs

# 4. 本机的 SSH/RDP 也可以走 Tailscale 网络
#    完全不需要端口转发，安全性极高
```

#### 7.3 Wake-on-LAN（远程唤醒）

如果需要关机省电、需要时再唤醒：

1. 在 BIOS 中开启 Wake-on-LAN
2. 路由器设置 MAC 绑定固定 IP
3. 使用 WoL 工具（手机 App 或 Python 脚本）远程唤醒

### ▎Step 8：Docker Compose 配置调整

本机方案的 `docker-compose.yml` 相比云端方案只需要微调：

#### 保留本地 SQLite（可选）

本机作为服务器，不一定要切 PostgreSQL。SQLite 对于个人或小团队使用完全足够：

```yaml
# 可以继续使用 SQLite，无需添加 PostgreSQL 服务
# 只需确保数据挂载到宿主机持久化
services:
  api:
    environment:
      DATABASE_URL: sqlite:///./data/tcm.db
```

> 什么时候需要切 PostgreSQL？多用户并发写入、需要数据完整性保障、数据量超过几 GB 时。个人使用 SQLite 更简单。

#### Docker Compose 参考（本机版）

创建 `docker-compose.home.yml`：

```yaml
# docker-compose.home.yml — 本机服务器覆盖配置
# 使用：docker compose -f docker-compose.yml -f docker-compose.home.yml up -d

services:
  # 所有管理端口只监听 127.0.0.1，不暴露到局域网
  minio:
    ports:
      - "127.0.0.1:9001:9001"
      - "127.0.0.1:9000:9000"

  milvus:
    ports:
      - "127.0.0.1:19530:19530"

  neo4j:
    ports:
      - "127.0.0.1:7474:7474"

  attu:
    ports:
      - "127.0.0.1:3000:3000"

  api:
    ports:
      - "8000:8000"
    environment:
      # LLM API 使用本地 Ollama（如果本机装了 Ollama）
      # OPENAI_API_KEY: ollama
      # OPENAI_MODEL: qwen2.5:7b
      # OPENAI_BASE_URL: http://host.docker.internal:11434/v1
      #
      # 或者使用云端 API
      OPENAI_API_KEY: ${OPENAI_API_KEY}
      OPENAI_MODEL: ${OPENAI_MODEL:-GLM-4.7-Flash}
      OPENAI_BASE_URL: ${OPENAI_BASE_URL:-https://open.bigmodel.cn/api/paas/v4}
    # 资源限制 — 本机资源充裕，可以给更多
    deploy:
      resources:
        limits:
          cpus: '8'
          memory: 8G
        reservations:
          cpus: '4'
          memory: 4G

  # 可选：开启 ELK 日志
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
    volumes:
      - elasticsearch_data:/usr/share/elasticsearch/data
    ports:
      - "127.0.0.1:9200:9200"

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
      - "127.0.0.1:5601:5601"

volumes:
  elasticsearch_data:
    name: tcm-elasticsearch-data
```

**关键变化：**
- 所有管理端口绑到 `127.0.0.1`，仅本机可访问
- API 端口 `8000` 保持对所有接口开放（Nginx 代理用）
- 资源限制放宽（本机 i7-12700H + 16GB，远强于云服务器）
- ELK 日志可选开启（ES 端口也绑 127.0.0.1）

---

## 运维与监控

### 日常维护

```bash
# 查看所有服务状态
docker compose ps

# 查看资源占用
docker stats

# 查看 API 日志
docker compose logs -f api

# 查看 Nginx 访问日志
type C:\nginx\logs\access.log

# 查看 ELK（通过 Kibana）
# 浏览器访问 http://localhost:5601（本机）或 Tailscale IP
```

### 自动重启策略

所有 Docker 服务已配置 `restart: unless-stopped`，Docker Desktop 重启后自动恢复。

Nginx 已设为开机自启计划任务。

### 本机特有监控脚本

创建 `C:\scripts\health_check.ps1`（PowerShell 脚本），定期检查：

```powershell
# 健康检查脚本，可通过计划任务每 5 分钟执行
$services = @(
    @{Name="API"; Url="http://localhost:8000/health"},
    @{Name="Kibana"; Url="http://localhost:5601/api/status"}
)

$allOk = $true
foreach ($svc in $services) {
    try {
        $response = Invoke-WebRequest -Uri $svc.Url -TimeoutSec 5
        $status = $response.StatusCode
    } catch {
        $status = "DOWN"
    }

    if ($status -ne 200) {
        Write-Host "[WARN] $($svc.Name) 状态异常: $status"
        $allOk = $false
    } else {
        Write-Host "[OK] $($svc.Name) 运行正常"
    }
}

if (-not $allOk) {
    # 可以通过邮件/钉钉/企业微信发送告警
    # 或者弹出系统通知
    # 或者重启 Docker 服务
}
```

### 省电与散热建议

| 措施 | 说明 |
|------|------|
| **合盖运行** | 电源设置中关闭"合盖操作"为睡眠 |
| **散热架** | 笔记本竖放或架高，避免底部积热 |
| **CPU 限频** | 电源计划设为"平衡"而非"高性能"，降低待机功耗 |
| **禁用独显** | 在设备管理器中禁用 RTX 独显（如果不需要 GPU 加速），可省 30-50W |
| **定时开关机** | BIOS 中设置定时开机，配合 WoL 远程唤醒 |
| **UPS 不间断电源** | 防止突然断电损坏硬件 |

---

## 安全注意事项（重要）

本机暴露到外网比云服务器风险更高，因为攻击者可能攻入你的家庭网络：

| 风险 | 缓解措施 |
|------|---------|
| **端口暴露** | 只转发 Nginx 的 80/443 端口到外网，其他全部内网 |
| **DDoS 攻击** | Nginx 配置 `limit_req` 限流；家庭宽带抗不了大流量 |
| **IP 泄露** | 使用 DDNS 域名而非直接暴露 IP；域名可随时更换 |
| **内网横向渗透** | 如果服务被攻破，攻击者可访问家庭内网其他设备 |
| **数据备份** | 本地单点故障 — 必须定期备份到外部硬盘或云存储 |

**最低安全基线**：
1. ✅ 只转发 80/443 端口
2. ✅ Nginx 配置 HTTPS（Let's Encrypt）
3. ✅ 使用 Tailscale 作为远程管理通道（不开放 RDP 到外网）
4. ✅ 所有管理端口绑定 `127.0.0.1`
5. ✅ 修改所有默认密码（MinIO、Neo4j、Admin）
6. ✅ 定期更新 Docker 镜像

---

## 本机方案 vs 云服务器方案对比

| 维度 | 本机方案 | 云服务器方案 |
|------|---------|------------|
| **月费用** | 电费 ~¥50-100/月 | ¥400-800/月 |
| **性能** | i7-12700H / 16G / 1TB NVMe | 4C / 16G / 100GB SSD |
| **GPU 加速** | ✅ 可选 RTX GPU | ❌ 需要额外费用 |
| **外网稳定性** | ❌ 依赖家庭宽带质量 | ✅ SLA 99.9% |
| **公网 IP** | ❌ 动态 IP，需 DDNS | ✅ 固定公网 IP |
| **7×24 运行** | ❌ 笔记本不易长期开机 | ✅ 专业机房环境 |
| **散热/噪音** | ❌ 风扇噪音、积热 | ✅ 无需操心 |
| **安全风险** | ❌ 可能波及家庭网络 | ✅ 独立环境 |
| **数据安全** | ❌ 单点故障 | ✅ 可多地备份 |
| **弹性扩容** | ❌ 硬件固定 | ✅ 一键升级配置 |
| **备案要求** | ❌ 本机不需要 ICP 备案 | ⚠️ 国内服务器需备案 |

### 推荐决策流程

```
需要对外服务？
├── 是
│   ├── 商业服务 / 有用户量 → 云服务器
│   ├── 个人项目 / 自己用 → 本机 + DDNS
│   └── 无公网 IP → 本机 + frp 穿透（或 Tailscale）
└── 否（仅内网使用）
    └── 本机直跑，最省事
```

---

## 完整部署流程总结

```
1. 确认 Docker 运行正常（已完成）
   └── docker compose ps 检查所有服务状态

2. 配置外网访问（根据需求选择）
   ├── 仅内网 → 跳过这步
   ├── DDNS → 注册域名 + 安装 ddns-go
   └── frp 穿透 → 购买轻量云服务器 + 配置 frp

3. Windows 防火墙放行端口
   └── 80, 443（Nginx），8000（API 可选）

4. 安装并配置 Nginx（Windows 原生）
   └── 下载 Nginx → 配置 conf → 启动

5. 申请 HTTPS 证书
   └── Certify The Web 或 acme.sh

6. 路由器端口转发
   └── 80 → 本机，443 → 本机

7. 配置开机自启
   └── Docker Desktop、Nginx、DDNS、电源设置

8. 配置远程管理
   └── Tailscale 组网（强烈推荐）

9. 安全加固
   └── 修改密码、关闭不需要的端口

10. 测试验证
    └── 外网访问 https://tcm.yourdomain.com/docs
    └── 聊天测试 POST /api/chat
```

---

## 总结

**本机完全可以代替云服务器**，而且性能更强、零月费。核心要点：

- ✅ **直接跑 Docker Compose**，配置几乎不需要改
- ✅ **DDNS + 端口转发**解决外网访问（约 ¥30-50/年域名费）
- ✅ **Tailscale** 解决远程管理（免费、安全、简单）
- ✅ **Nginx + Let's Encrypt** 搞定反向代理和 HTTPS
- ✅ **电源设置 + 计划任务**保证服务持续运行
- ⚠️ 不适合商业 SLA 级服务，不适合无公网 IP 的宽带
- ⚠️ 安全风险需注意，不要暴露管理端口到外网

**如果只需要内网使用（同 WiFi 下手机、平板、其他电脑访问），完全零成本，直接开跑就行。**

---

**相关文档：**
- [cloud_deployment.md](cloud_deployment.md) — 云服务器部署方案（与本方案互为补充）
- [DOCKER.md](../DOCKER.md) — Docker 本地部署说明
