#!/bin/sh
# 启动脚本：初始化数据库并导入知识库

echo "============================================================"
echo "数据库初始化..."
echo "============================================================"

python init_db.py

echo ""
echo "============================================================"
echo "检查知识库文件..."
echo "============================================================"

# 检查知识库目录
KNOWLEDGE_DIR="/app/data/knowledge_base"
if [ -d "$KNOWLEDGE_DIR" ]; then
    # 统计文件数量
    TXT_COUNT=$(find "$KNOWLEDGE_DIR" -type f -name "*.txt" | wc -l)
    JSON_COUNT=$(find "$KNOWLEDGE_DIR" -type f -name "*.json" | wc -l)
    MD_COUNT=$(find "$KNOWLEDGE_DIR" -type f -name "*.md" | wc -l)
    TOTAL_COUNT=$((TXT_COUNT + JSON_COUNT + MD_COUNT))

    echo "找到 $TOTAL_COUNT 个知识库文件（TXT: $TXT_COUNT, JSON: $JSON_COUNT, MD: $MD_COUNT）"

    if [ "$TOTAL_COUNT" -gt 0 ]; then
        echo ""
        echo "============================================================"
        echo "开始导入知识库..."
        echo "============================================================"

        # 调用 API 导入所有文件
        for file in $(find "$KNOWLEDGE_DIR" -type f \( -name "*.txt" -o -name "*.json" -o -name "*.md" \)); do
            REL_PATH="${file#$KNOWLEDGE_DIR/}"
            echo "  - 导入: $REL_PATH"

            curl -X POST http://localhost:8000/api/knowledge/import \
                -H "Content-Type: multipart/form-data" \
                -F "file_path=$REL_PATH" \
                -F "chunk_size=500" \
                -F "overlap=50" 2>&1 | grep -q "成功" && echo "    ✓" || echo "    ✗"
        done

        echo ""
        echo "============================================================"
        echo "知识库导入完成"
        echo "============================================================"
    fi
else
    echo "知识库目录不存在: $KNOWLEDGE_DIR"
fi

echo ""
echo "============================================================"
echo "启动 API 服务..."
echo "============================================================"

uvicorn src.api.main:app --host 0.0.0.0 --port 8000
