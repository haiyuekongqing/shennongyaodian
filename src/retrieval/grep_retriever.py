"""
Grep 精确检索器
基于文件系统和关键词匹配的精确检索
"""
import os
import re
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
import sqlite3

from src.config.settings import settings

logger = logging.getLogger(__name__)


@dataclass
class GrepResult:
    """Grep 检索结果"""
    file_path: str
    line_number: int
    line_content: str
    score: float
    context_before: str = ""
    context_after: str = ""
    matches: List[str] = None

    def __post_init__(self):
        if self.matches is None:
            self.matches = []


class GrepRetriever:
    """Grep 精确检索器"""

    def __init__(self, knowledge_base_dir: Optional[str] = None):
        """
        初始化 Grep 检索器

        Args:
            knowledge_base_dir: 知识库目录
        """
        self.knowledge_base_dir = knowledge_base_dir or settings.KNOWLEDGE_BASE_DIR
        # FTS5 数据库放在 data 目录（可写），而非只读的 knowledge_base 目录
        self.full_text_search_db = Path("/app/data") / "fts5.db"

    def search(self, query: str, top_k: int = 20, file_types: Optional[List[str]] = None) -> List[GrepResult]:
        """
        执行 Grep 搜索

        Args:
            query: 搜索关键词
            top_k: 返回 Top-K 个结果
            file_types: 限制文件类型 ['pharmacopedia', 'treatise', 'case']

        Returns:
            检索结果列表
        """
        results = []

        # 1. 使用 Grep 在文件系统中搜索
        grep_results = self._grep_search(query, file_types)
        results.extend(grep_results)

        # 2. 如果有全文检索数据库，也搜索
        if self.full_text_search_db.exists():
            fts_results = self._fts_search(query, file_types)
            results.extend(fts_results)

        # 3. 去重并排序
        results = self._deduplicate_and_sort(results, query, top_k)

        logger.info(f"✓ Grep 检索完成，返回 {len(results)} 个结果")
        return results[:top_k]

    def search_ingredient(self, ingredient_name: str) -> List[GrepResult]:
        """
        精确匹配中草药名称

        Args:
            ingredient_name: 中草药名称

        Returns:
            检索结果列表
        """
        # FTS5 不支持正则表达式语法 \b，使用普通搜索并让 FTS5 匹配
        # 移除 \b，使用 "  " 包裹确保单词边界匹配
        query = f" {ingredient_name} "
        return self.search(query, top_k=10)

    def search_formula(self, formula_name: str) -> List[GrepResult]:
        """
        搜索方剂名称

        Args:
            formula_name: 方剂名称

        Returns:
            检索结果列表
        """
        query = f" {formula_name} "
        return self.search(query, top_k=10)

    def search_compound(self, compound_name: str) -> List[GrepResult]:
        """
        精确匹配化学成分

        Args:
            compound_name: 化学成分名称

        Returns:
            检索结果列表
        """
        query = f" {compound_name} "
        return self.search(query, top_k=10)

    def get_file_info(self, file_path: str) -> Dict[str, Any]:
        """
        获取文件信息

        Args:
            file_path: 文件路径

        Returns:
            文件信息字典
        """
        file_path = Path(file_path)

        if not file_path.exists():
            return {
                'exists': False,
                'path': str(file_path)
            }

        stat = file_path.stat()
        return {
            'exists': True,
            'path': str(file_path),
            'name': file_path.name,
            'size': stat.st_size,
            'modified': stat.st_mtime,
            'extension': file_path.suffix,
        }

    def get_file_list(self, file_types: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        获取知识库文件列表

        Args:
            file_types: 限制文件类型

        Returns:
            文件列表
        """
        files = []

        knowledge_dir = Path(self.knowledge_base_dir)
        if not knowledge_dir.exists():
            return files

        for root, dirs, filenames in os.walk(knowledge_dir):
            for filename in filenames:
                if filename.endswith(('.md', '.txt', '.pdf')):
                    file_path = Path(root) / filename

                    # 过滤文件类型
                    if file_types:
                        parent_name = file_path.parent.name
                        if parent_name not in file_types:
                            continue

                    files.append({
                        'path': str(file_path),
                        'name': filename,
                        'size': file_path.stat().st_size,
                        'type': self._get_file_type(file_path)
                    })

        return files

    def create_fts_database(self):
        """创建全文检索数据库"""
        db_path = self.full_text_search_db

        if db_path.exists():
            logger.warning(f"全文检索数据库已存在: {db_path}")
            return

        # 创建 SQLite 数据库
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # 创建 FTS5 虚拟表
        cursor.execute("""
            CREATE VIRTUAL TABLE knowledge_fts USING fts5(
                path, line_number, line_content, file_type,
                content='knowledge',
                content_rowid='rowid'
            );
        """)

        # 创建触发器来同步数据
        # 注意：这是一个简化实现，实际应用中需要更复杂的同步机制
        conn.commit()
        conn.close()

        logger.info(f"✓ 全文检索数据库已创建: {db_path}")

    def _grep_search(self, query: str, file_types: Optional[List[str]]) -> List[GrepResult]:
        """
        Grep 搜索实现

        Args:
            query: 搜索关键词
            file_types: 限制文件类型

        Returns:
            检索结果列表
        """
        results = []

        knowledge_dir = Path(self.knowledge_base_dir)
        if not knowledge_dir.exists():
            return results

        # 转义特殊字符
        escaped_query = re.escape(query)
        pattern = re.compile(escaped_query)

        # 遍历文件
        for root, dirs, filenames in os.walk(knowledge_dir):
            for filename in filenames:
                if filename.endswith(('.md', '.txt', '.pdf')):
                    file_path = Path(root) / filename

                    # 过滤文件类型
                    if file_types:
                        parent_name = file_path.parent.name
                        if parent_name not in file_types:
                            continue

                    # 搜索文件
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            for line_number, line in enumerate(f, 1):
                                if pattern.search(line):
                                    # 提取上下文
                                    context_before, context_after = self._extract_context(
                                        file_path, line_number - 1, query
                                    )

                                    results.append(GrepResult(
                                        file_path=str(file_path),
                                        line_number=line_number,
                                        line_content=line.strip(),
                                        score=1.0,  # 精确匹配，分数为 1
                                        context_before=context_before,
                                        context_after=context_after,
                                        matches=[m.group() for m in pattern.finditer(line)]
                                    ))
                    except Exception as e:
                        logger.error(f"✗ 读取文件失败: {file_path} - {e}")

        return results

    def _fts_search(self, query: str, file_types: Optional[List[str]]) -> List[GrepResult]:
        """
        全文检索搜索实现

        Args:
            query: 搜索关键词
            file_types: 限制文件类型

        Returns:
            检索结果列表
        """
        results = []

        conn = sqlite3.connect(self.full_text_search_db)
        cursor = conn.cursor()

        # 执行全文检索
        try:
            cursor.execute("""
                SELECT rowid, path, line_number, line_content, file_type
                FROM knowledge_fts
                WHERE line_content MATCH ?
                ORDER BY rank
                LIMIT 100
            """, (query,))

            for row in cursor.fetchall():
                rowid, path, line_number, line_content, file_type = row

                results.append(GrepResult(
                    file_path=path,
                    line_number=line_number,
                    line_content=line_content.strip(),
                    score=1.0,  # FTS5 内置排序，这里简化处理
                ))
        except Exception as e:
            logger.error(f"✗ FTS 搜索失败: {e}")

        conn.close()
        return results

    def _deduplicate_and_sort(self, results: List[GrepResult], query: str, top_k: int) -> List[GrepResult]:
        """
        去重并排序结果

        Args:
            results: 原始结果
            query: 查询文本
            top_k: Top-K 数量

        Returns:
            排序后的结果
        """
        # 去重：按文件和行号去重
        seen = set()
        unique_results = []

        for result in results:
            key = (result.file_path, result.line_number)
            if key not in seen:
                seen.add(key)
                unique_results.append(result)

        # 简单的排序：查询词出现的次数越多，分数越高
        for result in unique_results:
            result.score = len([m for m in result.matches if query.lower() in m.lower()])

        # 按分数排序
        unique_results.sort(key=lambda x: x.score, reverse=True)

        return unique_results

    def _extract_context(self, file_path: Path, line_number: int, query: str) -> Tuple[str, str]:
        """
        提取上下文

        Args:
            file_path: 文件路径
            line_number: 行号
            query: 查询关键词

        Returns:
            (上下文前, 上下文后)
        """
        context_before = ""
        context_after = ""

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            # 前后各提取 3 行
            start = max(0, line_number - 3)
            end = min(len(lines), line_number + 4)

            for i in range(start, end):
                if i == line_number:
                    continue
                context_before += lines[i] if i < line_number else lines[i]
        except Exception as e:
            logger.error(f"✗ 提取上下文失败: {e}")

        return context_before, context_after

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
