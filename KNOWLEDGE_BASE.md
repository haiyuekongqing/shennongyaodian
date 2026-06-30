# 知识库导入指南

本文档详细说明如何为中草药 Agent 系统导入各类知识库数据。

## 目录

- [1. 数据库架构](#1-数据库架构)
- [2. 知识库分类](#2-知识库分类)
- [3. 向量数据导入](#3-向量数据导入)
- [4. 图谱数据导入](#4-图谱数据导入)
- [5. 常见问题](#5-常见问题)

---

## 1. 数据库架构

### 1.1 向量数据库

**Milvus 数据集**:
- **集合名称**: `tcm_knowledge_base`
- **向量维度**: 1024 (BGE-M3)
- **索引类型**: HNSW（推荐） / IVF_FLAT
- **度量类型**: IP (内积相似度)

**字段结构**:
```python
{
    "id": 1,                    # 主键（自增）
    "embedding": [0.1, 0.2, ...],  # 向量
    "chunk_id": 0,              # 分块ID
    "source_file": "黄芪.txt",  # 来源文件
    "file_type": "drug",        # 文件类型
    "position": {               # 块位置
        "line_start": 1,
        "line_end": 5
    },
    "content": "黄芪是微温的药..."  # 文本内容
}
```

### 1.2 图数据库

**Neo4j 数据集**:
- **节点类型**: Disease, Drug, Ingredient, Formula, Symptom, Food, Check, Department, Producer
- **关系类型**: HAS_SYMPTOM, TREATS_WITH, COMPATIBLE_WITH, NEEDS_CHECK, CONTAINS, PREVENTION, INTERACTION_WITH 等
- **属性**: name, desc, nature, taste, meridian, effects 等

---

## 2. 知识库分类

### 2.1 知识库文件结构

```
data/knowledge_base/
├── ancient_treatises/          # 中医古籍
│   ├── 内经.txt
│   ├── 伤寒论.txt
│   └── 金匮要略.txt
│
├── chinese_pharmacopedia/      # 中国药典
│   ├── 药典目录.txt
│   └── 常用中药.txt
│
├── medical_cases/              # 医案
│   ├── 医案1.txt
│   └── 医案2.txt
│
├── medical.json                # 结构化数据（图谱）
│   [
│       {
│           "name": "黄芪",
│           "nature": "微温",
│           "taste": "甘",
│           "meridian": "归脾、肺经",
│           "effects": ["补气固表", "利尿托毒"],
│           "contraindications": ["表实邪盛", "阴虚阳亢"]
│       }
│   ]
│
└── QASystemOnMedicalKG/        # 医疗知识图谱（参考）
    └── medical.json
```

### 2.2 文件类型标识

- **药典文件**: `file_type: "pharmacopedia"`
- **古籍文件**: `file_type: "treatise"`
- **医案文件**: `file_type: "case"`
- **结构化数据**: `file_type: "structured"`
- **图谱数据**: `file_type: "graph"`

---

## 3. 数据导入流程

### 3.1 方式一：通过 API 导入（推荐）

#### 3.1.1 批量导入非结构化数据

```bash
# 导入古籍数据
curl -X POST http://localhost:8000/api/knowledge/batch-import \
  -H "Content-Type: application/json" \
  -d '{
    "directory": "ancient_treatises",
    "chunk_size": 500,
    "overlap": 50,
    "file_types": ["treatise"]
  }'

# 导入药典数据
curl -X POST http://localhost:8000/api/knowledge/batch-import \
  -H "Content-Type: application/json" \
  -d '{
    "directory": "chinese_pharmacopedia",
    "chunk_size": 500,
    "overlap": 50,
    "file_types": ["pharmacopedia"]
  }'

# 导入医案数据
curl -X POST http://localhost:8000/api/knowledge/batch-import \
  -H "Content-Type: application/json" \
  -d '{
    "directory": "medical_cases",
    "chunk_size": 500,
    "overlap": 50,
    "file_types": ["case"]
  }'
```

**请求参数**:
- `directory`: 知识库目录
- `chunk_size`: 分块大小（字符数）
- `overlap`: 重叠大小（字符数）
- `file_types`: 文件类型列表

**响应示例**:
```json
{
  "success": true,
  "message": "导入成功",
  "statistics": {
    "total_files": 3,
    "total_chunks": 1234,
    "total_vectors": 1234
  }
}
```

#### 3.1.2 导入结构化数据（到图数据库）

```bash
curl -X POST http://localhost:8000/api/graph/import \
  -H "Content-Type: application/json" \
  -d '{
    "file": "medical.json",
    "entity_types": ["Drug", "Disease", "Formula"],
    "mode": "full_import"
  }'
```

**请求参数**:
- `file`: JSON文件路径
- `entity_types`: 实体类型列表（可选，默认全部）
- `mode`: 导入模式（full_import/append）

### 3.2 方式二：通过异步任务 API 导入（推荐）

> 异步方式不阻塞 API 服务，支持多文件上传和进度追踪。

#### 异步导入知识库（古籍/药典/医案）

```bash
# 异步导入（文件路径方式）
curl -X POST http://localhost:8000/api/tasks/import-knowledge \
  -H "Content-Type: application/json" \
  -d '{
    "file_paths": ["ancient_treatises/伤寒论.txt", "chinese_pharmacopedia/黄芪.txt"],
    "chunk_size": 500,
    "overlap": 50
  }'
# 返回: {"success": true, "data": {"task_id": "task_xxx", "status": "pending", ...}}

# 查询导入进度
curl http://localhost:8000/api/tasks/task_xxx
# 返回: {"success": true, "data": {"status": "running", "message": "正在导入 (1/2): ...", ...}}

# 异步上传导入（支持多文件）
curl -X POST http://localhost:8000/api/tasks/upload-knowledge \
  -F "files=@/path/to/伤寒论.txt" \
  -F "files=@/path/to/金匮要略.txt"
```

#### 异步导入图谱

```bash
# 异步导入图谱
curl -X POST http://localhost:8000/api/tasks/import-graph \
  -H "Content-Type: application/json" \
  -d '{
    "file_path": "medical.json",
    "mode": "full_import",
    "entity_types": ["Drug", "Disease", "Symptom"]
  }'

# 异步上传图谱
curl -X POST http://localhost:8000/api/tasks/upload-graph \
  -F "file=@medical.json" \
  -F "mode=full_import"
```

#### 任务通知查询

```bash
# 查询最近任务列表（用于通知中心）
GET /api/tasks?limit=20
```

### 3.3 方式三：通过脚本导入

#### 3.2.1 导入非结构化数据

```bash
# 使用 Python 脚本导入
python data_init.py
```

**data_init.py 内容**:
```python
import os
from src.retrieval.vector_store import VectorStore
from src.graph_importer import Neo4jImporter

# 初始化向量存储
vector_store = VectorStore()

# 导入目录
directories = [
    "data/knowledge_base/ancient_treatises",
    "data/knowledge_base/chinese_pharmacopedia",
    "data/knowledge_base/medical_cases"
]

for directory in directories:
    print(f"导入目录: {directory}")
    vector_store.batch_import_directory(
        directory=directory,
        chunk_size=500,
        overlap=50
    )

print("✓ 导入完成！")
```

#### 3.2.2 导入图数据库数据

```bash
# 导入图谱数据
python src/graph_importer.py --file data/medical.json --types Drug Disease Formula
```

**src/graph_importer.py 内容**:
```python
import json
from neo4j import GraphDatabase

class Neo4jImporter:
    def __init__(self, uri="bolt://localhost:7687",
                 user="neo4j", password="your_password"):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def import_medical_json(self, file_path, entity_types=None):
        """导入医疗 JSON 数据到 Neo4j"""

        # 读取 JSON
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # 解析实体和关系
        entities, relations = self.parse_medical_data(data, entity_types)

        # 导入到 Neo4j
        with self.driver.session() as session:
            # 创建节点
            session.run("""
                UNWIND $entities as e
                MERGE (n:{e.type} {name: e.name})
                SET n += e.properties
            """, entities=entities)

            # 创建关系
            session.run("""
                UNWIND $relations as r
                MATCH (a:{r.source_type} {name: r.source})
                MATCH (b:{r.target_type} {name: r.target})
                MERGE (a)-[:{r.type}]->(b)
            """, relations=relations)

        print(f"✓ 导入完成: {len(entities)} 个节点, {len(relations)} 条关系")

    def parse_medical_data(self, data, entity_types):
        """解析医疗数据"""
        entities = []
        relations = []

        for item in data:
            # 识别实体类型
            entity_type = self._detect_entity_type(item)

            if entity_types is None or entity_type in entity_types:
                # 创建实体节点
                entity = {
                    "type": entity_type,
                    "name": item.get("name"),
                    "properties": item.get("properties", {})
                }
                entities.append(entity)

                # 创建关系
                for prop_name, prop_value in item.get("properties", {}).items():
                    relation = {
                        "source_type": entity_type,
                        "target_type": self._map_property_to_type(prop_name),
                        "source": item["name"],
                        "target": str(prop_value),
                        "type": self._map_property_to_relation(prop_name)
                    }
                    relations.append(relation)

        return entities, relations

    def _detect_entity_type(self, item):
        """检测实体类型"""
        # 这里可以根据数据特征判断
        # 例如：包含"药"字 -> Drug，包含"症"字 -> Symptom
        name = item.get("name", "")
        if any(kw in name for kw in ["药", "方剂", "成分"]):
            return "Drug"
        elif any(kw in name for kw in ["症", "痛"]):
            return "Symptom"
        else:
            return "Entity"

    def _map_property_to_type(self, prop_name):
        """映射属性到实体类型"""
        # 这里需要根据实际数据结构调整
        return "Property"

    def _map_property_to_relation(self, prop_name):
        """映射属性到关系类型"""
        # 这里需要根据实际数据结构调整
        return "HAS_PROPERTY"

# 使用示例
if __name__ == "__main__":
    importer = Neo4jImporter()
    importer.import_medical_json(
        file_path="data/medical.json",
        entity_types=["Drug", "Disease", "Formula"]
    )
```

### 3.3 方式三：手动导入单个文件

```bash
# 导入单个文件
curl -X POST http://localhost:8000/api/knowledge/import \
  -H "Content-Type: multipart/form-data" \
  -F "file=@data/knowledge_base/黄芪.txt" \
  -F "directory=chinese_pharmacopedia" \
  -F "chunk_size=500"
```

---

## 4. 图谱数据导入

### 4.1 完整图谱数据

**数据来源**: `data/medical.json` 或参考 `QASystemOnMedicalKG/medical.json`

**数据规模**:
- 实体数量: 4.4万
- 关系数量: 30万

**数据格式**:
```json
[
  {
    "name": "糖尿病",
    "type": "Disease",
    "properties": {
      "desc": "一种比较常见的内分泌代谢性疾病",
      "cause": "胰岛素分泌不足...",
      "prevention": "注意饮食控制...",
      "symptoms": ["多饮", "多尿", "多食"],
      "cure_way": ["药物治疗", "饮食控制"],
      "cured_prob": 30,
      "easy_get": ["肥胖人群", "有家族史"]
    }
  },
  {
    "name": "黄芪",
    "type": "Drug",
    "properties": {
      "nature": "微温",
      "taste": "甘",
      "meridian": "归脾、肺经",
      "effects": ["补气固表", "利尿托毒"],
      "contraindications": ["表实邪盛", "阴虚阳亢"]
    }
  }
]
```

### 4.2 导入步骤

#### 步骤 1: 准备数据

确保数据格式正确：
1. 检查 JSON 文件是否存在
2. 验证数据格式是否符合要求
3. 备份原始数据

#### 步骤 2: 启动 Neo4j

```bash
# 启动 Neo4j 容器
docker-compose up -d neo4j

# 检查 Neo4j 状态
docker logs neo4j

# 访问 Neo4j Browser
# http://localhost:7474
# 用户名: neo4j
# 密码: your_password
```

#### 步骤 3: 导入数据

**方式 A: 通过 API**
```bash
curl -X POST http://localhost:8000/api/graph/import \
  -H "Content-Type: application/json" \
  -d '{
    "file": "data/medical.json",
    "entity_types": ["Drug", "Disease", "Formula", "Symptom", "Ingredient"],
    "mode": "full_import"
  }'
```

**方式 B: 通过脚本**
```bash
python src/graph_importer.py \
  --file data/medical.json \
  --types Drug Disease Formula Symptom Ingredient \
  --driver-uri bolt://localhost:7687 \
  --driver-user neo4j \
  --driver-password your_password
```

#### 步骤 4: 验证导入

**通过 Neo4j Browser 查询**:
1. 访问 http://localhost:7474
2. 执行 Cypher 查询验证：

```cypher
// 查询节点数量
MATCH (n)
RETURN labels(n) as type, count(n) as count
ORDER BY count DESC;

// 查询节点示例
MATCH (d:Disease {name: "糖尿病"})
RETURN d;

// 查询关系示例
MATCH (d:Disease)-[:HAS_SYMPTOM]->(s:Symptom)
RETURN d.name as disease, s.name as symptom
LIMIT 10;

// 查询图谱统计
MATCH (n)
WITH labels(n)[0] as type, count(n) as count
RETURN type, count;
```

**通过 API 查询**:
```bash
# 获取图谱统计
curl http://localhost:8000/api/graph/stats

# 查询节点
curl -X POST http://localhost:8000/api/graph/query \
  -H "Content-Type: application/json" \
  -d '{"entity_type": "Drug", "name": "黄芪"}'

# 多跳查询
curl -X POST http://localhost:8000/api/graph/multi-hop \
  -H "Content-Type: application/json" \
  -d '{"start_entity": "乏力", "hop_count": 3}'
```

### 4.3 图谱维护

#### 更新数据

```bash
# 添加新数据（追加模式）
curl -X POST http://localhost:8000/api/graph/import \
  -H "Content-Type: application/json" \
  -d '{
    "file": "data/new_medical.json",
    "mode": "append"
  }'
```

#### 清空数据

```bash
# ⚠️ 警告：此操作不可恢复！
curl -X DELETE http://localhost:8000/api/graph/clear
```

#### 导出数据

```bash
# 导出图谱为 JSON
curl -X GET http://localhost:8000/api/graph/export \
  -H "Content-Type: application/json" \
  -d '{"entity_types": ["Drug"], "limit": 100}'
```

---

## 5. 常见问题

### 5.1 导入失败

**问题**: 导入时出现错误

**解决方案**:
1. 检查数据文件格式是否正确
2. 验证 JSON 文件是否完整
3. 检查数据库连接状态
4. 查看日志文件：`docker logs tcm-api`

### 5.2 向量检索无结果

**问题**: 导入后向量检索返回空结果

**解决方案**:
1. 检查 Milvus 索引是否创建成功
2. 查看集合统计：`GET /api/milvus/collections`
3. 检查 Embedding 模型是否正常
4. 尝试不同的查询词

### 5.3 图谱查询无结果

**问题**: 图谱查询返回空结果

**解决方案**:
1. 检查 Neo4j 状态：`docker logs neo4j`
2. 验证数据是否导入成功：访问 Neo4j Browser
3. 检查 Cypher 查询语法
4. 查询图谱统计：`GET /api/graph/stats`

### 5.4 性能问题

**问题**: 导入速度慢

**解决方案**:
1. 使用批量导入（API 方式）
2. 减小 chunk_size
3. 使用并行导入多个目录
4. 监控系统资源使用情况

---

## 6. 最佳实践

### 6.1 数据准备

1. **数据质量**: 确保数据准确、完整、格式正确
2. **数据量**: 适度控制数据规模（建议 < 10万向量）
3. **文件类型**: 明确标识文件类型
4. **命名规范**: 使用规范的文件名

### 6.2 导入策略

1. **增量导入**: 定期更新知识库
2. **批量处理**: 使用批量 API 提升效率
3. **数据备份**: 导入前备份数据
4. **验证检查**: 导入后验证数据完整性

### 6.3 维护建议

1. **定期备份**: 定期备份 Neo4j 和 Milvus 数据
2. **索引优化**: 定期重建索引
3. **监控告警**: 监控系统性能和错误
4. **日志分析**: 定期分析查询日志

---

## 7. 相关资源

- [Milvus 官方文档](https://milvus.io/docs)
- [Neo4j 官方文档](https://neo4j.com/docs)
- [Architectures.md](ARCHITECTURE.md)
- [README.md](README.md)
- [性能优化方案](tasks/task1.md)
- [混合检索架构](tasks/task2.md)

---

**更新时间**: 2026-06-10
**版本**: v2.0
