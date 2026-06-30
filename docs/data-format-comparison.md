# 数据格式对比与导入说明

## 概述

本项目涉及两种不同格式的医疗数据：`KNOWLEDGE_BASE.md` 中定义的标准格式，以及从 [QASystemOnMedicalKG](https://github.com/liuhuanyong/QABasedOnMedicalKnowledgeGraph) 项目获取的 `QASystemOnMedicalKG/medical.json` 实际数据。本文档详细说明两者的差异，以及系统是如何处理这种差异完成导入的。

---

## 一、标准格式（KNOWLEDGE_BASE.md 定义）

### 文件结构

标准格式预期数据为 **JSON 数组**，用方括号包裹多个实体对象：

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
      "meridian": "归脾、肺经"
    }
  }
]
```

### 格式特征

| 特征 | 说明 |
|------|------|
| 整体结构 | `[{...}, {...}, ...]` JSON 数组 |
| 实体标识 | 通过 `type` 字段显式标注（`Disease`, `Drug`, `Symptom` 等） |
| 属性存储 | 所有属性嵌套在 `properties` 对象中 |
| 关系表达 | 通过 `properties` 内的字段名映射为关系类型（如 `symptoms` → `HAS_SYMPTOM`） |
| 层级 | 每个顶层元素对应一个实体节点 |

---

## 二、实际数据格式（QASystemOnMedicalKG/medical.json）

### 文件结构

实际数据为 **JSON Lines** 格式（也称 NDJSON），每行一个独立的 JSON 对象，**不是**数组：

```json
{ "_id": { "$oid": "5bb578b6831b973a137e3ee6" }, "name": "肺泡蛋白质沉积症", "desc": "...", "symptom": ["紫绀", "胸痛"], "acompany": ["多重肺部感染"], ... }
{ "_id": { "$oid": "5bb578b6831b973a137e3ee7" }, "name": "百日咳", "desc": "...", "symptom": ["痉挛性咳嗽"], ... }
```

### 格式特征

| 特征 | 说明 |
|------|------|
| 整体结构 | 每行一个 JSON 对象，无外层数组包裹 |
| 来源 | MongoDB 导出格式，含 `_id.$oid` 字段 |
| 实体标识 | **无**显式 `type` 字段，全部为疾病文档（隐式类型 = Disease） |
| 属性 | **扁平结构**，字段直接在顶层，无 `properties` 嵌套 |
| 关系表达 | 通过 **列表字段** 隐式表达关系（见下表） |
| 层级 | 一个文档 = 一个 Disease 主节点 + 多个关联实体节点 + 多条关系 |

### 字段到关系的映射

以下列表字段在导入时被解析为关系：

| 原字段 | 目标实体类型 | 关系类型 | 含义 |
|--------|-------------|----------|------|
| `symptom` | Symptom | `HAS_SYMPTOM` | 疾病→症状 |
| `acompany` | Disease | `RELATED_TO` | 疾病→并发疾病 |
| `cure_department` | Department | `NEEDS_DEPARTMENT` | 疾病→就诊科室 |
| `common_drug` | Drug | `TREATS_WITH` | 疾病→常用药 |
| `recommand_drug` | Drug | `TREATS_WITH` | 疾病→推荐用药 |
| `drug_detail` | Drug | `TREATS_WITH` | 疾病→药品明细 |
| `check` | Check | `NEEDS_CHECK` | 疾病→检查项目 |
| `do_eat` | Food | `GOOD_FOR` | 疾病→宜吃食物 |
| `recommand_eat` | Food | `GOOD_FOR` | 疾病→推荐食谱 |
| `not_eat` | Food | `BAD_FOR` | 疾病→忌吃食物 |

标量字段（`desc`, `cause`, `prevent`, `cure_way`, `cure_lasttime`, `cured_prob` 等）则作为 Disease 节点的属性存储。

---

## 三、两种格式的直观对比

| 维度 | 标准格式 (KNOWLEDGE_BASE.md) | 实际格式 (QASystemOnMedicalKG) |
|------|-----------------------------|-------------------------------|
| **文件结构** | JSON 数组 `[...]` | JSON Lines（每行一条） |
| **type 字段** | 有，显式标注 | 无，隐式全部为 Disease |
| **properties** | 有，嵌套结构 | 无，全部扁平展开 |
| **关系提取** | 从 properties 字段名映射 | 从列表字段名映射 |
| **MongoDB 痕迹** | 无 | 有 `_id.$oid` |
| **一个文档 → 图节点** | 一个节点 | 一个主节点 + 多个关联节点 |

---

## 四、导入器如何处理格式差异

`MedicalGraphImporter`（`src/graph_importer.py`）在 `import_medical_json()` 方法中自动检测格式：

### 检测逻辑

```
读取文件内容 →
  是否以 '[' 开头？
    ├─ 是 → 标准 JSON 数组格式 → 调用 parse_medical_data()
    └─ 否 → JSON Lines 格式 → 调用 _parse_mongo_json_lines()
```

### JSON Lines 解析流程（`_parse_mongo_json_lines` 方法）

```
每行 JSON 文档
  │
  ├─ 提取 name → Disease 主节点
  │    └─ scalar 字段（desc, cause, prevent...）→ Disease 属性
  │
  ├─ 遍历列表字段（symptom, common_drug...）
  │    │
  │    ├─ 每个列表项 → 创建对应类型实体节点（Symptom, Drug...）
  │    │    └─ 去重：相同 (type, name) 不重复创建
  │    │
  │    └─ Disease ↔ 实体 → 创建关系
  │
  └─ 返回 (实体列表, 关系列表)
```

### 导入优化

导入执行顺序经过优化以提升性能：

1. **清空** 已有数据（full_import 模式）
2. **创建约束/索引**（UNIQUE 约束加速后续节点 MATCH 查询）
3. **批量创建节点**（使用 `MERGE` + 约束，避免重复）
4. **批量创建关系**（使用 `UNWIND` 分组批处理，而非逐条执行）
5. **重新创建约束**（确保一致性）

---

## 五、与本项目（QASystemOnMedicalKG）的差异

| 维度 | 原项目 QASystemOnMedicalKG | 本项目（ShenNongYaoDian） |
|------|---------------------------|--------------------------|
| **数据用途** | 基于知识图谱的疾病问答（18类问题） | 基于 RAG（检索增强生成）的混合检索问答 |
| **图数据库驱动** | `py2neo` | 官方 `neo4j` Python Driver |
| **关系命名** | `has_symptom`, `belongs_to`, `common_drug`（snake_case） | `HAS_SYMPTOM`, `RELATED_TO`, `TREATS_WITH`（UPPER_CASE） |
| **节点创建方式** | 逐条 Node + Relationship 创建 | 批量 MERGE + UNWIND 优化 |
| **实体类型** | 7 类：Disease, Drug, Food, Check, Department, Producer, Symptom | 9 类：Disease, Drug, Ingredient, Formula, Symptom, Food, Check, Department, Producer |
| **问答方式** | 规则匹配 + Cypher 查询 | LLM 意图识别 + 混合检索（向量60% + 图谱40%） |
| **数据采集来源** | 垂直医疗网站结构化数据 | 不直接采集，通过导入接口接收数据 |
| **数据格式要求** | 固定 MongoDB JSON Lines | 支持两种格式（JSON 数组 + JSON Lines） |

### 原项目数据处理方式

原项目 `build_medicalgraph.py` 的处理方式是：

1. 逐行读取 `data/medical.json`
2. 对每行 `json.loads()` 解析为字典
3. 使用 `py2neo` 的 `Node()` 和 `Relationship()` 逐个创建
4. 关系名使用 snake_case（如 `has_symptom`、`common_drug`）
5. 支持完整的 Producer（药品生产商）、Food（食物）实体和关系
6. 执行耗时："导入数据较多，估计需要几个小时"

### 本项目数据处理方式

本项目的处理方式是：

1. 自动检测文件格式（JSON 数组 vs JSON Lines）
2. 通过 `MedicalGraphImporter` 批量解析
3. 使用官方 Neo4j Driver 通过 `MERGE` + `UNWIND` 批量提交
4. 关系名使用大写规范
5. 支持实体类型过滤，只导入指定的实体类型
6. 导入耗时：约 3 分钟完成 35,948 节点 + 304,198 关系

---

## 六、如何准备数据

### 方式 A：按标准格式准备

```json
[
  {
    "name": "疾病/药品名称",
    "type": "Disease",   // 或 Drug, Symptom, Food, Check 等
    "properties": {
      "desc": "描述",
      "cause": "病因",
      // 其他属性...
    }
  }
]
```

### 方式 B：按 JSON Lines 格式准备（兼容）

```json
{ "name": "疾病名", "desc": "...", "symptom": ["症状1", "症状2"], "common_drug": ["药品1"] }
{ "name": "疾病名", "desc": "...", "symptom": ["症状3"], "check": ["检查项1"] }
```

---

## 七、导入命令

```bash
# 标准格式
curl -X POST http://localhost:8000/api/graph/import \
  -H "Content-Type: application/json" \
  -d '{
    "file": "medical.json",
    "entity_types": ["Drug", "Disease", "Symptom"],
    "mode": "full_import"
  }'

# JSON Lines 格式（QASystemOnMedicalKG）
curl -X POST http://localhost:8000/api/graph/import \
  -H "Content-Type: application/json" \
  -d '{
    "file": "QASystemOnMedicalKG/medical.json",
    "entity_types": ["Drug", "Disease", "Symptom", "Food", "Check"],
    "mode": "full_import"
  }'
```

> 导入器会自动检测文件格式，无需手动指定。

---

---

## 八、导入后支持的查询对比

### 8.1 QASystemOnMedicalKG 原项目的查询能力

原项目是一个 **规则驱动的问答系统**，通过意图分类器将自然语言问题映射到 18 种问句类型，每种类型对应固定 Cypher 查询 + 回复模板。

#### 实体属性查询（6 类）

从 Disease 节点读取标量属性，不涉及关系遍历：

| 问句类型 | 含义 | 示例 | Cypher 查询 |
|---------|------|------|-------------|
| `disease_cause` | 疾病病因 | "为什么有人会失眠？" | `MATCH (m:Disease) WHERE m.name='失眠' RETURN m.cause` |
| `disease_prevent` | 预防措施 | "怎么预防肾虚？" | `MATCH (m:Disease) WHERE m.name='肾虚' RETURN m.prevent` |
| `disease_lasttime` | 治疗周期 | "感冒要多久才能好？" | `MATCH (m:Disease) WHERE m.name='感冒' RETURN m.cure_lasttime` |
| `disease_cureway` | 治疗方式 | "高血压要怎么治？" | `MATCH (m:Disease) WHERE m.name='高血压' RETURN m.cure_way` |
| `disease_cureprob` | 治愈概率 | "白血病能治好吗？" | `MATCH (m:Disease) WHERE m.name='白血病' RETURN m.cured_prob` |
| `disease_easyget` | 易感人群 | "什么人容易得高血压？" | `MATCH (m:Disease) WHERE m.name='高血压' RETURN m.easy_get` |
| `disease_desc` | 疾病描述 | "糖尿病" | `MATCH (m:Disease) WHERE m.name='糖尿病' RETURN m.desc` |

#### 关系遍历查询（12 类）

通过关系在有向图中进行一跳或两跳遍历：

| 问句类型 | 含义 | 遍历路径 | Cypher 查询 |
|---------|------|---------|-------------|
| `disease_symptom` | 疾病→症状 | `(d:Disease)-[:has_symptom]->(s:Symptom)` | `MATCH (m:Disease)-[:has_symptom]->(n:Symptom) WHERE m.name='{disease}' RETURN n.name` |
| `symptom_disease` | 症状→疾病 | `(s:Symptom)<-[:has_symptom]-(d:Disease)` | `MATCH (m:Disease)-[:has_symptom]->(n:Symptom) WHERE n.name='{symptom}' RETURN m.name` |
| `disease_acompany` | 疾病→并发症 | `(d:Disease)-[:acompany_with]->(d2:Disease)` | `MATCH (m:Disease)-[:acompany_with]->(n:Disease) WHERE m.name='{disease}' RETURN n.name` |
| `disease_not_food` | 疾病→忌吃 | `(d:Disease)-[:no_eat]->(f:Food)` | `MATCH (m:Disease)-[:no_eat]->(n:Food) WHERE m.name='{disease}' RETURN n.name` |
| `disease_do_food` | 疾病→宜吃 | `(d:Disease)-[:do_eat]->(f:Food)` | `MATCH (m:Disease)-[:do_eat]->(n:Food) WHERE m.name='{disease}' RETURN n.name` |
| `disease_do_food` | 疾病→推荐食谱 | `(d:Disease)-[:recommand_eat]->(f:Food)` | `MATCH (m:Disease)-[:recommand_eat]->(n:Food) WHERE m.name='{disease}' RETURN n.name` |
| `food_not_disease` | 忌吃→疾病 | `(d:Disease)<-[:no_eat]-(f:Food)` | `MATCH (m:Disease)-[:no_eat]->(n:Food) WHERE n.name='{food}' RETURN m.name` |
| `food_do_disease` | 宜吃→疾病 | `(d:Disease)<-[:do_eat]-(f:Food)` | `MATCH (m:Disease)-[:do_eat]->(n:Food) WHERE n.name='{food}' RETURN m.name` |
| `disease_drug` | 疾病→常用药 | `(d:Disease)-[:common_drug]->(dr:Drug)` | `MATCH (m:Disease)-[:common_drug]->(n:Drug) WHERE m.name='{disease}' RETURN n.name` |
| `disease_drug` | 疾病→推荐药 | `(d:Disease)-[:recommand_drug]->(dr:Drug)` | `MATCH (m:Disease)-[:recommand_drug]->(n:Drug) WHERE m.name='{disease}' RETURN n.name` |
| `drug_disease` | 药品→疾病 | `(d:Disease)<-[:common_drug]-(dr:Drug)` | `MATCH (m:Disease)-[:common_drug]->(n:Drug) WHERE n.name='{drug}' RETURN m.name` |
| `disease_check` | 疾病→检查 | `(d:Disease)-[:need_check]->(c:Check)` | `MATCH (m:Disease)-[:need_check]->(n:Check) WHERE m.name='{disease}' RETURN n.name` |
| `check_disease` | 检查→疾病 | `(d:Disease)<-[:need_check]-(c:Check)` | `MATCH (m:Disease)-[:need_check]->(n:Check) WHERE n.name='{check}' RETURN m.name` |

#### 原项目的问答流程

```
用户问句
   │
   ▼
意图分类器（question_classifier.py）
   │
   ▼  识别 18 种问句类型之一
问句解析器（question_parser.py）
   │
   ▼  生成固定格式 Cypher
Neo4j 查询（py2neo Graph.run）
   │
   ▼
回复模板（answer_search.py）
   │
   ▼
格式化答案
```

> 特点：规则固定、无语义理解、查询路径和回复模板硬编码

---

### 8.2 本项目（ShenNongYaoDian）的查询能力

本项目采用 **LLM + 混合检索** 架构，查询方式更加灵活：

#### 方式一：直接 API 查询

通过 REST API 直接操作图谱，适用于调试和集成：

| 端点 | 功能 | 说明 |
|------|------|------|
| `GET /api/graph/stats` | 图谱统计 | 返回节点/关系总数及类型分布 |
| `POST /api/graph/query` | 单实体查询 | 按类型+名称查询实体，返回关联节点和关系 |
| `POST /api/graph/multi-hop` | 多跳遍历 | 指定起点、跳数、关系类型，灵活遍历 |
| `DELETE /api/graph/clear` | 清空图谱 | ⚠️ 危险操作，清空所有数据 |
| `GET /api/graph/export` | 导出图谱 | 导出为 JSON 格式 |

**多跳查询示例** — 这是原项目不具备的能力：

```bash
# 从"乏力"出发，经症状→疾病→用药，3跳内找到所有关联
curl -X POST http://localhost:8000/api/graph/multi-hop \
  -H "Content-Type: application/json" \
  -d '{
    "start_entity": "乏力",
    "hop_count": 3,
    "path_types": ["HAS_SYMPTOM", "TREATS_WITH"]
  }'
```

对应 Cypher：
```cypher
MATCH path = (s:Entity {name: '乏力'})-[:HAS_SYMPTOM|TREATS_WITH*1..3]->(d)
RETURN path, length(path) as hop_count
```

#### 方式二：Neo4jTool 检索工具（供 Agent 内部调用）

`Neo4jTool`（`src/agents/tools/neo4j_tool.py`）封装了图谱检索能力，供 LLM Agent 在问答链中调用：

| 方法 | 功能 | 内部 Cypher |
|------|------|-------------|
| `search_entity(type, name)` | 按类型+名称查询实体 | `MATCH (n:{type} {name: $name}) OPTIONAL MATCH (n)-[r]-(m) RETURN n,r,m` |
| `search_disease_by_symptom(symptom)` | 症状→疾病 | `MATCH (s:Symptom {name: $symptom}) OPTIONAL MATCH (s)-[:HAS_SYMPTOM]->(d:Disease) RETURN s,d` |
| `search_drug_by_disease(disease)` | 疾病→药物 | `MATCH (d:Disease {name: $disease}) OPTIONAL MATCH (d)-[:TREATS_WITH]->(drug:Drug) RETURN d,drug` |
| `multi_hop_query(entity, type, hops, path_types)` | 多跳遍历 | `MATCH path = (s:{type} {name: $entity})-[:{path_types}*1..{hops}]->(d) RETURN path` |
| `get_graph_stats()` | 图谱统计 | `MATCH (n) RETURN count(n) ... MATCH ()-[r]->() RETURN count(r)` |

#### 方式三：自然语言问答（混合检索）

用户直接输入自然语言，系统自动决定是否查询图谱：

```
用户: "咳嗽应该吃什么药？"
  │
  ▼
意图识别 → 判断需要医疗知识
  │
  ▼
混合检索路由（权重：图谱 60% + 向量 40%）
  │
  ├── 图谱通道 → Neo4jTool.search_disease_by_symptom("咳嗽")
  │                  → 找到相关疾病 → search_drug_by_disease(...)
  │
  └── 向量通道 → Milvus 语义相似度检索
                    → 从知识库文本中匹配相关内容
  │
  ▼
LLM 汇总生成答案（含免责声明）
```

**图谱在此架构中的角色**：
- 提供精确的结构化知识（事实性关联）
- 适用于"疾病→症状→用药"的确定性子图遍历
- 与向量检索互补（向量处理非结构化文本语义，图谱处理结构化关系）

#### 两种查询体系的核心差异

| 维度 | QASystemOnMedicalKG | ShenNongYaoDian |
|------|--------------------|-----------------|
| **驱动方式** | 规则模板（18 类硬编码） | LLM Agent + 混合检索 |
| **图谱查询** | 固定单/双跳 Cypher | 灵活多跳 + 路径类型过滤 |
| **非图谱数据** | 不支持（纯 Neo4j） | Milvus 向量库 + SQLite FTS5 全文检索 |
| **答案生成** | 模板字符串拼接 | LLM 自然语言生成 |
| **可扩展性** | 新增问句需改代码 | 新增问句只需调整 Prompt |
| **关系命名** | `snake_case`（`has_symptom`） | `UPPER_CASE`（`HAS_SYMPTOM`） |
| **反向查询** | 每类手动写反向 Cypher | OPTIONAL MATCH 自动返回双向 |

---

### 8.3 Cypher 查询对照总表

相同的数据（同一批 medical.json）在两个系统中支持的查询对照：

| 查询目标 | 原项目 Cypher | 本项目 Cypher |
|---------|--------------|---------------|
| 疾病→症状 | `MATCH (d:Disease)-[:has_symptom]->(s:Symptom) WHERE d.name='X'` | `MATCH (d:Disease {name:$n}) OPTIONAL MATCH (d)-[:HAS_SYMPTOM]->(s:Symptom)` |
| 症状→疾病 | `MATCH (d:Disease)-[:has_symptom]->(s:Symptom) WHERE s.name='X'` | 多跳或 Agent 内部组合 |
| 疾病→药品 | `MATCH (d:Disease)-[:common_drug]->(dr:Drug) WHERE d.name='X'` | `MATCH (d:Disease {name:$n}) OPTIONAL MATCH (d)-[:TREATS_WITH]->(dr:Drug)` |
| 疾病→宜吃 | `MATCH (d:Disease)-[:do_eat]->(f:Food) WHERE d.name='X'` | 同上，关系改为 `GOOD_FOR` |
| 疾病→忌吃 | `MATCH (d:Disease)-[:no_eat]->(f:Food) WHERE d.name='X'` | 同上，关系改为 `BAD_FOR` |
| 疾病→检查 | `MATCH (d:Disease)-[:need_check]->(c:Check) WHERE d.name='X'` | 同上，关系改为 `NEEDS_CHECK` |
| 疾病→并发症 | `MATCH (d:Disease)-[:acompany_with]->(d2:Disease) WHERE d.name='X'` | 同上，关系改为 `RELATED_TO` |
| 任意多跳遍历 | ❌ 不支持 | ✅ `MATCH path=(s)-[:T1\|T2*1..n]->(d) RETURN path` |
| 属性查询 | `MATCH (d:Disease) WHERE d.name='X' RETURN d.cause` | 通过 Agent 读取节点属性 |

---

**更新时间**: 2026-06-16
**相关文件**: `src/graph_importer.py`, `src/retrieval/neo4j_store.py`, `src/agents/tools/neo4j_tool.py`, `src/api/routes/graph.py`, `KNOWLEDGE_BASE.md`
