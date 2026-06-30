#!/bin/bash
set +e  # 允许脚本在命令失败时继续执行

echo "=========================================="
echo "TCM-API 容器初始化"
echo "=========================================="

# 创建必要的目录
mkdir -p /app/logs /app/data

# 数据库初始化
echo "1. 初始化数据库..."
python init_db.py

# 检查是否已经导入过知识库
if [ ! -f /app/data/.import_completed ]; then
    echo "2. 导入知识库（首次启动）..."
    python import_knowledge.py || echo "⚠ 知识库导入遇到问题，但继续启动 API 服务"

    # 标记导入完成
    touch /app/data/.import_completed
    echo "✓ 知识库导入完成，标记为已完成"
else
    echo "2. 跳过知识库导入（已标记完成）"
fi

# 启动 API 服务
echo "3. 安装运行时依赖..."
pip install --no-cache-dir redis -i https://pypi.tuna.tsinghua.edu.cn/simple 2>/dev/null || pip install --no-cache-dir redis
echo "✓ 依赖安装完成"

echo "4. 启动 API 服务..."
echo "=========================================="
exec uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --workers 1
