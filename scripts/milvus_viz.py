"""
Milvus 可视化脚本
提供一个简单的 Web 界面来查看 Milvus 中的向量数据
"""
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from datetime import datetime
import logging

try:
    from pymilvus import connections, utility, Collection
    HAS_MILVUS = True
except ImportError:
    HAS_MILVUS = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Milvus 可视化", description="Milvus 向量数据可视化工具")

class CollectionInfo(BaseModel):
    name: str
    description: str
    num_entities: int
    dimension: int
    status: str

class Entity(BaseModel):
    id: str
    score: float
    entity: Dict[str, Any]

@app.get("/", response_model=HTMLResponse)
async def root():
    """主页"""
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Milvus 可视化</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body {
                font-family: Arial, sans-serif;
                background: #f5f5f5;
                padding: 20px;
            }
            .container {
                max-width: 1200px;
                margin: 0 auto;
                background: white;
                padding: 30px;
                border-radius: 10px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            }
            h1 { color: #333; margin-bottom: 30px; }
            .info {
                background: #e3f2fd;
                padding: 15px;
                border-radius: 5px;
                margin-bottom: 30px;
            }
            .stats {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 20px;
                margin-bottom: 30px;
            }
            .stat-card {
                background: #f8f9fa;
                padding: 20px;
                border-radius: 5px;
                border-left: 4px solid #2196F3;
            }
            .stat-card h3 {
                font-size: 14px;
                color: #666;
                margin-bottom: 5px;
            }
            .stat-card .value {
                font-size: 28px;
                font-weight: bold;
                color: #333;
            }
            .action-buttons {
                margin-bottom: 30px;
            }
            .action-buttons button {
                background: #2196F3;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 5px;
                cursor: pointer;
                margin-right: 10px;
                font-size: 14px;
            }
            .action-buttons button:hover {
                background: #1976D2;
            }
            table {
                width: 100%;
                border-collapse: collapse;
                margin-top: 20px;
            }
            th, td {
                padding: 12px 15px;
                text-align: left;
                border-bottom: 1px solid #ddd;
            }
            th {
                background: #f5f5f5;
                font-weight: 600;
            }
            tr:hover {
                background: #f9f9f9;
            }
            .badge {
                display: inline-block;
                padding: 4px 8px;
                border-radius: 4px;
                font-size: 12px;
                background: #4CAF50;
                color: white;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>📊 Milvus 向量数据可视化</h1>

            <div class="info">
                <strong>系统状态:</strong> <span id="system-status">加载中...</span>
                <br><br>
                <strong>访问时间:</strong> <span id="current-time"></span>
            </div>

            <div class="stats">
                <div class="stat-card">
                    <h3>集合名称</h3>
                    <div class="value" id="collection-name">-</div>
                </div>
                <div class="stat-card">
                    <h3>向量数量</h3>
                    <div class="value" id="vector-count">-</div>
                </div>
                <div class="stat-card">
                    <h3>向量维度</h3>
                    <div class="value" id="vector-dimension">-</div>
                </div>
            </div>

            <div class="action-buttons">
                <button onclick="loadCollections()">刷新数据</button>
                <button onclick="downloadJSON()">导出 JSON</button>
            </div>

            <h2>📊 向量数据列表</h2>
            <table>
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>相似度</th>
                        <th>元数据</th>
                    </tr>
                </thead>
                <tbody id="data-table">
                    <tr>
                        <td colspan="3">点击"刷新数据"按钮加载</td>
                    </tr>
                </tbody>
            </table>
        </div>

        <script>
            function updateTime() {
                const now = new Date();
                document.getElementById('current-time').textContent =
                    now.toLocaleString('zh-CN');
            }

            function loadCollections() {
                fetch('/api/collections')
                    .then(response => response.json())
                    .then(data => {
                        if (data.num_entities) {
                            document.getElementById('collection-name').textContent =
                                data.name || 'tcm_knowledge_base';
                            document.getElementById('vector-count').textContent =
                                data.num_entities;
                            document.getElementById('vector-dimension').textContent =
                                data.dimension;
                            document.getElementById('system-status').innerHTML =
                                '<span class="badge">运行正常</span>';
                        } else {
                            document.getElementById('system-status').innerHTML =
                                '<span style="color: red;">连接失败</span>';
                        }
                    })
                    .catch(error => {
                        console.error('Error:', error);
                        document.getElementById('system-status').innerHTML =
                            '<span style="color: red;">连接失败</span>';
                    });
            }

            function loadEntities(collectionName) {
                fetch(\`/api/entities/\${collectionName}\`)
                    .then(response => response.json())
                    .then(data => {
                        const tbody = document.getElementById('data-table');
                        if (data.entities && data.entities.length > 0) {
                            tbody.innerHTML = data.entities.map(entity => {
                                const metadata = JSON.stringify(entity.entity)
                                    .replace(/[{}"]/g, '')
                                    .substring(0, 100);
                                return \`<tr>
                                    <td>\${entity.id}</td>
                                    <td>\${entity.score.toFixed(4)}</td>
                                    <td>\${metadata}...</td>
                                </tr>\`;
                            }).join('');
                        } else {
                            tbody.innerHTML = '<tr><td colspan="3">暂无数据</td></tr>';
                        }
                    });
            }

            function downloadJSON() {
                fetch('/api/json')
                    .then(response => response.json())
                    .then(data => {
                        const blob = new Blob([JSON.stringify(data, null, 2)],
                            { type: 'application/json' });
                        const url = URL.createObjectURL(blob);
                        const a = document.createElement('a');
                        a.href = url;
                        a.download = 'milvus_data.json';
                        a.click();
                    });
            }

            // 初始化
            updateTime();
            setInterval(updateTime, 1000);
            loadCollections();
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@app.get("/api/health", response_model=Dict[str, str])
async def health():
    """健康检查"""
    if not HAS_MILVUS:
        raise HTTPException(status_code=500, detail="pymilvus 未安装")
    return {"status": "healthy"}

@app.get("/api/collections", response_model=Dict[str, Any])
async def get_collections():
    """获取集合信息"""
    if not HAS_MILVUS:
        raise HTTPException(status_code=500, detail="pymilvus 未安装")

    try:
        # 连接到 Milvus
        connections.connect(host="milvus", port="19530")

        # 获取所有集合
        collections = utility.list_collections()

        if not collections:
            return {
                "name": "tcm_knowledge_base",
                "description": "中草药知识库",
                "num_entities": 0,
                "dimension": 1024,
                "status": "empty"
            }

        # 获取第一个集合的信息
        collection_name = collections[0]
        collection = Collection(collection_name)

        # 获取统计信息
        stats = collection.num_entities

        # 获取维度
        schema = collection.schema
        dimension = schema.fields[1].type_params[0] if schema.fields else 0

        return {
            "name": collection_name,
            "description": "中草药知识库",
            "num_entities": stats,
            "dimension": dimension,
            "status": "active"
        }

    except Exception as e:
        logger.error(f"获取集合信息失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        connections.disconnect("default")

@app.get("/api/entities/{collection_name}", response_model=Dict[str, Any])
async def get_entities(collection_name: str, limit: int = 10):
    """获取实体数据"""
    if not HAS_MILvUS:
        raise HTTPException(status_code=500, detail="pymilvus 未安装")

    try:
        connections.connect(host="milvus", port="19530")

        collection = Collection(collection_name)
        entities = []

        # 随机采样
        collection.load()
        results = collection.query(
            expr="id >= 0",
            output_fields=["*"],
            limit=limit
        )

        for result in results:
            entities.append({
                "id": str(result.get("id", "")),
                "score": 1.0,  # 简化处理，不计算相似度
                "entity": result
            })

        return {
            "collection": collection_name,
            "count": len(entities),
            "entities": entities
        }

    except Exception as e:
        logger.error(f"获取实体数据失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        connections.disconnect("default")

@app.get("/api/json")
async def download_json():
    """导出所有数据为 JSON"""
    if not HAS_MILvUS:
        raise HTTPException(status_code=500, detail="pymilvus 未安装")

    try:
        connections.connect(host="milvus", port="19530")

        collections = utility.list_collections()
        all_data = {}

        for collection_name in collections:
            collection = Collection(collection_name)
            results = collection.query(
                expr="id >= 0",
                output_fields=["*"],
                limit=50  # 限制数量
            )

            all_data[collection_name] = {
                "num_entities": collection.num_entities,
                "dimension": collection.schema.fields[1].type_params[0] if collection.schema.fields else 0,
                "data": results
            }

        return all_data

    except Exception as e:
        logger.error(f"导出 JSON 失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        connections.disconnect("default")

if __name__ == "__main__":
    logger.info("🚀 Milvus 可视化服务启动: http://localhost:3000")
    uvicorn.run(app, host="0.0.0.0", port=3000)
