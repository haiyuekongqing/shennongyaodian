"""
知识库导入脚本 - 支持增量导入和批量优化
"""
import os
import logging
import json
from pathlib import Path
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_imported_files():
    """加载已导入的文件列表"""
    import_file_list = Path(".imported_files.json")
    if import_file_list.exists():
        with open(import_file_list, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def save_imported_files(imported_files):
    """保存已导入的文件列表"""
    import_file_list = Path(".imported_files.json")
    with open(import_file_list, 'w', encoding='utf-8') as f:
        json.dump(imported_files, f, ensure_ascii=False, indent=2)


def get_file_hash(file_path):
    """获取文件的哈希值（用于增量判断）"""
    import hashlib
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        # 只读取前 1MB 进行哈希计算，加快速度
        content = f.read(1024 * 1024)
        sha256_hash.update(content)
    return sha256_hash.hexdigest()


def main():
    """导入知识库（支持增量导入）"""

    # 初始化数据库
    logger.info("=" * 60)
    logger.info("数据库初始化...")
    logger.info("=" * 60)

    import subprocess
    subprocess.run(["python", "init_db.py"], check=True)

    # 导入到 Milvus
    logger.info("=" * 60)
    logger.info("导入知识库到 Milvus...")
    logger.info("=" * 60)

    from src.retrieval.vector_store import VectorStore
    from src.config.settings import settings

    vector_store = VectorStore()
    vector_store.initialize()

    knowledge_dir = settings.KNOWLEDGE_BASE_DIR
    if not os.path.exists(knowledge_dir):
        logger.warning(f"知识库目录不存在: {knowledge_dir}")
        return

    # 统计文件
    txt_count = 0
    json_count = 0
    md_count = 0

    for root, dirs, files in os.walk(knowledge_dir):
        for file in files:
            if file.endswith(('.txt', '.json', '.md')):
                file_path = Path(root) / file
                if file_path.suffix == '.txt':
                    txt_count += 1
                elif file_path.suffix == '.json':
                    json_count += 1
                else:
                    md_count += 1

    total = txt_count + json_count + md_count

    if total == 0:
        logger.warning("未找到知识库文件")
        return

    logger.info(f"找到 {total} 个文件（TXT: {txt_count}, JSON: {json_count}, MD: {md_count}）")

    # 加载已导入的文件
    imported_files = load_imported_files()
    logger.info(f"已导入文件数: {len(imported_files)}")

    # 扫描并导入文件
    success_count = 0
    fail_count = 0
    skip_count = 0
    updated_count = 0

    for root, dirs, files in os.walk(knowledge_dir):
        for file in files:
            if file.endswith(('.txt', '.json', '.md')):
                file_path = Path(root) / file
                rel_path = str(file_path.relative_to(knowledge_dir))

                file_hash = get_file_hash(file_path)
                file_key = str(file_path)

                # 检查是否需要重新导入
                if file_key in imported_files and imported_files[file_key] == file_hash:
                    skip_count += 1
                    continue

                try:
                    logger.info(f"导入: {rel_path}")

                    chunks = vector_store.import_file(str(file_path))

                    # 更新导入记录
                    imported_files[file_key] = file_hash
                    updated_count += 1

                    logger.info(f"  ✓ 成功（{chunks} 个分块）")

                except Exception as e:
                    logger.error(f"  ✗ 失败: {e}")
                    fail_count += 1
                    # 失败的文件也要记录，避免每次都重试
                    imported_files[file_key] = file_hash

    # 保存导入记录
    save_imported_files(imported_files)

    # 打印统计
    logger.info("=" * 60)
    logger.info(f"导入完成")
    logger.info(f"  总文件数: {total}")
    logger.info(f"  已导入: {len(imported_files)}")
    logger.info(f"  跳过（未变化）: {skip_count}")
    logger.info(f"  更新: {updated_count}")
    logger.info(f"  成功: {success_count + skip_count}")
    logger.info(f"  失败: {fail_count}")
    logger.info("=" * 60)

    # 获取 Milvus 统计
    try:
        stats = vector_store.get_stats()
        logger.info(f"\nMilvus 统计信息:")
        logger.info(f"  向量数量: {stats.get('num_entities', 0)}")
        logger.info(f"  总分块数: {stats.get('total_chunks', 0)}")
    except Exception as e:
        logger.warning(f"⚠ 无法获取统计信息: {e}")


if __name__ == "__main__":
    main()
