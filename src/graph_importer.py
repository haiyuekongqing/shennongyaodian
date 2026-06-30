"""
医疗知识图谱导入工具
"""
import json
import re
import logging
from typing import List, Dict, Any, Tuple, Optional, Set
from src.retrieval.neo4j_store import Neo4jStore

logger = logging.getLogger(__name__)


class MedicalGraphImporter:
    """医疗知识图谱导入器"""

    # JSON Lines 扁平格式 → 图谱实体/关系映射
    FLAT_FIELD_MAPPING = {
        'symptom': ('Symptom', 'HAS_SYMPTOM'),
        'acompany': ('Disease', 'RELATED_TO'),
        'cure_department': ('Department', 'NEEDS_DEPARTMENT'),
        'common_drug': ('Drug', 'TREATS_WITH'),
        'recommand_drug': ('Drug', 'TREATS_WITH'),
        'drug_detail': ('Drug', 'TREATS_WITH'),
        'check': ('Check', 'NEEDS_CHECK'),
        'do_eat': ('Food', 'GOOD_FOR'),
        'recommand_eat': ('Food', 'GOOD_FOR'),
        'not_eat': ('Food', 'BAD_FOR'),
    }

    def __init__(self, neo4j_store: Neo4jStore):
        """
        初始化导入器

        Args:
            neo4j_store: Neo4j存储实例
        """
        self.neo4j = neo4j_store
        self.node_map = {}  # name -> (type, properties)

    def import_medical_json(self, file_path: str, entity_types: List[str] = None,
                            mode: str = "full_import") -> Dict[str, Any]:
        """
        导入医疗JSON数据到Neo4j

        支持两种格式：
        1. JSON 数组格式：[{"type": "...", "properties": {...}}, ...]
        2. JSON Lines 格式（MongoDB 导出）：每行一个扁平 JSON 对象

        Args:
            file_path: JSON文件路径
            entity_types: 实体类型列表（可选）
            mode: 导入模式（full_import/append）

        Returns:
            导入统计信息
        """
        logger.info(f"开始导入: {file_path}")

        # 读取文件内容并检测格式
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        content = content.strip()

        if content.startswith('['):
            # JSON 数组格式（原有格式）
            data = json.loads(content)
            entities, relations = self.parse_medical_data(data, entity_types)
        else:
            # JSON Lines 格式（MongoDB 扁平格式）
            entities, relations = self._parse_mongo_json_lines(content, entity_types)

        # 根据模式选择导入方式
        if mode == "full_import":
            self.neo4j.clear_all()
            logger.info("✓ 已清空现有数据（full_import模式）")
        elif mode == "append":
            logger.info("使用追加模式")

        # 先创建约束/索引，加速后续关系创建
        self.neo4j.create_constraints()

        # 创建节点
        if entities:
            self.neo4j.batch_create_nodes(entities)
        else:
            logger.warning("未找到有效节点数据")

        # 创建关系
        if relations:
            self.neo4j.batch_create_relationships(relations)
        else:
            logger.warning("未找到有效关系数据")

        stats = {
            "total_nodes": len(entities),
            "total_relationships": len(relations),
            "mode": mode,
            "entity_types": entity_types
        }

        logger.info(f"✓ 导入完成: {len(entities)} 个节点, {len(relations)} 条关系")
        return stats

    # ---- JSON Lines / MongoDB 扁平格式解析 ----

    def _parse_mongo_json_lines(self, content: str,
                                 entity_types: List[str] = None) -> Tuple[List[Dict], List[Dict]]:
        """
        解析 MongoDB 导出的 JSON Lines 格式（每行一个扁平疾病文档）

        Args:
            content: 文件原始内容
            entity_types: 限制处理的实体类型

        Returns:
            (节点列表, 关系列表)
        """
        entities: List[Dict] = []
        relations: List[Dict] = []
        seen_nodes: Set[Tuple[str, str]] = set()  # (type, name)

        lines = [line.strip() for line in content.split('\n') if line.strip()]

        for line_num, line in enumerate(lines, 1):
            try:
                doc = json.loads(line)
            except json.JSONDecodeError as e:
                logger.warning(f"第 {line_num} 行 JSON 解析失败: {e}")
                continue

            disease_name = doc.get('name', '')
            if not disease_name:
                continue

            # 如果限制了实体类型且不包含 Disease，跳过整个疾病
            if entity_types and 'Disease' not in entity_types:
                continue

            # ---- 创建 Disease 主节点 ----
            disease_key = ('Disease', disease_name)
            if disease_key not in seen_nodes:
                disease_props = {
                    'name': disease_name,
                    'desc': doc.get('desc', ''),
                    'prevent': doc.get('prevent', ''),
                    'cause': doc.get('cause', ''),
                    'category': ','.join(doc.get('category', [])) if isinstance(doc.get('category'), list) else str(doc.get('category', '')),
                    'yibao_status': doc.get('yibao_status', ''),
                    'get_prob': doc.get('get_prob', ''),
                    'get_way': doc.get('get_way', ''),
                    'cure_lasttime': doc.get('cure_lasttime', ''),
                    'cured_prob': doc.get('cured_prob', ''),
                    'cost_money': doc.get('cost_money', ''),
                    'cure_way': ';'.join(doc.get('cure_way', [])) if isinstance(doc.get('cure_way'), list) else str(doc.get('cure_way', '')),
                }
                # 移除空值
                disease_props = {k: v for k, v in disease_props.items() if v}

                entities.append({
                    'type': 'Disease',
                    'properties': disease_props,
                    'name': disease_name,
                })
                seen_nodes.add(disease_key)

            # ---- 提取列表字段中的关联实体与关系 ----
            for field, (target_type, rel_type) in self.FLAT_FIELD_MAPPING.items():
                values = doc.get(field, [])
                if not values:
                    continue
                if isinstance(values, str):
                    values = [values]

                for val in values:
                    if not val or not str(val).strip():
                        continue
                    val = str(val).strip()

                    # 如果限制了实体类型，跳过不在白名单内的关联类型
                    if entity_types and target_type not in entity_types:
                        continue

                    # 创建关联实体节点
                    target_key = (target_type, val)
                    if target_key not in seen_nodes:
                        entities.append({
                            'type': target_type,
                            'properties': {'name': val},
                            'name': val,
                        })
                        seen_nodes.add(target_key)

                    # 创建关系
                    relations.append({
                        'source_type': 'Disease',
                        'target_type': target_type,
                        'source': disease_name,
                        'target': val,
                        'type': rel_type,
                    })

        return entities, relations

    # ---- 原有的 JSON 数组格式解析（保持不变） ----

    def parse_medical_data(self, data: List[Dict[str, Any]],
                          entity_types: List[str] = None) -> Tuple[List[Dict], List[Dict]]:
        """
        解析医疗数据，提取节点和关系

        Args:
            data: 医疗数据列表
            entity_types: 限制处理的实体类型

        Returns:
            (节点列表, 关系列表)
        """
        entities = []
        relations = []

        for item in data:
            # 检查是否跳过
            if entity_types and item.get("type") not in entity_types:
                continue

            # 解析节点
            entity = self._parse_entity(item)
            if entity:
                entities.append(entity)

            # 解析关系
            rels = self._parse_relations(item)
            relations.extend(rels)

        return entities, relations

    def _parse_entity(self, item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        解析单个医疗条目为节点

        Args:
            item: 医疗数据条目

        Returns:
            节点字典
        """
        # 检测实体类型
        entity_type = self._detect_entity_type(item)
        if not entity_type:
            return None

        # 获取名称
        name = item.get("name", "")
        if not name:
            return None

        # 提取属性
        properties = item.get("properties", {})

        # 添加实体到映射表
        self.node_map[name] = (entity_type, properties)

        return {
            "type": entity_type,
            "properties": properties
        }

    def _detect_entity_type(self, item: Dict[str, Any]) -> Optional[str]:
        """
        检测实体类型

        Args:
            item: 医疗数据条目

        Returns:
            实体类型
        """
        name = item.get("name", "").lower()
        properties = item.get("properties", {})

        # 通过名称关键词判断
        if any(kw in name for kw in ["药", "方剂", "成分", "提取物"]):
            return "Drug"
        elif any(kw in name for kw in ["症", "痛", "症状"]):
            return "Symptom"
        elif any(kw in name for kw in ["症候", "证型"]):
            return "Disease"
        elif any(kw in name for kw in ["食物", "饮食", "忌口", "宜吃"]):
            return "Food"
        elif any(kw in name for kw in ["检查", "化验", "测试"]):
            return "Check"
        elif any(kw in name for kw in ["科室", "科"]):
            return "Department"
        elif any(kw in name for kw in ["厂家", "生产商", "厂商"]):
            return "Producer"
        elif any(kw in name for kw in ["饮片", "草药"]):
            return "Ingredient"
        elif any(kw in name for kw in ["方"]):
            return "Formula"
        elif properties.get("category", "").lower() in ["药", "药品"]:
            return "Drug"
        elif properties.get("type", "").lower() in ["疾病", "症候", "综合征"]:
            return "Disease"
        else:
            return "Entity"

    def _parse_relations(self, item: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        解析医疗条目中的关系

        Args:
            item: 医疗数据条目

        Returns:
            关系列表
        """
        relations = []
        properties = item.get("properties", {})
        entity_type = self._detect_entity_type(item)

        if not properties:
            return relations

        # 将属性转换为关系
        for prop_name, prop_value in properties.items():
            if prop_value is None:
                continue

            # 简单关系映射
            rel = {
                "source_type": entity_type,
                "target_type": self._map_property_to_type(prop_name),
                "source": item.get("name", ""),
                "target": str(prop_value),
                "type": self._map_property_to_relation(prop_name)
            }

            # 避免自引用关系
            if rel["source"] != rel["target"]:
                relations.append(rel)

        return relations

    def _map_property_to_type(self, prop_name: str) -> str:
        """
        映射属性到目标实体类型

        Args:
            prop_name: 属性名称

        Returns:
            目标实体类型
        """
        prop_lower = prop_name.lower()

        # 性质相关
        if any(kw in prop_lower for kw in ["性", "味", "归经", "性质"]):
            return "Property"

        # 症状相关
        if any(kw in prop_lower for kw in ["症状", "症状表现", "并发症状"]):
            return "Symptom"

        # 疾病相关
        if any(kw in prop_lower for kw in ["疾病", "并发症", "并发疾病", "易感疾病"]):
            return "Disease"

        # 用药相关
        if any(kw in prop_lower for kw in ["用药", "主治", "主治疾病", "治疗"]):
            return "Drug"

        # 食物相关
        if any(kw in prop_lower for kw in ["宜吃", "忌口", "不宜吃", "推荐食物", "忌食"]):
            return "Food"

        # 检查相关
        if any(kw in prop_lower for kw in ["检查", "化验", "检测"]):
            return "Check"

        # 默认
        return "Property"

    def _map_property_to_relation(self, prop_name: str) -> str:
        """
        映射属性到关系类型

        Args:
            prop_name: 属性名称

        Returns:
            关系类型
        """
        prop_lower = prop_name.lower()

        # 性质相关
        if any(kw in prop_lower for kw in ["性", "味", "归经", "性质"]):
            return "HAS_PROPERTY"

        # 症状相关
        if any(kw in prop_lower for kw in ["症状", "症状表现", "并发症状", "易感人群"]):
            return "HAS_SYMPTOM"

        # 疾病相关
        if any(kw in prop_lower for kw in ["疾病", "并发症", "并发疾病", "易感疾病"]):
            return "RELATED_TO"

        # 用药相关
        if any(kw in prop_lower for kw in ["用药", "主治", "主治疾病", "治疗"]):
            return "TREATS_WITH"

        # 食物相关
        if any(kw in prop_lower for kw in ["宜吃", "忌口", "不宜吃", "推荐食物", "忌食"]):
            return "GOOD_FOR" if "宜" in prop_lower or "推荐" in prop_lower else "BAD_FOR"

        # 检查相关
        if any(kw in prop_lower for kw in ["检查", "化验", "检测"]):
            return "NEEDS_CHECK"

        # 默认
        return "HAS_PROPERTY"


# 使用示例
if __name__ == "__main__":
    import sys

    # 初始化
    neo4j_store = Neo4jStore()
    neo4j_store.connect()
    neo4j_store.create_constraints()

    # 创建导入器
    importer = MedicalGraphImporter(neo4j_store)

    # 导入数据
    file_path = sys.argv[1] if len(sys.argv) > 1 else "data/medical.json"
    entity_types = sys.argv[2:] if len(sys.argv) > 2 else None

    stats = importer.import_medical_json(
        file_path=file_path,
        entity_types=entity_types,
        mode="full_import"
    )

    # 打印统计信息
    print("\n=== 导入统计 ===")
    print(f"节点数量: {stats['total_nodes']}")
    print(f"关系数量: {stats['total_relationships']}")
    print(f"导入模式: {stats['mode']}")

    # 获取图谱统计
    graph_stats = neo4j_store.get_stats()
    print("\n=== 图谱统计 ===")
    print(f"总节点数: {graph_stats['total_nodes']}")
    print(f"总关系数: {graph_stats['total_relationships']}")
    print("\n节点类型分布:")
    for item in graph_stats['node_types']:
        print(f"  {item['type']}: {item['count']}")
