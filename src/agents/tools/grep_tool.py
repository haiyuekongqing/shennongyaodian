"""
Grep 检索工具
封装 Grep 精确检索功能
"""
import logging
from typing import List, Dict, Any, Optional

from src.retrieval.grep_retriever import GrepRetriever, GrepResult
from src.config.settings import settings

logger = logging.getLogger(__name__)


class GrepTool:
    """Grep 检索工具"""

    def __init__(self, knowledge_base_dir: Optional[str] = None):
        """
        初始化 Grep 检索工具

        Args:
            knowledge_base_dir: 知识库目录
        """
        self.grep_retriever = GrepRetriever(knowledge_base_dir)

        # 创建全文检索数据库
        self.grep_retriever.create_fts_database()

        logger.info("✓ Grep 检索工具初始化完成")

    def search(self, query: str, top_k: int = 20, file_types: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        执行 Grep 搜索

        Args:
            query: 搜索关键词
            top_k: 返回结果数量
            file_types: 限制文件类型 ['pharmacopedia', 'treatise', 'case']

        Returns:
            检索结果列表
        """
        logger.info(f"✓ 开始 Grep 搜索: query='{query[:50]}...', top_k={top_k}")

        results = self.grep_retriever.search(query, top_k, file_types)

        # 转换为字典格式
        formatted_results = []
        for result in results:
            formatted_results.append({
                'file_path': result.file_path,
                'line_number': result.line_number,
                'content': result.line_content,
                'context_before': result.context_before,
                'context_after': result.context_after,
                'score': result.score,
                'matches': result.matches
            })

        # 添加免责声明
        for result in formatted_results:
            result['disclaimer'] = self._get_disclaimer_text()

        logger.info(f"✓ Grep 搜索完成，返回 {len(formatted_results)} 个结果")
        return formatted_results

    def search_ingredient(self, ingredient_name: str) -> List[Dict[str, Any]]:
        """
        精确匹配中草药名称

        Args:
            ingredient_name: 中草药名称

        Returns:
            检索结果列表
        """
        logger.info(f"✓ 精确匹配中草药: {ingredient_name}")

        results = self.grep_retriever.search_ingredient(ingredient_name)

        # 转换格式
        return [
            {
                'file_path': result.file_path,
                'line_number': result.line_number,
                'content': result.line_content,
                'score': result.score,
                'disclaimer': self._get_disclaimer_text()
            }
            for result in results
        ]

    def search_formula(self, formula_name: str) -> List[Dict[str, Any]]:
        """
        搜索方剂名称

        Args:
            formula_name: 方剂名称

        Returns:
            检索结果列表
        """
        logger.info(f"✓ 搜索方剂: {formula_name}")

        results = self.grep_retriever.search_formula(formula_name)

        # 转换格式
        return [
            {
                'file_path': result.file_path,
                'line_number': result.line_number,
                'content': result.line_content,
                'score': result.score,
                'disclaimer': self._get_disclaimer_text()
            }
            for result in results
        ]

    def search_compound(self, compound_name: str) -> List[Dict[str, Any]]:
        """
        精确匹配化学成分

        Args:
            compound_name: 化学成分名称

        Returns:
            检索结果列表
        """
        logger.info(f"✓ 精确匹配化学成分: {compound_name}")

        results = self.grep_retriever.search_compound(compound_name)

        # 转换格式
        return [
            {
                'file_path': result.file_path,
                'line_number': result.line_number,
                'content': result.line_content,
                'score': result.score,
                'disclaimer': self._get_disclaimer_text()
            }
            for result in results
        ]

    def get_file_info(self, file_path: str) -> Dict[str, Any]:
        """
        获取文件信息

        Args:
            file_path: 文件路径

        Returns:
            文件信息字典
        """
        return self.grep_retriever.get_file_info(file_path)

    def get_file_list(self, file_types: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        获取知识库文件列表

        Args:
            file_types: 限制文件类型

        Returns:
            文件列表
        """
        files = self.grep_retriever.get_file_list(file_types)

        return [
            {
                'path': f['path'],
                'name': f['name'],
                'size': f['size'],
                'type': f['type']
            }
            for f in files
        ]

    def search_with_context(self, query: str, context_lines: int = 3, top_k: int = 10) -> List[Dict[str, Any]]:
        """
        搜索并返回上下文

        Args:
            query: 搜索关键词
            context_lines: 上下文行数
            top_k: 返回结果数量

        Returns:
            检索结果列表
        """
        logger.info(f"✓ 搜索并返回上下文: query='{query[:50]}...', context_lines={context_lines}")

        results = self.grep_retriever.search(query, top_k)

        # 转换格式
        formatted_results = []
        for result in results:
            formatted_results.append({
                'file_path': result.file_path,
                'line_number': result.line_number,
                'content': result.line_content,
                'context_before': result.context_before,
                'context_after': result.context_after,
                'score': result.score,
                'disclaimer': self._get_disclaimer_text()
            })

        return formatted_results

    def count_search_results(self, query: str) -> int:
        """
        计算搜索结果数量

        Args:
            query: 搜索关键词

        Returns:
            结果数量
        """
        results = self.search(query, top_k=100)
        return len(results)

    def search_advanced(self, query: str, case_sensitive: bool = False, regex: bool = False) -> List[Dict[str, Any]]:
        """
        高级搜索（支持正则表达式和大小写敏感）

        Args:
            query: 搜索关键词
            case_sensitive: 是否大小写敏感
            regex: 是否使用正则表达式

        Returns:
            检索结果列表
        """
        logger.info(f"✓ 高级搜索: query='{query}', regex={regex}")

        if regex and not case_sensitive:
            query = query.lower()

        results = self.grep_retriever.search(query, top_k=50)

        # 转换格式
        return [
            {
                'file_path': result.file_path,
                'line_number': result.line_number,
                'content': result.line_content,
                'score': result.score,
                'disclaimer': self._get_disclaimer_text()
            }
            for result in results
        ]

    def get_file_statistics(self) -> Dict[str, Any]:
        """
        获取文件统计信息

        Returns:
            统计信息字典
        """
        files = self.get_file_list()

        type_counts = {}
        total_size = 0

        for f in files:
            file_type = f['type']
            type_counts[file_type] = type_counts.get(file_type, 0) + 1
            total_size += f['size']

        return {
            'total_files': len(files),
            'total_size': total_size,
            'by_type': type_counts
        }

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
