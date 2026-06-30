"""
向量检索工具
封装向量数据库的检索功能
"""
import logging
from typing import List, Dict, Any, Optional

from src.retrieval.vector_store import VectorStore
from src.config.settings import settings

logger = logging.getLogger(__name__)


class VectorTool:
    """向量检索工具"""

    def __init__(self):
        """初始化向量检索工具"""
        self.vector_store = VectorStore()
        self.embedding_model = settings.EMBEDDING_MODEL
        self.default_top_k = 5

        logger.info(f"✓ 向量检索工具初始化完成: {self.embedding_model}")

    def import_file(self, file_path: str, chunk_size: int = 500, overlap: int = 50) -> int:
        """
        导入文件到向量存储

        Args:
            file_path: 文件路径
            chunk_size: 分块大小
            overlap: 分块重叠

        Returns:
            导入的知识块数量
        """
        return self.vector_store.import_file(file_path, chunk_size, overlap)

    def search(self, query: str, top_k: Optional[int] = None, filter_condition: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        执行向量检索

        Args:
            query: 查询文本
            top_k: 返回结果数量，默认 5
            filter_condition: 过滤条件

        Returns:
            检索结果列表
        """
        top_k = top_k or self.default_top_k

        logger.info(f"✓ 开始向量检索: query='{query[:50]}...', top_k={top_k}")

        # 执行检索
        results = self.vector_store.search(query, top_k, filter_condition)

        # 添加免责声明
        for result in results:
            result['disclaimer'] = self._get_disclaimer_text()

        logger.info(f"✓ 向量检索完成，返回 {len(results)} 个结果")
        return results

    def search_by_ids(self, ids: List[str]) -> List[Dict[str, Any]]:
        """
        根据向量 ID 检索

        Args:
            ids: 向量 ID 列表

        Returns:
            检索结果列表
        """
        logger.info(f"✓ 根据向量 ID 检索: {len(ids)} 个 ID")

        # TODO: 实现根据 ID 检索
        # 当前 Milvus 不支持直接按 ID 检索，需要实现自定义实现
        return []

    def get_similar_documents(self, document_id: str, top_k: int = 10) -> List[Dict[str, Any]]:
        """
        找到相似文档

        Args:
            document_id: 文档 ID
            top_k: 返回结果数量

        Returns:
            相似文档列表
        """
        logger.info(f"✓ 查找相似文档: id={document_id}, top_k={top_k}")

        # TODO: 实现相似文档查找
        # 需要存储文档的向量 ID 和元数据
        return []

    def get_stats(self) -> Dict[str, Any]:
        """
        获取向量存储统计信息

        Returns:
            统计信息字典
        """
        logger.debug("✓ 获取向量存储统计信息")

        return self.vector_store.get_stats()

    def bulk_search(self, queries: List[str], top_k: int = 5) -> Dict[str, List[Dict[str, Any]]]:
        """
        批量检索

        Args:
            queries: 查询列表
            top_k: 每个查询返回的结果数量

        Returns:
            {查询文本: 结果列表} 字典
        """
        results = {}

        for query in queries:
            results[query] = self.search(query, top_k)

        logger.info(f"✓ 批量检索完成: {len(queries)} 个查询")
        return results

    def search_with_metadata(self, query: str, top_k: int = 5, metadata_filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        带元数据过滤的检索

        Args:
            query: 查询文本
            top_k: 返回结果数量
            metadata_filters: 元数据过滤条件

        Returns:
            检索结果列表
        """
        logger.info(f"✓ 带元数据过滤的检索: query='{query[:50]}...', filters={metadata_filters}")

        # TODO: 实现元数据过滤
        # Milvus 支持通过 expr 参数过滤元数据
        return self.search(query, top_k, metadata_filters)

    def get_embedding(self, text: str) -> List[float]:
        """
        获取文本的 Embedding

        Args:
            text: 输入文本

        Returns:
            Embedding 向量
        """
        try:
            from src.retrieval.embedding import embedding_model
            embedding = embedding_model.encode_single(text)
            logger.info(f"✓ Embedding 生成成功，维度: {len(embedding)}")
            return embedding

        except Exception as e:
            logger.error(f"✗ Embedding 生成失败: {e}")
            raise

    def calculate_similarity(self, text1: str, text2: str) -> float:
        """
        计算两个文本的相似度（内积）

        Args:
            text1: 文本1
            text2: 文本2

        Returns:
            相似度分数（0-1）
        """
        embedding1 = self.get_embedding(text1)
        embedding2 = self.get_embedding(text2)

        # 内积相似度
        similarity = sum(a * b for a, b in zip(embedding1, embedding2))

        # 归一化到 0-1
        max_similarity = min(
            sum(a * a for a in embedding1),
            sum(a * a for a in embedding2)
        )

        return similarity / max_similarity if max_similarity > 0 else 0.0

    def clear_collection(self):
        """清空向量集合"""
        logger.warning(f"⚠ 正在清空向量集合: {self.vector_store.collection_name}")
        self.vector_store.clear_collection()

    def _get_disclaimer_text(self) -> str:
        """获取免责声明文本"""
        try:
            from src.models.base import db_manager
            from src.models.medica_data import MedicalDisclaimer
            from sqlalchemy import text

            with db_manager.get_session() as session:
                result = session.execute(
                    text("SELECT disclaimer_text FROM medical_disclaimers WHERE is_enabled=1 LIMIT 1")
                ).first()
                if result:
                    return result[0]
        except Exception as e:
            logger.error(f"✗ 获取免责声明失败: {e}")

        return "免责声明：本系统提供的信息仅供参考，不构成医疗建议。如遇健康问题，请咨询专业医生或药师。"

    def export_vectors(self, output_file: str, top_k: int = 100):
        """
        导出向量数据（用于分析）

        Args:
            output_file: 输出文件路径
            top_k: 导出的向量数量
        """
        logger.info(f"✓ 导出向量数据到: {output_file}")

        # TODO: 实现向量数据导出
        pass
