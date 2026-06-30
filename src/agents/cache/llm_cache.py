"""
LLM 响应缓存
"""
import hashlib
import json
import logging
from typing import Optional, Dict, Any
import time
from src.config.settings import settings

logger = logging.getLogger(__name__)

# 尝试导入 Redis（可选依赖）
try:
    import redis
    HAS_REDIS = True
except ImportError:
    HAS_REDIS = False
    logger.warning("redis 未安装，分布式缓存不可用")


class LLMLocalCache:
    """LLM 本地缓存（使用LRU）"""

    def __init__(self, maxsize: int = 1000):
        """
        初始化本地缓存

        Args:
            maxsize: 最大缓存数量
        """
        self.cache = {}
        self.maxsize = maxsize
        self.hits = 0
        self.misses = 0

    def _generate_key(self, query: str, context: Optional[Dict] = None) -> str:
        """
        生成缓存键

        Args:
            query: 查询文本
            context: 检索上下文

        Returns:
            缓存键
        """
        # 创建查询上下文的哈希
        context_str = json.dumps(context, sort_keys=True) if context else ""
        combined = f"{query}|{context_str}"

        # 生成SHA256哈希
        return hashlib.sha256(combined.encode()).hexdigest()

    def get(self, key: str) -> Optional[str]:
        """
        获取缓存

        Args:
            key: 缓存键

        Returns:
            缓存值
        """
        if key in self.cache:
            self.hits += 1
            return self.cache[key]
        self.misses += 1
        return None

    def set(self, key: str, value: str, ttl: Optional[int] = None):
        """
        设置缓存

        Args:
            key: 缓存键
            value: 缓存值
            ttl: 过期时间（秒）
        """
        # 如果缓存已满，移除最旧的
        if len(self.cache) >= self.maxsize and key not in self.cache:
            oldest_key = next(iter(self.cache))
            del self.cache[oldest_key]

        self.cache[key] = value
        self.misses += 1  # 统计设置也计为miss

    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        total = self.hits + self.misses
        hit_rate = self.hits / total if total > 0 else 0
        return {
            "maxsize": self.maxsize,
            "current_size": len(self.cache),
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": hit_rate
        }


class LLMDistributedCache:
    """LLM 分布式缓存（使用Redis）"""

    def __init__(self, host: str = "localhost", port: int = 6379,
                 password: Optional[str] = None, db: int = 0,
                 ttl: int = 3600):
        """
        初始化分布式缓存

        Args:
            host: Redis主机
            port: Redis端口
            password: Redis密码
            db: 数据库编号
            ttl: 过期时间（秒）
        """
        self.host = host
        self.port = port
        self.password = password
        self.db = db
        self.ttl = ttl
        self.redis_client = None
        self._connect()

    def _connect(self):
        """连接Redis"""
        if not HAS_REDIS:
            raise ImportError("redis 模块未安装，无法连接 Redis")

        try:
            self.redis_client = redis.Redis(
                host=self.host,
                port=self.port,
                password=self.password,
                db=self.db,
                decode_responses=True
            )
            # 测试连接
            self.redis_client.ping()
            logger.info(f"✓ 已连接到Redis: {self.host}:{self.port}")
        except Exception as e:
            logger.error(f"✗ 连接Redis失败: {e}")
            raise

    def _generate_key(self, query: str, context: Optional[Dict] = None) -> str:
        """
        生成缓存键

        Args:
            query: 查询文本
            context: 检索上下文

        Returns:
            缓存键
        """
        context_str = json.dumps(context, sort_keys=True) if context else ""
        combined = f"llm:{hashlib.sha256((query + context_str).encode()).hexdigest()}"
        return combined

    def get(self, key: str) -> Optional[str]:
        """
        获取缓存

        Args:
            key: 缓存键

        Returns:
            缓存值
        """
        try:
            value = self.redis_client.get(key)
            if value:
                self.hits += 1
            else:
                self.misses += 1
            return value
        except Exception as e:
            logger.error(f"✗ Redis获取缓存失败: {e}")
            return None

    def set(self, key: str, value: str, ttl: Optional[int] = None):
        """
        设置缓存

        Args:
            key: 缓存键
            value: 缓存值
            ttl: 过期时间（秒）
        """
        try:
            self.redis_client.setex(
                key,
                ttl if ttl else self.ttl,
                value
            )
        except Exception as e:
            logger.error(f"✗ Redis设置缓存失败: {e}")

    def delete(self, key: str):
        """删除缓存"""
        try:
            self.redis_client.delete(key)
        except Exception as e:
            logger.error(f"✗ Redis删除缓存失败: {e}")

    def clear(self):
        """清空缓存"""
        try:
            self.redis_client.flushdb()
            logger.warning("✓ Redis缓存已清空")
        except Exception as e:
            logger.error(f"✗ Redis清空缓存失败: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        try:
            info = self.redis_client.info("stats")
            keyspace = self.redis_client.info("keyspace")
            return {
                "host": f"{self.host}:{self.port}",
                "db": self.db,
                "total_keys": info.get("total_keys", 0),
                "used_memory": info.get("used_memory_human", "0"),
                "keyspace_hits": keyspace.get("hits", 0),
                "keyspace_misses": keyspace.get("misses", 0)
            }
        except Exception as e:
            logger.error(f"✗ 获取Redis统计失败: {e}")
            return {}


class LLMCache:
    """LLM缓存管理器"""

    def __init__(self, use_redis: bool = True, redis_host: str = "localhost",
                 redis_port: int = 6379, redis_password: Optional[str] = None):
        """
        初始化LLM缓存

        Args:
            use_redis: 是否使用Redis
            redis_host: Redis主机
            redis_port: Redis端口
            redis_password: Redis密码
        """
        self.use_redis = use_redis and HAS_REDIS

        if self.use_redis:
            self.local_cache = None
            self.distributed_cache = LLMDistributedCache(
                host=redis_host,
                port=redis_port,
                password=redis_password
            )
        else:
            self.local_cache = LLMLocalCache(maxsize=1000)
            self.distributed_cache = None

        self.hits = 0
        self.misses = 0

    def get(self, query: str, context: Optional[Dict] = None) -> Optional[str]:
        """
        获取缓存

        Args:
            query: 查询文本
            context: 检索上下文

        Returns:
            缓存值
        """
        key = self._generate_key(query, context)

        # 优先从分布式缓存获取
        if self.use_redis and self.distributed_cache:
            value = self.distributed_cache.get(key)
            if value:
                self.hits += 1
                return value

        # 其次从本地缓存获取
        if self.local_cache:
            value = self.local_cache.get(key)
            if value:
                self.hits += 1
                return value

        self.misses += 1
        return None

    def set(self, query: str, response: str, context: Optional[Dict] = None):
        """
        设置缓存

        Args:
            query: 查询文本
            response: 响应内容
            context: 检索上下文
        """
        key = self._generate_key(query, context)

        # 先设置本地缓存
        if self.local_cache:
            self.local_cache.set(key, response)

        # 再设置分布式缓存
        if self.use_redis and self.distributed_cache:
            self.distributed_cache.set(key, response)

    def delete(self, query: str, context: Optional[Dict] = None):
        """
        删除缓存

        Args:
            query: 查询文本
            context: 检索上下文
        """
        key = self._generate_key(query, context)

        # 删除本地缓存
        if self.local_cache and key in self.local_cache.cache:
            del self.local_cache.cache[key]

        # 删除分布式缓存
        if self.use_redis and self.distributed_cache:
            self.distributed_cache.delete(key)

    def clear(self):
        """清空所有缓存"""
        if self.local_cache:
            self.local_cache.cache.clear()
        if self.use_redis and self.distributed_cache:
            self.distributed_cache.clear()

    def _generate_key(self, query: str, context: Optional[Dict] = None) -> str:
        """生成缓存键"""
        context_str = json.dumps(context, sort_keys=True) if context else ""
        combined = f"{query}|{context_str}"
        return hashlib.sha256(combined.encode()).hexdigest()

    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        stats = {
            "use_redis": self.use_redis,
            "total_hits": self.hits,
            "total_misses": self.misses,
            "hit_rate": 0.0
        }

        if self.local_cache:
            stats["local_cache"] = self.local_cache.get_stats()

        if self.use_redis and self.distributed_cache:
            stats["redis_cache"] = self.distributed_cache.get_stats()

        total = self.hits + self.misses
        if total > 0:
            stats["hit_rate"] = self.hits / total

        return stats

    def reset_stats(self):
        """重置统计信息"""
        self.hits = 0
        self.misses = 0
        if self.local_cache:
            self.local_cache.hits = 0
            self.local_cache.misses = 0


# 全局缓存实例（默认不使用 Redis，如需分布式缓存请配置 Redis）
llm_cache = LLMCache(use_redis=False)
