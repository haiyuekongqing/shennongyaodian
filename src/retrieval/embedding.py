"""
Embedding 模型封装
支持 BGE-M3 模型
"""
import os
import logging
from typing import List, Optional
from pathlib import Path

from src.config.settings import settings

logger = logging.getLogger(__name__)


class EmbeddingModel:
    """Embedding 模型封装（懒加载）"""

    _instance = None
    _model = None
    _load_failed = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(EmbeddingModel, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        self.model_name = settings.EMBEDDING_MODEL
        self.device = settings.EMBEDDING_DEVICE
        self.dimension = 1024  # BGE-M3 默认维度

    def _load_model(self):
        """懒加载模型"""
        if self._model is not None:
            return
        if self._load_failed:
            return

        try:
            # 优先使用 FlagEmbedding（官方推荐）
            from FlagEmbedding import BGEM3FlagModel
            self._model = BGEM3FlagModel(
                self.model_name,
                use_fp16=(self.device == 'cuda'),
                devices=self.device
            )
            logger.info(f"✓ Embedding 模型加载完成（FlagEmbedding）: {self.model_name}")
        except Exception as e:
            logger.warning(f"⚠ FlagEmbedding 加载失败 ({e})，尝试 sentence-transformers...")
            try:
                # 降级：使用 sentence-transformers
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(self.model_name, device=self.device)
                logger.info(f"✓ Embedding 模型加载完成（sentence-transformers）: {self.model_name}")
            except Exception as e2:
                logger.error(f"✗ Embedding 模型加载失败（两种方式均失败）: {e2}")
                self._load_failed = True

    def encode_documents(self, texts: List[str], timeout: int = 10) -> List[List[float]]:
        """
        编码文档（用于入库）

        Args:
            texts: 文本列表
            timeout: 超时时间（秒）

        Returns:
            向量列表
        """
        import time
        import requests

        self._load_model()

        # 模型加载失败时返回零向量
        if self._model is None:
            logger.warning("⚠ Embedding 模型不可用，返回零向量")
            return [[0.0] * self.dimension for _ in texts]

        try:
            start_time = time.time()

            # FlagEmbedding BGEM3FlagModel
            from FlagEmbedding import BGEM3FlagModel
            if isinstance(self._model, BGEM3FlagModel):
                embeddings = self._model.encode(
                    texts,
                    batch_size=12,
                    max_length=512,
                    return_dense=True,
                    return_sparse=False,
                    return_colbert_vecs=False,
                )
                # BGEM3FlagModel.encode 返回 dict {'dense_vecs': ...}
                if isinstance(embeddings, dict):
                    return embeddings['dense_vecs'].tolist()
                return embeddings.tolist()
        except ImportError:
            pass
        except requests.exceptions.Timeout:
            logger.warning(f"⚠ Embedding 模型超时（{timeout}s），尝试降级处理")
            # 返回零向量作为 fallback
            return [[0.0] * self.dimension for _ in texts]
        except Exception as e:
            logger.error(f"✗ Embedding 模型生成失败: {e}，返回零向量")
            # 返回零向量作为 fallback
            return [[0.0] * self.dimension for _ in texts]
        finally:
            elapsed = time.time() - start_time
            if elapsed > timeout:
                logger.warning(f"⚠ Embedding 模型执行时间超过超时限制: {elapsed:.2f}s > {timeout}s")

        # sentence-transformers
        try:
            embeddings = self._model.encode(texts, convert_to_numpy=True)
            return embeddings.tolist()
        except requests.exceptions.Timeout:
            logger.warning(f"⚠ sentence-transformers 超时（{timeout}s），尝试降级处理")
            return [[0.0] * self.dimension for _ in texts]
        except Exception as e:
            logger.error(f"✗ sentence-transformers 生成失败: {e}，返回零向量")
            return [[0.0] * self.dimension for _ in texts]

    def encode_queries(self, texts: List[str]) -> List[List[float]]:
        """
        编码查询（用于检索）

        Args:
            texts: 查询文本列表

        Returns:
            向量列表
        """
        return self.encode_documents(texts)

    def encode_single(self, text: str, timeout: int = 10) -> List[float]:
        """
        编码单个文本

        Args:
            text: 输入文本
            timeout: 超时时间（秒）

        Returns:
            向量
        """
        import time
        import requests

        # 添加超时控制
        start_time = time.time()

        try:
            return self.encode_documents([text], timeout=timeout)[0]
        except requests.exceptions.Timeout:
            logger.warning(f"⚠ Embedding 模型超时（{timeout}s），尝试降级处理")
            # 返回零向量作为 fallback
            return [0.0] * self.dimension
        except Exception as e:
            logger.error(f"✗ Embedding 模型生成失败: {e}，返回零向量")
            # 返回零向量作为 fallback
            return [0.0] * self.dimension


# 全局实例
embedding_model = EmbeddingModel()
