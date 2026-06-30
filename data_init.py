"""
知识库数据初始化脚本
手动执行知识库导入
"""
import os
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.retrieval.vector_store import VectorStore
from src.models.medica_data import TCMIngredient

def init_knowledge_base():
    """初始化知识库"""
    print("=" * 60)
    print("中草药知识库初始化")
    print("=" * 60)

    # 获取知识库目录
    knowledge_dir = os.getenv('KNOWLEDGE_BASE_DIR', project_root / 'data' / 'knowledge_base')
    knowledge_dir = Path(knowledge_dir)

    if not knowledge_dir.exists():
        print(f"⚠ 知识库目录不存在: {knowledge_dir}")
        print(f"✓ 正在创建目录...")
        knowledge_dir.mkdir(parents=True, exist_ok=True)
        print(f"✓ 请将知识库文件放入: {knowledge_dir}")
        return

    print(f"✓ 知识库目录: {knowledge_dir}")
    print(f"✓ 开始扫描文件...")

    # 统计信息
    total_files = 0
    total_lines = 0
    total_chars = 0

    # 扫描文件
    for root, dirs, files in os.walk(knowledge_dir):
        for file in files:
            if file.endswith(('.md', '.txt', '.pdf')):
                file_path = Path(root) / file
                total_files += 1

                # 读取文件
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        total_lines += len(content.split('\n'))
                        total_chars += len(content)

                    print(f"  - {file_path.relative_to(knowledge_dir)}: "
                          f"{len(content)} 字符, {len(content.split(chr(10)))} 行")

                except Exception as e:
                    print(f"  ✗ {file_path.name}: 读取失败 - {e}")

    print(f"\n统计信息:")
    print(f"  - 文件数量: {total_files}")
    print(f"  - 总行数: {total_lines}")
    print(f"  - 总字符数: {total_chars}")

    if total_files == 0:
        print("\n⚠ 没有找到知识库文件！")
        print("✓ 请将知识库文件放入: " + str(knowledge_dir))
        print("✓ 支持的格式: .md, .txt, .pdf")
        return

    print(f"\n开始导入知识库到 Milvus...")

    try:
        # 初始化向量库
        vector_store = VectorStore(
            collection_name="tcm_knowledge_base",
            embedding_model="BAAI/bge-m3"
        )

        # 导入文件
        imported = 0
        for root, dirs, files in os.walk(knowledge_dir):
            for file in files:
                if file.endswith(('.md', '.txt', '.pdf')):
                    file_path = Path(root) / file

                    try:
                        vector_store.import_file(str(file_path))
                        imported += 1
                        print(f"  ✓ 导入: {file_path.relative_to(knowledge_dir)}")

                    except Exception as e:
                        print(f"  ✗ 导入失败: {file_path.name} - {e}")

        print(f"\n{'=' * 60}")
        print(f"✓ 知识库初始化完成！")
        print(f"  - 成功导入: {imported}/{total_files} 个文件")
        print(f"{'=' * 60}")

    except Exception as e:
        print(f"\n✗ 知识库初始化失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    init_knowledge_base()
