# 使用 Python 3.10 官方镜像作为基础
FROM python:3.10-slim

# 设置工作目录
WORKDIR /app

# 设置环境变量
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV TZ=Asia/Shanghai

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# 升级 pip
RUN pip install --upgrade pip

# 单独安装 CPU 版本的 PyTorch（避免下载 CUDA 包）
RUN pip install --no-cache-dir torch==2.5.1+cpu --index-url https://download.pytorch.org/whl/cpu

# 复制依赖文件
COPY requirements.txt .

# 安装 Python 依赖（允许重试，避免哈希校验失败）
RUN pip install --no-cache-dir -r requirements.txt || \
    pip install --no-cache-dir -r requirements.txt || \
    pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY src/ ./src/
COPY static/ ./static/
COPY init_db.py data_init.py import_knowledge.py ./scripts/
COPY scripts/milvus_viz.py /app/milvus_viz.py

# 创建必要的目录
RUN mkdir -p /app/logs /app/data/knowledge_base

# 暴露端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# 启动脚本：只启动 API 服务，导入由 init.sh 控制
COPY scripts/init.sh /app/init.sh
RUN chmod +x /app/init.sh
CMD ["/app/init.sh"]
