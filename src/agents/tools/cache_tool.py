"""
缓存工具
"""
import logging
import time
from typing import Optional, Dict, Any
from src.agents.cache.llm_cache import llm_cache
from src.agents.cache.semantic_cache import semantic_cache, embedding_cache
from src.retrieval.embedding import embedding_model

logger = logging.getLogger(__name__)


class CacheTool:
    """缓存工具"""

    def __init__(self):
        """初始化缓存工具"""
        self.llm_cache = llm_cache
        self.semantic_cache = semantic_cache
        self.embedding_cache = embedding_cache

    def get_llm_cache_stats(self) -> Dict[str, Any]:
        """
        获取LLM缓存统计信息

        Returns:
            统计信息
        """
        return self.llm_cache.get_stats()

    def get_semantic_cache_stats(self) -> Dict[str, Any]:
        """
        获取语义缓存统计信息

        Returns:
            统计信息
        """
        return self.semantic_cache.get_stats()

    def get_embedding_cache_stats(self) -> Dict[str, Any]:
        """
        获取Embedding缓存统计信息

        Returns:
            统计信息
        """
        return self.embedding_cache.get_stats()

    def get_all_cache_stats(self) -> Dict[str, Any]:
        """
        获取所有缓存统计信息

        Returns:
            统计信息
        """
        return {
            "llm_cache": self.llm_cache.get_stats(),
            "semantic_cache": self.semantic_cache.get_stats(),
            "embedding_cache": self.embedding_cache.get_stats()
        }

    def clear_all_cache(self) -> bool:
        """
        清空所有缓存

        Returns:
            是否成功
        """
        try:
            self.llm_cache.clear()
            self.semantic_cache.clear()
            self.embedding_cache.clear()
            logger.warning("✓ 所有缓存已清空")
            return True
        except Exception as e:
            logger.error(f"✗ 清空缓存失败: {e}")
            return False

    def clear_llm_cache(self) -> bool:
        """
        清空LLM缓存

        Returns:
            是否成功
        """
        try:
            self.llm_cache.clear()
            logger.warning("✓ LLM缓存已清空")
            return True
        except Exception as e:
            logger.error(f"✗ 清空LLM缓存失败: {e}")
            return False

    def clear_semantic_cache(self) -> bool:
        """
        清空语义缓存

        Returns:
            是否成功
        """
        try:
            self.semantic_cache.clear()
            logger.warning("✓ 语义缓存已清空")
            return True
        except Exception as e:
            logger.error(f"✗ 清空语义缓存失败: {e}")
            return False

    def clear_embedding_cache(self) -> bool:
        """
        清空Embedding缓存

        Returns:
            是否成功
        """
        try:
            self.embedding_cache.clear()
            logger.warning("✓ Embedding缓存已清空")
            return True
        except Exception as e:
            logger.error(f"✗ 清空Embedding缓存失败: {e}")
            return False

    def clear_cache_by_query(self, query: str) -> bool:
        """
        清空指定查询的缓存

        Args:
            query: 查询文本

        Returns:
            是否成功
        """
        try:
            self.llm_cache.delete(query)
            logger.warning(f"✓ 已清空查询缓存: {query[:50]}...")
            return True
        except Exception as e:
            logger.error(f"✗ 清空查询缓存失败: {e}")
            return False

    def check_cache_hit(self, query: str, context: Optional[Dict] = None) -> bool:
        """
        检查缓存命中

        Args:
            query: 查询文本
            context: 检索上下文

        Returns:
            是否命中
        """
        # 检查LLM缓存
        cached_answer = self.llm_cache.get(query, context)
        if cached_answer:
            logger.info(f"✓ LLM缓存命中")
            return True

        # 检查语义缓存
        semantic_result = self.semantic_cache.search(query)
        if semantic_result:
            logger.info(f"✓ 语义缓存命中")
            return True

        return False

    def get_cache_time_stats(self) -> Dict[str, Any]:
        """
        获取缓存时间统计

        Returns:
            统计信息
        """
        return {
            "llm_hit_rate": self.llm_cache.hits / (self.llm_cache.hits + self.llm_cache.misses) if self.llm_cache.hits + self.llm_cache.misses > 0 else 0,
            "semantic_cache_items": len(self.semantic_cache.cache_data),
            "embedding_cache_items": len(self.embedding_cache.cache),
            "embedding_hit_rate": self.embedding_cache.hits / (self.embedding_cache.hits + self.embedding_cache.misses) if self.embedding_cache.hits + self.embedding_cache.misses > 0 else 0
        }
