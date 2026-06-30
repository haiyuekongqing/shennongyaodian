"""
数据库初始化脚本
在应用启动时自动执行
"""
import os
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from src.config.settings import settings
from src.models.base import db_manager


def init_database():
    """初始化数据库"""
    print("=" * 60)
    print("数据库初始化")
    print("=" * 60)

    # 初始化数据库管理器
    db_manager.initialize()

    engine = db_manager.get_engine()
    Session = sessionmaker(bind=engine)

    with Session() as session:
        # 创建表（如果不存在）
        from src.models.base import Base
        Base.metadata.create_all(bind=engine)
        print("[OK] Database tables created successfully")

        # 检查是否已初始化
        result = session.execute(text("SELECT COUNT(*) FROM knowledge_base_config"))
        count = result.scalar()

        if count == 0:
            # 通过 ORM 插入（自动生成 UUID 主键）
            from src.models.medica_data import KnowledgeBaseConfig
            config = KnowledgeBaseConfig(
                collection_name='tcm_knowledge_base',
                embedding_model='BAAI/bge-m3',
                description='中草药知识库'
            )
            session.add(config)
            session.commit()
            print("[OK] Default knowledge base config inserted successfully")

        # 检查免责声明
        result = session.execute(text("SELECT COUNT(*) FROM medical_disclaimers"))
        disclaimer_count = result.scalar()
        if disclaimer_count == 0:
            # 直接通过 ORM 插入（避免 SQL 方言差异）
            from src.models.medica_data import MedicalDisclaimer
            disclaimer = MedicalDisclaimer(
                disclaimer_text='免责声明：本系统提供的信息仅供参考，不构成医疗建议。如遇健康问题，请咨询专业医生或药师。',
                applicable_scenarios=['medical_advice', 'medicine_recommendation'],
                language='zh',
                version='1.0',
                is_enabled=True
            )
            session.add(disclaimer)
            session.commit()
            print("[OK] Default disclaimer inserted successfully")
        else:
            print("[OK] Disclaimer already exists")

    print("=" * 60)
    print("数据库初始化完成！")
    print("=" * 60)

if __name__ == "__main__":
    init_database()
