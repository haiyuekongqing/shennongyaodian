"""
批量导入知识库文件到向量数据库
Usage: python scripts/bulk_import.py [files...]
"""
import sys
import time
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

sys.path.insert(0, '/app')

from src.retrieval.vector_store import VectorStore
from src.agents.tools.vector_tool import VectorTool


def import_file(v: VectorTool, path: str, label: str) -> int:
    logger.info(f"开始导入: {label}")
    t0 = time.time()
    count = v.import_file(path, chunk_size=500, overlap=50)
    elapsed = time.time() - t0
    rate = count / elapsed if elapsed > 0 else 0
    logger.info(f"完成导入: {label} ({count} chunks, {elapsed:.1f}s, {rate:.2f} chunks/s)")
    return count


def main():
    files = sys.argv[1:] if len(sys.argv) > 1 else [
        '/app/data/knowledge_base/ancient_treatises/伤寒论.txt',
        '/app/data/knowledge_base/ancient_treatises/神农本草经.txt',
    ]

    v = VectorTool()

    # 检查已有数据
    stats = v.get_stats()
    existing = stats.get('num_entities', 0)
    logger.info(f"当前向量库已有 {existing} 条数据")

    total = 0
    for f in files:
        label = f.split('/')[-1]
        count = import_file(v, f, label)
        total += count

    stats = v.get_stats()
    logger.info(f"导入完成! 共 {total} chunks, 向量库总计 {stats.get('num_entities', 0)} 条")


if __name__ == '__main__':
    main()
