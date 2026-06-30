"""
Milvus 向量数据库客户端
"""
import hashlib
from pymilvus import (
    connections,
    Collection,
    CollectionSchema,
    FieldSchema,
    DataType,
    utility,
)
from typing import List, Dict, Any, Optional
import logging

from src.config.settings import settings
from src.retrieval.embedding import embedding_model

logger = logging.getLogger(__name__)


class MilvusClient:
    """Milvus 客户端封装"""

    def __init__(self, host: Optional[str] = None, port: Optional[int] = None):
        """
        初始化 Milvus 客户端

        Args:
            host: Milvus 主机地址，默认从配置读取
            port: Milvus 端口，默认从配置读取
        """
        self.host = host or settings.MILVUS_HOST
        self.port = port or settings.MILVUS_PORT
        self.collection_name = "tcm_knowledge_base"
        self.embedding_model_name = settings.EMBEDDING_MODEL

        # 建立连接
        self._connect()

    def _connect(self):
        """建立 Milvus 连接"""
        try:
            connections.connect(
                alias="default",
                host=self.host,
                port=self.port
            )
            logger.info(f"✓ 已连接到 Milvus: {self.host}:{self.port}")
        except Exception as e:
            logger.error(f"✗ 连接 Milvus 失败: {e}")
            raise

    def create_collection(self, collection_name: str, dimension: int = 1024):
        """
        创建向量集合

        Args:
            collection_name: 集合名称
            dimension: 向量维度，默认 1024（BGE-M3）
        """
        if utility.has_collection(collection_name):
            logger.warning(f"集合 {collection_name} 已存在")
            return self.get_collection(collection_name)

        # 定义字段
        fields = [
            FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
            FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=dimension),
            FieldSchema(name="chunk_id", dtype=DataType.INT64),
            FieldSchema(name="source_file", dtype=DataType.VARCHAR, max_length=500),
            FieldSchema(name="file_type", dtype=DataType.VARCHAR, max_length=50),
            FieldSchema(name="position", dtype=DataType.JSON),
            FieldSchema(name="content", dtype=DataType.VARCHAR, max_length=65535),
            FieldSchema(name="content_hash", dtype=DataType.VARCHAR, max_length=64),
        ]

        schema = CollectionSchema(fields, description="中草药知识库")

        # 创建集合
        collection = Collection(name=collection_name, schema=schema)
        logger.info(f"✓ 已创建集合: {collection_name}")

        # 创建索引
        index_params = {
            "metric_type": "IP",
            "index_type": "IVF_FLAT",
            "params": {"nlist": 128}
        }
        collection.create_index(field_name="embedding", index_params=index_params)
        collection.create_index(field_name="content_hash", index_name="idx_content_hash")
        logger.info(f"✓ 已创建索引: IVF_FLAT (nlist=128) + content_hash 标量索引")

        return collection

    def get_collection(self, collection_name: str = None):
        """
        获取集合

        Args:
            collection_name: 集合名称

        Returns:
            Collection 对象
        """
        if collection_name is None:
            collection_name = self.collection_name

        if not utility.has_collection(collection_name):
            raise ValueError(f"集合 {collection_name} 不存在")

        collection = Collection(name=collection_name)
        collection.load()
        return collection

    def insert_embeddings(self, collection_name: str, texts: List[str],
                          metadata: Optional[List[Dict[str, Any]]] = None) -> int:
        """
        插入向量数据（自动计算 content_hash 并去重）

        Args:
            collection_name: 集合名称
            texts: 文本列表
            metadata: 元数据列表

        Returns:
            插入的向量数量
        """
        if not texts:
            return 0

        # 1. 计算每个文本的 content_hash
        content_hashes = [hashlib.sha256(t.encode('utf-8')).hexdigest() for t in texts]

        # 2. 同批次内去重（避免同一个 batch 内出现重复内容）
        seen_local = set()
        local_dedup_indices = []
        for i, h in enumerate(content_hashes):
            if h not in seen_local:
                seen_local.add(h)
                local_dedup_indices.append(i)

        if len(local_dedup_indices) < len(texts):
            logger.debug(f"同批次内去重: {len(texts)} -> {len(local_dedup_indices)}")

        # 3. 获取集合
        collection = self.get_collection(collection_name)

        # 4. 检查集合是否有 content_hash 字段（新集合有，旧集合可能没有）
        has_content_hash_field = any(f.name == 'content_hash' for f in collection.schema.fields)

        # 5. 如果字段存在，查询已存在的 content_hash 做去重
        if has_content_hash_field:
            deduped_hashes = [content_hashes[i] for i in local_dedup_indices]
            indices = self._filter_existing_hashes(collection, deduped_hashes)
            if not indices:
                logger.info(f"所有 {len(texts)} 条数据均与 Milvus 中现有记录重复，跳过导入")
                return 0
            # 将 local_dedup_indices 中的实际索引映射回去
            indices = [local_dedup_indices[i] for i in indices]
        else:
            indices = local_dedup_indices

        # 5. 只处理新数据
        filtered_texts = [texts[i] for i in indices]
        filtered_hashes = [content_hashes[i] for i in indices]
        filtered_metadata = [metadata[i] for i in indices] if metadata else None

        # 6. 生成 Embeddings（只对新数据）
        embeddings = embedding_model.encode_documents(filtered_texts)

        # 7. 准备插入数据
        sources = [m.get('source_file', '') for m in filtered_metadata] if filtered_metadata else [''] * len(filtered_texts)
        file_types = [m.get('file_type', '') for m in filtered_metadata] if filtered_metadata else [''] * len(filtered_texts)
        positions = [m.get('position', {}) for m in filtered_metadata] if filtered_metadata else [{}] * len(filtered_texts)
        chunk_ids = list(range(len(filtered_texts)))

        if has_content_hash_field:
            data = [
                embeddings,           # embedding
                chunk_ids,            # chunk_id
                sources,              # source_file
                file_types,           # file_type
                positions,            # position
                filtered_texts,       # content
                filtered_hashes,      # content_hash
            ]
        else:
            # 旧集合没有 content_hash 字段，保持原有数据结构
            data = [
                embeddings,
                chunk_ids,
                sources,
                file_types,
                positions,
                filtered_texts,
            ]

        # 8. 插入数据
        collection.insert(data)
        collection.flush()

        dup_count = len(texts) - len(filtered_texts)
        if dup_count > 0:
            logger.info(f"✓ 已插入 {len(filtered_texts)} 条向量数据（去重跳过 {dup_count} 条重复）")
        else:
            logger.info(f"✓ 已插入 {len(filtered_texts)} 条向量数据到集合 {collection_name}")
        return len(filtered_texts)

    def _filter_existing_hashes(self, collection: Collection,
                                 content_hashes: List[str]) -> List[int]:
        """
        批量查询哪些 content_hash 已存在于 Milvus 中，返回需要插入的索引

        Args:
            collection: Milvus Collection 对象
            content_hashes: 所有待插入文本的 content_hash 列表

        Returns:
            需要插入的文本在原始列表中的索引
        """
        try:
            existing_hashes = set()
            # 分批查询，避免 IN 子句过长
            batch_size = 999
            for i in range(0, len(content_hashes), batch_size):
                batch = content_hashes[i:i + batch_size]
                if not batch:
                    continue
                res = collection.query(
                    expr=f'content_hash in {batch}',
                    output_fields=['content_hash']
                )
                existing_hashes.update(r['content_hash'] for r in res)

            return [i for i, h in enumerate(content_hashes) if h not in existing_hashes]

        except Exception as e:
            logger.warning(f"内容哈希去重查询失败，将全部插入（避免阻塞导入流程）: {e}")
            return list(range(len(content_hashes)))

    def search(self, query_text: str, collection_name: str = None,
               top_k: int = 5) -> List[Dict[str, Any]]:
        """
        向量检索

        Args:
            query_text: 查询文本
            collection_name: 集合名称
            top_k: 返回 Top-K 个结果

        Returns:
            检索结果列表
        """
        # 获取集合
        collection = self.get_collection(collection_name)

        # 生成查询向量
        query_embedding = embedding_model.encode_queries([query_text])[0]

        # 执行搜索
        search_params = {
            "metric_type": "IP",
            "params": {"nprobe": 16}
        }

        results = collection.search(
            data=[query_embedding],
            anns_field="embedding",
            param=search_params,
            limit=top_k,
            output_fields=["content", "source_file", "file_type", "position"]
        )

        # 格式化结果（按 content 去重）
        formatted_results = []
        seen_content = set()
        for hits in results:
            for hit in hits:
                entity = hit.entity
                content = entity.get("content") if entity else None
                # 跳过重复内容
                if content is not None:
                    if content in seen_content:
                        continue
                    seen_content.add(content)
                formatted_results.append({
                    "id": hit.id,
                    "score": hit.score,
                    "content": content,
                    "source_file": entity.get("source_file") if entity else None,
                    "file_type": entity.get("file_type") if entity else None,
                    "position": entity.get("position") if entity else None,
                })

        logger.info(f"✓ 向量检索完成，返回 {len(formatted_results)} 条唯一结果")
        return formatted_results

    def delete_collection(self, collection_name: str):
        """删除集合"""
        if utility.has_collection(collection_name):
            utility.drop_collection(collection_name)
            logger.info(f"✓ 已删除集合: {collection_name}")
        else:
            logger.warning(f"集合 {collection_name} 不存在")

    def collection_stats(self, collection_name: str = None) -> Dict[str, Any]:
        """
        获取集合统计信息

        Args:
            collection_name: 集合名称

        Returns:
            统计信息字典
        """
        try:
            collection = self.get_collection(collection_name)
            num_entities = collection.num_entities
            return {
                "collection_name": collection_name,
                "num_entities": num_entities,
            }
        except Exception as e:
            logger.error(f"✗ 获取集合统计失败: {e}")
            return {
                "collection_name": collection_name,
                "num_entities": 0,
                "error": str(e)
            }

    def close(self):
        """关闭连接"""
        try:
            connections.disconnect("default")
            logger.info("✓ 已关闭 Milvus 连接")
        except Exception:
            pass
