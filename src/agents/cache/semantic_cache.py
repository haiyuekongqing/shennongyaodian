"""
语义缓存
使用向量相似度匹配高度相似的查询，直接复用历史答案
"""
import time
import logging
import numpy as np
from typing import Optional, Dict, Any, List
from src.agents.cache.llm_cache import LLMCache, llm_cache
from src.retrieval.embedding import embedding_model

logger = logging.getLogger(__name__)


class SemanticCache:
    """语义缓存"""

    def __init__(self, llm_cache: LLMCache, threshold: float = 0.95,
                 top_k: int = 10):
        """
        初始化语义缓存

        Args:
            llm_cache: LLM缓存
            threshold: 相似度阈值（0-1）
            top_k: 检索的Top-K数量
        """
        self.llm_cache = llm_cache
        self.threshold = threshold
        self.top_k = top_k
        self.cache_data: List[Dict[str, Any]] = []

    def search(self, query: str, query_embedding: Optional[np.ndarray] = None) -> Optional[Dict[str, Any]]:
        """
        语义缓存搜索

        Args:
            query: 查询文本
            query_embedding: 查询向量（可选）

        Returns:
            匹配的缓存项，如果没有则返回None
        """
        if not self.cache_data:
            return None

        # 生成查询向量
        if query_embedding is None:
            query_embedding = embedding_model.encode_queries([query])[0]

        # 计算所有缓存的相似度
        scores = []
        for item in self.cache_data:
            # 这里假设缓存的查询向量存在
            cached_embedding = item.get("embedding")
            if cached_embedding is not None:
                # 计算余弦相似度
                similarity = self._cosine_similarity(query_embedding, cached_embedding)
                scores.append((similarity, item))
            else:
                scores.append((0.0, item))

        # 按相似度排序
        scores.sort(key=lambda x: x[0], reverse=True)

        # 找到相似度超过阈值的结果
        for similarity, item in scores[:self.top_k]:
            if similarity >= self.threshold:
                logger.info(f"✓ 语义缓存命中，相似度: {similarity:.3f}")
                self.llm_cache.hits += 1
                return {
                    "answer": item.get("answer"),
                    "similarity": similarity,
                    "query": item.get("query")
                }

        # 没有匹配到
        self.llm_cache.misses += 1
        logger.info(f"✗ 语义缓存未命中（相似度最高: {scores[0][0]:.3f}）")
        return None

    def store(self, query: str, answer: str):
        """
        存储到语义缓存

        Args:
            query: 查询文本
            answer: 回答内容
        """
        try:
            # 生成查询向量
            query_embedding = embedding_model.encode_queries([query])[0]

            # 存储到LLM缓存
            self.llm_cache.set(query, answer)

            # 存储到语义缓存
            self.cache_data.append({
                "query": query,
                "answer": answer,
                "embedding": list(query_embedding),
                "timestamp": time.time()
            })

            # 限制缓存大小
            max_size = 1000  # 最大缓存条目数
            if len(self.cache_data) > max_size:
                # 移除最旧的
                self.cache_data = self.cache_data[-max_size:]

            logger.info(f"✓ 已缓存: {query[:50]}...")

        except Exception as e:
            logger.error(f"✗ 语义缓存存储失败: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        if not self.cache_data:
            return {
                "total_items": 0,
                "threshold": self.threshold,
                "top_k": self.top_k
            }

        return {
            "total_items": len(self.cache_data),
            "threshold": self.threshold,
            "top_k": self.top_k
        }

    def clear(self):
        """清空语义缓存"""
        self.cache_data.clear()
        logger.warning("✓ 语义缓存已清空")

    def _cosine_similarity(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        """
        计算余弦相似度

        Args:
            vec1: 向量1
            vec2: 向量2

        Returns:
            余弦相似度
        """
        dot_product = np.dot(vec1, vec2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return dot_product / (norm1 * norm2)


class EmbeddingCache:
    """Embedding 缓存（避免重复计算相同的Embedding）"""

    def __init__(self, maxsize: int = 5000):
        """
        初始化Embedding缓存

        Args:
            maxsize: 最大缓存数量
        """
        self.cache = {}
        self.maxsize = maxsize
        self.hits = 0
        self.misses = 0

    def _generate_key(self, text: str) -> str:
        """
        生成缓存键

        Args:
            text: 文本

        Returns:
            缓存键
        """
        return hashlib.sha256(text.encode()).hexdigest()

    def get(self, text: str) -> Optional[np.ndarray]:
        """
        获取Embedding

        Args:
            text: 文本

        Returns:
            Embedding向量
        """
        key = self._generate_key(text)

        if key in self.cache:
            self.hits += 1
            return self.cache[key]

        self.misses += 1
        return None

    def set(self, text: str, embedding: np.ndarray):
        """
        设置Embedding缓存

        Args:
            text: 文本
            embedding: Embedding向量
        """
        key = self._generate_key(text)

        # 如果缓存已满，移除最旧的
        if len(self.cache) >= self.maxsize and key not in self.cache:
            oldest_key = next(iter(self.cache))
            del self.cache[oldest_key]

        self.cache[key] = embedding

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        total = self.hits + self.misses
        hit_rate = self.hits / total if total > 0 else 0
        return {
            "maxsize": self.maxsize,
            "current_size": len(self.cache),
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": hit_rate
        }

    def clear(self):
        """清空缓存"""
        self.cache.clear()
        self.hits = 0
        self.misses = 0


# 全局缓存实例
embedding_cache = EmbeddingCache(maxsize=5000)
semantic_cache = SemanticCache(llm_cache=llm_cache, threshold=0.95, top_k=10)
