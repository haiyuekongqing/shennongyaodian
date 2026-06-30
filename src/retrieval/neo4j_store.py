"""
Neo4j 图数据库存储
"""
from neo4j import GraphDatabase
from typing import List, Dict, Any, Optional, Tuple
import logging
from src.config.settings import settings

logger = logging.getLogger(__name__)


class Neo4jStore:
    """Neo4j 知识图谱存储"""

    def __init__(self, uri: str = None,
                 user: str = None,
                 password: str = None):
        """
        初始化 Neo4j 存储实例

        Args:
            uri: Neo4j 连接地址 (默认从 settings 读取)
            user: 用户名 (默认从 settings 读取)
            password: 密码 (默认从 settings 读取)
        """
        self.uri = uri or settings.NEO4J_URI
        self.user = user or settings.NEO4J_USER
        self.password = password or settings.NEO4J_PASSWORD
        self.driver = None

    def connect(self):
        """建立连接"""
        try:
            self.driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
            # 测试连接
            self.driver.verify_connectivity()
            logger.info(f"✓ 已连接到 Neo4j: {self.uri}")
        except Exception as e:
            logger.error(f"✗ 连接 Neo4j 失败: {e}")
            raise

    def close(self):
        """关闭连接"""
        if self.driver:
            self.driver.close()
            logger.info("✓ 已关闭 Neo4j 连接")

    def create_constraints(self):
        """创建索引和约束"""
        with self.driver.session() as session:
            # 创建实体名称的唯一约束
            constraints = [
                """
                CREATE CONSTRAINT IF NOT EXISTS FOR (d:Disease) REQUIRE d.name IS UNIQUE
                """,
                """
                CREATE CONSTRAINT IF NOT EXISTS FOR (d:Drug) REQUIRE d.name IS UNIQUE
                """,
                """
                CREATE CONSTRAINT IF NOT EXISTS FOR (d:Formula) REQUIRE d.name IS UNIQUE
                """,
                """
                CREATE CONSTRAINT IF NOT EXISTS FOR (d:Symptom) REQUIRE d.name IS UNIQUE
                """,
                """
                CREATE CONSTRAINT IF NOT EXISTS FOR (d:Ingredient) REQUIRE d.name IS UNIQUE
                """,
                """
                CREATE CONSTRAINT IF NOT EXISTS FOR (d:Food) REQUIRE d.name IS UNIQUE
                """,
                """
                CREATE CONSTRAINT IF NOT EXISTS FOR (d:Check) REQUIRE d.name IS UNIQUE
                """,
                """
                CREATE CONSTRAINT IF NOT EXISTS FOR (d:Department) REQUIRE d.name IS UNIQUE
                """,
                """
                CREATE CONSTRAINT IF NOT EXISTS FOR (d:Producer) REQUIRE d.name IS UNIQUE
                """,
            ]

            for constraint in constraints:
                try:
                    session.run(constraint)
                    logger.info("✓ 已创建约束")
                except Exception as e:
                    logger.warning(f"约束创建失败（可能已存在）: {e}")

    def query_by_name(self, entity_type: str, name: str) -> List[Dict[str, Any]]:
        """
        根据实体名称查询

        Args:
            entity_type: 实体类型
            name: 实体名称

        Returns:
            查询结果列表
        """
        query = f"""
        MATCH (n:{entity_type} {{name: $name}})
        OPTIONAL MATCH (n)-[r]-(m)
        RETURN n, r, m
        """

        with self.driver.session() as session:
            result = session.run(query, name=name)
            return [record.data() for record in result]

    def multi_hop_query(self, start_entity: str, start_type: str = None,
                        hop_count: int = 3, path_types: List[str] = None) -> List[Dict[str, Any]]:
        """
        多跳查询（例如：症状 → 疾病 → 用药）

        Args:
            start_entity: 起始实体名称
            start_type: 起始实体类型
            hop_count: 跳数
            path_types: 关系类型列表

        Returns:
            查询结果列表
        """
        if not path_types:
            path_types = ["HAS_SYMPTOM", "TREATS_WITH", "COMPATIBLE_WITH", "NEEDS_CHECK"]

        query = f"""
        MATCH path = (s:{start_type or 'Entity'} {{name: $start_entity}})
                -[:{path_types[0]}*1..{hop_count}]->(d)
        RETURN path, length(path) as hop_count, s.name as start_entity,
               [node in nodes(path) | labels(node)[0] as type] as path_types,
               [relationship in relationships(path) | type(relationship) as rel_type] as rel_types
        ORDER BY hop_count
        LIMIT 10
        """

        with self.driver.session() as session:
            result = session.run(query, start_entity=start_entity)
            return [record.data() for record in result]

    def get_stats(self) -> Dict[str, Any]:
        """
        获取图谱统计信息

        Returns:
            统计信息字典
        """
        with self.driver.session() as session:
            # 节点统计
            node_stats = session.run("""
                MATCH (n)
                WITH labels(n)[0] as type, count(n) as count
                RETURN type, count
                ORDER BY count DESC
            """).data()

            # 关系统计
            rel_stats = session.run("""
                MATCH ()-[r]->()
                WITH type(r) as rel_type, count(r) as count
                RETURN rel_type, count
                ORDER BY count DESC
                LIMIT 10
            """).data()

            # 总节点数
            total_nodes = session.run("MATCH (n) RETURN count(n) as count").single()[0]

            # 总关系数
            total_rels = session.run("MATCH ()-[r]->() RETURN count(r) as count").single()[0]

            return {
                "total_nodes": total_nodes,
                "total_relationships": total_rels,
                "node_types": node_stats,
                "relationship_types": rel_stats
            }

    def clear_all(self):
        """清空所有数据（⚠️ 危险操作）"""
        with self.driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")
            logger.warning("✓ 已清空所有数据")

    def export_graph(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        导出图谱数据

        Args:
            limit: 导出数量限制

        Returns:
            图谱数据列表
        """
        with self.driver.session() as session:
            result = session.run("""
                MATCH (n)
                WITH n, labels(n)[0] as type
                RETURN type, n.name as name, properties(n) as properties
                LIMIT $limit
            """, limit=limit)
            return [record.data() for record in result]

    def batch_create_nodes(self, nodes: List[Dict[str, Any]]):
        """
        批量创建节点

        Args:
            nodes: 节点列表，每个节点包含 type 和 properties
        """
        if not nodes:
            return

        with self.driver.session() as session:
            for node in nodes:
                entity_type = node.get("type")
                properties = node.get("properties", {})
                name = properties.get("name", "")

                if not name or not entity_type:
                    continue

                query = f"""
                MERGE (n:{entity_type} {{name: $name}})
                SET n += $properties
                """
                session.run(query, name=name, properties=properties)
            logger.info(f"✓ 批量创建节点: {len(nodes)} 个")

    def batch_create_relationships(self, relations: List[Dict[str, Any]]):
        """
        批量创建关系（使用 UNWIND 批量优化）

        Args:
            relations: 关系列表，每个关系包含 source_type, target_type, source, target, type
        """
        if not relations:
            return

        # 按 (source_type, target_type, rel_type) 分组
        groups: Dict[Tuple[str, str, str], List[Dict]] = {}
        for rel in relations:
            source_type = rel.get("source_type")
            target_type = rel.get("target_type")
            source = rel.get("source")
            target = rel.get("target")
            rel_type = rel.get("type")

            if not all([source_type, target_type, source, target, rel_type]):
                continue

            key = (source_type, target_type, rel_type)
            if key not in groups:
                groups[key] = []
            groups[key].append({"source": source, "target": target})

        total = 0
        BATCH_SIZE = 500

        with self.driver.session() as session:
            for (source_type, target_type, rel_type), items in groups.items():
                for i in range(0, len(items), BATCH_SIZE):
                    batch = items[i:i + BATCH_SIZE]
                    query = f"""
                    UNWIND $batch AS item
                    MATCH (a:{source_type} {{name: item.source}})
                    MATCH (b:{target_type} {{name: item.target}})
                    MERGE (a)-[:{rel_type}]->(b)
                    """
                    session.run(query, batch=batch)
                    total += len(batch)

        logger.info(f"✓ 批量创建关系: {total} 条")


# 全局实例
neo4j_store = Neo4jStore()
