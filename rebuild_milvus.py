"""
Rebuild Milvus vector DB (drop + recreate) and re-import all data.
Only touches Milvus, leaves Neo4j untouched.
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.retrieval.vector_store import VectorStore


def rebuild():
    print("=" * 60)
    print("[Rebuild] 重建 Milvus 向量库")
    print("=" * 60)

    # 1. Clear SQLite imported-file tracking
    print("\n[1/4] 清空 SQLite 导入记录...")
    from src.models.base import db_manager
    from sqlalchemy import text
    with db_manager.get_session() as s:
        s.execute(text("DELETE FROM imported_files"))
        s.commit()
    print("  [OK] ImportedFile 表已清空")

    # 2. Drop old Milvus collection
    print("\n[2/4] 删除旧 Milvus 集合...")
    vs = VectorStore()
    vs.milvus_client.delete_collection("tcm_knowledge_base")
    print("  [OK] 旧集合已删除")

    # 3. Create new collection (with content_hash field)
    print("\n[3/4] 创建新集合...")
    vs.initialize()
    print("  [OK] 新集合已创建")

    # 4. Re-import vector-related knowledge files (exclude Neo4j-only data)
    print("\n[4/4] 重新导入知识库文件（排除图谱数据）...")
    knowledge_dir = project_root / "data" / "knowledge_base"
    # 只导入 ancient_treatises 等文本类知识，排除图谱专用目录
    exclude_dirs = {"QASystemOnMedicalKG", "neo4j"}
    files = sorted(knowledge_dir.rglob("*"))
    files = [
        f for f in files
        if f.is_file()
        and f.suffix.lower() in (".txt", ".md")
        and not any(excl in f.parts for excl in exclude_dirs)
    ]

    total_chunks = 0
    for f in files:
        print(f"  导入 {f.relative_to(project_root)}")
        try:
            count = vs.import_file(str(f))
            print(f"    [OK] {count} chunks")
            total_chunks += count
        except Exception as e:
            print(f"    [ERR] {e}")

    # 5. Clean up standalone import record
    import_json = project_root / ".imported_files.json"
    if import_json.exists():
        import_json.unlink()
        print("\n  [OK] 已清除 .imported_files.json")

    # Summary
    print("\n" + "=" * 60)
    stats = vs.get_stats()
    print("[Done] 重建完成!")
    print("  Milvus entity count : {}".format(stats.get("num_entities", 0)))
    print("  本次导入分块       : {}".format(total_chunks))
    print("  content_hash 去重  : enabled (insert-time)")
    print("  content 去重       : enabled (query-time)")
    print("=" * 60)


if __name__ == "__main__":
    rebuild()
