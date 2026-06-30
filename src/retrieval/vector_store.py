"""
向量存储管理器
封装向量数据库的高级操作
"""
import os
import json
import hashlib
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
from sqlalchemy import text

from src.retrieval.milvus_client import MilvusClient
from src.models.base import db_manager
from src.models.medica_data import KnowledgeReference, ImportedFile, KnowledgeBaseConfig

logger = logging.getLogger(__name__)


class VectorStore:
    """向量存储管理器"""

    def __init__(self, collection_name: str = "tcm_knowledge_base"):
        """
        初始化向量存储

        Args:
            collection_name: 集合名称
        """
        self.collection_name = collection_name
        self.milvus_client = MilvusClient()
        self.dimension = 1024  # BGE-M3 向量维度

    def initialize(self):
        """初始化向量存储"""
        try:
            self.milvus_client.create_collection(self.collection_name, self.dimension)
            logger.info(f"✓ 向量存储初始化完成: {self.collection_name}")
        except Exception as e:
            logger.error(f"✗ 向量存储初始化失败: {e}")
            raise

    def import_file(self, file_path: str, chunk_size: int = 500, overlap: int = 50) -> int:
        """
        导入单个文件到向量存储

        Args:
            file_path: 文件路径
            chunk_size: 分块大小（字符数）
            overlap: 分块重叠（字符数）

        Returns:
            导入的向量数量
        """
        # 自动初始化（首次导入时创建集合）
        try:
            self.milvus_client.create_collection(self.collection_name, self.dimension)
        except Exception:
            pass

        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        # 计算文件哈希并检查是否已导入（基于内容去重）
        file_hash = self._compute_file_hash(file_path)
        if self._is_file_imported(file_hash):
            logger.info(f"✓ 文件已导入（哈希匹配），跳过: {file_path.name}")
            return 0

        # 根据文件类型选择不同的导入策略
        if file_path.suffix == '.json':
            count = self._import_json_file(file_path, chunk_size, overlap)
        else:
            count = self._import_text_file(file_path, chunk_size, overlap)

        # 记录已导入的文件哈希
        if count > 0:
            self._record_imported_file(file_hash, file_path, count)

        return count

    def _import_json_file(self, file_path: Path, chunk_size: int = 500, overlap: int = 50) -> int:
        """导入 JSON 文件（支持 JSON 数组和 JSON Lines 两种格式）"""
        try:
            import json

            with open(file_path, 'r', encoding='utf-8') as f:
                first_char = f.read(1)
                f.seek(0)

                if first_char == '[':
                    # 标准 JSON 数组格式
                    data = json.load(f)
                    items = data if isinstance(data, list) else [data]
                else:
                    # JSON Lines 格式：每行一个 JSON 对象
                    items = []
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                items.append(json.loads(line))
                            except json.JSONDecodeError:
                                continue

            chunks = []
            metadata_list = []

            for i, item in enumerate(items):
                item_str = json.dumps(item, ensure_ascii=False, allow_nan=False)
                if len(item_str) > 50000:
                    item_str = item_str[:50000] + "...[内容过长，已截断]"

                chunks.append(item_str)

                metadata_list.append({
                    'source_file': str(file_path.name),
                    'file_type': 'medical_json',
                    'position': {
                        'file': file_path.name,
                        'item_index': i + 1,
                        'total_items': len(items)
                    }
                })

            # 插入向量
            self.milvus_client.insert_embeddings(
                self.collection_name,
                chunks,
                metadata_list
            )

            # 保存到数据库
            self._save_to_database(file_path, chunks, metadata_list)

            logger.info(f"✓ JSON 文件导入完成: {file_path.name} ({len(chunks)} 个分块，共 {len(items)} 个条目)")
            return len(chunks)

        except Exception as e:
            logger.error(f"✗ JSON 导入失败: {file_path} - {e}")
            raise

    def _import_text_file(self, file_path: Path, chunk_size: int = 500, overlap: int = 50) -> int:
        """导入文本文件"""
        # 读取文件内容
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            logger.error(f"✗ 读取文件失败: {file_path} - {e}")
            raise

        # 分块处理
        chunks = self._split_text(content, chunk_size, overlap)

        if not chunks:
            logger.warning(f"文件 {file_path.name} 内容为空或无法分块")
            return 0

        # 准备元数据
        file_type = self._get_file_type(file_path)
        source_file = str(file_path.relative_to(file_path.parent.parent.parent)) if file_path.parent.parent.name == 'knowledge_base' else str(file_path)

        metadata = []
        for i, chunk in enumerate(chunks):
            metadata.append({
                'source_file': source_file,
                'file_type': file_type,
                'position': {
                    'file': file_path.name,
                    'chunk_index': i + 1,
                    'total_chunks': len(chunks)
                }
            })

        # 插入向量
        vector_ids = self.milvus_client.insert_embeddings(
            self.collection_name,
            chunks,
            metadata
        )

        # 保存到数据库
        self._save_to_database(file_path, chunks, metadata)

        logger.info(f"✓ 文件导入完成: {file_path.name} ({len(chunks)} 个分块)")
        return len(chunks)

    def import_directory(self, directory: str, chunk_size: int = 500, overlap: int = 50) -> Dict[str, int]:
        """
        批量导入目录到向量存储

        Args:
            directory: 目录路径
            chunk_size: 分块大小
            overlap: 分块重叠

        Returns:
            {文件路径: 导入数量} 字典
        """
        directory = Path(directory)
        if not directory.exists():
            logger.error(f"目录不存在: {directory}")
            return {}

        results = {}

        # 扫描目录
        for root, dirs, files in os.walk(directory):
            for file in files:
                file_path = Path(root) / file
                if file_path.suffix.lower() in ['.md', '.txt', '.pdf']:
                    try:
                        count = self.import_file(str(file_path), chunk_size, overlap)
                        results[str(file_path.relative_to(directory.parent))] = count
                    except Exception as e:
                        logger.error(f"✗ 导入文件失败 {file_path}: {e}")

        logger.info(f"✓ 目录导入完成: {directory} (共 {len(results)} 个文件)")
        return results

    def search(self, query: str, top_k: int = 5, filter_condition: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        检索向量数据

        Args:
            query: 查询文本
            top_k: 返回 Top-K 个结果
            filter_condition: 过滤条件

        Returns:
            检索结果列表
        """
        try:
            results = self.milvus_client.search(query, self.collection_name, top_k)

            # 添加免责声明
            for result in results:
                result['disclaimer'] = self._get_disclaimer_text()

            return results
        except Exception as e:
            logger.warning(f"⚠ 向量检索失败（使用 fallback）: {e}")
            # 返回空的检索结果
            return [{'disclaimer': self._get_disclaimer_text()}]

    def get_stats(self) -> Dict[str, Any]:
        """
        获取统计信息

        Returns:
            统计信息字典
        """
        from src.config.settings import settings

        stats = self.milvus_client.collection_stats(self.collection_name)

        # 补充前端需要的字段
        stats['total_chunks'] = stats.get('num_entities', 0)
        stats['embedding_model'] = settings.EMBEDDING_MODEL

        # 获取数据库统计
        try:
            with db_manager.get_session() as session:
                stats['database_count'] = stats.get('num_entities', 0)
        except Exception as e:
            logger.warning(f"⚠ 无法获取数据库统计: {e}")
            stats['database_count'] = stats.get('num_entities', 0)

        return stats

    def clear_collection(self):
        """清空集合"""
        logger.warning(f"⚠ 正在清空集合: {self.collection_name}")
        self.milvus_client.delete_collection(self.collection_name)
        self.initialize()
        logger.info(f"✓ 集合已清空并重新初始化: {self.collection_name}")

    def _split_text(self, text: str, chunk_size: int, overlap: int) -> List[str]:
        """
        分块文本

        Args:
            text: 原始文本
            chunk_size: 分块大小
            overlap: 分块重叠

        Returns:
            文本分块列表
        """
        if not text:
            return []

        chunks = []
        start = 0
        text_len = len(text)

        while start < text_len:
            end = start + chunk_size
            chunk = text[start:end]

            # 尝试在换行符处分割
            if end < text_len and chunk[-1] != '\n':
                # 找到最近的换行符
                last_newline = chunk.rfind('\n')
                if last_newline > 0:
                    end = start + last_newline
                    chunk = text[start:end]

            chunks.append(chunk.strip())
            start = end - overlap

            # 防止死循环
            if start <= 0:
                start = end
                if start >= text_len:
                    break

        return chunks

    def _get_file_type(self, file_path: Path) -> str:
        """获取文件类型"""
        if file_path.parent.name == 'chinese_pharmacopedia':
            return 'pharmacopedia'
        elif file_path.parent.name == 'ancient_treatises':
            return 'treatise'
        elif file_path.parent.name == 'medical_cases':
            return 'case'
        else:
            return 'unknown'

    def _save_to_database(self, file_path: Path, chunks: List[str], metadata: List[Dict[str, Any]]):
        """
        保存到数据库（暂时禁用，避免数据库保存错误影响主流程）

        Args:
            file_path: 文件路径
            chunks: 文本分块
            metadata: 元数据
        """
        try:
            with db_manager.get_session() as session:
                # 获取或创建知识库配置
                config = session.query(KnowledgeBaseConfig).filter_by(
                    collection_name=self.collection_name
                ).first()

                if not config:
                    config = KnowledgeBaseConfig(
                        collection_name=self.collection_name,
                        embedding_model=self.milvus_client.embedding_model,
                        description="中草药知识库"
                    )
                    session.add(config)

                # 更新统计信息
                total_chunks = session.query(KnowledgeReference).filter_by(
                    collection_name=self.collection_name
                ).count()

                config.total_chunks = total_chunks + len(chunks)
                config.updated_at = datetime.now()

                # 保存知识库引用
                for i, chunk in enumerate(chunks):
                    ref = KnowledgeReference(
                        ingredient_id="",  # 待后续关联
                        file_path=str(file_path),
                        file_type=metadata[i]['file_type'],
                        file_title=file_path.name,
                        position_in_file=metadata[i]['position'],
                        reference_summary=chunk[:100] + "..." if len(chunk) > 100 else chunk,
                        relevance_score=0
                    )
                    session.add(ref)

                session.commit()
                logger.info(f"✓ 数据库保存成功: {file_path.name}")
        except Exception as e:
            logger.warning(f"⚠ 数据库保存跳过（不影响主流程）: {e} - {type(e).__name__}")
            # 不抛出异常，避免影响主流程

    @staticmethod
    def _compute_file_hash(file_path: Path) -> str:
        """
        计算文件的 SHA-256 哈希值（用于去重判断）

        Args:
            file_path: 文件路径

        Returns:
            文件的 SHA-256 哈希字符串
        """
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            # 只读取前 1MB 进行哈希计算，加快速度
            content = f.read(1024 * 1024)
            sha256_hash.update(content)
        return sha256_hash.hexdigest()

    def _is_file_imported(self, file_hash: str) -> bool:
        """
        检查文件哈希是否已导入过

        Args:
            file_hash: 文件 SHA-256 哈希

        Returns:
            True 表示已导入
        """
        try:
            with db_manager.get_session() as session:
                existing = session.query(ImportedFile).filter_by(file_hash=file_hash).first()
                return existing is not None
        except Exception as e:
            logger.warning(f"⚠ 去重检查失败（将正常导入）: {e}")
            return False

    def _record_imported_file(self, file_hash: str, file_path: Path, chunk_count: int):
        """
        记录已导入的文件哈希

        Args:
            file_hash: 文件 SHA-256 哈希
            file_path: 文件路径
            chunk_count: 导入的分块数
        """
        try:
            with db_manager.get_session() as session:
                record = ImportedFile(
                    file_hash=file_hash,
                    file_path=str(file_path),
                    file_name=file_path.name,
                    chunk_count=chunk_count,
                )
                session.add(record)
                session.commit()
                logger.info(f"✓ 已记录导入哈希: {file_path.name}")
        except Exception as e:
            logger.warning(f"⚠ 记录导入哈希失败（不影响数据）: {e}")

    def _get_disclaimer_text(self) -> str:
        """获取免责声明文本"""
        try:
            with db_manager.get_session() as session:
                result = session.execute(
                    text("SELECT disclaimer_text FROM medical_disclaimers WHERE is_enabled=1 LIMIT 1")
                ).first()
                if result:
                    return result[0]
        except Exception as e:
            logger.error(f"✗ 获取免责声明失败: {e}")

        return "免责声明：本系统提供的信息仅供参考，不构成医疗建议。如遇健康问题，请咨询专业医生或药师。"
