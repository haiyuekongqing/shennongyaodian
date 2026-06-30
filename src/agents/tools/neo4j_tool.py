"""
Neo4j 检索工具
"""
import logging
from typing import List, Dict, Any, Optional
from src.retrieval.neo4j_store import neo4j_store

logger = logging.getLogger(__name__)


class Neo4jTool:
    """Neo4j 图谱检索工具"""

    def __init__(self):
        """初始化 Neo4j 工具"""
        self.store = neo4j_store
        self._connect()

    def _connect(self):
        """连接到 Neo4j"""
        try:
            if not self.store.driver:
                self.store.connect()
            logger.info("✓ Neo4j 工具初始化完成")
        except Exception as e:
            logger.error(f"✗ Neo4j 连接失败: {e}")

    def search_entity(self, entity_type: str, name: str) -> List[Dict[str, Any]]:
        """
        根据实体名称搜索

        Args:
            entity_type: 实体类型（Disease, Drug, Formula等）
            name: 实体名称

        Returns:
            检索结果列表
        """
        try:
            results = self.store.query_by_name(entity_type, name)
            logger.info(f"✓ Neo4j 查询成功: {entity_type} - {name}")
            return results
        except Exception as e:
            logger.error(f"✗ Neo4j 查询失败: {e}")
            return []

    def search_disease_by_symptom(self, symptom: str) -> List[Dict[str, Any]]:
        """
        根据症状查找疾病

        Args:
            symptom: 症状名称

        Returns:
            疾病列表
        """
        try:
            query = """
            MATCH (s:Symptom {name: $symptom})
            OPTIONAL MATCH (s)-[:HAS_SYMPTOM]->(d:Disease)
            RETURN s, d
            LIMIT 10
            """
            with self.store.driver.session() as session:
                result = session.run(query, symptom=symptom)
                return [record.data() for record in result]
        except Exception as e:
            logger.error(f"✗ 症状-疾病查询失败: {e}")
            return []

    def search_drug_by_disease(self, disease: str) -> List[Dict[str, Any]]:
        """
        根据疾病查找药物

        Args:
            disease: 疾病名称

        Returns:
            药物列表
        """
        try:
            query = """
            MATCH (d:Disease {name: $disease})
            OPTIONAL MATCH (d)-[:TREATS_WITH]->(drug:Drug)
            RETURN d, drug
            LIMIT 10
            """
            with self.store.driver.session() as session:
                result = session.run(query, disease=disease)
                return [record.data() for record in result]
        except Exception as e:
            logger.error(f"✗ 疾病-药物查询失败: {e}")
            return []

    def multi_hop_query(self, start_entity: str, start_type: str = None,
                        hop_count: int = 3, path_types: List[str] = None) -> Dict[str, Any]:
        """
        多跳查询（症状 → 疾病 → 用药）

        Args:
            start_entity: 起始实体
            start_type: 起始实体类型
            hop_count: 跳数
            path_types: 关系类型列表

        Returns:
            查询结果
        """
        try:
            results = self.store.multi_hop_query(
                start_entity=start_entity,
                start_type=start_type,
                hop_count=hop_count,
                path_types=path_types
            )
            logger.info(f"✓ 多跳查询成功: {start_entity} ({hop_count}跳)")
            return results
        except Exception as e:
            logger.error(f"✗ 多跳查询失败: {e}")
            return []

    def get_graph_stats(self) -> Dict[str, Any]:
        """
        获取图谱统计信息

        Returns:
            统计信息
        """
        try:
            return self.store.get_stats()
        except Exception as e:
            logger.error(f"✗ 获取统计失败: {e}")
            return {}

    def clear_graph(self) -> bool:
        """
        清空图谱数据

        Returns:
            是否成功
        """
        try:
            self.store.clear_all()
            return True
        except Exception as e:
            logger.error(f"✗ 清空图谱失败: {e}")
            return False

    def export_graph(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        导出图谱数据

        Args:
            limit: 导出数量限制

        Returns:
            图谱数据列表
        """
        try:
            return self.store.export_graph(limit=limit)
        except Exception as e:
            logger.error(f"✗ 导出图谱失败: {e}")
            return []
